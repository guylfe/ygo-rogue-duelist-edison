"""Campaign acts at the real save, acquisition, prepare and victory entry points."""
from copy import deepcopy
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
import shop_rewards
import storage

rng = random.Random(113)
random.seed(113)
cid = lambda name: game.BY_NAME[name]['id']
cyber, honest, stardust = map(cid, ['Cyber Dragon','Honest','Stardust Dragon'])
assert len(acts.ACTS)==3 and 'EN-EXVC' not in content.PACK_BY_ID
assert 'EN-DPKB' in acts.native_packs(3)
assert all(content.PACK_BY_ID[p]['date']<='2010-04-20' for p in acts.native_packs(3))
assert 'EN-TLM' in acts.native_packs(1)
assert 'EN-CRV' not in acts.native_packs(1) and 'EN-CRV' in acts.native_packs(2)
assert 'EN-LODT' in acts.native_packs(2)
assert not acts.allows({'act':1},cyber) and acts.allows({'act':2},cyber)
assert acts.allows({'act':2},honest) and not acts.allows({'act':2},stardust)
for n in ['Trishula, Dragon of the Ice Barrier','Infernity Launcher','Pot of Duality','Reborn Tengu']:
    assert n not in game.BY_NAME,n

# The same seed is reproducible. Each era can vary within its own whitelist,
# and every native booster has a path into a rotation across seeds.
sampled = [acts.draft_rotations([], random.Random(seed)) for seed in range(80)]
assert sampled[0] == acts.draft_rotations([], random.Random(0))
for act, rules in enumerate(acts.ACTS, 1):
    native = set(acts.native_packs(act))
    lineups = [set(r[str(act)]) for r in sampled]
    assert len({frozenset(lineup) for lineup in lineups}) > 1
    assert all(len(lineup) == acts.CONFIG['rotation_size'] < len(native) for lineup in lineups)
    assert all(rules['featured_pack'] in lineup and lineup.intersection(rules['companion_packs']) for lineup in lineups)
    assert set.union(*lineups) == native

def dispatch(action, value=None):
    return json.loads(mobile_backend.dispatch(json.dumps(dict(action=action,value=value))))

def verify_stock(run):
    allowed = set(acts.rotation(run,approved_relics.has(run,'duelist_catalogue')))
    for item in run['shop']:
        if item['kind']=='pack' and item['id']!='RANDOM-PACK':
            assert item['id'] in allowed or item['id']==run.get('pinned_pack') or (
                item['opponent_pack'] and acts.shop_pack_available(run,item['id'])),item
        if item['kind']=='single':
            ids=item.get('bundle',[item['id']])
            assert all(acts.allows(run,c) for c in ids if c in game.BY_ID and not c>=190_000_000),item
        if item['kind']=='deck':
            assert all(acts.allows(run,c) for c in item['cards']),item

