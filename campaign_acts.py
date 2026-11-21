"""Solo campaign card eras, pack rotation, and act transitions."""
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

CONFIG = json.loads((Path(__file__).parent / 'data/campaign-acts.json').read_text(encoding='utf8'))
ACTS = CONFIG['acts']
FIRST_ACT = {cid: n for n, ids in enumerate(CONFIG['card_ids'], 1) for cid in ids}


def active(run):
    return bool(run and run.get('act'))


def era(run):
    return int(run.get('act', 3)) if run else 3


def allows(run, cid):
    return not active(run) or FIRST_ACT.get(cid, 4) <= era(run)


def base_minimum(run):
    act = ACTS[era(run) - 1]
    return act['final_stretch_minimum'] if run['round'] >= act['duels'] - 3 else act['minimum']


@lru_cache(maxsize=None)
def pack_act(pid):
    from content import PACK_BY_ID
    pack = PACK_BY_ID[pid]
    if pid.startswith('DRAFT-'):
        return pack.get('home_act', 1)
    if pack.get('region') != 'EN' or not pid.startswith('EN-'):
        return None
    return next((i for i, act in enumerate(ACTS, 1) if pack['date'] <= act['cutoff']), None)


def edition(run, pack):
    """Project every slot and rarity of a pack into the current act."""
    if not active(run):
        return pack
    if pack.get('goat_slots') and era(run) < pack['home_act']:
        slots = pack['goat_slots']
        rarities = {str(cid): [label] for key, label in (('common','Common'),('rare','Rare')) for cid in slots[key]}
        pack = dict(pack, **slots, rare_display=slots['rare'], rarities=rarities)
    from campaign import card_identity, normal_starter
    card_fields = ('common', 'rare', 'starter_support', 'rare_display')
    result = dict(pack, **{k: [cid for cid in pack[k] if allows(run, cid)] for k in card_fields if k in pack})
    ids = result['common'] + result['rare'] + result.get('starter_support', [])
    result['rarities'] = {str(cid): pack.get('rarities', {}).get(str(cid), []) for cid in ids}
    if not any(normal_starter(cid) for cid in ids):
        result['shop_only'] = True
    return result


@lru_cache(maxsize=None)
def openable(pid, act):
    from campaign import card_identity
    from content import PACK_BY_ID
    pack = edition({'act': act}, PACK_BY_ID[pid])
    return len({card_identity(cid) for cid in pack['common'] + pack['rare']}) >= 9


def native_packs(act, starters=False):
    from content import PACKS
    return [p['id'] for p in PACKS
            if not p.get('draft_only') and pack_act(p['id']) == act and openable(p['id'], act)
            and (not starters or not edition({'act': act}, p).get('shop_only'))]


def draft_rotations(preferred, rng, duelist=None):
    """Draw the three native shop lineups once, before any campaign offers."""
    rotations = {}
    starters = dict.fromkeys(preferred[:3])
    for act, rules in enumerate(ACTS, 1):
        native = native_packs(act)
        # GOAT pairs TLM with Machine, Warrior, or Chaos support. GX pairs LODT
        # with Gladiator Beast or LIGHT support. Edison pairs TDGS with Tuners and Synchros.
        featured = rules['featured_pack']
        lineup = [featured] if featured in native else []
        companions = [pid for pid in rules['companion_packs'] if pid in native and pid not in lineup]
        if companions:
            lineup.append(rng.choice(companions))
        if duelist and duelist['home_act'] == act and duelist['support'] in native and duelist['support'] not in lineup:
            lineup.append(duelist['support'])
        if act == 1:
            lineup.extend(pid for pid in starters if pid in native and pid not in lineup)
        limit = CONFIG['rotation_size']
        lineup = lineup[:limit]
        remaining = [pid for pid in native if pid not in lineup]
        lineup.extend(rng.sample(remaining, min(len(remaining), limit - len(lineup))))
        rotations[str(act)] = lineup
    return rotations


def native_rotation(run, act):
    # Existing campaigns retain the lineups and offers they started with.
    if 'pack_rotations' not in run:
        return native_packs(act)
    return run['pack_rotations'][str(act)]


def rotation(run, draft_relic=False):
    from content import PACKS
    if not active(run):
        return [p['id'] for p in PACKS if not p.get('home_act')]
    act = era(run)
    # Draft packs are available through their signature start or the dedicated relic.
    themed = [p['id'] for p in PACKS if p.get('draft_only') and p.get('home_act',act)==act and openable(p['id'], act)] if draft_relic else []
    return list(dict.fromkeys(native_rotation(run, act) + run.get('carried_packs', []) + themed))


