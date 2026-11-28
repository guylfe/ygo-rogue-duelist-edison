import campaign as game,storage,unlocks,character_progression
from content import CHARACTERS,PLAYABLE_IDS

def entries(profile=None):
 p=profile or storage.profile();rows=[]
 for i in PLAYABLE_IDS:
  if i in character_progression.STARTERS:continue
  act,metric,target,description=character_progression.rule(i)
  value=character_progression.value(p,i)
  key='character:'+str(i)
  synced=key in p.get('synced_achievements',[])
  if synced:value=max(value,target)
  done=value>=target
  unlocked=i in p['unlocked']
  rows.append(dict(id=key,name=CHARACTERS[i]['name'],reward='Unlock duelist',description=description,
                   value=value,target=target,done=done,unlocked=unlocked,act=None if i in character_progression.SPECIAL else act,
                   cumulative=metric in character_progression.CUMULATIVE,testing=unlocked and not done and bool(p.get('unlock_all'))))
 import sleeve_progress
 rows+=sleeve_progress.achievements(p)
 for row in rows:
  kind,key=row['id'].split(':',1)
  if kind=='sleeve':continue
  row['image']=CHARACTERS[int(key)]['sprite'] if kind=='character' else 'packs/'+key+'.jpg' if kind=='pack' else 'cards/'+str(game.BY_NAME[key]['id'] if key in game.BY_NAME else key)+'.jpg'
 return rows
