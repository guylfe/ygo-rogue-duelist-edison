import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const oldBuild = String(readFileSync(new URL('../VERSION', import.meta.url))).trim();
const storage = new Map([
 ['ygo-cloud-saves-enabled','true'],
 ['ygo-cloud-save-code-v1','K7QXM-4TB9R'],
 ['ygo-cloud-save-state-v1','{"updatedAt":1700000000000}'],
 ['ygo-stats-batches-v2','{"pending":{"duels":99},"batch":null}'],
 ['tag-endpoint','https://old-room.example'],
 ['ygo-global-stats-v1','{"counts":{"seconds":120},"seen":[]}']
]);
const requests = [];
globalThis.localStorage = {
 getItem: key => storage.get(key) ?? null,
 setItem: (key,value) => storage.set(key,value),
 removeItem: key => storage.delete(key)
};
globalThis.location = {hostname:'edison.example',search:'?tagtest=1'};
globalThis.Audio = class { addEventListener(){} };
globalThis.addEventListener = () => {};
globalThis.window = {addEventListener(){}};
globalThis.document = {hidden:false,addEventListener(){}};
globalThis.fetch = async url => {requests.push(url);throw Error('Unexpected network request');};

const {replayVersion,edisonBuild} = await import('./web/replay-version.js');
const {TagUI} = await import('./web/tag-ui.js');
const {CollectorUI} = await import('./web/collector-ui.js');
const {DraftUI} = await import('./web/draft-ui.js');
const {DeviceSync} = await import('./web/device-sync.js');
const {deviceBackup,validateRecovery,recoveryFromFile} = await import('./web/device-backup.js');
const {fetchStats,syncStats,recordStat,personalPlaySeconds} = await import('./web/global-stats.js');
const {sendReplayBatch,sendUnsentFlags,uploadReplays,uploadBehaviour,startRecording,packReplay,unpackReplay} = await import('./web/replays.js');
const {explainOnlineError} = await import('./web/online-status.js');

assert.equal(replayVersion,oldBuild);
assert.equal(edisonBuild,replayVersion+'-edison');
for (const action of [
 () => TagUI.prototype.endpoint.call({}),
 () => CollectorUI.prototype.api.call({},'leaderboard'),
 () => DraftUI.prototype.api.call({},'create'),
 () => new DeviceSync(async () => ({link:{group:'old',token:'old'},progress:{}})).run('sync')
]) await assert.rejects(action,/unavailable in this Edison build/);

assert.equal(await explainOnlineError(Error('Tag Duels, Draft Duels and Ultimate Collector are unavailable in this Edison build.')),
 'Tag Duels, Draft Duels and Ultimate Collector are unavailable in this Edison build.');
assert.equal(deviceBackup.isEnabled(),false);
assert.deepEqual(deviceBackup.status(),{code:null,updatedAt:undefined,error:''});
assert.equal(deviceBackup.migrate(), 'K7QXM-4TB9R');
assert.throws(() => deviceBackup.setEnabled(true),/Cloud Save.*unavailable/);
await assert.rejects(() => deviceBackup.fetchSave('K7QXM-4TB9R'),/Cloud Save.*unavailable/);
await assert.rejects(() => deviceBackup.deleteCloud(),/Cloud Save.*unavailable/);
const files = {'profile.json':'{"wins":3}','slot-1.json':'{"act":2}'};
deviceBackup.queue(JSON.stringify(files));
await deviceBackup.saveNow();
assert.deepEqual(validateRecovery(recoveryFromFile(files)).files,files);
assert.equal(storage.get('ygo-cloud-saves-enabled'),'true');
assert.equal(storage.get('ygo-cloud-save-code-v1'),'K7QXM-4TB9R');

for (const action of [() => sendReplayBatch([]),sendUnsentFlags,uploadReplays,() => uploadBehaviour(null,'test')])
 await assert.rejects(action,/Replay uploads.*unavailable/);
const engine = {};
startRecording(engine,[123n]);
assert.equal(engine.replayRecord.build,edisonBuild);
assert.deepEqual(await unpackReplay(await packReplay(engine.replayRecord)),engine.replayRecord);

await assert.rejects(fetchStats,/Worldwide and character statistics are unavailable/);
recordStat('duels','local-test');
recordStat('duels','local-test');
await syncStats();
assert.equal(personalPlaySeconds(),120);
assert.equal(JSON.parse(storage.get('ygo-global-stats-v1')).counts.duels,1);
assert.equal(JSON.parse(storage.get('ygo-stats-batches-v2')).pending.duels,99);
assert.deepEqual(requests,[]);
console.log('PASS disabled Edison service entry points make zero requests, preserve local data and identify new replay builds');