def home_pack(run, character):
    from content import EDISON_DUELISTS
    duelist = EDISON_DUELISTS.get(character)
    if active(run) and not run.get('loop') and duelist and duelist['home_act'] == era(run):
        return duelist['pack']
    return None


def shop_pack_available(run, pid):
    from content import PACK_BY_ID
    pack = PACK_BY_ID.get(pid, {})
    return pid in rotation(run) or (pack.get('home_act') == era(run) and not run.get('loop'))


def register_pack(run, pid):
    if active(run) and pid not in run.setdefault('opened_packs', []):
        run['opened_packs'].append(pid)


def pin_options(run):
    from content import PACK_BY_ID
    if not active(run):
        return []
    eligible = set(rotation(run))
    eligible.update(pid for pid in run.get('opened_packs', []) if shop_pack_available(run, pid))
    if era(run) == 1:
        eligible.update(run.get('pack_ids', []))
    return [pid for pid in run.get('opened_packs', []) if pid in eligible and pid in PACK_BY_ID]


def pin(run, pid):
    if run.get('stage') not in ('draft', 'shop'):
        raise ValueError('Mark a booster between duels.')
    if pid and pid not in pin_options(run):
        raise ValueError('Open this booster in the current rotation before marking it.')
    run['pinned_pack'] = pid or None
    stock = [item for item in run.get('shop', []) if item['kind'] == 'pack']
    if pid and all(item['id'] != pid for item in stock):
        slot = next((item for item in reversed(stock) if not item['sold'] and not item['opponent_pack']), None)
        if slot:
            slot['id'] = pid
            run['offered_packs'] = list(dict.fromkeys(run.get('offered_packs', []) + [pid]))


def stocked_packs(run, ids, tied, available, rng):
    pinned = run.get('pinned_pack')
    if len(ids) > tied and pinned in pin_options(run) and pinned not in ids:
        ids[-1] = pinned
    used = set(ids[:tied])
    for i in range(tied, len(ids)):
        if ids[i] in used:
            alternatives = [pid for pid in available if pid not in ids and pid not in used]
            if alternatives:
                ids[i] = rng.choice(alternatives)
        used.add(ids[i])
    from content import PACK_BY_ID
    run['offered_packs'] = list(dict.fromkeys(run.get('offered_packs', []) + [pid for pid in ids if pid in PACK_BY_ID]))
    return ids


def starter_list(run, preferred, rng):
    """Keep the first three workable signature packs and advertise a supporting choice."""
    from content import PACK_BY_ID
    rotation = native_rotation(run, 1)
    fallback = [pid for pid in rotation if not edition(run, PACK_BY_ID[pid]).get('shop_only')]
    core = []
    for pid in preferred[:3]:
        if pid in rotation or PACK_BY_ID.get(pid, {}).get('draft_only') and openable(pid, 1):
            core.append(pid)
        else:
            core.append(rng.choice(fallback))
    if not core:
        return [], []
    options = rng.sample(fallback, min(len(fallback), CONFIG['starter_options']))
    return core, options


def choose_starter(run, pid):
    offer = run.get('starter_offer') or {}
    if run['stage'] != 'starter' or pid not in offer:
        raise ValueError('Choose a supporting booster from the starting offer.')
    cards = offer[pid]
    run['pool'].extend(cards)
    run['packs'].append(cards)
    run['pack_ids'].append(pid)
    for opened in run['pack_ids']:
        register_pack(run, opened)
    run.pop('starter_offer')
    run['stage'] = 'draft'


def transition_offer(run, rng):
    from content import PACK_BY_ID, EDISON_DUELISTS
    incoming = era(run) + 1
    packs = native_rotation(run, incoming)
    # Rotate the preview once at the boundary. Persist it so returning to the
    # run never rerolls the choices or awards cards twice.
    offered = list(dict.fromkeys(run.get('offered_packs', []) + (run.get('pack_ids', []) if era(run) == 1 else [])))
    carryable = [pid for pid in offered if pid in PACK_BY_ID and openable(pid, incoming)]
    anchor = ACTS[incoming - 1]['featured_pack']
    choices = [anchor] if anchor in packs else []
    duelist = EDISON_DUELISTS.get(run.get('character'))
    if duelist and duelist['home_act']==incoming:
        if duelist['support'] in packs and duelist['support'] not in choices:
            choices.append(duelist['support'])
        choices.append(duelist['pack'])
    eligible = [pid for pid in packs if pid not in choices]
    choices += rng.sample(eligible, min(len(eligible), CONFIG['transition_choices'] - len(choices)))
    return dict(incoming=incoming, choices=choices, carryable=carryable,
                picks=CONFIG['transition_picks'], carry_limit=CONFIG['carry_limit'])


