import {L, M, R} from './engine.js';

const TUNER = 0x1000;
const SYNCHRO = 0x2000;
const FACE_UP = 5;
const SYNCHRO_MATERIAL = 512;
export const PLAGUESPREADER = 33420078;
const ZOMBIE = 16;
const WHITE_STONE = 79814787;
const GOBLIN_ZOMBIE = 63665875;
const REBORN_TENGU = 10028593;
const effectValue = new Map([
 ['Stardust Dragon', 400],
 ['Colossal Fighter', 250],
 ['Thought Ruler Archfiend', 250],
 ['Ally of Justice Catastor', 150],
]);

export const isSynchro = data => !!(data?.type & SYNCHRO);

function combinations(cards, data, target) {
 // Forecast the straightforward procedures. The core alone offers legal summons and materials.
 const requirement = /^(?:1 Tuner|"([^"]+)") \+ (\d+)(\+| or more)? non-Tuner(?: (Zombie))? monsters?$/i.exec(target.desc?.split('\n')[0]);
 if (!requirement) return [];
 const [, namedTuner, count, more, zombie] = requirement;
 const min = Number(count);
 const type = card => data[card.code]?.type || 0;
 const level = card => card.level || data[card.code]?.level || 0;
 const nonTuners = cards.filter(c => !(type(c) & TUNER) && (!zombie || Number(c.race ?? data[c.code]?.race)===ZOMBIE));
 const tuners = cards.filter(c => (type(c) & TUNER) && (!namedTuner || c.name === namedTuner));
 const lines = [];
 for (const tuner of tuners) {
  for (let bits = 1; bits < (1 << nonTuners.length); bits++) {
   const materials = nonTuners.filter((_, i) => bits & (1 << i));
   if (materials.length < min || (!more && materials.length !== min)) continue;
   if (materials.reduce((sum, c) => sum + level(c), level(tuner)) === target.level) lines.push([tuner, ...materials]);
  }
 }
 return lines;
}

