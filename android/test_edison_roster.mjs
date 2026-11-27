// Run the production CPU against legal, staged positions in the packaged duel core.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root = process.argv[2] ? path.resolve(process.argv[2]) : fileURLToPath(new URL('./web/',import.meta.url));
const {MobileDuel,M,R,I,B,L} = await import(pathToFileURL(path.join(root,'duel.js')));
const load = name => JSON.parse(fs.readFileSync(path.join(root,name+'.json'),'utf8'));
const content = load('content');
const cards = [...content.cards,...content.tokenCards];
const ids = new Map(cards.map(c => [c.name,c.id]));
const inputs = [load('engine-data'),load(fs.existsSync(path.join(root,'scripts-0.json'))?'scripts-0':'scripts')];
const duel = await new MobileDuel(cards).init(inputs);

const idle = (action,index=null) => ({type:R.SELECT_IDLECMD,action,index});
const pass = m => m.type===M.SELECT_IDLECMD ? idle(I.TO_EP) :
  m.type===M.SELECT_CHAIN&&!m.forced ? {type:R.SELECT_CHAIN,index:null} :
  m.type===M.SELECT_EFFECTYN ? {type:R.SELECT_EFFECTYN,yes:false} : duel.auto(m);
const zone = (p,l) => duel.query(p,l).filter(Boolean).map(c => duel.name(c.code));
const field = name => zone(1,L.MZONE).includes(name);
const grave = name => zone(1,L.GRAVE).includes(name);
const back = name => zone(1,L.SZONE).includes(name);
const ACTIVATE = I.SELECT_ACTIVATE;

function start(states,seed,enemyLP) {
  const lua = ['Debug.ReloadFieldBegin(DUEL_MODE_MR1,1)','Debug.SetPlayerInfo(0,8000,0,0)',`Debug.SetPlayerInfo(1,${enemyLP},0,0)`];
  for (let p=0;p<states.length;p++) {
    const state = states[p];
    const add = (l,name,i,pos) => {
      assert.ok(ids.has(name),name);
      lua.push(`Debug.AddCard(${ids.get(name)},${p},${p},LOCATION_${l},${i},${pos})`);
    };
    for (const [i,item] of (state.field||[]).entries()) {
      const [name,pos='POS_FACEUP_ATTACK'] = Array.isArray(item)?item:[item];
      add('MZONE',name,i,pos);
    }
    for (const [i,name] of (state.back||[]).entries()) add('SZONE',name,i,'POS_FACEUP_ATTACK');
    if(state.fieldSpell)add('SZONE',state.fieldSpell,5,'POS_FACEUP_ATTACK');
    for (const [location,values] of Object.entries({HAND:state.hand,GRAVE:state.grave,EXTRA:state.extra,DECK:state.deck||Array(10).fill('Battle Ox')}))
      for (const name of (values||[])) add(location,name,0,location==='GRAVE'?'POS_FACEUP_ATTACK':'POS_FACEDOWN_DEFENSE');
  }
  duel.start([],[],8000,enemyLP,0,seed,[],[],lua.concat('Debug.ReloadFieldEnd()').join('\n'),0);
  duel.core.startDuel(duel.h);
  duel.advance();
}

