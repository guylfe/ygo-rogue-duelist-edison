// Run normal menu, selection, continue, duel and results interactions in both packaged clients.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require('./require-module.cjs').requireModule('playwright');

const [pwa,android,fixtures]=process.argv.slice(2);
assert.ok(pwa&&android&&fixtures,'Usage: node tools/test_act_character_browser.cjs <PWA> <APK assets/web> <fixtures>');
const version=require('node:fs').readFileSync(path.join(__dirname,'../VERSION'),'utf8').trim();
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json',
 '.css':'text/css','.wasm':'application/wasm','.png':'image/png','.jpg':'image/webp','.webp':'image/webp'};
const roots={web:path.resolve(pwa),android:path.resolve(android)};
const createServer=root=>http.createServer(async(req,res)=>{
 try{
  const relative=decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1);
  const file=path.resolve(root,relative||'index.html');
  if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return}
  const body=await fs.readFile(file);
  res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'}).end(body);
 }catch{res.writeHead(404).end()}
});
const button=(page,action)=>page.locator(`[data-do="${action}"]`);
const series=(page,name)=>page.locator('.duelist-series').getByRole('button',{name,exact:true});
const textHas=async(locator,pattern)=>{
 await locator.waitFor();
 assert.match(await locator.textContent(),pattern);
};

async function open(browser,url,client,save){
 const context=await browser.newContext({viewport:{width:844,height:390},reducedMotion:'reduce',serviceWorkers:'block'});
 await context.addInitScript(({client,backup,version})=>{
  localStorage.setItem('ygo-preload-visuals','sounds');
  localStorage.setItem('ygo-patch-notes-seen',version);
  if(client==='android'){
   window.ShadowNative={
    load:()=>localStorage.getItem('roster-qa-android')||backup,
    store:data=>{localStorage.setItem('roster-qa-android',data);return true},
   };
  }else if(backup!=='{}'&&!localStorage.getItem('shadow-run-mobile')){
   localStorage.setItem('shadow-run-mobile',backup);
  }
 },{client,version,backup:save?await fs.readFile(path.join(fixtures,save+'.json'),'utf8'):'{}'});
 const page=await context.newPage();
 const errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(url);
 try{
  await page.waitForFunction(()=>window.shadowTest||document.querySelector('#retry-startup'),{},{timeout:180000});
  assert.ok(await page.evaluate(()=>!!window.shadowTest),'Game startup failed');
 }
 catch(error){console.error(client,save,errors,(await page.locator('body').innerText()).slice(0,600));await context.close();throw error}
 assert.equal(await page.locator('.title-version').textContent(),'v'+version);
 const offlineOffer=page.locator('#web-offline-offer [data-later]');
 if(await offlineOffer.isVisible())await offlineOffer.click();
 return {page,context,errors};
}

async function selectSavedRun(page,slot=1){
 await titleEntry(page,'Continue');
 await page.locator(`[data-do="load-slot"][data-slot="${slot}"]`).click();
}

async function titleEntry(page,name){
 const card=page.locator('.menu-card').filter({has:page.locator('h3',{hasText:new RegExp('^'+name+'$')})});
 const center=page.locator('.menu-card[data-distance="0"]');
 const id=await card.getAttribute('data-menu');
 for(let step=0;step<15;step++){
  const before=await center.getAttribute('data-menu');
  if(before===id){await card.click();return}
  await page.keyboard.press('ArrowRight');
  await page.waitForFunction(old=>document.querySelector('.menu-card[data-distance="0"]')?.dataset.menu!==old,before);
 }
 throw new Error('Could not center the '+name+' menu card');
}

async function openRoster(page){
 await titleEntry(page,'New Run');
 const skip=page.getByRole('button',{name:'Yes, start my run'});
 await skip.or(page.locator('.duelist-series')).waitFor();
 if(await skip.isVisible())await skip.click();
}

async function freshRoster(page){
 await openRoster(page);
 for(const [name,pair] of [['Duel Monsters',[0,1]],['GX',[98,99]],["5D's",[106,107]]]){
  await series(page,name).click();
  const available=await page.locator('.roster .portrait:not(.locked)').evaluateAll(nodes=>nodes.map(n=>+n.dataset.character));
  assert.deepEqual(available,pair);
  const newcomers=page.locator('.roster .portrait').filter({has:page.locator('img')});
  for(const entry of await newcomers.all()){
   const id=Number(await entry.getAttribute('data-character'));
   if(id<112)continue;
   await entry.click();
   const hero=page.locator('.duelist-hero img');
   assert.equal(await hero.getAttribute('alt'),await entry.locator('span').textContent());
   const cover=page.locator('.duelist-selection img[data-do="inspect-pack"]').first();
   for(const art of [hero,cover]){
    await art.evaluate(async img=>{await img.decode();if(!img.naturalWidth)throw Error('Empty duelist art: '+img.src)});
   }
  }
 }
 await page.locator('[data-character="109"]').click();
 assert.equal(await button(page,'new').isDisabled(),true);
 await textHas(button(page,'new'),/Buy 6 single cards in Act III shops · 0 \/ 6/);
 await page.locator('[data-character="107"]').click();
 await button(page,'new').click();
 await page.locator('[data-do="new-slot"][data-slot="1"]').click();
 await button(page,'act-starter').first().waitFor();
 const run=await page.evaluate(()=>window.shadowTest.state().run);
 assert.equal(run.character,107);
 assert.equal(run.act,1);
}

