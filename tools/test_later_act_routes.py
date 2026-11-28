"""Exercise the later-act guest limit through the shared Android/web commands."""
from copy import deepcopy
import json
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'android')]
import boss_preview
import campaign as game
import campaign_acts as acts
import content
import mobile_backend
import storage


def command(action, value=None):
    mobile_backend.dispatch(json.dumps(dict(action=action, value=value)))
    return mobile_backend.run


def enter_next_act(run):
    offer = run['act_transition']
    return command('act-transition', dict(packs=[offer['choices'][0]] * offer['picks'], carry=[]))


def start_gx(character, cards_only):
    run = command('new', dict(character=character, level=0, slot=1, replace=True, cards_only=cards_only))
    run = command('act-starter', next(iter(run['starter_offer'])))
    run.update(round=9, stage='act_transition', act_transition=acts.transition_offer(run, random))
    return enter_next_act(run)


def begin(rival):
    command('auto')
    command('choose', rival)
    return command('begin')


def win():
    command('finish', dict(winner=0, lp=8000, events=[]))
    run = command('reward-accept')
    while run.get('cursed_offer'):
        run = command('cursed-choose', run['cursed_offer']['options'][0])
    return run


def verify_later_acts(seed, character, cards_only):
    random.seed(seed)
    run = start_gx(character, cards_only)
    assert bool(run.get('cards_only')) == cards_only and run['challenge_level'] == 0
    if cards_only:
        assert not run['artifacts']
    guest_wins = []
    for act in (2, 3):
        rules = acts.LATER_OPPONENTS[act]
        home = set(rules['home'])
        guests = set(rules.get('route_guests', rules['returning']))
        if act == 3:
            assert guests == {9, 18, 98}
        assert run['later_route_act'] == act
        fought = set()
        for rd in range(9):
            assert run['round'] == rd and set(run['defeated_opponents']) == fought
            plan = deepcopy(run['next_boss'])
            if rd in (5, 8):
                run = command('boss-reroll')
                assert run['next_boss']['opponent'] != plan['opponent']
                plan = deepcopy(run['next_boss'])
            routes = list(run['routes'])
            assert not set(routes) & (fought | {character})
            is_boss = rd % 3 == 2
            guest_budget = 2 - len(fought & guests)
            held_guest = not is_boss and plan['opponent'] in guests
            allowed = home if rd in (0, 8) or guest_budget <= int(held_guest) else home | guests
            available = allowed - fought - {character}
            if not is_boss:
                available.discard(plan['opponent'])
            assert len(routes) == min(1 if is_boss else 5, len(available))
            assert set(routes) <= available
            if is_boss:
                assert routes == [plan['opponent']]
            # Reload every offer. Select a guest whenever possible to stress the cap.
            run = command('select-slot', 1)
            assert run['routes'] == routes and run['next_boss'] == plan
            rival = next((i for i in routes if i in guests), routes[-1])
            run = begin(rival)
            game.save(run)
            assert command('select-slot', 1)['duel']['opponent'] == rival
            fought.add(rival)
            run = win()
        assert len(fought & guests) <= 2
        guest_wins.append(len(fought & guests))
        if act == 2:
            run = enter_next_act(run)
    assert run['stage'] == 'complete' and len(run['timeline']) == 18
    run = command('champion')
    assert run['encore_active'] and not acts.route_limited(run)
    run = begin(run['opponent'])
    run = win()
    assert run['encore_won'] and run['stage'] == 'complete'
    run = command('next-loop')
    assert run['loop'] == 1 and not acts.route_limited(run)
    assert not acts.route_limited(command('select-slot', 1))
    return guest_wins


def verify_preview_reservation(character):
    # Only one guest slot remains. Holding it for a boss must not make that
    # boss unselectable, nor consume it for another act or a special mode.
    run = dict(act=2, later_route_act=2, later_opponent_act=2, round=3, character=character,
               defeated_opponents=[1, 99, 100], next_boss=dict(round=5, loop=0, opponent=3))
    assert boss_preview.planned(run)['opponent'] == 3
    assert set(acts.encounter_opponents(run, content.deck_round(run), reserved=(3,))) == set(acts.LATER_OPPONENTS[2]['home'])
    assert not acts.route_limited(dict(run, loop=1))
    assert not acts.route_limited(dict(run, history_mode='tag'))
    assert not acts.route_limited(dict(run, secret_challenge=True))


with tempfile.TemporaryDirectory() as folder, patch.object(storage, 'ROOT', Path(folder)), patch.object(game, 'RUNTIME', Path(folder) / 'runtime'):
    game.RUNTIME.mkdir()
    profile = storage.profile()
    profile.update(unlocked=content.PLAYABLE_IDS[:])
    storage.write(storage.ROOT / 'profile.json', profile)

    # Build a legacy offer under the original native roster sizes, then reload
    # it after restoring the expanded production rosters.
    legacy_rules = {act: dict(rules, home=[i for i in rules['home'] if i < 112])
                    for act, rules in acts.LATER_OPPONENTS.items()}
    with patch.dict(acts.LATER_OPPONENTS, legacy_rules):
        random.seed(421)
        legacy = start_gx(98, False)
        assert not acts.route_limited(legacy)
        for _ in range(7):
            begin(legacy['routes'][0])
            legacy = win()
        assert 0 < len(legacy['routes']) < 5
        fields = {key: deepcopy(legacy[key]) for key in ('next_boss', 'routes', 'opponent', 'pool', 'route_rewards')}

    loaded = command('select-slot', 1)
    assert all(loaded[key] == value for key, value in fields.items())
    assert not acts.route_limited(loaded)
    verify_preview_reservation(98)
    for cards_only in (False, True):
        samples = [verify_later_acts(seed, character, cards_only)
                   for seed, character in ((11, 98), (77, 106), (302, 98), (881, 106))]
        assert all(any(row[index] == 2 for row in samples) for index in (0, 1)), samples
        print(f'PASS {"Singles & packs" if cards_only else "Standard"}: guest wins by act {samples}')
    print('PASS later-act openers and finales, rerolls, reloads, reserved guest boss, legacy offers, and loop/Tag/secret behavior')