const tests = [
  ['Jaden Yuki', {hand:['Elemental HERO Avian','Elemental HERO Burstinatrix','Polymerization'],extra:['Elemental HERO Flame Wingman']},
   () => field('Elemental HERO Flame Wingman')],
  ['Chazz Princeton', {field:['Armed Dragon LV3'],hand:['Armed Dragon LV5','Level Up!']},
   () => field('Armed Dragon LV5')],
  ['Chazz Princeton', {hand:['Ojama Green','Ojama Black','Ojama Yellow','Polymerization'],extra:['Ojama King']},
   () => field('Ojama King')],
  ['Zane Truesdale', {hand:['Cyber Dragon','Cyber Dragon','Cyber Dragon','Power Bond'],extra:['Cyber End Dragon']},
   () => field('Cyber End Dragon')],
  ['Alexis Rhodes', {hand:['Blade Skater','Etoile Cyber','Polymerization'],extra:['Cyber Blader']},
   () => field('Cyber Blader')],
  ['Vellian Crowler', {field:['Ancient Gear Soldier','Ancient Gear Knight'],hand:['Ancient Gear Golem']},
   () => field('Ancient Gear Golem'),{field:['Summoned Skull']}],
  ['Aster Phoenix', {field:['Destiny HERO - Diamond Dude'],deck:Array(5).fill('Smashing Ground')},
   () => grave('Smashing Ground'),{}],
  ['Sartorius', {hand:['Light Barrier','Arcana Force VII - The Chariot']},
   () => back('Light Barrier') && field('Arcana Force VII - The Chariot')],
  ['Sartorius', {field:['Arcana Force 0 - The Fool','Arcana Force 0 - The Fool','Arcana Force VI - The Lovers','Shining Angel'],
    hand:['Light Barrier','Arcana Force XXI - The World']},
   () => field('Arcana Force XXI - The World') && duel.turn>=3 && duel.player===1,{}],
  ['Jesse Anderson', {hand:['Crystal Beast Sapphire Pegasus'],deck:['Crystal Beast Ruby Carbuncle',...Array(10).fill('Battle Ox')]},
   () => field('Crystal Beast Sapphire Pegasus') && back('Crystal Beast Ruby Carbuncle')],
  ['Yusei Fudo', {hand:['Junk Synchron'],grave:['Quillbolt Hedgehog'],extra:['Junk Warrior']},
   () => field('Junk Warrior'),{field:['Dark Elf']}],
  ['Jack Atlas', {field:['Dark Resonator','The Tricky'],extra:['Red Dragon Archfiend']},
   () => field('Red Dragon Archfiend'),{field:['Summoned Skull']}],
  ['Akiza Izinski', {field:['Rose, Warrior of Revenge','Lonefire Blossom'],extra:['Black Rose Dragon']},
   () => grave('Black Rose Dragon') && zone(0,L.MZONE).length===0,{field:['Summoned Skull','Dark Elf','Luster Dragon']}],
  ['Leo', {field:['Morphtronic Scopen'],hand:['Morphtronic Radion'],extra:['Power Tool Dragon'],deck:['Double Tool C&D','United We Stand','Mage Power',...Array(10).fill('Battle Ox')]},
   () => field('Power Tool Dragon'),{field:['Berserk Gorilla']}],
  ['Crow Hogan', {field:['Blackwing - Gale the Whirlwind','Blackwing - Bora the Spear'],extra:['Blackwing Armor Master']},
   () => field('Blackwing Armor Master'),{field:['Summoned Skull']}],
  ['Kalin Kessler', {field:[['Infernity Necromancer','POS_FACEUP_DEFENSE']],grave:['Infernity Archfiend'],deck:Array(10).fill('Infernity Force')},
   () => field('Infernity Archfiend')],
];