export function synchroChoice(engine, prompt, smart, own, enemy, strength) {
 const side = prompt.player;
 const deck = engine.query(side, L.EXTRA).filter(Boolean);
 if (!deck.some(c => isSynchro(engine.data[c.code]))) return null;
 const prepared = own.filter(c => c.position & FACE_UP).map(c => ({...c, name:engine.name(c.code)}));
 const currentDamage = smart.planDamage();
 const offer = prompt.special_summons ?? [];
 const deckHas = code => engine.query(side,L.DECK).some(c=>c?.code===code);
 const revival = own.length<5 && engine.query(side,L.HAND).some(Boolean) ? (prompt.activates||[])
  .findIndex(c=>c.code===PLAGUESPREADER&&c.location===L.GRAVE) : -1;

 // Hold attackers for their battle before consolidating them. On a blocked board,
 // a new attack threshold or a defensive/effect upgrade can justify the material.
 function score(target, materials, setup) {
  const candidate = {code:target.id, controller:side, location:L.EXTRA};
  const attack = smart.projectedAttack(candidate);
  const defense = smart.projectedDefense(candidate);
  const spent = materials.filter(c => c.location === L.MZONE);
  const remaining = prepared.filter(c => !spent.includes(c));
  const onSend = c => {
   if(!smart.effectsEnabled(side))return 0;
   if(c.code===WHITE_STONE&&deckHas(89631139))return 350;
   if(c.code===GOBLIN_ZOMBIE)return 220;
   if(c.code===REBORN_TENGU&&deckHas(REBORN_TENGU))return 400;
   return 0;
  };
  const lose = materials.reduce((sum, c) => sum + Math.min(7000, smart.expendable(c)) * 0.17 - onSend(c), 0);
  const strongestSpent = Math.max(0, ...materials.map(c => c.position & 1 ? c.attack : (c.defense || 0) * 0.85));
  const plannedDamage = smart.planDamage(
   smart.attackAllowed(candidate,!enemy.length) && !smart.attackBlocked(candidate,side,true) ? [attack] : [],
   [], spent,
  );
  if (prompt.to_bp && plannedDamage >= engine.lp[1-side] && currentDamage < engine.lp[1-side]) return 10000 - lose;

  const beat = power => enemy.filter(c => power > strength(c)).length;
  const bestBefore = Math.max(0, ...prepared.filter(c => c.position & 1).map(c => c.attack));
  const bestAfter = Math.max(attack, ...remaining.filter(c => c.position & 1).map(c => c.attack));
  const breakthrough = (beat(bestAfter) - beat(bestBefore)) * 550;
  const doomkaiser = target.name==='Doomkaiser Dragon' && engine.query(1-side,L.GRAVE)
   .some(c=>c&&Number(engine.data[c.code]?.race)===ZOMBIE);
  const effects = smart.effectsEnabled(side) ? (effectValue.get(target.name) || 0) + Number(doomkaiser)*650 : 0;
  const defenceFallback = Math.max(0, defense - strongestSpent) * 0.35;
  const earlierAttack = prompt.to_bp ? Math.max(0, currentDamage - plannedDamage) : 0;
  if (earlierAttack > 250 && !breakthrough) return -Infinity;
  return Math.max(attack - strongestSpent, defenceFallback) + breakthrough + effects - lose -
   earlierAttack * 0.5 - (materials.length - 2) * 350 - (setup==='revive'?500:setup==='normal'?120:0);
 }

 let best = null;
 const consider = (kind,index,code,target,board,setupCard) => {
  for (const materials of combinations(board,engine.data,target)) {
   if (setupCard && !materials.includes(setupCard)) continue;
   const value = score(target,materials,kind);
   if (value >= 250 && (!best || value > best.value)) best = {kind,index,code,materials,value};
  }
 };
 offer.forEach((card,index) => {
  if (card.location !== L.EXTRA || !isSynchro(engine.data[card.code])) return;
  const target = engine.cards.get(card.code);
  if (target) consider('special',index,card.code,target,prepared);
 });
 if (best) return best;

 if (own.length >= 5 || !prepared.length) return null;
 (prompt.summons || []).forEach((card,index) => {
  const data = engine.data[card.code];
  if (!data || data.level > 4 || engine.destroyedOnNormalSummon(card)) return;
  const setupCard = {...card, name:engine.name(card.code), level:data.level, attack:data.attack,
   defense:data.defense, position:1};
  for (const extra of deck) {
   const target = engine.cards.get(extra.code);
   if (target && isSynchro(engine.data[extra.code])) consider('normal',index,extra.code,target,[...prepared,setupCard],setupCard);
  }
 });
 if (revival>=0) {
  const tuner = {code:PLAGUESPREADER, controller:side, location:L.GRAVE, name:'Plaguespreader Zombie', level:2, attack:400, defense:200, position:1};
  for (const extra of deck) {
   const target = engine.cards.get(extra.code);
   if(target&&isSynchro(engine.data[extra.code]))consider('revive',revival,extra.code,target,[...prepared,tuner],tuner);
  }
 }
 return best;
}

export function synchroMaterialResponse(engine, prompt, smart) {
 if (engine.selectionHint !== SYNCHRO_MATERIAL || prompt.type !== M.SELECT_UNSELECT_CARD) return null;
 const plan = engine.synchroPlan?.code === engine.materialSubject ? engine.synchroPlan : null;
 const matches = (a,b) => a.sequence === b.sequence && a.location === b.location &&
  a.code === b.code && a.controller === b.controller;
 const chosen = c => plan?.materials.some(m => matches(m,c));
 const response = index => ({type:R.SELECT_UNSELECT_CARD,index});
 const preferred = prompt.select_cards.findIndex(chosen);
 if (preferred >= 0) return response(preferred);
 if (prompt.can_finish) return response(null);
 const legal = prompt.select_cards.map((c,index) => ({
  index, value:smart.expendable(engine.query(c.controller,c.location)[c.sequence] || c),
 })).sort((a,b) => a.value - b.value);
 return legal.length ? response(legal[0].index) : null;
}
