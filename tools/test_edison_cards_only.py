"""Run through the shared Android/web transport and audit opening booster availability."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'android')]
import campaign as game
import campaign_acts as acts
import content
import mobile_backend
import storage


def dispatch(action, value=None):
    return json.loads(mobile_backend.dispatch(json.dumps(dict(action=action, value=value))))


def rejected(action, value, message):
    try:
        dispatch(action, value)
    except ValueError as error:
        assert message in str(error), error
    else:
        raise AssertionError(f'{action} should have failed')


def verify_stock(run, count):
    from random_cards import RANDOM_PACK
    packs = [item['id'] for item in run['shop'] if item['kind'] == 'pack']
    assert len(packs) == len(set(packs)) == count, packs
    assert acts.personal_pack(run) in packs
    assert all(pid == RANDOM_PACK or acts.shop_pack_available(run, pid) for pid in packs)
    if run.get('cards_only'):
        assert not run['artifacts'] and not run.get('cursed_offer')
        assert all(item['kind'] in ('single', 'pack') for item in run['shop'])
        assert RANDOM_PACK not in packs
    assert all(acts.allows(run, cid) for item in run['shop'] if item['kind'] == 'single'
               for cid in item.get('bundle', [item['id']]))
    return packs


def verify_distribution():
    samples = 128
    for character in (0, 1, 98):
        for cards_only, choice_count, stock_count in ((False, 5, 3), (True, 7, 5)):
            support_hits, first_shop_hits, lineups = Counter(), Counter(), set()
            for seed in range(samples):
                rng = random.Random(seed)
                run = game.new_run(character, rng, act_campaign=True, cards_only=cards_only)
                offers = run['starter_offer']
                assert len(offers) == choice_count and not set(offers).intersection(run['pack_ids'])
                assert all(acts.allows(run, cid) for cards in offers.values() for cid in cards)
                lineups.add(tuple(sorted(offers)))
                support_hits.update(offers.keys())
                assert sum(pid == content.CHARACTERS[character]['pack'] for pid in run['pack_ids']) >= 2
                # Take one of the real opening choices, then generate the first shop as a
                # first-round victory would. Use a fixed route policy and no booster pin.
                acts.choose_starter(run, next(iter(offers)))
                run.update(stage='shop', round=1, shop_reward=run['route_rewards'][str(run['opponent'])])
                game.restock(run, rng)
                first_shop_hits.update(verify_stock(run, stock_count))
            assert len(lineups) > samples // 2
            targets = ('EN-TLM', 'EN-IOC')
            assert all(0 < support_hits[pid] < samples for pid in targets)
            assert all(0 < first_shop_hits[pid] < samples for pid in targets)
            assert first_shop_hits[content.CHARACTERS[character]['pack']] == samples
            mode = 'Singles & packs' if cards_only else 'Standard'
            print(f'{content.CHARACTERS[character]["name"]}, {mode}: {len(lineups)}/{samples} distinct starter menus; '
                  + ', '.join(f'{pid} in starter {support_hits[pid]}/{samples}; first shop {first_shop_hits[pid]}/{samples}'
                              for pid in targets))


def win(run):
    dispatch('auto')
    dispatch('choose', run['routes'][0])
    dispatch('begin')
    assert not run['artifacts']
    assert all(acts.allows(run, cid) for cid in run['duel']['enemy_deck'])
    dispatch('finish', {'winner': 0, 'lp': 4000, 'events': []})
    assert run['last_reward_cards'] and not run['artifacts'] and not run.get('cursed_offer')
    dispatch('reward-accept')


def verify_run():
    new = dispatch('new', dict(character=98, slot=1, cards_only=True, level=6))
    start = new['run']
    assert start['stage'] == 'starter' and start['starting_relic'] == 'none'
    assert start['cards_only'] is new['slots'][0]['run']['cards_only'] is True
    with patch.object(acts, 'draft_rotations', side_effect=AssertionError('rerolled on load')):
        loaded = dispatch('select-slot', 1)['run']
    assert start['starter_offer_order'] == list(start['starter_offer'])
    for field in ('cards_only', 'starter_offer', 'starter_offer_order', 'pack_seed', 'pack_rotations', 'pack_ids', 'pool'):
        assert loaded[field] == start[field]
    key = next(iter(start['starter_offer']))
    before = deepcopy(mobile_backend.run)
    preview = dispatch('pack-inspect', {'id': key, 'campaign': True})['result']
    pulls = {game.card_identity(cid) for cid in start['starter_offer'][key]}
    assert pulls <= {game.card_identity(entry['id']) for entry in preview if not entry.get('locked')}
    assert mobile_backend.run == before
    rejected('act-starter', 'EN-CRV', 'starting offer')
    result = dispatch('act-starter', key)['run']
    assert result['stage'] == 'draft' and result['pool'] == start['pool'] + start['starter_offer'][key]
    assert 'starter_offer_order' not in result
    rejected('act-starter', key, 'starting offer')
    restarted = dispatch('restart-run')['run']
    assert restarted['cards_only'] and restarted['challenge_level'] == 6 and restarted['pack_seed'] != start['pack_seed']
    dispatch('act-starter', next(iter(restarted['starter_offer'])))
    run = mobile_backend.run
    win(run)
    verify_stock(run, 5)
    stock = deepcopy(run['shop'])
    assert dispatch('select-slot', 1)['run']['shop'] == stock
    run = mobile_backend.run
    run['gold'] = 700
    i = next(i for i, item in enumerate(run['shop']) if item['kind'] == 'single')
    for kind in ('artifact', 'deck'):
        run['shop'].append(dict(kind=kind, id='ankh', price=1, sold=False))
        before = deepcopy(run)
        rejected('buy-many', [i, len(run['shop']) - 1], 'Only singles and boosters')
        rejected('buy', len(run['shop']) - 1, 'Only singles and boosters')
        assert run == before
        run['shop'].pop()
    rejected('cheat', 'relic:ankh', 'Relics are disabled')
    rejected('relic-pick', 'ankh', 'Relics are disabled')
    p = next(j for j, item in enumerate(run['shop']) if item['kind'] == 'pack')
    bought = dispatch('buy-many', [i, p])['result']
    assert [item['kind'] for item in bought] == ['single', 'pack'] and len(bought[1]['cards']) == 9
    dispatch('shop-reroll')
    verify_stock(run, 5)
    for act in (1, 2, 3):
        assert run['act'] == act and run['cards_only']
        for _ in range(run['round'], acts.ACTS[act - 1]['duels']):
            win(run)
            if run['stage'] == 'shop':
                verify_stock(run, 5)
        if act < 3:
            offer = run['act_transition']
            assert len(set(offer['choices'])) == 8
            dispatch('act-transition', {'packs': [offer['choices'][0]] * offer['picks'], 'carry': []})
            assert len(run['free_packs']) == offer['picks']
            verify_stock(run, 5)
    assert run['stage'] == 'complete' and len(run['timeline']) == 27
    assert any(entry['curses'] for entry in run['timeline'])
    dispatch('champion')
    win(run)
    dispatch('next-loop')
    assert run['cards_only'] and run['loop'] == 1
    verify_stock(run, 5)
    for special in (37, 38):
        for variant in (0, 1):
            rejected('new', dict(character=special, slot=1, replace=True, cards_only=True, variant=variant),
                     'builds their deck')
    assert mobile_backend.run is run

    standard = dispatch('new', dict(character=0, slot=2))['run']
    assert not standard.get('cards_only') and standard['artifacts']
    # Existing saved starter choices can include a core pack and can lack any seed metadata.
    old_offer = deepcopy(standard['starter_offer'])
    old_offer['EN-MFC'] = game.open_pack('EN-MFC', random.Random(5), {'act': 1})
    mobile_backend.run['starter_offer'] = old_offer
    mobile_backend.run.pop('pack_seed')
    mobile_backend.run.pop('starter_offer_order')
    game.save(mobile_backend.run)
    saved = dispatch('select-slot', 2)['run']
    assert saved['starter_offer'] == old_offer and saved['artifacts'] == standard['artifacts']
    assert 'cards_only' not in saved and 'pack_seed' not in saved
    dispatch('act-starter', next(iter(old_offer)))
    standard = mobile_backend.run
    standard.update(stage='shop', round=1, gold=900)
    game.restock(standard, random.Random(11))
    verify_stock(standard, 3)
    i = next(i for i, item in enumerate(standard['shop']) if item['kind'] == 'artifact')
    relic = standard['shop'][i]['id']
    dispatch('buy', i)
    assert relic in standard['artifacts'] or standard.get('fusion_events') or standard.get('relic_picks')
    assert dispatch('select-slot', 1)['run']['cards_only']


with tempfile.TemporaryDirectory() as folder, patch.object(storage, 'ROOT', Path(folder)), \
        patch.object(game, 'RUNTIME', Path(folder) / 'runtime'):
    game.RUNTIME.mkdir()
    profile = storage.profile()
    profile.update(unlocked=content.PLAYABLE_IDS[:], variants_unlocked=True, character_levels={'98': 5})
    storage.write(storage.ROOT / 'profile.json', profile)
    random.seed(81)
    verify_run()
    print('PASS starter preview, reloaded choices and mode, standard saves and relic purchase, mixed cart protection, '
          'rerolls, 27 victories in Singles & packs, both act transitions, and the next loop')
    verify_distribution()
