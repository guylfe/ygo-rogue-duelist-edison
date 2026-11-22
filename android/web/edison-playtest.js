const repo='guylfe/ygo-rogue-duelist-edison';
const github=`https://github.com/${repo}`;
const folder='playtest-feedback';
const storageKey='edison-playtest-drafts-v1';
const idPattern=/^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/;
export const noteLimit=500;
const unicode=text=>new TextDecoder().decode(new TextEncoder().encode(text));

function line(value,limit=72){
 return unicode(String(value??'').replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,limit));
}

export function newPlaytestDraft(context,events,id=crypto.randomUUID()){
 const fields=['Version','Screen','Act','Character','Encounter','Opponent','Turn'];
 const details=fields.map(key=>[key,line(context[key])]).filter(([,value])=>value);
 // Cap the actual query cost of the newest events so a full Unicode note still fits the issue URL.
 const log=[];
 let cost=0;
 for(const entry of events.slice(0,14)){
  const event=line(entry,110);
  const size=new URLSearchParams({event}).toString().length;
  if(cost+size>1250)break;
  if(event){log.push(event);cost+=size}
 }
 return {id,details,log,note:'',opened:false,archived:false};
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

const indent=text=>text.split('\n').map(row=>'    '+row).join('\n');
const cleanNote=note=>unicode(note.replace(/\r\n?/g,'\n').replace(/[\u0000-\u0009\u000b-\u001f\u007f]/g,' ').trim());

export const reportLink=id=>`${github}/blob/main/${folder}/${id}.md`;

export function reportMarkdown(draft){
 const log=draft.log.length?draft.log.join('\n'):'No recent game events were available.';
 return `# Edison playtest note\n\nReport ID: \`${draft.id}\`\n\n[Recent game log](#recent-game-log)\n\n## Note\n\n${indent(cleanNote(draft.note))}\n\n## Game context\n\n${indent(draft.details.map(([key,value])=>`${key}: ${value}`).join('\n'))}\n\n## Recent game log\n\n${indent(log)}\n`;
}

export function playtestIssue(draft){
 if(!idPattern.test(draft.id)||!cleanNote(draft.note)||draft.note.length>noteLimit)throw Error('Write a note before opening GitHub.');
 const title=`[Edison playtest] ${draft.id}`;
 const body=`${reportMarkdown(draft)}\n[Archived report after submission](${reportLink(draft.id)})\n`;
 const url=`${github}/issues/new?${new URLSearchParams({title,body})}`;
 if(url.length>7000)throw Error('The report is too long for GitHub. Shorten the note and try again.');
 return {title,body,url};
}

export async function playtestArchived(draft){
 const response=await fetch(`https://api.github.com/repos/${repo}/contents/${folder}/${draft.id}.md?ref=main`,
  {cache:'no-store',credentials:'omit',headers:{Accept:'application/vnd.github.raw+json'},signal:AbortSignal.timeout(8000)});
 if(response.status===404)return false;
 if(!response.ok)throw Error('GitHub could not be checked. Your draft is still saved on this device.');
 if(await response.text()!==reportMarkdown(draft))throw Error('GitHub has a different report with this reference. Your draft is still saved.');
 return true;
}
