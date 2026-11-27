// Play complete matches with the drafted decks emitted by tools/test_later_act_opponents.py.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const [fixture,enginePath]=process.argv.slice(2);
assert.ok(fixture,'Usage: node android/test_later_act_matchups.mjs <fixture.json> [engine web directory]');
const web=enginePath?path.resolve(enginePath):fileURLToPath(new URL('./web/',import.meta.url));
const {MobileDuel}=await import(pathToFileURL(path.join(web,'duel.js')));
const load=(dir,name)=>JSON.parse(fs.readFileSync(path.join(dir,name),'utf8'));
const content=load(fileURLToPath(new URL('./web/',import.meta.url)),'content.json');
const duel=await new MobileDuel([...content.cards,...content.tokenCards]).init([
 load(web,'engine-data.json'),load(web,'scripts.json'),
]);
const rows=JSON.parse(fs.readFileSync(fixture,'utf8'));
for(const act of [1,2,3]){
 const encounters=rows.filter(row=>row.act===act);
 if(!encounters.length)continue;
 const results={wins:0,bossWins:0,finished:0,engineErrors:[],examples:[]};
 for(const row of encounters){
  try{
   duel.start(row.deck,row.enemy,row.lp,row.enemyLP,row.draw,row.seed,row.extra,row.enemyExtra,row.passives,row.enemyDraw);
   for(let n=0;!duel.finished&&n<5000&&duel.turn<200;n++){
    duel.respond(duel.auto());
    duel.visuals.length=0;
   }
   assert.ok(duel.finished,`unfinished on turn ${duel.turn}`);
   assert.deepEqual(duel.errors,[]);
   results.finished++;
   if(duel.finished.player===0){
    results.wins++;
    if(row.encounter%3===0)results.bossWins++;
    if(results.examples.length<4||row.encounter===9){
     results.examples.push(`${row.name} (Duel ${row.encounter}, ${row.enemyLP} LP, turn ${duel.turn})`);
    }
   }
  }catch(error){
   results.engineErrors.push(`seed ${row.run_seed}, duel ${row.encounter}, ${row.name}: ${error.message}`);
  }finally{duel.destroy();}
 }
 console.log(`Act ${act}: ${results.wins}/${encounters.length} wins, ${results.bossWins} boss wins. ${results.examples.join(' | ')}`);
 assert.deepEqual(results.engineErrors,[]);
 assert.equal(results.finished,encounters.length);
}
