"""Audit the eleven retail sources through the solo campaign's two purchase modes."""
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
from pack_odds import inspect_pack
import storage


EXPECTED = {
    'EN-DP1': (98, 2), 'EN-DP03': (98, 2), 'EN-DP06': (98, 2),
    'EN-DP2': (99, 2), 'EN-DP04': (100, 2), 'EN-DP05': (103, 2),
    'EN-DP07': (105, 2), 'EN-DP08': (106, 3), 'EN-DP09': (106, 3),
    'EN-DPYG': (13, 3), 'EN-DPKB': (1, 3),
}


def identities(cards):
    return {game.card_identity(cid) for cid in cards}


def cards(pack):
    return pack['common'] + pack['rare'] + pack.get('starter_support', [])


def stock(run):
    return [item for item in run['shop'] if item['kind'] == 'pack']


def check_offers(ids, count):
    assert len(ids) == len(set(ids)) == count, ids
    assert not set(ids).intersection(EXPECTED), ids


def verify_card_access(profile):
    assert set(EXPECTED) == set(acts.RETAIL_BOOSTERS)
    assert set(EXPECTED) == {p['id'] for p in content.PACKS if p['name'].startswith('Duelist Pack:')}
    for source, (owner, first_act) in EXPECTED.items():
        target = content.CHARACTERS[owner]['pack']
        assert acts.offer_id(source) == target and acts.pack_act(source) == first_act
        original = content.PACK_BY_ID[source]
        for act in (1, 2, 3):
            for cards_only in (False, True):
                run = dict(act=act, character=owner, cards_only=cards_only)
                merged = acts.edition(run, content.PACK_BY_ID[target], personal=True)
                assert merged == acts.edition(run, original, personal=True)
                baseline = acts.edition(dict(run, history_mode='tag'), content.PACK_BY_ID[target])
                extras = {cid for slot in merged.get('goat_exceptions', {}).values() for cid in slot}
                assert identities(cards(baseline)) <= identities(cards(merged))
                assert all(acts.allows(run, cid) or cid in extras for cid in cards(merged))
                if act < first_act:
                    continue
                retail = identities(cid for cid in cards(original) if acts.allows(run, cid))
                preview = inspect_pack(target, profile, run, personal=True)
                assert retail <= identities(row['id'] for row in preview if row['chance'] > 0)
                assert abs(sum(row['chance'] for row in preview) - 9) < 1e-8
                assert identities(merged['common']).intersection(identities(merged['rare'])) <= \
                    identities(baseline['common']).intersection(identities(baseline['rare']))
        assert source not in acts.native_packs(first_act)
        assert target in acts.native_packs(first_act)


def verify_live_offers(cards_only):
    start_count, shop_count, transition_count = (7, 5, 8) if cards_only else (5, 3, 6)
    for owner in sorted({owner for owner, _ in EXPECTED.values()}):
        rng = random.Random(owner)
        run = game.new_run(owner, rng, act_campaign=True, cards_only=cards_only)
        check_offers(run['starter_offer_order'], start_count)
        acts.choose_starter(run, run['starter_offer_order'][0])
        for act in (1, 2, 3):
            run.update(stage='shop', gold=900, act=act, round=1, next_boss=None)
            game.routes(run, rng)
            check_offers([reward['pack'] for reward in run['route_rewards'].values()], len(run['routes']))
            run['shop_reward'] = run['route_rewards'][str(run['opponent'])]
            game.restock(run, rng)
            check_offers([item['id'] for item in stock(run)], shop_count)
            personal = acts.personal_pack(run)
            item = next(item for item in stock(run) if item['id'] == personal)
            result, = game.buy_many(run, [run['shop'].index(item)], rng)
            assert len(result['cards']) == 9
            assert result['rare_display'] == [cid for cid in result['cards']
                                               if cid in acts.edition(run, content.PACK_BY_ID[personal], personal=True)['rare_display']]
            if act < 3:
                offer = acts.transition_offer(run, rng)
                check_offers(offer['choices'], transition_count)
                assert offer['carryable'] == acts.unique_offers(offer['carryable'])

    # All broad offers still enter the seeded public rotation for another
    # duelist, even where multiple retail sets used to occupy that rotation.
    rotations = [acts.draft_rotations([], random.Random(seed), cards_only=cards_only) for seed in range(80)]
    for source, (_, act) in EXPECTED.items():
        assert any(acts.offer_id(source) in r[str(act)] for r in rotations)
    assert rotations[0] == acts.draft_rotations([], random.Random(0), cards_only=cards_only)


with tempfile.TemporaryDirectory() as folder, patch.object(storage, 'ROOT', Path(folder)), \
        patch.object(game, 'RUNTIME', Path(folder) / 'runtime'):
    game.RUNTIME.mkdir()
    profile = storage.profile()
    profile.update(unlocked=content.PLAYABLE_IDS[:])
    storage.write(storage.ROOT / 'profile.json', profile)
    verify_card_access(profile)
    for mode in (False, True):
        verify_live_offers(mode)
print('PASS eleven retail mappings, era eligibility, preview and receipt rarity, seeded access, and distinct offers in both solo modes.')
