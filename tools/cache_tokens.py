"""Audit token-producing era scripts and cache every token variant they create."""
import sys,json,re,sqlite3,urllib.request,shutil
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
# Variant ranges are the actual IDs in the bundled summoning scripts.
SUMMONERS={75622824:[75622825],86871614:[86871615],86801871:[86801872],12965761:[12965762],24874630:[24874631],91512835:[91512836],21770260:[21770261],62543393:[62543394],22493811:[22493812],40703222:[40703223],29843091:[29843092,29843093,29843094],63442604:[63442605],73915051:[73915052,73915053,73915054,73915055],65810489:[65810490],60764581:[60764582,60764583],82556058:[82556059]}
# Synchro-era scripts use these actual token codes, including alternate prints.
SUMMONERS.update({
 12958919: [12958920],
 14089428: [14089429],
 15341821: [15341822, 15341823],
 16946849: [16946850],
 21179143: [21179144],
 23116808: [23116809],
 28062325: [28062326],
 28355718: [28355719],
 30069398: [30069399],
 31986288: [31986289],
 35268887: [35268888],
 35514096: [35514097],
 38041940: [38041941],
 42956963: [42956964],
 43140791: [43140792],
 44330098: [44330099],
 46173679: [46173680, 46173681],
 48115277: [48115278],
 49808196: [49808197],
 51987571: [51987572],
 54289683: [93130022],
 56051648: [56051649],
 56597272: [56597273],
 60406591: [60406592],
 64382839: [64382840],
 68815401: [68815402],
 69890967: [69890968],
 71645242: [71645243],
 74440055: [74440056],
 75524092: [75524093],
 75732622: [75732623],
 82324105: [82324106],
 82340056: [82340057],
 82994509: [82994510],
 83239739: [83239740],
 93130021: [93130022],
 93224848: [93224849],
 93912845: [93912846],
 97452817: [97452818],
})

def audit(cards):
 # The client only has a name and art for catalogued tokens; any other token looks like an empty zone.
 for card in cards:
  path=ROOT/'runtime/script/official'/f'c{card["id"]}.lua'
  if path.exists() and 'Duel.CreateToken' in path.read_text(encoding='utf8'):
   assert card['id'] in SUMMONERS,('Uncatalogued token summoner',card['name'])
def manifest():
 sys.path.insert(0,str(ROOT))
 from content import era_cards
 cards=era_cards();byid={c['id']:c for c in cards}
 audit(cards)
 db=sqlite3.connect(ROOT/'runtime/expansions/cards.cdb');entries=[];seen=set()
 for summoner,ids in SUMMONERS.items():
  assert summoner in byid
  for cid in ids:
   if cid in seen:continue
   seen.add(cid)
   row=db.execute('SELECT t.name,d.type FROM texts t JOIN datas d ON d.id=t.id WHERE t.id=?',(cid,)).fetchone()
   assert row and row[1]&16384,(cid,row)
   entries.append(dict(id=cid,name=row[0],summoner=summoner,summoner_name=byid[summoner]['name'],image=f'https://images.ygoprodeck.com/images/cards/{cid}.jpg'))
 (ROOT/'data/tokens.json').write_text(json.dumps(entries,indent=2),encoding='utf8');return entries
if __name__=='__main__':
 tokens=manifest()
 for t in tokens:
  path=ROOT/'assets/cards'/f'{t["id"]}.jpg';dest=ROOT/'runtime/pics'/path.name
  if not path.exists():
   data=urllib.request.urlopen(t['image'],timeout=20).read();tmp=path.with_suffix('.token-download');tmp.write_bytes(data)
   with Image.open(tmp) as im:im.verify()
   tmp.replace(path)
  with Image.open(path) as im:im.verify()
  shutil.copy2(path,dest)
  print('Cached',t['id'],t['name'],flush=True)
 print('PASS:',len(tokens),'token variants from',len(SUMMONERS),'era token summoners')
