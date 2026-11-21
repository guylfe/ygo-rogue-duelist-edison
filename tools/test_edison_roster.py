"""Check append-only roster data and the actual campaign acquisition flow."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'android')]
import campaign as game
import campaign_acts as acts
import content
import mobile_backend
import storage


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def dispatch(action, value=None):
    return json.loads(mobile_backend.dispatch(json.dumps(dict(action=action, value=value))))


assert digest(content.CHARACTERS[:98]) == 'e6007bd9bd06cc40d1433baf794c38d21b2cb6ba7dc8d98f802d4e99928e3ab4'
assert digest(content.PLAYABLE_IDS[:36]) == '2beb586475543e995f2460c25ed4f356dea805a14785dd0239038665fa11a25f'
assert digest(content.PACKS[:126]) == '1cf01f98a38ef644eb5a628f8439d31cce30f8f5339e178573c27bf3011467f1'
legacy_decks = {str(i): [content.opponent_record(t*3,i) for t in range(3)] + [content.opponent_record(0,i,loop=1)] for i in content.GAME_DECKS}
assert digest(legacy_decks) == '85ea1f16e0426bde6ce0cab9dcb9ca2a349c6407209086c5eba9d26fbf534539'
assert content.PLAYABLE_IDS[36:] == list(range(98,112))
assert [content.CHARACTERS[i]['series'] for i in range(98,112)] == ['GX']*8+["5D's"]*6
assert 'Infernity Launcher' not in game.BY_NAME
assert 'EN-EXVC' not in content.PACK_BY_ID and len(acts.ACTS)==3

def deploy_home_run(roster, rng):
    """A reproducible home-act state with enough already owned cards to begin."""
    run = mobile_backend.run
    dispatch('act-starter', next(iter(run['starter_offer'])))
    run = mobile_backend.run
    home = roster['home_act']
    run.update(act=home, round=1, next_boss=None, gold=999)
    for pid in run['pack_rotations'][str(home)][:4]:
        run['pool'].extend(game.open_pack(pid,rng,run))
    game.auto_deck(run)
    return run


with tempfile.TemporaryDirectory() as tmp, patch.object(storage,'ROOT',Path(tmp)), patch.object(game,'RUNTIME',Path(tmp)/'runtime'):
    game.RUNTIME.mkdir()
    p=storage.profile()
    p['relicless_unlocked']=True
    storage.write(storage.ROOT/'profile.json',p)
    assert set(content.EDISON_DUELISTS)<=set(storage.profile()['unlocked'])
    for i, duelist in content.EDISON_DUELISTS.items():
        rng = random.Random(i)
        home, pid = duelist['home_act'], duelist['pack']
        assert acts.pack_act(duelist['support'])==home and acts.pack_act(pid)==home
        assert (ROOT/'assets'/content.CHARACTERS[i]['sprite']).is_file()
        assert (ROOT/'assets'/'packs'/(pid+'.jpg')).is_file()
        pack=content.PACK_BY_ID[pid]
        assert pack['name']==duelist['name'] and pack['archetypes']==duelist['tags']
        for act in range(1,4):
            assert (i in content.eligible_opponents(1,act=act))==(home==act)
            assert all(acts.allows({'act':act}, x) for x in game.open_pack(pid,rng,{'act':act}))
        assert i not in content.eligible_opponents(1) and i not in content.eligible_opponents(1,loop=1,act=home)
        deck=content.EDISON_DECKS[i]
        assert len(deck['main'])==40 and all(acts.allows({'act':home},cid) for cid in deck['main']+deck['extra'])
        ace=game.BY_NAME[duelist['ace']]['id']
        assert ace in pack['common']+pack['rare'] and ace in deck['main']+deck['extra']
        assert all(game.BY_NAME[name]['id'] in pack['common'] for name in duelist['enablers'])

        dispatch('new',dict(character=i,level=-1,slot=1,replace=True))
        run=mobile_backend.run
        assert run['pack_ids']==[pid]*3 and run['act']==1
        dispatch('act-starter', next(iter(run['starter_offer'])))
        dispatch('auto')
        assert game.validate(run) is None and all(acts.allows(run,cid) for cid in run['pool'])
        assert duelist['support'] in run['pack_rotations'][str(home)]
        draft_offer=acts.transition_offer(dict(run,act=home-1),rng)
        assert pid in draft_offer['choices'] and duelist['support'] in draft_offer['choices']

        # Use the regular route draw and the same opponent preparation, win,
        # and shop actions as the browser. Only the home-act position is staged.
        dispatch('new',dict(character=0,level=-1,slot=1,replace=True))
        run=deploy_home_run(duelist,rng)
        for _ in range(80):
            game.routes(run,rng)
            if i in run['routes']:break
            if run['next_boss']['opponent']==i:
                run['round']=2
                game.routes(run,rng)
                break
        assert i in run['routes'], duelist['name']
        assert run['route_rewards'][str(i)]['pack']==pid
        assert run['route_examples'][str(i)][0]==ace
        dispatch('reward-target',dict(opponent=i,card=ace))
        dispatch('choose',i)
        dispatch('begin')
        assert ace in run['duel']['enemy_deck']
        dispatch('finish',dict(winner=0,lp=8000,events=[]))
        assert run['last_reward_cards'][0]==ace
        dispatch('reward-accept')
        slot=next(n for n,p in enumerate(run['shop']) if p['id']==pid and p['opponent_pack'])
        before=len(run['pool'])
        dispatch('buy',slot)
        assert len(run['pool'])==before+9 and pid in run['opened_packs']
        assert all(acts.allows(run,cid) for cid in run['pool'][before:])
        assert pid in acts.pin_options(run)
    print('PASS 14 legal newcomer starts, own home support, encounters, previews, exact ace rewards, purchasable signature packs, and era gates')

    # Keep one new duelist selected from the real starter through the finale.
    dispatch('new',dict(character=106,level=-1,slot=1,replace=True))
    run=mobile_backend.run
    dispatch('act-starter',next(iter(run['starter_offer'])))
    rotations=deepcopy(run['pack_rotations'])
    for act in (1,2,3):
        assert run['character']==106 and run['act']==act
        for _ in range(9):
            dispatch('auto')
            assert game.validate(run) is None
            dispatch('choose',run['routes'][0])
            dispatch('begin')
            dispatch('finish',dict(winner=0,lp=8000,events=[]))
            dispatch('reward-accept')
        if act==3:break
        offer=deepcopy(run['act_transition'])
        owned,selected=run['pool'][:],run['selected'][:]
        dispatch('select-slot',1)
        run=mobile_backend.run
        assert run['act_transition']==offer and run['pack_rotations']==rotations
        target=content.CHARACTERS[106]['pack'] if act==2 else offer['choices'][0]
        dispatch('act-transition',dict(packs=[target]*3,carry=offer['carryable'][:2]))
        assert run['pool'][:len(owned)]==owned and run['selected']==selected
        assert len(run['pool'])==len(owned)+27
    assert run['stage']=='complete' and len(run['timeline'])==27 and run['character']==106
    print('PASS Yusei retained through both reloaded transitions, deck rebuilds, and the 27-duel finale')
