"""Existing saved Collector routes retain their frozen duel decks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import content,campaign as game,fallen_collectors
retired=content.RETIRED_COLLECTOR_IDS
assert retired and not content.UC_OPPONENTS
assert all(content.CHARACTERS[cid]['ultimate_collector'] for cid in retired)
assert not retired.intersection(content.PLAYABLE_IDS)
for loop in [0,1,2,9]:
 assert not retired.intersection(content.eligible_opponents(5,loop))
cid=min(retired)
standard=content.eligible_opponents(5,1)[0]
deck=content.opponent_record(5,standard,1)
run={'loop':1,'round':5,'opponent':cid,'routes':[cid],'fallen_routes':{str(cid):{'deck':deck}}}
assert game.run_opponent_record(run)['main']==deck['main']
assert run['fallen_routes'][str(cid)]['deck']==deck
fallen_collectors.add_route(run,None)
assert not run.get('fallen_routes')
print('PASS saved Collector deck resumes, retired IDs stay reserved and new routes skip them')
