"""Edison card availability, Rogue Duelist deck rules and campaign opponent wiring."""
from collections import Counter
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import campaign as game
import content
from pack_odds import inspect_pack

cards = json.loads((ROOT / 'data/edison-cards.json').read_text(encoding='utf8'))
packs = json.loads((ROOT / 'data/edison-packs.json').read_text(encoding='utf8'))
assert len({card['id'] for card in cards}) == len(cards)
assert len({card['name'].casefold() for card in cards}) == len(cards)
assert all(card['date'] <= '2010-04-20' and card['sets'] for card in cards)
assert 'Trishula, Dragon of the Ice Barrier' not in game.BY_NAME
assert 'Infernity Launcher' not in game.BY_NAME

kaiba = content.PACK_BY_ID['EN-DPKB']
assert kaiba['date'] == '2010-04-20'
assert Counter(r for rs in kaiba['rarities'].values() for r in rs) == {
    'Common':19, 'Rare':8, 'Super Rare':5, 'Ultra Rare':3, 'Ultimate Rare':5,
}
assert game.BY_NAME['Malefic Blue-Eyes White Dragon']['id'] in kaiba['rare']
assert game.BY_NAME['The White Stone of Legend']['id'] in kaiba['rare']

obtainable = set()
with patch('storage.profile', return_value={}):
    for pack in packs:
        pid = pack['id']
        assert (ROOT / 'assets/packs' / (pid + '.jpg')).is_file(), pid
        pulls = game.open_pack(pid, random.Random(20100420))
        assert len({game.card_identity(cid) for cid in pulls}) == 9, pid
        obtainable.update(row['id'] for row in inspect_pack(pid, {}) if row['chance'] > 0)
assert {c['id'] for c in cards} <= obtainable
print(f'PASS {len(cards)} distinct dated TCG additions, all with positive pull odds across {len(packs)} boosters')

synchro = game.BY_NAME['Armory Arm']['id']
tuner = game.BY_NAME['The White Stone of Legend']['id']
main = [c['id'] for c in game.CARDS if game.normal_starter(c['id']) and not game.is_extra(c['id'])][:20]
assert game.is_extra(synchro) and not game.normal_starter(synchro)
assert not game.is_extra(tuner)
run = dict(character=0, round=0, artifacts=[], pool=[*main,tuner,synchro], selected=list(range(21)))
assert game.validate(run) is None
run['selected'] = list(range(19)) + [21]
assert '20 to 60' in game.validate(run), 'a Synchro cannot satisfy the Main Deck minimum'
run['pool'] = main + [c['id'] for c in cards if game.is_extra(c['id'])][:16]
run['selected'] = list(range(36))
assert 'at most 15' in game.validate(run), 'Extra Deck retains its cap'

for index, round_number in ((1,6),(9,3)):
    record = content.opponent_record(round_number,index)
    assert record['deck'].endswith('-edison')
    assert index in content.eligible_opponents(round_number)
    assert any(game.BY_ID[c]['data']['type'] & 0x1000 for c in record['main'])
    assert all(game.is_extra(c) for c in record['extra'])
    assert any(game.BY_ID[c]['data']['type'] & 0x2000 for c in record['extra'])
print('PASS Rogue Duelist deck minimum and Extra Deck cap; real campaign records contain Tuners and Synchros')
