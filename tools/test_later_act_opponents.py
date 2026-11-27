"""Seeded campaign checks using the same commands as the Android and web client."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, help='Sample a clean edison-v0.2.47 checkout for comparison.')
parser.add_argument('--output', type=Path, help='Write the prepared duels for the WASM matchup check.')
parser.add_argument('--browser-saves', type=Path, help='Write pending boundary rewards as browser save fixtures.')
parser.add_argument('--finale-output', type=Path, help='Write Act 3 final boss matches for a legal constructed deck.')
args = parser.parse_args()
root = args.baseline or Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root.resolve()), str((root / 'android').resolve())]
import campaign as game
import campaign_acts as acts
import content
import encounters
import mobile_backend
import storage


def command(action, value=None):
    mobile_backend.dispatch(json.dumps(dict(action=action, value=value)))
    return mobile_backend.run


def profile():
    result = storage.profile()
    result.update(relicless_unlocked=True, unlocked=content.PLAYABLE_IDS[:])
    storage.write(storage.ROOT / 'profile.json', result)


def enter_next_act(run):
    offer = deepcopy(run['act_transition'])
    assert command('select-slot', 1)['act_transition'] == offer
    return command('act-transition', dict(packs=[offer['choices'][0]] * offer['picks'], carry=[]))


def validate_deck(run, record):
    main, extra, side = (record[key] for key in ('main', 'extra', 'side'))
    assert len(main) == 40 and len(extra) <= 15 and len(side) <= 15
    assert all(acts.allows(run, cid) and not game.is_extra(cid) for cid in main)
    assert all(acts.allows(run, cid) and game.is_extra(cid) for cid in extra)
    assert all(acts.allows(run, cid) for cid in side)
    assert max(Counter(game.limit_identity(cid) for cid in main + extra + side).values()) <= 3
    assert any(acts.FIRST_ACT[cid] == run['act'] for cid in main + extra)


def sample_campaign(seed, character):
    random.seed(seed)
    run = command('new', dict(character=character, level=-1, slot=1, replace=True))
    if run['stage'] == 'starter':
        run = command('act-starter', next(iter(run['starter_offer'])))
    rows = []
    for act in (1, 2, 3):
        defeated = set()
        assert run['act'] == act and run['character'] == character
        for round_index in range(9):
            assert run['round'] == round_index
            routes = list(run['routes'])
            planned = deepcopy(run.get('next_boss'))
            assert not set(routes) & (defeated | {character})
            if planned:
                if (round_index + 1) % 3 == 0:
                    assert routes == [planned['opponent']]
                else:
                    assert planned['opponent'] not in routes
            if not args.baseline and act > 1:
                assert run['later_opponent_act'] == act
                assert set(routes) <= set(acts.encounter_opponents(run, content.deck_round(run)))
                for opponent in routes:
                    record = game.run_opponent_record(run, opponent)
                    validate_deck(run, record)
                    shown = run['route_examples'][str(opponent)]
                    assert shown and set(shown) <= set(record['main'] + record['extra'])
                run = command('select-slot', 1)
                assert run['routes'] == routes and run['next_boss'] == planned
            command('auto')
            opponent = routes[0]
            command('choose', opponent)
            run = command('begin')
            duel = deepcopy(run['mobile_duel'])
            expected_lp = acts.LATER_OPPONENTS[act]['lp'][round_index] if not args.baseline and act > 1 else encounters.LP[round_index]
            assert duel['enemyLP'] == expected_lp
            rows.append(dict(run_seed=seed, act=act, encounter=round_index+1, opponent=opponent,
                             name=content.CHARACTERS[opponent]['name'], **duel))
            defeated.add(opponent)
            run = command('finish', dict(winner=0, lp=8000, events=[]))
            if round_index in (0, 8):
                assert run['reward_slots']['pending']
                run = command('select-slot', 1)
                assert run['reward_slots']['pending'] and run['round'] == round_index+1
                assert run['timeline'][-1]['act'] == act
            if args.browser_saves and seed == 0 and round_index == 8 and act < 3:
                files = {p.name: p.read_text(encoding='utf-8') for p in storage.ROOT.glob('*.json')}
                args.browser_saves.mkdir(parents=True, exist_ok=True)
                (args.browser_saves / f'act-{act}-boundary.json').write_text(json.dumps(files), encoding='utf-8')
            run = command('reward-accept')
        if act < 3:
            run = enter_next_act(run)
            assert run['round'] == 0 and len(run['timeline']) == act*9
    assert run['stage'] == 'complete' and len(run['timeline']) == 27
    return rows


def resume_legacy_stretch():
    # Generate a pre-patch-form save with an announced opponent and planned boss.
    random.seed(451)
    with patch.object(acts, 'later_opponents', return_value=None):
        run = command('new', dict(character=37, level=-1, slot=1, replace=True))
        run.update(round=9, stage='act_transition', act_transition=acts.transition_offer(run, random))
        game.save(run)
        run = enter_next_act(run)
    planned, routes, pool = deepcopy(run['next_boss']), list(run['routes']), list(run['pool'])
    run = command('select-slot', 1)
    assert run['routes'] == routes and run['next_boss'] == planned and run['pool'] == pool
    for rd in range(3):
        command('choose', run['routes'][0])
        run = command('begin')
        assert run['mobile_duel']['enemyLP'] == encounters.LP[rd]
        if rd == 0:
            initialized = deepcopy(run['mobile_duel'])
            run = command('select-slot', 1)
            assert run['mobile_duel'] == initialized and run['stage'] == 'duel'
        if rd == 2:
            assert run['opponent'] == planned['opponent']
        command('finish', dict(winner=0, lp=8000, events=[]))
        run = command('reward-accept')
    assert run['round'] == 3 and run['later_opponent_act'] == 2
    assert acts.opponent_lp(run) == 7500


with tempfile.TemporaryDirectory() as folder, patch.object(storage, 'ROOT', Path(folder)), patch.object(game, 'RUNTIME', Path(folder) / 'runtime'):
    game.RUNTIME.mkdir()
    profile()
    rows = [row for seed, character in [(0, 0), (113, 98), (901, 106)] for row in sample_campaign(seed, character)]
    if not args.baseline:
        for act, rules in acts.LATER_OPPONENTS.items():
            run = dict(act=act, later_opponent_act=act, round=0, character=0)
            roster = acts.encounter_opponents(run, 1)
            assert len(set(roster)) == len(roster) == 12
            for opponent in roster:
                validate_deck(run, game.run_opponent_record(run, opponent))
            print(f'Act {act} roster: ' + ', '.join(content.CHARACTERS[i]['name'] for i in roster))
        resume_legacy_stretch()
        print('PASS all 24 decks legal by Act, zone, and shared copy identity; 3 seeded runs, reloads, and in-flight legacy stretch')

if args.output:
    args.output.write_text(json.dumps(rows), encoding='utf-8')
if args.finale_output:
    # A known legal, focused deck isolates the boss's duel from the quality of the auto-built draft.
    blackwings = content.EDISON_DECKS[110]
    validate_deck({'act': 3}, blackwings)
    fixtures = []
    for row in rows:
        if (row['act'], row['encounter']) != (3, 9):
            continue
        for seed in (13, 33, 71, 91):
            rng = random.Random(seed)
            main, enemy = list(blackwings['main']), list(row['enemy'])
            rng.shuffle(main)
            rng.shuffle(enemy)
            fixtures.append(dict(row, deck=main, enemy=enemy, extra=blackwings['extra'], seed=seed))
    args.finale_output.write_text(json.dumps(fixtures), encoding='utf-8')
for act in (1, 2, 3):
    rounds = [r for r in rows if r['act'] == act]
    first_run = [r for r in rounds if r['run_seed'] == 0]
    print(f'Act {act} seed 0: ' + ' | '.join(f"{r['name']} ({r['enemyLP']:,})" for r in first_run))
    print(f"  27 duels, {len({r['opponent'] for r in rounds})} distinct opponents, "
          f"mean main deck {sum(len(r['enemy']) for r in rounds)/len(rounds):.1f}, "
          f"mean LP {sum(r['enemyLP'] for r in rounds)/len(rounds):,.0f}")
