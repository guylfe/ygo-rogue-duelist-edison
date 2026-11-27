"""Personal, opponent and marked boosters through the real solo shop and save path."""
from copy import deepcopy
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import campaign as game
import campaign_acts as acts
import content
import random_cards
import shop_rewards
import storage
from pack_odds import inspect_pack


def pack_items(run):
    return [item for item in run['shop'] if item['kind'] == 'pack']


def open_shop(run, act, rng):
    run.update(act=act, round=1, stage='shop', gold=900)
    game.routes(run, rng)
    run['shop_reward'] = run['route_rewards'][str(run['opponent'])]
    game.restock(run, rng)
    return run['shop_reward']['pack']


with tempfile.TemporaryDirectory() as folder, patch.object(storage, 'ROOT', Path(folder)), \
        patch.object(game, 'RUNTIME', Path(folder)/'runtime'):
    game.RUNTIME.mkdir()
    profile = storage.profile()
    profile.update(unlocked=content.PLAYABLE_IDS[:], variants_unlocked=True)
    storage.write(storage.ROOT/'profile.json', profile)
    rng = random.Random(672)
    signatures = 0
    for character in content.PLAYABLE_IDS:
        char = content.CHARACTERS[character]
        personal = char['pack']
        if personal not in content.PACK_BY_ID:
            continue
        signatures += 1
        start = game.new_run(character, rng, act_campaign=True)
        acts.choose_starter(start, next(iter(start['starter_offer'])))
        for act in (1, 2, 3):
            run = deepcopy(start)
            opponent = open_shop(run, act, rng)
            assert len(pack_items(run)) == 3
            assert [p['id'] for p in pack_items(run) if p['opponent_pack']] == [opponent]
            assert sum(p['id'] == personal for p in pack_items(run)) == 1
            assert [p['id'] for p in pack_items(run) if p['id'] == personal and not p['opponent_pack']] == [personal]
            assert personal in run['offered_packs']
            if char.get('alternate'):
                assert acts.personal_pack(dict(run, variant=1)) == personal

            marked = next(p for p in acts.rotation(run) if p not in {i['id'] for i in pack_items(run)})
            acts.register_pack(run, marked)
            acts.pin(run, marked)
            assert {p['id'] for p in pack_items(run)} == {personal, opponent, marked}
            assert set(run['offered_packs']).issuperset((personal, opponent, marked))
            game.reroll_shop(run, rng)
            assert {p['id'] for p in pack_items(run)} == {personal, opponent, marked}

            pack = content.PACK_BY_ID[personal]
            early = set()
            if act < pack.get('home_act', 1):
                early = {cid for slot in pack.get('goat_exceptions', {}).values() for cid in slot}
            preview = inspect_pack(personal, profile, run, personal=True)
            assert preview and all(acts.allows(run, row['id']) or row['id'] in early for row in preview)
            slot = next(i for i, p in enumerate(run['shop']) if p['id'] == personal)
            previous_pool = run['pool'][:]
            game.buy(run, slot, rng)
            pulls = run['pool'][len(previous_pool):]
            assert len(pulls) == 9 and len({game.card_identity(cid) for cid in pulls}) == 9
            assert all(acts.allows(run, cid) or cid in early for cid in pulls)
            preview_identities = {game.card_identity(row['id']) for row in preview if row['chance'] > 0}
            assert {game.card_identity(cid) for cid in pulls} <= preview_identities
    assert signatures == 47

    jaden = game.new_run(98, rng, act_campaign=True)
    assert jaden['pack_ids'] == ['DRAFT-JADEN-YUKI'] * 3
    acts.choose_starter(jaden, next(iter(jaden['starter_offer'])))
    for act in (1, 2, 3):
        run = deepcopy(jaden)
        opponent = open_shop(run, act, rng)
        personal = acts.personal_pack(run)
        rotation = acts.rotation(run)
        carried = dict(run, carried_packs=[personal, rotation[0]])
        assert all(reward['pack'] != personal for reward in
                   shop_rewards.route_rewards(run['routes'], rng, profile, carried).values())
        seen_stock = [pid for pid in rotation if pid not in (opponent, personal)][:2]
        old_shop = deepcopy(run['shop'])
        for item, pid in zip([p for p in pack_items(run) if not p['opponent_pack']], seen_stock):
            item['id'] = pid
        pack_items(run)[1]['sold'] = True
        marked = next(pid for pid in rotation if pid not in (personal, opponent, *seen_stock))
        run.update(carried_packs=rotation[:2], opened_packs=[marked], pinned_pack=marked)
        run['offered_packs'] = [opponent, *seen_stock]
        old = deepcopy(run)
        if act == 2:
            old.pop('pack_rotations')
        game.save(old)
        restored = game.load_run()
        assert restored['pool'] == old['pool'] and restored['selected'] == old['selected']
        assert restored['carried_packs'] == old['carried_packs']
        assert restored.get('pack_rotations') == old.get('pack_rotations')
        assert restored['pinned_pack'] == marked
        assert pack_items(restored)[0]['id'] == opponent
        assert pack_items(restored)[1]['id'] == seen_stock[0] and pack_items(restored)[1]['sold']
        assert pack_items(restored)[2]['id'] == personal
        assert [x for x in restored['shop'] if x['kind'] != 'pack'] == [
            x for x in old_shop if x['kind'] != 'pack']
        assert restored['offered_packs'] == [opponent, *seen_stock, personal]
        assert game.load_run()['shop'] == restored['shop']
        game.reroll_shop(restored, rng)
        assert {p['id'] for p in pack_items(restored)} == {personal, opponent, marked}

    for character in (36, 37, 38):
        for variant in (0, 1):
            start = game.new_run(character, rng, variant=variant, act_campaign=True)
            if start['stage'] == 'starter':
                acts.choose_starter(start, next(iter(start['starter_offer'])))
            for act in (1, 2, 3):
                run = deepcopy(start)
                opponent = open_shop(run, act, rng)
                assert acts.personal_pack(run) is None
                stock = pack_items(run)
                if character == 37 and variant:
                    assert {p['id'] for p in stock} == {random_cards.RANDOM_PACK}
                    assert not acts.pin_options(run)
                else:
                    assert [p['id'] for p in stock if p['opponent_pack']] == [opponent]
                if character == 38 or character == 37 and not variant:
                    try:
                        game.buy(run, run['shop'].index(stock[0]), rng)
                    except ValueError as error:
                        assert 'only buy relics' in str(error)
                    else:
                        raise AssertionError('Fixed deck could buy a pack')

    for duelist in content.EDISON_DUELISTS.values():
        if duelist['home_act'] != 3:
            continue
        pack = content.PACK_BY_ID[duelist['pack']]
        goat = acts.edition({'act': 1}, pack)
        gx = acts.edition({'act': 2}, pack)
        edison = acts.edition({'act': 3}, pack)
        cards = lambda x: set(x['common'] + x['rare'])
        assert cards(goat) == cards(pack['goat_slots'])
        assert cards(gx) == cards(goat) | {cid for cid in cards(pack) if acts.FIRST_ACT[cid] <= 2}
        assert cards(edison) == cards(pack)
        assert not any(acts.FIRST_ACT[cid] == 3 for cid in cards(gx))
        assert len(cards(gx)) >= 9
    yusei = content.EDISON_DUELISTS[106]['pack']
    gx_odds = {game.BY_ID[row['id']]['name']:row['chance']
               for row in inspect_pack(yusei, profile, {'act': 2})}
    assert gx_odds['Limit Reverse'] > 0 and 'Junk Synchron' not in gx_odds

    golem = game.BY_NAME['Ancient Gear Golem']['id']
    assert acts.allows({'act': 1}, golem)
    assert any(row['id'] == golem and row['chance'] > 0
               for row in inspect_pack('EN-TLM', profile, {'act': 1}))

print('PASS 141 three-act personal shops, marks, rerolls and legal purchases; Jaden saved stock in all acts; '
      '5D\'s GX editions, special loadouts and GOAT Ancient Gear Golem.')
