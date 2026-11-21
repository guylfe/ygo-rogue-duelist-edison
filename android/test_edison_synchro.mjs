// Stage a few open game states in the same WASM core and use the normal campaign AI or player commands.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {MobileDuel, M, R, I, B, L, P} from './web/duel.js';

const load = name => JSON.parse(fs.readFileSync(new URL('./web/' + name + '.json', import.meta.url), 'utf8'));
const content = load('content');
const cards = [...content.cards, ...content.tokenCards];
const id = name => {
 const card = cards.find(c => c.name === name);
 assert.ok(card,name);
 return card.id;
};
const duel = await new MobileDuel(cards).init([load('engine-data'),load('scripts')]);
const start = (states) => {
 const add = (name,p,location,sequence,position) => 'Debug.AddCard('+[id(name),p,p,location,sequence,position].join(',')+')';
 const lua = ['Debug.ReloadFieldBegin(DUEL_MODE_MR1,1)','Debug.SetPlayerInfo(0,8000,0,0)','Debug.SetPlayerInfo(1,8000,0,0)'];
 for (let p=0;p<2;p++) {
  const state=states[p] || {};
  (state.field || []).forEach((value,i) => {
   const [name,position='POS_FACEUP_ATTACK']=Array.isArray(value)?value:[value];
   lua.push(add(name,p,'LOCATION_MZONE',i,position));
  });
  for (const [zone,cards] of [['EXTRA',state.extra],['HAND',state.hand],['DECK',Array(12).fill('Battle Ox')]])
   (cards || []).forEach(name => lua.push(add(name,p,'LOCATION_'+zone,0,'POS_FACEDOWN_DEFENSE')));
 }
 duel.start([],[],8000,8000,0,2211,[],[],lua.concat('Debug.ReloadFieldEnd()').join('\n'),0);
 duel.core.startDuel(duel.h);
 duel.advance();
};
const zone = (p,l) => duel.query(p,l).filter(Boolean).map(x => duel.name(x.code));
const idle = (action,index=null) => ({type:R.SELECT_IDLECMD,action,index});
const pass = m => m.type===M.SELECT_IDLECMD ? idle(I.TO_EP) :
 m.type===M.SELECT_CHAIN&&!m.forced ? {type:R.SELECT_CHAIN,index:null} :
 m.type===M.SELECT_EFFECTYN ? {type:R.SELECT_EFFECTYN,yes:false} : duel.auto(m);
const STARDUST = 'Stardust Dragon', IRON_CHAIN = 'Iron Chain Dragon', ROSE = 'Rose, Warrior of Revenge';
const PLAGUE = 'Plaguespreader Zombie', WHITE_STONE = 'The White Stone of Legend';

