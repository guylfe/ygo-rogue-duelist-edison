// Run immediately before deployment, then verify after deploying the stats Worker.
// Writes only public aggregate totals; no tokens, device records or player saves.
import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';
const [mode,file]=process.argv.slice(2);
if(!['before','verify'].includes(mode)||!file)throw Error('Usage: node tools/snapshot_global_stats.mjs before|verify D:/.../stats-before.json');
const endpoint=process.env.EDISON_STATS_ORIGIN;
if(!endpoint)throw Error('Edison has no statistics service configured.');
const origin=new URL(endpoint);
if(origin.protocol!=='https:'||origin.username||origin.password||origin.hostname.endsWith('.hadow--un--esktop.workers.dev'))throw Error('Use an Edison-owned HTTPS statistics origin.');
const target=path.resolve(file);if(!/^D:[\\/]/i.test(target))throw Error('Snapshot must be on D:');
const response=await fetch(new URL((mode==='before'?'/v1':'/v2')+'/stats',origin),{redirect:'error',cache:'no-store',signal:AbortSignal.timeout(15000)});
if(!response.ok)throw Error('Statistics snapshot failed: '+response.status);const totals=await response.json();
for(const key of ['devices','runs','duels','wins','losses','seconds'])assert(Number.isSafeInteger(totals[key])&&totals[key]>=0,'Invalid '+key);
if(mode==='before'){await fs.mkdir(path.dirname(target),{recursive:true});await fs.writeFile(target,JSON.stringify({capturedAt:new Date().toISOString(),totals},null,2),{flag:'wx'});console.log('Saved pre-deployment aggregate snapshot: '+target);}
else{const before=JSON.parse(await fs.readFile(target,'utf8'));for(const key of ['runs','duels','wins','losses','seconds'])assert(totals[key]>=before.totals[key],'Counter decreased: '+key);assert(totals.firstTimePlayers>=before.totals.devices,'Player baseline lost');assert.equal(totals.since,before.totals.since,'History start changed');await fs.writeFile(target+'.verified.json',JSON.stringify({verifiedAt:new Date().toISOString(),totals},null,2),{flag:'wx'});console.log('Verified preserved totals and player baseline');}
