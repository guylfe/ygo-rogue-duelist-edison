"""Audit effective personal booster pools and test campaign acquisition.

Use --audit for reproducible results. Compare a prior checkout with --root PATH.
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
import payment
import storage
import unlocks


ROSTER = [1, *content.EDISON_DUELISTS]
CURRENT = any('goat_exceptions' in row for row in content.EDISON_DUELISTS.values())

# Functional lines used to count fresh cards with a role. The same list is
# applied to both versions. A line only counts if all its cards can be pulled.
PLANS = {
    1: ['Blue-Eyes White Dragon|Burst Stream of Destruction', "Blue-Eyes White Dragon|Lord of D.|The Flute of Summoning Dragon",
        'X-Head Cannon|Y-Dragon Head|Z-Metal Tank|XYZ-Dragon Cannon', 'King Dragun|Lord of D.|Divine Dragon Ragnarok'],
    98: ['Elemental HERO Flame Wingman|Elemental HERO Avian|Elemental HERO Burstinatrix|Polymerization',
         'Elemental HERO Thunder Giant|Elemental HERO Sparkman|Elemental HERO Clayman|Polymerization',
         'Elemental HERO Steam Healer|Elemental HERO Bubbleman|Elemental HERO Burstinatrix|Polymerization',
         'Elemental HERO Rampart Blaster|Elemental HERO Clayman|Elemental HERO Burstinatrix|Polymerization',
         'Elemental HERO Mariner|Elemental HERO Avian|Elemental HERO Bubbleman|Polymerization',
         'Elemental HERO Mudballman|Elemental HERO Clayman|Elemental HERO Bubbleman|Polymerization',
         'Elemental HERO Wildedge|Elemental HERO Wildheart|Elemental HERO Bladedge|Miracle Fusion',
         'Elemental HERO Absolute Zero|Elemental HERO Bubbleman|Elemental HERO Ocean|Miracle Fusion',
         'Elemental HERO Gaia|Elemental HERO Clayman|Elemental HERO Wildheart|Miracle Fusion'],
    99: ['Ojama King|Polymerization|Ojama Green|Ojama Black|Ojama Yellow',
         'Armed Dragon LV3|Armed Dragon LV5|Armed Dragon LV7|Level Up!',
         'X-Head Cannon|Y-Dragon Head|Z-Metal Tank|XYZ-Dragon Cannon',
         'V-Tiger Jet|W-Wing Catapult|VW-Tiger Catapult'],
    100: ['Cyber Saurus|Blast Juggler|Two-Headed King Rex|Polymerization',
          'Jinzo|Soul Exchange', 'Cyber End Dragon|Cyber Dragon|Power Bond',
          'Cyber Twin Dragon|Cyber Dragon|Proto-Cyber Dragon|Polymerization',
          'Cyberdark Dragon|Cyberdark Horn|Cyberdark Edge|Cyberdark Keel|Overload Fusion'],
    101: ['Mystic Swordsman LV2|Mystic Swordsman LV4|Level Up!',
          'Warrior Dai Grepher|Spirit Ryu|Ryu Senshi|Polymerization', 'Cyber Prima|Marauding Captain',
          'Cyber Blader|Blade Skater|Etoile Cyber|Polymerization', 'Ruin, Queen of Oblivion|End of the World'],
    102: ['Ancient Gear Golem|Ancient Gear Soldier|Soul Exchange',
          'Ancient Gear Golem|Ancient Gear Castle', 'Ancient Gear Beast|Ancient Gear Tank',
          'Ultimate Ancient Gear Golem|Ancient Gear Golem|Ancient Gear Cannon|Ancient Gear Soldier|Polymerization',
          'Geartown|Ancient Gear Gadjiltron Dragon'],
    103: ['Elemental HERO Flame Wingman|Elemental HERO Avian|Elemental HERO Burstinatrix|Polymerization',
          'Elemental HERO Phoenix Enforcer|Elemental HERO Avian|Elemental HERO Burstinatrix|Polymerization',
          'Destiny HERO - Doom Lord|Destiny Signal', 'Destiny HERO - Diamond Dude|Destiny Draw',
          'Destiny End Dragoon|Destiny HERO - Dogma|Destiny HERO - Plasma|Polymerization',
          'Clock Tower Prison|Eternal Dread|Destiny HERO - Dreadmaster'],
    104: ['Barrel Dragon|Second Coin Toss', 'Warrior of Zera|Archlord Zerato|The Sanctuary in the Sky',
          'Arcana Force I - The Magician|Arcana Force IV - The Emperor|Reversal of Fate|Light Barrier',
          'Arcana Force XXI - The World|Arcana Force VI - The Lovers|Light Barrier'],
    105: ['Giant Rat|Rescue Cat|Des Kangaroo', 'Master of Oz|Big Koala|Des Kangaroo|Polymerization',
          'Crystal Beast Amber Mammoth|Crystal Promise|Crystal Release',
          'Crystal Beast Sapphire Pegasus|Crystal Beacon|Crystal Beast Ruby Carbuncle',
          'Crystal Beast Sapphire Pegasus|Ancient City - Rainbow Ruins|Rare Value'],
    106: ['Marauding Captain|Warrior Dai Grepher|The Warrior Returning Alive',
          'Junk Synchron|Speed Warrior', 'Graceful Revival|Quillbolt Hedgehog',
          'Junk Synchron|Speed Warrior|Junk Warrior', 'Drill Synchron|Shield Warrior|Drill Warrior',
          'Majestic Dragon|Stardust Xiaolong|Stardust Dragon|Majestic Star Dragon'],
    107: ['Horus the Black Flame Dragon LV4|Horus the Black Flame Dragon LV6|Horus the Black Flame Dragon LV8',
          "Red-Eyes Black Dragon|Black Dragon's Chick|Inferno Fire Blast",
          'Masked Dragon|Exploder Dragon', 'Dark Resonator|Big Piece Golem|Red Dragon Archfiend',
          'Medium Piece Golem|Big Piece Golem|Multiple Piece Golem|Polymerization'],
    108: ['Lord Poison|Fairy King Truesdale', 'Des Dendle|Vampiric Orchis',
          'Cursed Fig|Botanical Girl|Miracle Fertilizer', 'Lonefire Blossom|Gigaplant|Miracle Fertilizer',
          'Debris Dragon|Dandylion|Black Rose Dragon', 'Nettles|Vampiric Orchis|Queen of Thorns'],
    109: ['X-Head Cannon|Y-Dragon Head|Z-Metal Tank|XYZ-Dragon Cannon',
          'Iron Blacksmith Kotetsu|Armed Samurai - Ben Kei|United We Stand',
          'Morphtronic Celfon|Morphtronic Cameran|Morphtronic Repair Unit',
          'Morphtronic Scopen|Morphtronic Boomboxen|Power Tool Dragon|Double Tool C&D'],
    110: ["Harpie Lady|Elegant Egotist|Harpie Lady Sisters|Harpies' Hunting Ground",
          'Blackwing - Fane the Steel Chain|Against the Wind', 'Harpie Queen|Icarus Attack',
          'Blackwing - Gale the Whirlwind|Blackwing - Shura the Blue Flame|Blackwing Armor Master|Black Whirlwind',
          'Blackwing - Vayu the Emblem of Honor|Blackwing - Sirocco the Dawn|Blackwing Armed Wing'],
    111: ['Terrorking Archfiend|Vilepawn Archfiend|Pandemonium',
          'Flash Assailant|Theban Nightmare|Dark Core', 'Infernity Beast|Depth Amulet|Infernity Force',
          'Infernity Archfiend|Infernity Necromancer|Dark Grepher',
          'Earthbound Immortal Ccapac Apu|Mausoleum of the Emperor'],
}
UTILITY = [
    'Book of Moon', 'Call of the Haunted', 'Compulsory Evacuation Device', 'Dark Hole', 'Dust Tornado',
    'Enemy Controller', 'Fissure', 'Forbidden Chalice', 'Heavy Storm', 'Mirror Force', 'Monster Reborn',
    'Mystical Space Typhoon', 'Premature Burial', 'Reinforcement of the Army', 'Sakuretsu Armor',
    'Smashing Ground', 'Solemn Judgment', 'Torrential Tribute', 'Trap Hole', 'Waboku',
]


def ids(names):
    return {game.BY_NAME[name]['id'] for name in names if name in game.BY_NAME}


def pack_id(character):
    return content.CHARACTERS[character]['pack']


def native_pack(character):
    return content.PACK_BY_ID[pack_id(character)]


def personal_edition(character, act):
    view = {'act': act, 'character': character}
    return acts.edition(view, native_pack(character), personal=True) if CURRENT else acts.edition(view, native_pack(character))


def pools(character, act):
    pack = personal_edition(character, act)
    assert unlocks.available('pack', pack['id'])
    return {tier: {game.card_identity(cid): cid for cid in reversed(pack[tier])
                   if unlocks.card_allowed(game.BY_ID[cid])} for tier in ('common', 'rare')}


def exceptions(character):
    return set().union(*native_pack(character).get('goat_exceptions', {}).values())


def draw(character, act, rng):
    view = {'act': act, 'character': character}
    if CURRENT:
        return game.open_pack(pack_id(character), rng, view, personal=True)
    return game.open_pack(pack_id(character), rng, view)


def verify_open(character, act, cards, slots):
    identities = [game.card_identity(cid) for cid in cards]
    assert len(set(identities)) == 9
    assert set(identities[:8]) <= slots['common'].keys() and identities[8] in slots['rare']
    assert all(acts.allows({'act': act}, cid) or cid in exceptions(character) for cid in cards)
    assert sum(game.normal_starter(cid) for cid in cards) >= 3


def audit():
    samples, starts = 512, 48
    result = {}
    flame = ids(['Elemental HERO Flame Wingman', 'Elemental HERO Avian', 'Elemental HERO Burstinatrix'])
    flame_ace = next(iter(ids(['Elemental HERO Flame Wingman'])))
    fusion = ids(['Polymerization', 'Fusion Gate'])

    def full_line(cards):
        cards = set(cards)
        return flame <= cards and bool(cards & fusion)

    def names(cards):
        return {game.card_identity(cid) for cid in cards}

    for character in ROSTER:
        pid = pack_id(character)
        opening_samples = 2048 if character == 98 else samples
        starting_samples = 384 if character == 98 else starts
        records = []
        for act in (1, 2, 3):
            slots = pools(character, act)
            population = set(slots['common']) | set(slots['rare'])
            card_ids = set(slots['common'].values()) | set(slots['rare'].values())
            plans = [plan.split('|') for plan in PLANS[character]]
            live = [ids(plan) for plan in plans if all(name in game.BY_NAME for name in plan) and ids(plan) <= card_ids]
            useful = names(set.union(ids(UTILITY), *live) | {
                cid for cid in card_ids if game.normal_starter(cid)
                and (game.BY_ID[cid]['atk'] >= 1500 or game.BY_ID[cid]['defense'] >= 1700)
            })
            frequency = Counter()
            seen_drawable = set()
            for seed in range(opening_samples):
                rng = random.Random(seed)
                seen = set()
                for n in range(1, 6):
                    cards = draw(character, act, rng)
                    verify_open(character, act, cards, slots)
                    names_drawn = names(cards)
                    if n == 1 and character == 98:
                        frequency['flame_wingman_one'] += flame_ace in cards
                        frequency['flame_line_one'] += full_line(cards)
                    if n >= 3:
                        fresh = names_drawn - seen
                        frequency[f'fresh_{n}'] += len(fresh)
                        frequency[f'useful_{n}'] += len(fresh & useful)
                    seen.update(names_drawn)
                    if n == 2:
                        frequency['seen_after_two'] += len(seen)
                seen_drawable.update(seen)
            assert seen_drawable == population
            measured = {key: round(value / opening_samples, 4) for key, value in frequency.items()}
            measured['depleted_pct'] = round(100 * measured['seen_after_two'] / len(population), 1)
            records.append(dict(act=act, common=len(slots['common']), premium=len(slots['rare']),
                                total=len(population), useful_pool=len(useful & population),
                                live_lines=len(live), **measured))
        conditioned = Counter()
        for seed in range(starting_samples):
            rng = random.Random(seed)
            run = game.new_run(character, rng, act_campaign=True)
            packs = [cards for key, cards in zip(run['pack_ids'], run['packs']) if key == pid]
            assert len(packs) == (2 if character == 1 else 3)
            third = packs[2] if len(packs) == 3 else draw(character, 1, rng)
            conditioned['third_new_after_actual_first_two'] += len(names(third) - names(packs[0] + packs[1]))
            acts.choose_starter(run, next(iter(run['starter_offer'])))
            conditioned['next_personal_new_after_full_draft'] += len(names(draw(character, 1, rng)) - names(run['pool']))
            if character == 98:
                conditioned['flame_wingman_in_draft'] += flame_ace in run['pool']
                conditioned['flame_line_in_draft'] += full_line(run['pool'])
        result[content.CHARACTERS[character]['name']] = {
            'acts': records, 'starting_draft': {key: round(value / starting_samples, 4) for key, value in conditioned.items()},
        }
    print(json.dumps(dict(samples=samples, actual_starts=starts, jaden_samples=2048, jaden_starts=384, result=result), indent=2))


def dispatch(action, value=None):
    result = json.loads(mobile_backend.dispatch(json.dumps(dict(action=action, value=value))))
    assert not result.get('error'), (action, result.get('error'))
    return result


def win_duel(run, selected=None):
    dispatch('auto')
    if selected is not None and selected not in run['selected']:
        dispatch('toggle', [selected])
    assert game.validate(run) is None
    dispatch('choose', run['routes'][0])
    dispatch('begin')
    assert all(acts.allows(run, cid) for cid in run['duel']['enemy_deck'])
    assert all(acts.allows(run, cid) or cid in exceptions(run['character']) for cid in game.deck(run))
    if selected is not None:
        code = run['pool'][selected]
        lua = (game.RUNTIME / 'puzzles' / 'shadow-run.lua').read_text(encoding='utf8')
        assert re.search(rf'Debug.AddCard\({code},0,0,LOCATION_(DECK|EXTRA),', lua)
    dispatch('finish', dict(winner=0, lp=8000, events=[]))
    assert all(acts.allows(run, cid) for cid in run.get('last_reward_cards', []))
    dispatch('reward-accept')
    for item in run['shop']:
        if item['kind'] == 'single':
            assert all(acts.allows(run, cid) for cid in item.get('bundle', [item['id']]))


def purchases(run, character, act):
    pid = pack_id(character)
    seen, pulled = set(), []
    while len(pulled) < 3:
        assert run['stage'] == 'shop', (character, act, run['stage'])
        slot = next(i for i, item in enumerate(run['shop'])
                    if item['kind'] == 'pack' and item['id'] == pid and not item['sold'])
        item = run['shop'][slot]
        if payment.can_pay(run, item['price']):
            balance, before = run['gold'], run['pool'][:]
            dispatch('buy', slot)
            cards = run['pool'][len(before):]
            verify_open(character, act, cards, pools(character, act))
            assert run['pool'][:len(before)] == before and run['gold'] == balance - item['price']
            identities = {game.card_identity(cid) for cid in cards}
            pulled.append(len(identities - seen))
            seen.update(identities)
            saved_shop = deepcopy(run['shop'])
            dispatch('select-slot', 1)
            run = mobile_backend.run
            assert run['pool'] == before + cards and run['shop'] == saved_shop and run['shop'][slot]['sold']
        if len(pulled) < 3:
            win_duel(run)
    return run, pulled


def test_campaigns():
    for character in ROSTER:
        pid = pack_id(character)
        for act in (1, 2, 3):
            lists = pools(character, act)
            allowed = set(lists['common'].values()) | set(lists['rare'].values())
            for seed in range(30):
                verify_open(character, act, draw(character, act, random.Random(seed)), lists)
            if character != 1:
                for cid in allowed:
                    if game.is_extra(cid):
                        recipe = game.BY_ID[cid]['desc'].splitlines()[0]
                        named = [n for n in re.findall(r'"([^"]+)"', recipe) if n in game.BY_NAME]
                        assert ids(named) <= allowed, (character, act, game.BY_ID[cid]['name'], named)
        random.seed(character)
        dispatch('new', dict(character=character, level=-1, slot=1, replace=True))
        run = mobile_backend.run
        assert run['pack_ids'].count(pid) == (2 if character == 1 else 3)
        dispatch('act-starter', next(iter(run['starter_offer'])))
        win_duel(run)
        for act in (1, 2, 3):
            assert run['act'] == act and acts.personal_pack(run) == pid
            preview = dispatch('pack-inspect', dict(id=pid, campaign=True, personal=True))['result']
            slots = pools(character, act)
            assert {game.card_identity(row['id']) for row in preview} == (slots['common'].keys() | slots['rare'].keys())
            run, fresh = purchases(run, character, act)
            print(f'{content.CHARACTERS[character]["name"]}, Act {act}: new in successive shop packs {fresh}')
            for _ in range(run['round'], acts.ACTS[act - 1]['duels']):
                win_duel(run)
            if act == 3:
                assert run['stage'] == 'complete' and len(run['timeline']) == 27
                break
            offer = run['act_transition']
            choice = pid if pid in offer['choices'] else offer['choices'][0]
            dispatch('act-transition', dict(packs=[choice] * offer['picks'], carry=[]))


def test_exceptions():
    apart = ids(['Elemental HERO Shining Flare Wingman'])
    assert not apart & set(personal_edition(98, 1)['rare'])
    approved = set().union(*(exceptions(i) for i in content.EDISON_DUELISTS))
    for pid in acts.native_packs(1):
        pack = acts.edition({'act': 1, 'character': 98}, content.PACK_BY_ID[pid], personal=True)
        assert not approved & set(pack['common'] + pack['rare'])
    checked = 0
    for character in content.EDISON_DUELISTS:
        pid, pack = pack_id(character), native_pack(character)
        view = {'act': 1, 'character': character}
        regular = acts.edition(view, pack)
        visitor = acts.edition({'act': 1, 'character': 1}, pack, personal=True)
        tag = acts.edition(dict(view, history_mode='tag'), pack, personal=True)
        own = personal_edition(character, 1)
        expected = exceptions(character)
        assert expected and all(not acts.allows(view, cid) for cid in expected)
        assert regular == visitor == tag
        for tier in ('common', 'rare'):
            assert set(own[tier]) - set(regular[tier]) == set(pack['goat_exceptions'][tier])
        # Find an ordinary starting draft that owns each card. Save and reload
        # exactly that draft, select the copy and prepare the normal duel.
        for seed in range(300):
            rng = random.Random(seed)
            run = game.new_run(character, rng, level=-1, act_campaign=True)
            off_era = {cid for cid in run['pool'] if not acts.allows(run, cid)}
            assert off_era <= exceptions(character)
            assert all(acts.allows(run, cid) for cards in run['starter_offer'].values() for cid in cards)
            found = off_era & expected
            if not found:
                continue
            acts.choose_starter(run, next(iter(run['starter_offer'])))
            for cid in found:
                snapshot = deepcopy(run)
                snapshot['_save_slot'] = 2
                game.save(snapshot)
                dispatch('select-slot', 2)
                saved = mobile_backend.run
                win_duel(saved, saved['pool'].index(cid))
                checked += 1
            expected -= found
            if not expected:
                break
        assert not expected, (character, expected)
    assert checked == sum(len(exceptions(i)) for i in content.EDISON_DUELISTS)
    print(f'PASS all {checked} exceptions drafted, selected after reload and present in real duel setup')


with tempfile.TemporaryDirectory() as folder, patch.object(storage, 'ROOT', Path(folder)), \
        patch.object(game, 'RUNTIME', Path(folder) / 'runtime'):
    game.RUNTIME.mkdir()
    profile = storage.profile()
    profile['unlocked'] = content.PLAYABLE_IDS[:]
    profile['relicless_unlocked'] = True
    storage.write(storage.ROOT / 'profile.json', profile)
    if args.audit:
        audit()
    else:
        test_campaigns()
        test_exceptions()
