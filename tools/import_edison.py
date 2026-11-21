"""Compile the fork's April 2010 card and pack additions from dated TCG product rows.

Usage: python tools/import_edison.py KONAMI_PRODUCTS_JSON YGOJSON_AGGREGATE_ZIP
Product rows have pid, name, date, category, url and [Konami card ID, name, rarity] entries.
The input is the English Konami Neuron product index and checklists. YGOJSON crosswalks
Konami card/product IDs to passcodes and booster codes. The bundled Project Ignis CDB,
engine data and scripts supply gameplay data.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sqlite3
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2010-04-20'
PREVIOUS_CUTOFF = '2005-05-29'
PACK_CATEGORIES = {'Booster Packs', 'Duelist Packs'}
PACK_CODE_OVERRIDES = {
    '11106002': 'PP01', '11107003': 'PP02', '11106005': 'DR04',
    '11107007': 'YAP1', '16601000': 'DP1', '16601001': 'DP2',
    '11104004': 'CRV', '11104006': 'EEN', '11107001': 'LODT',
}
# Konami files the JUMP issue under its cover month and lists the prize in a later reprint.
# The playable SJCS printing predates that reprint.
DARK_END = dict(pid='sjcs-en007', date='2009-04-26', name='Shonen Jump Championship prize',
                url='https://yugiohblog.konami.com/2010/sjc/sjc-history-the-dark-end-dragon-age-2009-2010/',
                category='Tournaments', cards=[[88643579, 'Dark End Dragon', 'Ultra Rare']])
MONTHS = {name: i for i, name in enumerate(
    'January February March April May June July August September October November December'.split(), 1)}
WORLD_MATCH_WINNERS = {5925, 5929, 6533, 6534, 6958, 6959, 7374, 7375, 7992, 7993, 8610, 8611}
RACE = ['Warrior', 'Spellcaster', 'Fairy', 'Fiend', 'Zombie', 'Machine', 'Aqua', 'Pyro', 'Rock',
        'Winged Beast', 'Plant', 'Insect', 'Thunder', 'Dragon', 'Beast', 'Beast-Warrior',
        'Dinosaur', 'Fish', 'Sea Serpent', 'Reptile', 'Psychic', 'Divine-Beast']
ATTRIBUTES = ['EARTH', 'WATER', 'FIRE', 'WIND', 'LIGHT', 'DARK', 'DIVINE']
SPELL_TRAP = {0x80: 'Ritual', 0x10000: 'Quick-Play', 0x20000: 'Continuous', 0x40000: 'Equip',
              0x80000: 'Field', 0x100000: 'Counter'}


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(name, rows):
    # One record per line makes catalogue edits and comparisons reviewable.
    text = '[\n' + ',\n'.join('  ' + json.dumps(row, ensure_ascii=False) for row in rows) + '\n]\n'
    (ROOT / 'data' / name).write_text(text, encoding='utf8')


def product_date(product):
    date = product['date']
    if date != '1990-01-01':
        return date
    issue = re.search(r' - (\w+) (\d{4}) -$', product['name'])
    return f'{issue[2]}-{MONTHS[issue[1]]:02}-01' if issue else None


def set_index(ygojson):
    by_pid = {}
    for row in json.load(ygojson.open('sets.json')):
        if not row.get('name', {}).get('en'):
            continue
        locales = row.get('locales', {})
        for key in ('en', 'na', 'eu', 'oc'):
            locale = locales.get(key, {})
            for pid in locale.get('externalIDs', {}).get('dbIDs', []):
                by_pid.setdefault(str(pid), (row['name']['en'], locale.get('prefix'), locale.get('image')))
    # Konami's newer archive ID shares the TCG product identity with the original checklist.
    if '161601230' in by_pid:
        by_pid['11107001'] = by_pid['161601230']
    return by_pid


def make_pack(code, name, date, prints, source, art=None, shop_only=False):
    rarities = {str(cid): list(dict.fromkeys(r for r in values)) for cid, values in prints.items()}
    common = [cid for cid in prints if all(r in ('Common', 'Short Print') for r in rarities[str(cid)])]
    rare = [cid for cid in prints if cid not in common]
    row = dict(id=f'EN-{code}', name=name, region='EN', code=code, date=date, image=art or '',
               common=common, rare=rare, size=9, rarities=rarities, rare_display=rare,
               rarity_source=source)
    if shop_only:
        row['shop_only'] = True
    return row


def compile_catalog(products, source_zip):
    base = load(ROOT / 'data/era-cards.json')
    old_packs = load(ROOT / 'data/packs.json')
    existing_packs = {row['id'] for row in old_packs}
    engine_cards = load(ROOT / 'android/web/engine-data.json')
    base_names = {row['name'].casefold(): row['id'] for row in base}
    base_ids = {row['id'] for row in base}
    with ZipFile(source_zip) as ygojson:
        crosswalk = {
            c['externalIDs']['dbID']: c for c in json.load(ygojson.open('cards.json'))
            if c.get('externalIDs', {}).get('dbID')
        }
        set_metadata = set_index(ygojson)
    releases = defaultdict(list)
    packs = []
    selected_cards = {}
    for product in sorted([*products, DARK_END], key=lambda row: (product_date(row) or '9999', row['pid'])):
        date = product_date(product)
        # Duel Terminal previews are not retail TCG availability for this historical cutoff.
        if not date or date > CUTOFF or product['category'] == 'Duel Terminal Cards':
            continue
        prints = defaultdict(list)
        for konami_id, name, rarity in product['cards']:
            if konami_id in WORLD_MATCH_WINNERS:
                continue
            name = name.split(' (Updated from:', 1)[0]
            found = crosswalk.get(konami_id, {})
            ids = found.get('externalIDs', {})
            options = [ids.get('ygoprodeck', {}).get('id'), ids.get('yamlyugiID'), *found.get('passwords', [])]
            if product is DARK_END:
                options = [88643579]
            code = base_names.get(name.casefold()) or next(
                (int(cid) for cid in options if cid and str(cid).isdigit() and str(int(cid)) in engine_cards),
                None,
            )
            if code is None:
                raise ValueError(f'No supported passcode for {name} ({konami_id}) in {product["name"]}')
            # These are alternate artworks of the same card. Use the supported main script ID.
            code = {4376659: 4376658, 31764354: 31764353}.get(code, code)
            prints[code].append(rarity)
            releases[code].append(dict(name=product['name'], rarity=rarity, date=date, source=product['url']))
            selected_cards.setdefault(code, (name, found))
        if product['category'] not in PACK_CATEGORIES or date <= PREVIOUS_CUTOFF or len(prints) < 9:
            continue
        pack_name, prefix, art = set_metadata.get(product['pid'], (product['name'].title(), None, None))
        code = PACK_CODE_OVERRIDES.get(product['pid']) or (prefix or '').split('-')[0]
        if not code:
            continue  # cards from these checklists remain in the joint reward booster
        if f'EN-{code}' in existing_packs:
            continue
        existing_packs.add(f'EN-{code}')
        has_starter = any(
            1 <= engine_cards[str(cid)]['level'] <= 4
            and bool(engine_cards[str(cid)]['type'] & 1)
            and not engine_cards[str(cid)]['type'] & (0x40 | 0x80 | 0x2000 | 0x2000000)
            for cid in prints
        )
        packs.append(make_pack(code, pack_name, date, prints, product['url'], art, shop_only=not has_starter))

    new_cards = []
    with sqlite3.connect(ROOT / 'runtime/expansions/cards.cdb') as db:
        for code, (name, found) in sorted(selected_cards.items()):
            if code in base_ids:
                continue
            data = engine_cards[str(code)]
            row = db.execute('SELECT * FROM texts WHERE id=?', (code,)).fetchone()
            if row is None:
                raise ValueError(f'Missing CDB text and prompts for {name} ({code})')
            _, _, description, *strings = row
            description = description.replace('\r\n', '\n').split('\n\n* The above text', 1)[0].strip()
            t = data['type']
            attribute = ''
            if t & 1:
                race = RACE[int(data['race']).bit_length() - 1]
                attribute = ATTRIBUTES[data['attribute'].bit_length() - 1]
                kind = next(label for mask, label in (
                    (0x2000, 'Synchro Monster'), (0x40, 'Fusion Monster'), (0x80, 'Ritual Monster'),
                    (0x1000, 'Tuner Monster'), (0x20, 'Effect Monster'), (1, 'Normal Monster')) if t & mask)
            else:
                kind = 'Spell Card' if t & 2 else 'Trap Card'
                race = next((label for mask, label in SPELL_TRAP.items() if t & mask), 'Normal')
            new_cards.append(dict(id=code, name=name, desc=description, type=kind, race=race,
                                  attribute=attribute, level=data['level'], atk=data['attack'],
                                  defense=data['defense'], date=releases[code][0]['date'],
                                  sets=releases[code], image=f'https://images.ygoprodeck.com/images/cards/{code}.jpg',
                                  data=data, strings=strings))
    covered = {cid for row in packs for cid in row['common'] + row['rare']}
    uncovered = {
        row['id']: [releases[row['id']][0]['rarity']]
        for row in new_cards if row['id'] not in covered
    }
    # This in-game booster collects promos, tin inserts, structure-deck cards and other
    # dated TCG printings that have no matching booster in the new shop rotation.
    packs.append(make_pack('EDISON-REWARDS', 'Edison Promos & Deck Cards', CUTOFF, uncovered,
                           'https://www.db.yugioh-card.com/yugiohdb/card_list.action?request_locale=en',
                           shop_only=True))
    write('edison-cards.json', new_cards)
    write('edison-packs.json', packs)
    print(f'Wrote {len(new_cards)} cards and {len(packs)} packs, including {len(uncovered)} cards in the reward booster.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('products', type=Path)
    parser.add_argument('ygojson', type=Path)
    args = parser.parse_args()
    compile_catalog(load(args.products), args.ygojson)


if __name__ == '__main__':
    main()
