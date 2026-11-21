"""Campaign acts at the real save, acquisition, prepare and victory entry points."""
import json
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'android'))
import approved_relics
import campaign as game
import campaign_acts as acts
import content
import mobile_backend
import storage

rng = random.Random(113)
cid = lambda name: game.BY_NAME[name]['id']
tengu, cyber, honest, stardust = map(cid, ['Reborn Tengu','Cyber Dragon','Honest','Stardust Dragon'])
exvc = content.EXTREME_VICTORY_PACK
official = set(exvc['common'] + exvc['rare'])
assert len(official) == 100 and tengu in official
assert not any(game.BY_ID[c]['data']['type'] & 0x800000 for c in official)
assert 'EN-TLM' in acts.native_packs(1)
assert 'EN-CRV' not in acts.native_packs(1) and 'EN-CRV' in acts.native_packs(2)
assert 'EN-LODT' in acts.native_packs(2)
assert not acts.allows({'act':1},cyber) and acts.allows({'act':2},cyber)
assert acts.allows({'act':2},honest) and not acts.allows({'act':2},stardust)
assert not acts.allows({'act':1,'extreme_victory':True},tengu)
assert not acts.allows({'act':2,'extreme_victory':True},tengu)
assert not acts.allows({'act':3,'extreme_victory':False},tengu)
assert acts.allows({'act':3,'extreme_victory':True},tengu)
for n in ['Trishula, Dragon of the Ice Barrier','Infernity Launcher','Pot of Duality']:
    assert n not in game.BY_NAME,n

def dispatch(action, value=None):
    return json.loads(mobile_backend.dispatch(json.dumps(dict(action=action,value=value))))

def verify_stock(run):
    allowed = set(acts.rotation(run,approved_relics.has(run,'duelist_catalogue')))
    for item in run['shop']:
        if item['kind']=='pack' and item['id']!='RANDOM-PACK':
            assert item['id'] in allowed or item['id']==run.get('pinned_pack'),item
        if item['kind']=='single':
            ids=item.get('bundle',[item['id']])
            assert all(acts.allows(run,c) for c in ids if c in game.BY_ID and not c>=190_000_000),item
        if item['kind']=='deck':
            assert all(acts.allows(run,c) for c in item['cards']),item

