// Read-only UI audit. Slow generation/preview responses are simulated.
const fs=require('fs'),assert=require('assert');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const base=process.env.AVATAR_TEST_URL||'http://127.0.0.1:8765';
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],external=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(!r.url().startsWith(base+'/')&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))external.push(r.url());});
 await page.addInitScript(()=>{const Original=window.Audio;window.auditAudioCount=0;window.Audio=class extends Original{constructor(...args){super(...args);window.auditAudioCount++;}};});
 try{
  await page.goto(base+'/?edition=lab#create');await page.waitForFunction(()=>window.studioReady===true);
  let releaseScript,scriptSeen;const scriptStarted=new Promise(r=>scriptSeen=r);
  await page.route('**/api/script',async route=>{scriptSeen();await new Promise(r=>releaseScript=r);await route.fulfill({json:{script:'Questa bozza appartiene al vecchio argomento.',note:'Simulazione'}});});
  await page.locator('#script').fill('Il mio testo da conservare.');await page.locator('#topic-tab').click();await page.locator('#topic').fill('Argomento iniziale');await page.locator('#generate').click();await scriptStarted;
  await page.locator('#topic').fill('Argomento nuovo');releaseScript();
  await page.waitForFunction(()=>!document.querySelector('#generate').disabled);
  assert.equal(await page.locator('#script').inputValue(),'Il mio testo da conservare.');assert.match(await page.locator('#status').innerText(),/cambiato/);
  let releasePreview,previewSeen;const previewStarted=new Promise(r=>previewSeen=r);
  await page.route('**/api/preview',async route=>{previewSeen();await new Promise(r=>releasePreview=r);await route.fulfill({json:{audio:'/never-play.wav',project:{duration:1,captions:[],envelope:[],settings:{}}}});});
  const audioBefore=await page.evaluate(()=>window.auditAudioCount);
  await page.locator('#preview').click();await previewStarted;
  await page.locator('#script').fill('Il testo modificato mentre la voce viene preparata.');
  const reply=page.waitForResponse(r=>r.url().endsWith('/api/preview'));releasePreview();await reply;
  await page.waitForFunction(()=>!document.querySelector('#preview').dataset.loading);
  assert.equal(await page.evaluate(()=>window.auditAudioCount),audioBefore);
  await page.unroute('**/api/preview');
  await page.locator('[data-view="lab"]').click();await page.locator('[data-character="ari"]').click();
  let releaseLab,labSeen;const labStarted=new Promise(r=>labSeen=r);
  await page.route('**/api/preview',async route=>{labSeen();await new Promise(r=>releaseLab=r);await route.fulfill({json:{audio:'/never-play.wav',project:{duration:1,captions:[],envelope:[],settings:{}}}});});
  const labAudioBefore=await page.evaluate(()=>window.auditAudioCount);
  await page.locator('#lab-listen').click();await labStarted;await page.locator('[data-character="lumo"]').click();
  const labReply=page.waitForResponse(r=>r.url().endsWith('/api/preview'));releaseLab();await labReply;
  await page.waitForFunction(()=>!document.querySelector('#lab-listen').disabled);
  assert.equal(await page.evaluate(()=>window.auditAudioCount),labAudioBefore);
  const sections=await page.locator('[data-view]').evaluateAll(nodes=>nodes.map(n=>n.dataset.view));
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1050});await page.locator('#text-size').selectOption('22');
   for(const name of sections){await page.locator(`[data-view="${name}"]`).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`Overflow ${name} ${width}`);}
  }
  await page.locator('[data-view="create"]').click();await page.screenshot({path:'output/audit-ui-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={stale_topic_response_rejected:true,stale_preview_not_played:true,lab_preview_keeps_selected_character:true,sections:sections.length,text_size:22,widths:[1440,390],errors,external_requests:external};
  fs.writeFileSync('output/audit-ui-verification.json',JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