async function legacyProfile(page){
 await openRoster(page);
 await series(page,'GX').click();
 assert.equal(await page.locator('[data-character="100"].locked').count(),1);
 assert.equal(await page.locator('[data-character="103"]:not(.locked)').count(),1);
 await series(page,"5D's").click();
 assert.equal(await page.locator('[data-character="108"]:not(.locked)').count(),1);
 await page.reload();
 await page.waitForFunction(()=>!!window.shadowTest,{},{timeout:120000});
 await selectSavedRun(page,2);
 await button(page,'act-starter').first().waitFor();
 assert.equal(await page.evaluate(()=>window.shadowTest.state().run.character),108);
}

async function returnEncounter(page,act,resume){
 const roman=act===2?'II':'III',name=`Mako Tsunami (Act ${roman})`;
 await selectSavedRun(page);
 if(!resume){
  await page.locator('.shop-next[data-do="routes"]').click();
  const route=page.locator('.opponent[data-encounter="18"]');
  await route.locator('[data-do="preview-win"]').click();
  assert.equal(await page.locator('#modal h2').textContent(),'Opponent card preview');
  await page.locator('#modal [data-do="close"]').first().click();
  await route.locator('[data-do="reveal-opponent"]').click();
  await page.locator('#modal [data-confirmed="1"]').click();
  assert.equal(await route.locator('h2').textContent(),name);
  await page.locator('.portrait-reveal-flash').waitFor({state:'hidden'});
  await route.locator('[data-do="preview-win"]').click();
  assert.equal(await page.locator('#modal h2').textContent(),name+' · Card preview');
  await page.locator('#modal [data-do="close"]').first().click();
  await route.locator('[data-do="start"]').click();
  await page.getByText(name,{exact:true}).first().waitFor();
 }
 const nameplate=page.locator('.duel .life.enemy span:not(.life-meter)');
 await nameplate.waitFor();
 assert.equal(await nameplate.textContent(),name);
 await button(page,'duel-options').click();
 await button(page,'surrender').click();
 await button(page,'confirm-surrender').click();
 await textHas(page.locator('.run-end-left'),new RegExp(`Defeated by Mako Tsunami \\(Act ${roman}\\)`));
 const timeline=await page.evaluate(()=>window.shadowTest.state().history[0].timeline);
 assert.equal(timeline.at(-1).opponent_variant_act,act);
 await button(page,'title').click();
 await titleEntry(page,'Collection');
 await page.locator('[data-do="collection-kind"][data-kind="history"]').click();
 const details=page.locator('.run-history-row').first().locator('details');
 await details.locator('summary').click();
 await textHas(details.locator('.run-timeline .lost').last(),new RegExp(`Mako Tsunami \\(Act ${roman}\\)`));
 const keys=await details.locator('.run-replay').evaluateAll(nodes=>nodes.map(n=>n.dataset.key));
 assert.equal(keys.length,new Set(keys).size);
}

async function victoryReceipt(page){
 await selectSavedRun(page);
 const dialog=page.locator('#modal');
 await textHas(dialog.locator('.reward-tally'),/Seto Kaiba \(Act II\) defeated/);
 await dialog.locator('[data-do="reward-slots"]').click();
 await textHas(dialog.locator('.reward-screen header'),/Seto Kaiba \(Act II\) defeated/);
 assert.ok(await page.evaluate(()=>window.shadowTest.state().profile.unlocked.includes(104)));
 await dialog.locator('[data-reward-spin-all]').click();
 await dialog.locator('[data-do="reward-accept"]').click({timeout:30000});
 await page.locator('[data-do="cursed-choose"]').first().click();
 const pick=page.locator('[data-do="act-add-pack"]').first();
 for(let i=0;i<3;i++)await pick.click();
 await button(page,'act-claim').click();
 await page.locator('.page.shop').waitFor();
 const after=await page.evaluate(()=>window.shadowTest.state());
 assert.equal(after.run.act,3);
 assert.equal(after.run.round,0);
 assert.ok(after.profile.unlocked.includes(104));
 assert.equal(after.profile.campaign_unlock_progress['3'],undefined);
}

(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome',
  args:['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1']});
 try{
  for(const client of ['web','android'].filter(target=>!process.env.EDISON_TEST_CLIENT||target===process.env.EDISON_TEST_CLIENT)){
   const server=createServer(roots[client]);
   await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
   try{
    const url=`http://127.0.0.1:${server.address().port}/`;
    for(const [name,fixture,run] of [
     ['fresh roster',null,freshRoster],['legacy profile','legacy-profile',legacyProfile],
     ['Act II routes and duel','act-2-mako',page=>returnEncounter(page,2,false)],
     ['Act III in-flight duel','act-3-mako-resume',page=>returnEncounter(page,3,true)],
     ['Act II receipt and transition','act-2-receipt',victoryReceipt],
    ].filter(([name])=>!process.env.EDISON_TEST_CASE||name.includes(process.env.EDISON_TEST_CASE))){
     const {page,context,errors}=await open(browser,url,client,fixture);
     const consoleErrors=[];
     page.on('console',line=>{if(line.type()==='error')consoleErrors.push(line.text())});
     try{await run(page);assert.deepEqual(errors,[]);console.log(`PASS ${client} ${name}`)}
     catch(error){console.error(name,errors,consoleErrors.slice(-8),(await page.locator('body').innerText()).slice(0,750));throw error}
     finally{await context.close()}
    }
   }finally{server.close()}
  }
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
