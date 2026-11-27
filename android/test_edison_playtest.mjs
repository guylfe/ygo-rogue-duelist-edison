import assert from 'node:assert/strict';
import {
 loadPlaytestDrafts, newPlaytestDraft, pendingPlaytestDrafts, playtestPreviouslySent,
 playtestReceipt, postPlaytest, savePlaytestDraft,
} from './web/edison-playtest.js';

const data=new Map();
globalThis.localStorage={getItem:key=>data.get(key),setItem:(key,value)=>data.set(key,value)};
const draft={...newPlaytestDraft({Version:'0.2.46',Screen:'Duel',Turn:4},['Draw']),
 note:'  Synthetic suggestion\r\nSecond line  ',queued:true,submittedBuild:'0.2.46'};
const endpoint='https://guylfe-game-feedback.netlify.app/v3/feedback';
const receipt={game:'edison',reportId:draft.id,filePath:`playtest-feedback/${draft.id}.json`};

assert.equal(savePlaytestDraft({...draft,rejected:true}),true,'Keep queued reports from older clients');
const historical={...draft,id:crypto.randomUUID(),queued:false,issueNumber:42};
assert.equal(savePlaytestDraft(historical),true);
assert.equal(playtestPreviouslySent(historical),true);
assert.equal(playtestReceipt(historical),null);
assert.deepEqual(pendingPlaytestDrafts(),[{...draft,rejected:true}]);

const requestBodies=[];
let reply=()=>new Response(null,{status:202});
globalThis.fetch=async (url,options)=>{
 assert.equal(url,endpoint);
 assert.equal(options.method,'POST');
 assert.equal(options.credentials,'omit');
 assert.deepEqual(options.headers,{'Content-Type':'application/json'});
 requestBodies.push(JSON.parse(options.body));
 return reply();
};
assert.deepEqual(await postPlaytest(draft,'0.2.47'),{pending:true});
reply=()=>{throw Error('Offline')};
await assert.rejects(postPlaytest(draft,'0.2.47'),/Offline/);
reply=()=>new Response(null,{status:503});
assert.deepEqual(await postPlaytest(draft,'0.2.47'),{pending:true});
reply=()=>new Response(null,{status:429,headers:{'Retry-After':'120'}});
const retry=await postPlaytest(draft,'0.2.47');
assert.equal(retry.pending,true);
assert.ok(retry.retryAt>Date.now()+119000);
for(const status of [400,409]){
 reply=()=>new Response(null,{status});
 assert.deepEqual(await postPlaytest(draft,'0.2.47'),{rejected:true});
}
for(const invalid of [{...receipt,game:'waystone'},{...receipt,reportId:crypto.randomUUID()},
 {...receipt,filePath:'playtest-feedback/other.json'}, {issueNumber:42},null]){
 reply=()=>Response.json(invalid);
 await assert.rejects(postPlaytest(draft,'0.2.47'),/Invalid feedback receipt/);
}
reply=()=>Response.json(receipt);
const accepted=await postPlaytest(draft,'0.2.47');
assert.deepEqual(accepted,{filePath:receipt.filePath});
for(const body of requestBodies)assert.deepEqual(body,{
 game:'edison',reportId:draft.id,build:'0.2.46',note:'Synthetic suggestion\nSecond line',
 context:{details:{Version:'0.2.46',Screen:'Duel',Turn:'4'},recentEvents:['Draw']},
});

assert.equal(savePlaytestDraft({...draft,...accepted,queued:false}),true);
assert.equal(playtestReceipt(loadPlaytestDrafts().find(row=>row.id===draft.id)),receipt.filePath);
assert.deepEqual(pendingPlaytestDrafts(),[]);
assert.equal(loadPlaytestDrafts().length,2);
console.log('PASS Edison file submission, legacy queue, stable retry payload, and matching durable receipt');