def transition(game, run, value, rng):
    offer = run.get('act_transition')
    if run.get('stage') != 'act_transition' or not offer or run.get('reward_slots', {}).get('pending') or run.get('cursed_offer'):
        raise ValueError('Finish the victory rewards before choosing era boosters.')
    incoming, carry = value.get('packs'), value.get('carry')
    if not isinstance(incoming, list) or len(incoming) != offer['picks'] or any(p not in offer['choices'] for p in incoming):
        raise ValueError('Select the required number of incoming boosters.')
    if not isinstance(carry, list) or len(carry) > offer['carry_limit'] or len(set(carry)) != len(carry) or any(p not in offer['carryable'] for p in carry):
        raise ValueError('Select up to the allowed number of distinct carryover boosters.')
    from copy import deepcopy
    nxt = deepcopy(run)
    nxt.update(act=offer['incoming'], round=0, stage='shop', shop=[], carried_packs=list(carry),
               offered_packs=[], defeated_opponents=[], last_deck_minimum_increase=0)
    for key in ('act_transition', 'next_boss', 'tutorial_variants', 'cursed_offer', 'free_packs', 'duel', 'mobile_duel',
                'reward_target', 'reward_targets'):
        nxt.pop(key, None)
    if not shop_pack_available(nxt,nxt.get('pinned_pack')):
        nxt['pinned_pack'] = None
    nxt['new_cards_from'] = len(nxt['pool'])
    opened = [dict(id=pid, cards=game.open_pack(pid, rng, nxt)) for pid in incoming]
    from content import fixed_deck
    for pack in opened:
        nxt['pool'].extend(pack['cards'])
        if fixed_deck(nxt):
            nxt.setdefault('act_pack_cards', []).extend(pack['cards'])
        register_pack(nxt, pack['id'])
    nxt['free_packs'] = opened
    game.routes(nxt, rng)
    nxt['shop_reward'] = nxt['route_rewards'][str(nxt['opponent'])]
    nxt['bias'] = nxt['shop_reward']['key']
    game.restock(nxt, rng, general_stock=True)
    run.clear()
    run.update(nxt)


def preview(game, run, opponent):
    record = game.run_opponent_record(run, opponent)
    main, extra = record['main'], record['extra']
    from content import EDISON_DUELISTS
    duelist = EDISON_DUELISTS.get(opponent)
    if duelist:
        examples = [game.BY_NAME[name]['id'] for name in [duelist['ace'],*duelist['enablers']]]
        return [cid for cid in examples if cid in main or cid in extra]
    interesting = sorted(dict.fromkeys(extra + main), key=lambda cid: (
        -(FIRST_ACT.get(cid, 0) == era(run)),
        -(cid in extra or bool(game.BY_ID[cid]['data']['type'] & 0x1000)),
        -game.BY_ID[cid]['level'],
    ))
    return interesting[:4]


def filter_deck(game, run, record, opponent):
    if not active(run):
        return record
    from content import CHARACTERS
    result = dict(record)
    raw = record['main']
    main = [cid for cid in raw if allows(run, cid)]
    extra = [cid for cid in record['extra'] if allows(run, cid)]
    if len(main) < len(raw):
        race = CHARACTERS[opponent].get('race')
        counts = Counter(game.card_identity(cid) for cid in main + extra)
        original = list(dict.fromkeys(main))
        themed = [c['id'] for c in game.CARDS if c.get('race') == race and allows(run, c['id']) and game.normal_starter(c['id'])]
        general = [c['id'] for c in game.CARDS if allows(run, c['id']) and game.normal_starter(c['id'])]
        strength = lambda cid: abs(game.BY_ID[cid]['atk'] - 1550)
        choices = sorted([cid for cid in original if game.normal_starter(cid)], key=strength)
        choices += sorted(themed, key=strength) + sorted(general, key=strength)
        for cid in choices:
            identity = game.card_identity(cid)
            while counts[identity] < 2 and len(main) < len(raw):
                main.append(cid)
                counts[identity] += 1
            if len(main) >= len(raw):
                break
    result.update(main=main, extra=extra, side=[cid for cid in record.get('side', []) if allows(run, cid)])
    return result