with tempfile.TemporaryDirectory() as folder, patch.object(storage,'ROOT',Path(folder)), patch.object(game,'RUNTIME',Path(folder)/'runtime'):
    game.RUNTIME.mkdir()
    profile=storage.profile()
    profile['relicless_unlocked']=True
    storage.write(storage.ROOT/'profile.json',profile)
    legacy=game.new_run(0,rng,level=-1)
    legacy['_save_slot']=3
    game.save(legacy)
    assert 'act' not in game.load_run(3)
    seeded_runs=[game.new_run(0,random.Random(seed),level=-1,act_campaign=True) for seed in (0,1)]
    assert all(set(seeded_runs[0]['pack_rotations'][act]) != set(seeded_runs[1]['pack_rotations'][act]) for act in ('1','2','3'))
    dispatch('new',{'character':0,'level':-1,'slot':1})
    run=mobile_backend.run
    assert run['stage']=='starter' and game.load_run(1)['stage']=='starter'
    rotations=deepcopy(run['pack_rotations'])
    assert game.load_run(1)['pack_rotations']==rotations
    supports=list(run['starter_offer'])
    assert set(supports).issubset(rotations['1'])
    assert all(acts.allows(run,c) and c!=cyber for ids in run['starter_offer'].values() for c in ids)
    assert 'DRAFT-YAMI-YUGI' in run['pack_ids']
    assert all(p.startswith('DRAFT-') or p in rotations['1'] for p in run['pack_ids'])
    dispatch('act-starter',supports[0])
    assert all(acts.allows(run,c) for c in run['pool'])
    assert len(run['pack_ids'])==4 and supports[0] in run['opened_packs']
    game.auto_deck(run)
    dispatch('pin-booster',supports[0])
    turn=0
    retired=None
    for act in (1,2,3):
        assert run['act']==act
        assert run['pack_rotations']==rotations
        excluded = set(acts.native_packs(act)) - set(rotations[str(act)])
        for round_number in range(9):
            assert run['round']==round_number
            expected=(20,30,40)[act-1]+(5 if act!=3 and round_number>=6 else 0)
            assert approved_relics.minimum(run)==expected
            if run['stage']=='shop':
                verify_stock(run)
            assert not excluded.intersection(reward['pack'] for reward in run['route_rewards'].values())
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
            if round_number==0:
                # Check both the candidates fed to the real random shop picker
                # and the products it stocked. An absent native pack never enters the draw.
                with patch.object(shop_rewards,'pack_offered',wraps=shop_rewards.pack_offered) as candidates:
                    game.restock(run,rng,general_stock=True)
                considered={call.args[0]['id'] for call in candidates.call_args_list}
                assert considered and not excluded.intersection(considered)
                verify_stock(run)
        if act==3:
            assert run['stage']=='complete'
            break
        assert run['stage']=='act_transition'
        offer=run['act_transition']
        with patch.object(acts,'draft_rotations',side_effect=AssertionError('rerolled on resume')):
            dispatch('select-slot',1)
        run=mobile_backend.run
        assert run['act_transition']==offer and run['pack_rotations']==rotations
        assert set(offer['choices']).issubset(rotations[str(act+1)])
        assert all(acts.pack_act(p)==act+1 for p in offer['choices'])
        assert all(content.PACK_BY_ID[p]['date']<=acts.ACTS[act]['cutoff'] for p in offer['choices'])
        assert ('EN-LODT' in offer['choices'])==(act==1)
        keep=offer['carryable'][:2]
        if act==1:retired=next(p for p in offer['carryable'] if p not in keep)
        if act==2 and retired not in acts.rotation(run):assert retired not in offer['carryable']
        packs=[offer['choices'][0]]*3
        pool,selected=run['pool'][:],run['selected'][:]
        dispatch('act-transition',{'packs':packs,'carry':keep})
        assert run['pool'][:len(pool)]==pool and run['selected']==selected
        assert len(run['pool'])-len(pool)==27
        assert run['carried_packs']==keep
        assert len(run['free_packs'])==3
        verify_stock(run)
        assert set(packs).issubset(acts.rotation(run))
        assert not set(run['carried_packs'])-set(acts.rotation(run))
        if act==1:
            # A save from the previous three-act build can keep its visible
            # stock, selected deck, and full-era rotation.
            old=deepcopy(run)
            old.pop('pack_rotations')
            old['_save_slot']=2
            game.save(old)
            legacy_act=game.load_run(2)
            assert legacy_act['pool']==run['pool'] and legacy_act['selected']==run['selected']
            assert set(acts.native_packs(2)).issubset(acts.rotation(legacy_act))
    assert turn==27
    assert {entry['act'] for entry in run['timeline']}=={1,2,3}
    assert storage.profile()['wins']==1

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
print('PASS 80 seeds cover all native boosters with varied eight-pack lineups; 27 campaign victories cover shops, routes, both reloaded transitions, cards, legacy saves, and era gates')
