const storageKey='edison-playtest-drafts-v1';
const idPattern=/^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/;
export const noteLimit=500;
const endpoint='https://guylfe-game-feedback.netlify.app/v3/feedback';
const filePath=id=>`playtest-feedback/${id}.json`;

function playtestId(){
 if(crypto.randomUUID)return crypto.randomUUID();
 const bytes=crypto.getRandomValues(new Uint8Array(16));
 bytes[6]=(bytes[6]&15)|64;
 bytes[8]=(bytes[8]&63)|128;
 const hex=Array.from(bytes,byte=>byte.toString(16).padStart(2,'0')).join('');
 return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
}

export function playtestReceipt(draft){
 return draft.filePath===filePath(draft.id)?draft.filePath:null;
}

export function playtestPreviouslySent(draft){
 return draft.archived===true||(Number.isSafeInteger(draft.issueNumber)&&draft.issueNumber>0);
}

export function pendingPlaytestDrafts(){
 return loadPlaytestDrafts().filter(draft=>draft.queued&&!playtestReceipt(draft)&&!playtestPreviouslySent(draft));
}

export async function postPlaytest(draft,version){
 const details=Object.fromEntries(draft.details);
 const response=await fetch(endpoint,{
  method:'POST',credentials:'omit',redirect:'error',cache:'no-store',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({game:'edison',reportId:draft.id,build:draft.submittedBuild||details.Version||version,
   note:cleanNote(draft.note),context:{details,recentEvents:draft.log}}),
  signal:AbortSignal.timeout(8000)
 });
 if(response.status===202||response.status===429||response.status>=500){
  const header=response.headers.get('Retry-After');
  const retryAt=/^\d+$/.test(header||'')?Date.now()+Number(header)*1000:Date.parse(header||'');
  return Number.isFinite(retryAt)&&retryAt>Date.now()?{pending:true,retryAt}:{pending:true};
 }
 if(response.status===409||response.status===400)return {rejected:true};
 if(response.status!==200)throw Error('Feedback service could not be reached.');
 const receipt=await response.json();
 if(receipt?.game!=='edison'||receipt.reportId!==draft.id||receipt.filePath!==filePath(draft.id)){
  throw Error('Invalid feedback receipt.');
 }
 return {filePath:receipt.filePath};
}

const unicode=text=>new TextDecoder().decode(new TextEncoder().encode(text));

function line(value,limit=72){
 return unicode(String(value??'').replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,limit));
}

export function newPlaytestDraft(context,events,id=playtestId()){
 const fields=['Version','Screen','Act','Character','Encounter','Opponent','Turn'];
 const details=fields.map(key=>[key,line(context[key])]).filter(([,value])=>value);
 const log=events.slice(0,14).map(entry=>line(entry,110)).filter(Boolean);
 return {id,details,log,note:''};
}

export function loadPlaytestDrafts(){
 try{
  const drafts=JSON.parse(localStorage.getItem(storageKey)||'[]');
  if(Array.isArray(drafts))return drafts.filter(draft=>draft&&idPattern.test(draft.id)&&Array.isArray(draft.details)&&Array.isArray(draft.log)&&typeof draft.note==='string');
 }catch{}
 return [];
}

export function savePlaytestDraft(draft){
 try{
  const drafts=loadPlaytestDrafts().filter(other=>other.id!==draft.id);
  localStorage.setItem(storageKey,JSON.stringify([draft,...drafts]));
  return true;
 }catch{return false}
}

const cleanNote=note=>unicode(note.replace(/\r\n?/g,'\n').replace(/[\u0000-\u0009\u000b-\u001f\u007f]/g,' ').trim());
