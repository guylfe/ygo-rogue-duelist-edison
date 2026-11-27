"""Keep previously saved Collector opponents playable in existing runs."""
from collections import Counter

def sanitize(rows):
 import campaign as g
 import content
 result=[]
 for row in rows if isinstance(rows,list) else []:
  if not isinstance(row,dict):continue
  deck=row.get('deck',{});character=row.get('character')
  if character not in content.PLAYABLE_IDS or not isinstance(deck,dict):continue
  main,extra=deck.get('main'),deck.get('extra',[])
  if not isinstance(main,list) or not isinstance(extra,list) or not 40<=len(main)<=60 or len(extra)>15:continue
  if any(type(cid) is not int or cid not in g.BY_ID for cid in main+extra):continue
  if any(g.is_extra(cid) for cid in main) or any(not g.is_extra(cid) for cid in extra):continue
  if max(Counter(g.limit_identity(cid) for cid in main+extra).values(),default=0)>3:continue
  result.append(dict(id=str(row.get('id',''))[:64],name=str(row.get('name','Fallen duelist'))[:32],character=character,deck=dict(main=main[:],extra=extra[:])))
 return result


def add_route(run,rng):
 run.pop('fallen_routes',None)


def opponent(run,cid=None):
 if not run.get('loop') or run.get('encore_active'):return None
 return run.get('fallen_routes',{}).get(str(run.get('opponent') if cid is None else cid))
