// Exercise the shipped web UI with saved, unclaimed rewards at both Act boundaries.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require('./require-module.cjs').requireModule('playwright');

const [build,saves]=process.argv.slice(2);
assert.ok(build&&saves,'Usage: node tools/test_later_act_browser.cjs <PWA directory> <boundary save directory>');
const root=path.resolve(build);
const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json',
 '.css':'text/css','.wasm':'application/wasm','.png':'image/png','.jpg':'image/webp',
 '.webp':'image/webp','.webmanifest':'application/manifest+json'};
const server=http.createServer(async(req,res)=>{
 try{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  const body=await fs.readFile(file);
  res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'}).end(body);
 }catch{res.writeHead(404).end();}
});

async function continueRun(page,start){
 if(start)await page.goto(start);
 await page.waitForFunction(()=>!!window.shadowTest,{},{timeout:120000});
 await page.locator('.menu-card').filter({has:page.getByRole('heading',{name:'Continue',exact:true})}).click();
 await page.locator('[data-do="load-slot"][data-slot="1"]').click();
}

async function boundary(browser,url,act,viewport){
 const backup=await fs.readFile(path.join(saves,`act-${act}-boundary.json`),'utf8');
 const context=await browser.newContext({viewport,reducedMotion:'reduce',serviceWorkers:'block'});
 await context.route('**/*',route=>route.request().url().startsWith(url)?route.continue():route.abort());
 await context.addInitScript(save=>{
  if(!localStorage.getItem('shadow-run-mobile'))localStorage.setItem('shadow-run-mobile',save);
  localStorage.setItem('ygo-preload-visuals','sounds');
  localStorage.setItem('ygo-patch-notes-seen','0.2.47');
 },backup);
 const page=await context.newPage(),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 try{
  await continueRun(page,url);
  const dialog=page.locator('#modal');
  await dialog.locator('.reward-tally').waitFor();
  assert.equal(await dialog.locator('.modal-head h2').textContent(),`Act ${act} · Duel 9 / 9`);
  await dialog.locator('[data-do="reward-slots"]').click();
  assert.equal(await dialog.locator('.modal-head h2').textContent(),`Act ${act} · Duel 9 / 9`);
  await dialog.locator('[data-reward-spin-all]').click();
  await dialog.locator('[data-do="reward-accept"]').click({timeout:30000});
  await dialog.waitFor({state:'hidden'});
  const progress=page.locator('.run-strip.act-progress:visible');
  assert.equal(await progress.getAttribute('aria-label'),`Act ${act} progress: 9 of 9 victories`);
  const pick=page.locator('[data-do="act-add-pack"]').first();
  for(let i=0;i<3;i++)await pick.click();
  await page.locator('[data-do="act-claim"]').click();
  await page.locator('.page.shop').waitFor();
  const checkShop=async()=>{
   assert.equal(await progress.getAttribute('aria-label'),`Act ${act+1} progress: 0 of 9 victories, Duel 1 next`);
   assert.equal(await progress.locator('.next').count(),1);
   assert.equal(await progress.locator('.won').count(),0);
   assert.equal(await progress.locator('.run-strip-label').isVisible(),true);
  };
  await checkShop();
  await page.reload();
  await continueRun(page);
  await page.locator('.page.shop').waitFor();
  await checkShop();
  const state=await page.evaluate(()=>window.shadowTest.state().run);
  assert.equal(state.timeline.length,act*9);
  assert.equal(state.round,0);
  assert.equal(state.later_opponent_act,act+1);
  assert.deepEqual(errors,[]);
  console.log(`PASS Act ${act} → ${act+1}, ${viewport.width}×${viewport.height}: saved rewards, next-Act shop, and reload`);
 }finally{await context.close();}
}

(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const url=`http://127.0.0.1:${server.address().port}/`;
 let browser;
 try{
  browser=await chromium.launch({headless:true,channel:'chrome'});
  await boundary(browser,url,1,{width:390,height:844});
  await boundary(browser,url,2,{width:844,height:390});
 }finally{await browser?.close();server.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
