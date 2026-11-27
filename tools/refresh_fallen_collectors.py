"""Build a Collector opponent snapshot from explicitly supplied fixture rows."""
import json,sys
from pathlib import Path
from datetime import datetime,timezone
import safe_write;safe_write.install()
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def refresh(rows=None):
 import content,fallen_collectors
 if rows is None:
  raise RuntimeError('Edison has no Collector service to refresh. Supply local fixture rows when testing.')
 target=ROOT/'data/fallen-collectors.json'
 old=json.loads(target.read_text(encoding='utf8'))['opponents'] if target.exists() else []
 combined={}
 for row in fallen_collectors.sanitize(old+rows):
  combined[row['id'] or json.dumps(row,sort_keys=True)]=row
 identities={row['id']:row['opponent_id'] for row in old}
 next_id=max([len(content.CHARACTERS)-1,*identities.values()])+1
 for row in combined.values():
  if row['id'] not in identities:identities[row['id']]=next_id;next_id+=1
  row['opponent_id']=identities[row['id']]
 opponents=sorted(combined.values(),key=lambda row:row['opponent_id'])
 data={'schema':1,'source':'shared-ultimate-collector-registry','updatedAt':datetime.now(timezone.utc).isoformat(),'opponents':opponents}
 # Keep the previous roster intact if the request or validation fails.
 temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8');temporary.replace(target)
 print(f'Bundled {len(opponents)} shared Ultimate Collector opponents; received {len(rows)} server records.')
 return data

if __name__=='__main__':refresh()