try {
 start([{field:[WHITE_STONE,'Battle Ox'],extra:['Ally of Justice Catastor',STARDUST]}]);
 const offer = duel.choices().find(c => c.code===id('Ally of Justice Catastor') && c.label.startsWith('Synchro summon'));
 assert.ok(offer,'player sees Catastor in Extra Deck');
 assert.ok(!duel.pending.special_summons.some(c => c.code===id(STARDUST)), 'wrong Level never offered');
 duel.respond(offer.response);
 let materialPrompts=0;
 while (duel.pending.type===M.SELECT_UNSELECT_CARD) {
  assert.equal(duel.pending.player,0);
  assert.equal(duel.selectionHint,512);
  materialPrompts++;
  const m=duel.pending;
  const index=m.can_finish?null:m.select_cards.findIndex(c=>[id(WHITE_STONE),id('Battle Ox')].includes(c.code));
  assert.ok(index===null||index>=0);
  duel.respond({type:R.SELECT_UNSELECT_CARD,index});
 }
 while ([M.SELECT_PLACE,M.SELECT_POSITION].includes(duel.pending.type)) duel.respond(duel.auto());
 assert.ok(materialPrompts>=2,'player actually received material prompts');
 assert.ok(zone(0,L.MZONE).includes('Ally of Justice Catastor'));
 assert.ok(zone(0,L.GRAVE).includes(WHITE_STONE));
 assert.ok(zone(0,L.GRAVE).includes('Battle Ox'));
 assert.deepEqual(duel.errors,[]);
 console.log('PASS player Extra Deck choice -> material prompts -> Catastor on field, both materials in GY');
 duel.destroy();

 start([{field:[['Battle Ox','POS_FACEDOWN_DEFENSE'],WHITE_STONE],extra:['Ally of Justice Catastor']}]);
 assert.ok(!duel.pending.special_summons.length,'cannot use face-down material');
 assert.deepEqual(duel.errors,[]);
 console.log('PASS a face-down material cannot make Catastor');
 duel.destroy();

 function cpu(states,done) {
  start(states);
  const actions=[];
  for(let i=0;i<100 && !duel.finished && !done();i++){
   const m=duel.pending, r=m.player===1?duel.auto(m):pass(m);
   if(m.player===1) actions.push({m,r,phase:duel.phase});
   duel.respond(r);
  }
  assert.deepEqual(duel.errors,[]);
  return actions;
 }
 let actions=cpu([{field:['Summoned Skull']},{field:['Luster Dragon'],hand:[ROSE],extra:[STARDUST]}],
  ()=>zone(1,L.MZONE).includes(STARDUST));
 assert.ok(zone(1,L.MZONE).includes(STARDUST),'CPU used a hand Tuner to get past a blocker');
 assert.ok(actions.some(({m,r})=>m.type===M.SELECT_IDLECMD&&r.action===I.SELECT_SUMMON&&m.summons[r.index].code===id(ROSE)));
 assert.ok(zone(1,L.GRAVE).includes(ROSE));
 console.log('PASS CPU Normal Summons its Tuner and resolves Stardust through the real material prompts');
 duel.destroy();

 actions=cpu([{}, {field:[ROSE,'Luster Dragon'],extra:[STARDUST]}],
  ()=>zone(1,L.MZONE).includes(STARDUST));
 const attack=actions.findIndex(({m,r})=>m.type===M.SELECT_BATTLECMD&&r.action===B.SELECT_BATTLE);
 const special=actions.findIndex(({m,r})=>m.type===M.SELECT_IDLECMD&&r.action===I.SELECT_SPECIAL_SUMMON);
 assert.ok(attack>=0&&special>attack,'CPU uses stronger attack line before consolidating in Main Phase 2');
 assert.equal(actions[special].phase,256);
 console.log('PASS CPU holds both attackers through Battle Phase and summons Stardust in Main Phase 2');
 duel.destroy();

 actions=cpu([{field:['Summoned Skull']},{field:[PLAGUE,'Battle Ox','Gemini Elf'],extra:[IRON_CHAIN]}],
  ()=>zone(1,L.MZONE).includes(IRON_CHAIN));
 assert.ok(zone(1,L.MZONE).includes(IRON_CHAIN),'CPU upgrades into Iron Chain Dragon');
 assert.ok(zone(1,L.MZONE).includes('Gemini Elf'),'CPU kept its stronger Level 4');
 assert.ok(zone(1,L.GRAVE).includes('Battle Ox'));
 console.log('PASS CPU chooses cheaper of two valid material combinations');
 duel.destroy();

 function shuffled(deck, seed) {
  const ids = [...deck];
  for (let i=ids.length-1; i>0; i--) {
   seed = (Math.imul(1664525,seed)+1013904223)>>>0;
   const j = Math.floor(seed*(i+1)/2**32);
   [ids[i],ids[j]] = [ids[j],ids[i]];
  }
  return ids;
 }
 for (const [opponent,tier,seed,target] of [
  [1,3,4,'Ally of Justice Catastor'], [9,2,13,'Gaia Knight, the Force of Earth'],
 ]) {
  const deck = content.cpuDecks[opponent][tier-1];
  duel.start(Array(30).fill(id('Battle Ox')),shuffled(deck.main,seed),8000,8000,5,seed,[],deck.extra);
  for (let i=0; i<260 && !duel.finished && !zone(1,L.MZONE).includes(target); i++) {
   const m=duel.pending;
   duel.respond(m.player===1?duel.auto(m):pass(m));
  }
  assert.ok(zone(1,L.MZONE).includes(target),deck.name);
  assert.deepEqual(duel.errors,[]);
  console.log(`PASS ${deck.name} summoned ${target} in a shuffled duel on turn ${duel.turn}`);
  duel.destroy();
 }
} finally {
 duel.destroy();
}
