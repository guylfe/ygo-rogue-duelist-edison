import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';

const repo='guylfe/ygo-rogue-duelist-edison';
const ownerId=127800290;
const github=`https://github.com/${repo}`;
const idPattern='[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
const headers=['## Note','## Game context','## Recent game log'];

function block(section,header){
 if(!section.startsWith(header+'\n\n'))throw Error('Report section is missing.');
 const lines=section.slice(header.length+2).split('\n');
 if(lines.some(line=>!line.startsWith('    ')))throw Error('Report sections must contain plain indented text.');
 return lines.map(line=>line.slice(4));
}

export function parseIssue(event){
 if(event.action!=='opened'||event.repository?.full_name!==repo||event.sender?.id!==ownerId||event.issue?.user?.id!==ownerId)
  throw Error('This issue is outside the Edison playtest archive.');
 const id=event.issue.title?.match(new RegExp(`^\\[Edison playtest\\] (${idPattern})$`))?.[1];
 if(!id||typeof event.issue.body!=='string'||Buffer.byteLength(event.issue.body)>3500)throw Error('Invalid Edison playtest report.');
 const path=`playtest-feedback/${id}.md`;
 const link=`${github}/blob/main/${path}`;
 const prefix=`# Edison playtest note\n\nReport ID: \`${id}\`\n\n[Recent game log](#recent-game-log)\n\n`;
 const suffix=`\n\n[Archived report after submission](${link})`;
 const body=event.issue.body.replace(/\r\n/g,'\n').trimEnd();
 if(!body.startsWith(prefix)||!body.endsWith(suffix)||/[\u0000-\u0009\u000b-\u001f\u007f]/.test(body))throw Error('Malformed Edison playtest report.');
 const archive=body.slice(0,-suffix.length);
 const sections=archive.slice(prefix.length).split(/\n\n(?=## (?:Game context|Recent game log)\n)/);
 if(sections.length!==3)throw Error('Unexpected number of report sections.');
 const [note,context,log]=sections.map((section,i)=>block(section,headers[i]));
 if(!note.join('\n').trim()||note.join('\n').length>500||log.length>14||log.some(line=>!line||line.length>110))
  throw Error('Report text exceeds the permitted bounds.');
 const fields=new Map();
 for(const line of context){
  const match=line.match(/^(Version|Screen|Act|Character|Encounter|Opponent|Turn): (.{1,72})$/u);
  if(!match||fields.has(match[1]))throw Error('Unknown or repeated game context field.');
  fields.set(match[1],match[2]);
 }
 if(!/^\d{1,5}\.\d{1,5}\.\d{1,5}$/.test(fields.get('Version')||'')||
    !['Starter','Deck building','Route select','Shop','Act transition','Duel'].includes(fields.get('Screen'))||
    ['Act','Encounter','Turn'].some(key=>fields.has(key)&&!/^\d{1,6}$/.test(fields.get(key))))throw Error('Invalid game context.');
 return {id,path,link,content:archive+'\n'};
}

export async function archiveReport(report,request){
 const url=`https://api.github.com/repos/${repo}/contents/${report.path}`;
 // A retry always targets the original file. The create request never supplies an existing blob SHA.
 for(let attempt=0;attempt<3;attempt++){
  const existing=await request(`${url}?ref=main`);
  if(existing.ok){
   const file=await existing.json();
   if(file.encoding!=='base64'||Buffer.from(file.content,'base64').toString('utf8')!==report.content)
    throw Error('The report reference is already in use.');
   return 'already archived';
  }
  if(existing.status!==404)throw Error(`Could not check archive (${existing.status}).`);
  const result=await request(url,{method:'PUT',body:JSON.stringify({branch:'main',message:`Archive Edison playtest note ${report.id}`,content:Buffer.from(report.content).toString('base64')})});
  if(result.status===201)return 'archived';
  if(result.status!==409&&result.status!==422)throw Error(`Could not write archive (${result.status}).`);
 }
 throw Error('The report could not be archived after concurrent writes.');
}

if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const report=parseIssue(JSON.parse(await readFile(process.env.GITHUB_EVENT_PATH,'utf8')));
 const request=(url,options={})=>fetch(url,{...options,headers:{Authorization:`Bearer ${process.env.GH_TOKEN}`,
  Accept:'application/vnd.github+json','Content-Type':'application/json'},signal:AbortSignal.timeout(15000)});
 const result=await archiveReport(report,request);
 console.log(`${result}: ${report.link}`);
}
