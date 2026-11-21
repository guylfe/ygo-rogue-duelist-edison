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
        return 1
    if pack.get('region') != 'EN' or not pid.startswith('EN-'):
        return None
    return next((i for i, act in enumerate(ACTS, 1) if pack['date'] <= act['cutoff']), None)


def edition(run, pack):
    """Project every slot and rarity of a pack into the current act."""
    if not active(run):
        return pack
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


def rotation(run, draft_relic=False):
    from content import PACKS
    if not active(run):
        return [p['id'] for p in PACKS]
    act = era(run)
    # Draft packs are available through their signature start or the dedicated relic.
    themed = [p['id'] for p in PACKS if p.get('draft_only') and openable(p['id'], act)] if draft_relic else []
    return list(dict.fromkeys(native_packs(act) + run.get('carried_packs', []) + themed))


def register_pack(run, pid):
    if active(run) and pid not in run.setdefault('opened_packs', []):
        run['opened_packs'].append(pid)


def pin_options(run):
    from content import PACK_BY_ID
    if not active(run):
        return []
    eligible = set(rotation(run))
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
    fallback = native_packs(1, starters=True)
    core = [pid if pid in PACK_BY_ID and openable(pid, 1) else rng.choice(fallback) for pid in preferred[:3]]
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
    incoming = era(run) + 1
    packs = native_packs(incoming)
    # Rotate the preview once at the boundary. Persist it so returning to the
    # run never rerolls the choices or awards cards twice.
    offered = list(dict.fromkeys(run.get('offered_packs', []) + (run.get('pack_ids', []) if era(run) == 1 else [])))
    from content import PACK_BY_ID
    carryable = [pid for pid in offered if pid in PACK_BY_ID and openable(pid, incoming)]
    anchor = {2: 'EN-LODT', 3: 'EN-TDGS'}[incoming]
    choices = [anchor] if anchor in packs else []
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
    if nxt.get('pinned_pack') not in rotation(nxt):
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
