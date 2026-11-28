"""Exercise Act-scoped awards and save upgrades through the shared mobile commands."""
import argparse
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
import character_progression as progression
import content
import mobile_backend as mobile
import storage


def command(action, value=None):
    return json.loads(mobile.dispatch(json.dumps(dict(action=action, value=value))))


def save_browser_fixture(directory, name):
    if directory:
        directory.mkdir(parents=True, exist_ok=True)
        files = {p.name: p.read_text(encoding='utf8') for p in storage.ROOT.glob('*.json')}
        (directory / (name + '.json')).write_text(json.dumps(files), encoding='utf8')


def test_migration(directory):
    old = dict(unlocked=[0, 1, 2, *content.EDISON_DUELISTS], victories=100, wins=50,
               won_as=[1, 101], character_levels={'102': 0}, character_last_levels={'104': 0},
               run_history=[dict(character=103)], synced_achievements=['character:110'])
    storage.write(storage.ROOT / 'profile.json', old)
    preload = dict(storage.profile(), unlocked=old['unlocked'])
    with patch.object(storage, 'profile', return_value=preload):
        active = game.new_run(108, random.Random(123), act_campaign=True)
    storage.write(storage.run_path(2), active)
    data = command('init')
    assert set(data['profile']['unlocked']) == progression.STARTERS | {2, 101, 102, 103, 108, 110}
    saved = storage.run_path(2).read_bytes()
    resumed = command('select-slot', 2)['run']
    assert resumed['character'] == 108 and storage.run_path(2).read_bytes() == saved
    assert command('init')['profile']['run_history'] == old['run_history']
    save_browser_fixture(directory, 'legacy-profile')
    for row in data['achievements']:
        if row['id'] in ('character:2', 'character:108'):
            assert row['unlocked'] and not row['done'] and row['value'] == 0
    assert 'campaign_unlock_progress' not in data['profile']


