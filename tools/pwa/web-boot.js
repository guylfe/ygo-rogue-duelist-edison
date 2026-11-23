import {replayVersion} from './replay-version.js';

const versionParts=value=>typeof value==='string'&&/^\d+\.\d+\.\d+$/.test(value)?value.split('.').map(Number):null;
function newer(candidate,current){
 const next=versionParts(candidate),now=versionParts(current);
 if(!next||!now)return false;
 const changed=next.findIndex((part,i)=>part!==now[i]);
 return changed!==-1&&next[changed]>now[changed];
}
async function liveVersion(){
 if(navigator.onLine===false)return null;
 try{
  const response=await fetch('live-version.json',{cache:'no-store',signal:AbortSignal.timeout(2500)});
  if(!response.ok)return null;
  const latest=await response.json();
  return newer(latest.version,replayVersion)&&/^[a-f0-9]{16}$/.test(latest.assetVersion)?latest:null;
 }catch{return null}
}
function installed(worker){
 if(!worker||worker.state!=='installing')return Promise.resolve();
 return new Promise(resolve=>{
  const done=()=>{
   if(worker.state==='installing')return;
   worker.removeEventListener('statechange',done);resolve();
  };
  worker.addEventListener('statechange',done);
  done();
 });
}
function getWorkerVersion(worker){
 return new Promise(resolve=>{
  const channel=new MessageChannel();
  const dispose=()=>channel.port1.close();
  const timer=setTimeout(()=>{dispose();resolve(null)},2500);
  channel.port1.onmessage=({data})=>{clearTimeout(timer);dispose();resolve(data?.version)};
  worker.postMessage({type:'OFFLINE_STATUS'},[channel.port2]);
 });
}
async function activate(worker){
 const service=navigator.serviceWorker;
 await new Promise((resolve,reject)=>{
  const finish=error=>{
   clearTimeout(timer);
   service.removeEventListener('controllerchange',changed);
   service.removeEventListener('message',message);
   if(error)reject(Error(error));else resolve();
  };
  const changed=()=>finish();
  const message=({data})=>{if(data?.type==='UPDATE_BLOCKED')finish('Close the other Edison tabs, then try again.')};
  const timer=setTimeout(()=>finish('Edison could not switch builds. Try again.'),8000);
  service.addEventListener('controllerchange',changed);
  service.addEventListener('message',message);
  worker.postMessage({type:'SKIP_WAITING'});
 });
}

function assertTitle(){
 if(!document.querySelector('.edison-startup-update'))throw Error('Return to the main menu to apply the update.');
}

async function install(latest,status){
 const verified=await liveVersion();
 if(!verified||verified.version!==latest.version||verified.assetVersion!==latest.assetVersion){
  throw Error('The live build changed. Reopen Edison to check again.');
 }
 const registration=await navigator.serviceWorker?.getRegistration('./');
 if(!registration){assertTitle();location.reload();return}
 const progress=({data})=>{
  if(data?.type==='CACHE_PROGRESS')status('Checking game files · '+data.done+' / '+data.total);
 };
 status('Preparing Edison '+latest.version+'…');
 navigator.serviceWorker.addEventListener('message',progress);
 try{
  await registration.update();
  await installed(registration.installing);
  const waiting=registration.waiting;
  if(waiting&&await getWorkerVersion(waiting)===latest.assetVersion){
   assertTitle();
   await activate(waiting);
  }
  else if(!registration.active||await getWorkerVersion(registration.active)!==latest.assetVersion){
   throw Error('Edison could not verify the downloaded build. Try again.');
  }
  assertTitle();
  location.reload();
 }finally{navigator.serviceWorker.removeEventListener('message',progress)}
}

if(!window.ShadowNative)void liveVersion().then(latest=>{
 if(!latest)return;
 window.EdisonWebUpdate={version:latest.version,install:status=>install(latest,status)};
 window.dispatchEvent(new Event('edison-update-available'));
});
await Promise.all([import('./mobile.js'),import('./pwa.js')]);