const later = JSON.parse(load('campaign-files')['data/later-act-opponents.json']);
const returning = [
  [2, 1, {field:['Horus the Black Flame Dragon LV6'],hand:['Level Up!'],deck:['Horus the Black Flame Dragon LV8',...Array(10).fill('Spear Dragon')]},
   () => field('Horus the Black Flame Dragon LV8')],
  [2, 3, {hand:['Harpie Queen',"Harpies' Hunting Ground"]},
   () => field('Harpie Queen') && back("Harpies' Hunting Ground"),{}],
  [2, 9, {field:['Zombie Master'],hand:['Regenerating Mummy'],grave:['Pyramid Turtle']},
   () => field('Pyramid Turtle') || field('Regenerating Mummy')],
  [2, 18, {field:['Levia-Dragon - Daedalus'],fieldSpell:'A Legendary Ocean'},
   () => field('Levia-Dragon - Daedalus') && zone(0,L.MZONE).length===0,
   {field:['Summoned Skull','Dark Elf','Luster Dragon']}],
  [3, 9, {field:['Zombie Master','Plaguespreader Zombie'],extra:['Doomkaiser Dragon']},
   () => field('Doomkaiser Dragon'),{field:['Summoned Skull'],grave:['Ryu Kokki']}],
  [3, 10, {hand:['Doom Dozer'],grave:['Insect Knight','Howling Insect']},
   () => field('Doom Dozer'),{field:['Summoned Skull']}],
  [3, 14, {hand:['Bountiful Artemis','Dark Bribe']},
   () => field('Bountiful Artemis') && back('Dark Bribe')],
  [3, 18, {hand:['Deep Sea Diva'],deck:['Spined Gillman',...Array(10).fill('Mother Grizzly'),'Spined Gillman'],extra:['Ally of Justice Catastor']},
   () => field('Ally of Justice Catastor'),{field:['Battle Ox']}],
  [3, 98, {hand:['Miracle Fusion'],grave:['Elemental HERO Ocean','Snowman Eater'],extra:['Elemental HERO Absolute Zero']},
   () => field('Elemental HERO Absolute Zero'),{field:['Battle Ox']}],
  [3, 103, {field:['Krebons','Destiny HERO - Malicious'],extra:['Stardust Dragon']},
   () => field('Stardust Dragon')],
];
const lines = [
  ...tests.map(([name,own,done,other])=>{
    const index=content.characters.findIndex(c=>c.name===name&&c.home_act);
    return {name,own,done,other,deck:content.cpuWatchDecks[index][0],lp:8000};
  }),
  ...returning.map(([act,index,own,done,other])=>{
    const row=later[act].returning[index];
    return {name:`Act ${act} ${content.characters[index].name}`,own,done,other,lp:later[act].lp[0],
      deck:{main:Object.keys(row.main).map(name=>ids.get(name)),extra:row.extra.map(name=>ids.get(name))}};
  }),
];
let failures = 0;
for (const {name,own,done,other={field:['Battle Ox']},deck,lp} of lines) {
  for (const card of [
    ...(own.field||[]).map(c=>Array.isArray(c)?c[0]:c), ...(own.hand||[]), ...(own.grave||[]),
    ...(own.extra||[]), ...(own.fieldSpell?[own.fieldSpell]:[]),
  ]) {
    assert.ok([...deck.main,...deck.extra].includes(ids.get(card)),`${name} uses ${card} in the campaign`);
  }
  const actions = [];
  try {
    start([other,own],3317,lp);
    for (let i=0;i<150&&!duel.finished&&duel.turn<5&&!done();i++) {
      const m = duel.pending;
      const r = m.player===1 ? duel.auto(m) : pass(m);
      if (m.player===1) {
        const c = m.type===M.SELECT_IDLECMD ? (r.action===ACTIVATE?m.activates:r.action===I.SELECT_SUMMON?m.summons:r.action===I.SELECT_SPECIAL_SUMMON?m.special_summons:[])[r.index] : m;
        actions.push([duel.turn,m.type,r.action??r.yes??r.index??r.position,duel.name(c?.code||0),
          m.type===M.SELECT_CHAIN?m.selects.map(card=>duel.name(card.code)):null]);
      }
      duel.respond(r);
    }
    assert.ok(done(),JSON.stringify({actions,monsters:zone(1,L.MZONE),back:zone(1,L.SZONE),grave:zone(1,L.GRAVE)}));
    assert.deepEqual(duel.errors,[]);
    console.log('PASS',name,'completed the staged signature line');
  } catch (error) {
    failures++;
    console.error('FAIL',name,error.message);
  } finally {duel.destroy();}
}
assert.equal(failures,0);