def test_campaign(directory):
    random.seed(0)
    data = command('init')
    assert data['profile']['unlocked'] == sorted(progression.STARTERS)
    for i in sorted(progression.STARTERS):
        assert command('new', dict(character=i, replace=True))['run']['character'] == i
    for i in (2, *sorted(progression.LATER_UNLOCKS)):
        try:
            command('new', dict(character=i, replace=True))
        except ValueError as error:
            assert 'locked' in str(error)
        else:
            raise AssertionError(f'Locked character {i} started a campaign')

    random.seed(0)
    run = command('new', dict(character=0, replace=True))['run']
    run = command('act-starter', run['starter_offer_order'][0])['run']
    fusion = game.BY_NAME['Elemental HERO Flame Wingman']['id']
    synchro = game.BY_NAME['Stardust Dragon']['id']
    events = [dict(kind='summon', card=fusion), dict(kind='summon', card=synchro),
              dict(kind='sleeve_metrics', diceRolled=10, coinsTossed=10)]
    bought, variants, opponents = {}, {}, {}
    for act in (1, 2, 3):
        bought[act] = 0
        variants[act] = []
        opponents[act] = set()
        for rd in range(9):
            assert run['round'] == rd and run['act'] == act
            if act > 1 and run['stage'] == 'shop' and bought[act] < 6:
                coins = run['gold']
                cart = []
                for index, item in enumerate(run['shop']):
                    if item['kind'] == 'single' and not item['sold'] and item['price'] <= coins:
                        coins -= item['price']
                        cart.append(index)
                    if len(cart) == 6 - bought[act]:
                        break
                if cart:
                    run = command('buy-many', cart)['run']
                    bought[act] += len(cart)

            command('auto')
            opponent = 18 if 18 in run['routes'] else run['routes'][0]
            opponents[act].add(opponent)
            if act > 1 and opponent == 18:
                run = command('choose', opponent)['run']
                save_browser_fixture(directory, f'act-{act}-mako')
            else:
                command('choose', opponent)
            run = command('begin')['run']
            expected_variant = act if opponent in acts.LATER_OPPONENTS.get(act, {}).get('returning', {}) else None
            assert run['duel'].get('opponent_variant_act') == expected_variant
            if expected_variant:
                variants[act].append(opponent)
                if opponent == 18:
                    saved = deepcopy(mobile.run)
                    saved['duel'].pop('opponent_variant_act')
                    game.save(saved)
                    restored = command('select-slot', 1)['run']
                    assert restored['duel']['opponent_variant_act'] == act
                    assert restored['mobile_duel'] == run['mobile_duel']
                    save_browser_fixture(directory, f'act-{act}-mako-resume')
            # Staged duel telemetry tests attribution through the real result handler.
            result = dict(winner=0, lp=8000, events=events if rd == 0 else [])
            data = command('finish', result)
            run = data['run']
            assert run['timeline'][-1]['opponent'] == opponent
            assert run['timeline'][-1].get('opponent_variant_act') == expected_variant
            unlocked = set(data['profile']['unlocked'])
            if act < 2:
                assert not progression.LATER_UNLOCKS & unlocked
            if act < 3:
                assert not set(range(108, 112)) & unlocked
            if act == 2:
                assert 100 in unlocked
                assert (101 in unlocked) == (rd >= 2)
                assert (103 in unlocked) == (rd >= 5)
                assert (104 in unlocked) == (rd == 8)
            if act == 3:
                assert 108 in unlocked
                assert (110 in unlocked) == (rd >= 5)
                assert (111 in unlocked) == (rd == 8)
            assert (2 in unlocked) == (act > 1 or rd == 8)
            assert 19 in unlocked
            assert 37 not in unlocked  # World Champion remains its own special unlock.
            if rd == 8:
                save_browser_fixture(directory, f'act-{act}-receipt')
            run = command('reward-accept')['run']
            while run.get('cursed_offer'):
                offer = run['cursed_offer']
                run = command('cursed-skip' if offer.get('picked') else 'cursed-choose',
                              offer['options'][0])['run']
        if act < 3:
            before = storage.profile()['campaign_unlock_progress']
            offer = run['act_transition']
            run = command('act-transition', dict(packs=[offer['choices'][0]] * offer['picks'], carry=[]))['run']
            assert run['round'] == 0 and run['act'] == act + 1
            assert storage.profile()['campaign_unlock_progress'] == before

    unlocked = set(storage.profile()['unlocked'])
    assert set(range(100, 106)) | set(range(108, 112)) <= unlocked
    assert bought[2] == bought[3] == 6
    assert set(range(100, 106)) & opponents[2]
    assert set(range(108, 112)) & opponents[3]
    history = command('init')['history'][0]['timeline']
    assert len(history) == 27
    if not set(range(112, 135)) & set(content.PLAYABLE_IDS):
        # These seeded routes generate the browser fixtures for the released roster.
        assert {18} <= set(variants[2]) & set(variants[3])
        assert {row['opponent_variant_act'] for row in history if row['opponent'] == 18 and row.get('opponent_variant_act')} == {2, 3}


def test_no_crossover():
    p = storage.profile()
    run = dict(act=2, character=0, round=9, stage='act_transition', gold=1000, artifacts=['dragon'],
               character_challenges=['singleton_win'], duel={'id': 'act-two-won'}, started_at=123, last_gold=350)
    game.update_profile(run, True, ({'singleton_win', 'synchro_win'}, True, 15, 15))
    game.update_profile(run, True, ({'singleton_win', 'synchro_win'}, True, 15, 15))
    p = storage.profile()
    assert p['campaign_unlock_progress']['2']['victories'] == 1
    assert p['campaign_unlock_progress']['2']['duel_coins'] == 350
    assert p['campaign_unlock_progress']['2']['boss_wins'] == 1
    assert {102, 104} <= set(p['unlocked'])
    assert not {2, 19, 24, 28, 108} & set(p['unlocked'])
    run.update(act=3, round=0, stage='shop')
    game.update_profile(run)
    assert not {2, 19, 24, 28, 108} & set(storage.profile()['unlocked'])
    run.update(act=3, stage='gameover', duel={'id': 'act-three-lost'})
    game.update_profile(run, False, (set(), False, 0, 0))
    assert progression.value(storage.profile(), 108) == 0


