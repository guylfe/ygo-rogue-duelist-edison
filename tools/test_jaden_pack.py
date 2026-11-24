"""Audit both personal boosters and exercise campaign acquisition for the expanded one.

Use --audit for seeded pull rates. The same audit can run against a prior checkout
with --root PATH, without writing to either checkout's saves.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import re
import sys
import tempfile
from unittest.mock import patch


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--audit', action='store_true')
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
args = parser.parse_args()
sys.path[:0] = [str(args.root.resolve()), str(args.root.resolve() / 'android')]

import campaign as game
import campaign_acts as acts
import content
import mobile_backend
import storage
import unlocks


DUELISTS = {'Jaden': 98, 'Kaiba': 1}
FLAME = ['Elemental HERO Flame Wingman', 'Elemental HERO Avian', 'Elemental HERO Burstinatrix']
THUNDER = ['Elemental HERO Thunder Giant', 'Elemental HERO Sparkman', 'Elemental HERO Clayman']
BLUE_EYES = ['Blue-Eyes White Dragon', 'Burst Stream of Destruction']
FUSION_SPELLS = ['Polymerization', 'Fusion Gate']
FUSION_ACCESS = FUSION_SPELLS + ['Fusion Sage', 'King of the Swamp']


def ids(names):
    return {game.BY_NAME[name]['id'] for name in names}


def pack_id(character):
    return content.CHARACTERS[character]['pack']


def pools(character, act):
    pack = acts.edition({'act': act}, content.PACK_BY_ID[pack_id(character)])
    assert unlocks.available('pack', pack['id'])
    return {
        tier: {game.card_identity(cid): cid for cid in reversed(pack[tier]) if unlocks.card_allowed(game.BY_ID[cid])}
        for tier in ('common', 'rare')
    }


def verified_open(character, act, rng, slots):
    cards = game.open_pack(pack_id(character), rng, {'act': act})
    identities = [game.card_identity(cid) for cid in cards]
    assert len(identities) == len(set(identities)) == 9
    assert set(identities[:8]) <= slots['common'].keys() and identities[8] in slots['rare']
    assert all(acts.allows({'act': act}, cid) for cid in cards)
    assert sum(game.normal_starter(cid) for cid in cards) >= 3
    return cards


def fusion_line(cards, recipe):
    return ids(recipe) <= cards and bool(cards & ids(FUSION_SPELLS))


def audit():
    samples = 4096
    results = []
    for name, character in DUELISTS.items():
        for act in range(1, 4):
            slots = pools(character, act)
            seen = set()
            frequency = Counter()
            rarity = content.PACK_BY_ID[pack_id(character)]['rarity_weights']
            for seed in range(samples):
                rng = random.Random(seed)
                first, second, third = [verified_open(character, act, rng, slots) for _ in range(3)]
                one = set(first)
                three = one.union(second, third)
                seen.update(three)
                if name == 'Jaden':
                    frequency['ace_per_pack'] += bool(one & ids(FLAME[:1]))
                    frequency['polymerization_per_pack'] += bool(one & ids(['Polymerization']))
                    frequency['fusion_spell_or_polymerization_searcher_per_pack'] += bool(one & ids(FUSION_ACCESS))
                    frequency['flame_recipe_over_three'] += fusion_line(three, FLAME)
                    frequency['thunder_recipe_over_three'] += fusion_line(three, THUNDER)
                    starter = three | ids(FLAME[1:])
                    frequency['flame_recipe_over_three_with_guaranteed_materials'] += fusion_line(starter, FLAME)
                else:
                    frequency['ace_per_pack'] += bool(one & ids(BLUE_EYES[:1]))
                    frequency['blue_eyes_and_burst_stream_over_three'] += ids(BLUE_EYES) <= three
            expected = set(slots['common']) | set(slots['rare'])
            assert {game.card_identity(cid) for cid in seen} == expected
            results.append(dict(duelist=name, act=act, unique=len(expected),
                                common=len(slots['common']), rare=len(slots['rare']),
                                overlap=len(slots['common'].keys() & slots['rare'].keys()),
                                normal_starters=sum(game.normal_starter(cid) for cid in slots['common'].values()),
                                custom_weights={game.BY_ID[int(cid)]['name']: weight for cid, weight in rarity.items()},
                                percent={key: round(hits * 100 / samples, 2) for key, hits in frequency.items()}))
    print(json.dumps(dict(samples=samples, results=results), indent=2))


def dispatch(action, value=None):
    result = json.loads(mobile_backend.dispatch(json.dumps(dict(action=action, value=value))))
    assert not result.get('error'), (action, result.get('error'))
    return result


def win_duel(run):
    dispatch('auto')
    assert game.validate(run) is None
    dispatch('choose', run['routes'][0])
    dispatch('begin')
    assert all(acts.allows(run, cid) for cid in game.deck(run) + run['duel']['enemy_deck'])
    dispatch('finish', dict(winner=0, lp=8000, events=[]))
    dispatch('reward-accept')


def test_acquisition():
    profile = storage.profile()
    profile['unlocked'] = content.PLAYABLE_IDS[:]
    profile['relicless_unlocked'] = True
    storage.write(storage.ROOT / 'profile.json', profile)
    for name, character in DUELISTS.items():
        pid = pack_id(character)
        for act in range(1, 4):
            slots = pools(character, act)
            for seed in range(64):
                verified_open(character, act, random.Random(seed), slots)
            if name == 'Jaden':
                all_ids = set(slots['common'].values()) | set(slots['rare'].values())
                for cid in all_ids:
                    if not game.is_extra(cid):
                        continue
                    recipe = game.BY_ID[cid]['desc'].splitlines()[0]
                    materials = [material for material in re.findall(r'"([^"]+)"', recipe)
                                 if material not in ('HERO', 'Elemental HERO')]
                    assert ids(materials) <= all_ids, (act, game.BY_ID[cid]['name'], materials)
                assert ids(THUNDER + FLAME) <= all_ids
                zero = ids(['Elemental HERO Absolute Zero'])
                assert bool(all_ids & zero) == (act == 3)
                if act >= 2:
                    assert ids(['Elemental HERO Neos', 'Miracle Fusion', 'Neo-Spacian Grand Mole']) <= all_ids
                if act == 3:
                    assert ids(['Elemental HERO Bubbleman', 'Elemental HERO Clayman']) <= all_ids

        random.seed(character)
        preview = dispatch('pack-inspect', dict(id=pid, starter=True))['result']
        assert {game.card_identity(row['id']) for row in preview} == (pools(character, 1)['common'].keys() | pools(character, 1)['rare'].keys())
        dispatch('new', dict(character=character, level=-1, slot=1, replace=True))
        run = mobile_backend.run
        assert run['pack_ids'].count(pid) == (3 if name == 'Jaden' else 2)
        dispatch('act-starter', next(iter(run['starter_offer'])))
        win_duel(run)
        for act in range(1, 4):
            assert run['act'] == act and acts.personal_pack(run) == pid
            preview = dispatch('pack-inspect', dict(id=pid, campaign=True))['result']
            slots = pools(character, act)
            assert {game.card_identity(row['id']) for row in preview} == (slots['common'].keys() | slots['rare'].keys())
            slot = next(i for i, item in enumerate(run['shop'])
                        if item['kind'] == 'pack' and item['id'] == pid and not item['sold'])
            balance, before = run['gold'], deepcopy(run['pool'])
            price = run['shop'][slot]['price']
            dispatch('buy', slot)
            cards = run['pool'][len(before):]
            assert run['pool'][:len(before)] == before and run['gold'] == balance - price
            assert len({game.card_identity(cid) for cid in cards}) == 9
            assert all(acts.allows(run, cid) for cid in cards)
            saved_shop = deepcopy(run['shop'])
            dispatch('select-slot', 1)
            run = mobile_backend.run
            assert run['pool'] == before + cards and run['shop'] == saved_shop and run['shop'][slot]['sold']
            print(f'{name} Act {act}: {price} coins, 9 legal pulls, purchase persisted')
            for _ in range(run['round'], acts.ACTS[act - 1]['duels']):
                win_duel(run)
            if act == 3:
                assert run['stage'] == 'complete' and len(run['timeline']) == 27
                break
            offer = run['act_transition']
            choice = pid if pid in offer['choices'] else offer['choices'][0]
            dispatch('act-transition', dict(packs=[choice] * offer['picks'], carry=[]))
            assert run['pool'][:len(before + cards)] == before + cards


with tempfile.TemporaryDirectory() as folder, patch.object(storage, 'ROOT', Path(folder)), \
        patch.object(game, 'RUNTIME', Path(folder) / 'runtime'):
    game.RUNTIME.mkdir()
    if args.audit:
        audit()
    else:
        test_acquisition()