with tempfile.TemporaryDirectory() as folder, patch.object(storage,'ROOT',Path(folder)), patch.object(game,'RUNTIME',Path(folder)/'runtime'):
    game.RUNTIME.mkdir()
    assert storage.settings()['extremeVictory'] is False
    profile=storage.profile()
    profile['relicless_unlocked']=True
    storage.write(storage.ROOT/'profile.json',profile)
    legacy=game.new_run(0,rng,level=-1)
    legacy['_save_slot']=3
    game.save(legacy)
    assert 'act' not in game.load_run(3)
    dispatch('settings',{'extremeVictory':True})
    state=dispatch('new',{'character':0,'level':-1,'slot':1})
    run=mobile_backend.run
    assert run['extreme_victory'] is True and run['stage']=='starter'
    dispatch('settings',{'extremeVictory':False})
    assert game.load_run(1)['extreme_victory'] is True
    supports=list(run['starter_offer'])
    assert all(acts.pack_act(p)==1 for p in supports)
    assert all(acts.allows(run,c) and c!=cyber for ids in run['starter_offer'].values() for c in ids)
    assert 'DRAFT-YAMI-YUGI' in run['pack_ids']
    dispatch('act-starter',supports[0])
    assert all(acts.allows(run,c) for c in run['pool'])
    assert len(run['pack_ids'])==4 and supports[0] in run['opened_packs']
    game.auto_deck(run)
    dispatch('pin-booster',supports[0])
    turn=0
    retired=None
    for act in (1,2,3):
        assert run['act']==act
        for round_number in range(9):
            assert run['round']==round_number
            expected=(20,30,40)[act-1]+(5 if act!=3 and round_number>=6 else 0)
            assert approved_relics.minimum(run)==expected
            if run['stage']=='shop':
                verify_stock(run)
            for opponent in run['routes']:
                record=game.run_opponent_record(run,opponent)
                assert all(acts.allows(run,c) for c in record['main']+record['extra'])
                examples=run['route_examples'][str(opponent)]
                assert examples and all(c in record['main']+record['extra'] for c in examples)
                if act==1: assert cyber not in record['main']
            game.auto_deck(run)
            assert game.validate(run) is None, (act,round_number,len(run['pool']))
            opponent=run['routes'][0]
            won_card=run['route_examples'][str(opponent)][0]
            dispatch('reward-target',{'opponent':opponent,'card':won_card})
            dispatch('choose',opponent)
            dispatch('begin')
            assert won_card in run['duel']['enemy_deck']
            turn+=1
            dispatch('finish',{'winner':0,'lp':8000,'events':[]})
            assert run['last_reward_cards'][0]==won_card
            if turn==1:
                assert any(x['kind']=='pack' and x['id']==supports[0] for x in run['shop'])
                verify_stock(run)
            dispatch('reward-accept')
        if act==3:
            assert run['stage']=='complete'
            break
        assert run['stage']=='act_transition'
        offer=run['act_transition']
        assert game.load_run(1)['act_transition']==offer
        assert all(acts.pack_act(p)==act+1 for p in offer['choices'])
        assert ('EN-EXVC' in offer['choices'])==(act==2)
        assert ('EN-LODT' in offer['choices'])==(act==1)
        keep=offer['carryable'][:2]
        if act==1:retired=next(p for p in offer['carryable'] if p not in keep)
        if act==2 and retired not in acts.rotation(run):assert retired not in offer['carryable']
        packs=[offer['choices'][0]]*3 if act==1 else ['EN-EXVC']*3
        pool,selected=run['pool'][:],run['selected'][:]
        dispatch('act-transition',{'packs':packs,'carry':keep})
        assert run['pool'][:len(pool)]==pool and run['selected']==selected
        assert len(run['pool'])-len(pool)==27
        assert run['carried_packs']==keep
        assert len(run['free_packs'])==3
        verify_stock(run)
        assert not set(run['carried_packs'])-set(acts.rotation(run))
    assert turn==27
    assert {entry['act'] for entry in run['timeline']}=={1,2,3}
    assert storage.profile()['wins']==1
    plain=dispatch('new',{'character':0,'level':-1,'slot':2})['run']
    assert plain['extreme_victory'] is False
    assert 'EN-EXVC' not in acts.transition_offer(dict(plain,act=2),rng)['choices']
    for source in (None,{'act':1,'extreme_victory':True},{'act':2,'extreme_victory':True},{'act':3,'extreme_victory':False}):
        try:
            game.open_pack('EN-EXVC',rng,source)
        except ValueError:
            pass
        else:
            raise AssertionError('Optional booster granted outside its act')
    assert set(game.open_pack('EN-EXVC',rng,{'act':3,'extreme_victory':True}))<=official

    # Fixed decks keep the transition cards in the pool when their normal
    # per-opponent or reward deck replaces the list of selected cards.
    profile=storage.profile()
    profile['unlocked']=content.PLAYABLE_IDS[:]
    storage.write(storage.ROOT/'profile.json',profile)
    for key in ('copycat','engine_deck'):
        index=next(i for i,c in enumerate(content.CHARACTERS) if c.get(key))
        fixed=game.new_run(index,rng,act_campaign=True)
        fixed['stage']='act_transition'
        fixed['round']=9
        fixed['act_transition']=acts.transition_offer(fixed,rng)
        packs=[fixed['act_transition']['choices'][0]]*3
        acts.transition(game,fixed,{'packs':packs,'carry':[]},rng)
        assert len(fixed['act_pack_cards'])==27
        if key=='copycat':
            game.copy_deck(fixed,rng)
        else:
            game.prepare_duel(fixed,rng)
        assert fixed['pool'][-27:]==fixed['act_pack_cards']
        assert all(i<len(fixed['pool'])-27 for i in fixed['selected'])
print('PASS 27 campaign victories, both saved transitions, targeted opponent rewards, shop and carry gates, minimums, and optional set isolation')