def test_reserved_roster():
    gx = ['Bastion Misawa', 'Axel Brodie', 'Syrus Truesdale', 'Tyranno Hassleberry', 'Camula', 'Amnael',
          'Adrian Gecko', 'Professor Viper', 'Titan', 'Don Zaloog', 'Tania', 'Nightshroud']
    five_ds = ['Luna', 'Tetsu Trudge', 'Greiger', 'Misty Tredwell', 'Carly Carmine', 'Roman Goodwin',
               'Devack', 'Sayer', 'Rex Goodwin', 'Lazar', 'Hunter Pace']
    assert len(gx) == 12 and len(five_ds) == 11
    rows = [dict(content.CHARACTERS[0], name=name, home_act=act)
            for act, names in ((2, gx), (3, five_ds)) for name in names]
    reserved = list(range(112, 135))
    for i, row in zip(reserved, rows):
        if i in content.EDISON_DUELISTS:
            actual = content.EDISON_DUELISTS[i]
            assert (actual['name'], actual['home_act']) == (row['name'], row['home_act'])
    base_chars = content.CHARACTERS[:112]
    base_ids = [i for i in content.PLAYABLE_IDS if i < 112]
    card = lambda name: game.BY_NAME[name]['id']
    deck = {}
    for entry in game.CARDS:
        if entry['data']['type'] & 1 and not game.is_extra(entry['id']) and acts.allows({'act':2},entry['id']):
            deck.setdefault(entry['attribute'], entry['id'])
    ids = list(dict.fromkeys([*deck.values(), *(c['id'] for c in game.CARDS if not game.is_extra(c['id']))]))[:40]
    assert len(ids) == len({game.limit_identity(cid) for cid in ids}) == 40
    events = [dict(kind='summon', card=card('Blue-Eyes White Dragon'), method='special')] * 3
    events += [dict(kind='summon', card=card('Dark Magician'), method='normal')] * 3
    events += [dict(kind='activate', card=card('Axe of Despair'))] * 2
    events += [dict(kind='activate', card=card('Mirror Force'))] * 2
    events += [dict(kind='activate', card=card('Sangan'))] * 3
    events += [dict(kind='battle_destroy')] * 3 + [dict(kind='attack')] * 4
    events += [dict(kind='effect_damage', amount=1500), dict(kind='damage', amount=7000),
               dict(kind='recover', amount=1500),
               dict(kind='sleeve_metrics', diceRolled=4,coinsTossed=4,graveSpecials=1)]

    with patch.object(content, 'CHARACTERS', base_chars+rows), patch.object(game, 'CHARACTERS', base_chars+rows), \
         patch('achievement_model.CHARACTERS', base_chars+rows), patch('achievement_model.PLAYABLE_IDS', base_ids+reserved), \
         patch.object(game, 'deck', return_value=ids), patch('campaign_expansion.PLAYABLE_IDS', base_ids+reserved):
        assert not set(reserved) & set(storage.profile()['unlocked'])
        for act in (1, 2, 3):
            for n in range(1 if act < 3 else 5):
                run = dict(act=act,character=0,stage='shop',round=2,gold=40,lp=3000,artifacts=[],
                           challenge_level=1,started_at=100+n,duel={'id': f'{act}-{n}'},opponent=18)
                result = dict(lp=3000,events=events+[dict(kind='duel_metrics',turns=12 if act==2 else 9,banished_count=5)])
                if act==3 and n==0:
                    lost=progression.duel(game,run,result,False,True)
                    game.update_profile(run,False,lost)
                    assert not set(range(124,135)) & set(storage.profile()['unlocked'])
                    run['duel']['id'] += '-win'
                observed=progression.duel(game,run,result,True,True)
                run.update(round=9,stage='complete' if act==3 else 'act_transition')
                game.update_profile(run,True,observed)
            p=storage.profile()
            assert set(reserved) & set(p['unlocked']) == {i for i in reserved if progression.rule(i)[0] <= act}
        records={row['id']:row for row in mobile.achievement_model.entries(storage.profile())}
        assert all(records[f'character:{i}']['name']==row['name'] and records[f'character:{i}']['done']
                   for row,i in zip(rows,reserved))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--browser-saves', type=Path)
args = parser.parse_args()
for test in (lambda: test_migration(args.browser_saves), lambda: test_campaign(args.browser_saves),
             test_no_crossover, test_reserved_roster):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with patch.object(storage, 'ROOT', root / 'saves'), patch.object(game, 'RUNTIME', root / 'runtime'):
            game.RUNTIME.mkdir()
            mobile.run = None
            test()
print('PASS six fresh starters, legacy evidence, all ten live later unlocks, 23 integration rules, Act boundaries, and returning decks')
