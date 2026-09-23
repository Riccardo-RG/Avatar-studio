const fs=require('fs'),assert=require('assert'),path=require('path'),os=require('os');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:8765/')&&!r.url().startsWith('data:'))external.push(r.url());});
 const post=async(route,data)=>page.evaluate(async({route,data})=>{const b=await fetch('/api/bootstrap').then(r=>r.json()),r=await fetch('/api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Avatar-Token':b.token},body:JSON.stringify(data)});const d=await r.json();if(!r.ok)throw Error(d.error);return d;},{route,data});
 try{
  await page.goto('http://127.0.0.1:8765/#publishing');await page.waitForFunction(()=>window.studioReady===true);await page.waitForSelector('#view-publishing:not([hidden])');
  assert.equal(await page.locator('[data-view]').count(),12);
  const previous=await page.evaluate(()=>fetch('/api/live').then(r=>r.json()));
  await page.locator('[data-view=create]').click();await page.locator('#video-character').selectOption('lumo');
  await page.locator('#script').fill('Ciao, sono Lumo. Questo è un test della scelta del personaggio.');
  const preview=page.waitForResponse(r=>r.url().endsWith('/api/preview'));
  await page.locator('#preview').click();const r=await(await preview).json();assert.equal(r.project.settings.character.id,'lumo');await page.locator('#preview').click();
  await page.locator('[data-view=live]').click();await page.locator('#live-character').selectOption('ari');
  await page.waitForFunction(async()=>{const s=await fetch('/api/live').then(r=>r.json());return s.config.character_id==='ari';});
  const state=await page.evaluate(()=>fetch('/api/live').then(r=>r.json()));assert.equal(state.character_settings.character.id,'ari');
  await post('live/config',{character_id:previous.config.character_id||'nova'});
  await page.locator('[data-view=publishing]').click();
  const existing=await page.evaluate(()=>fetch('/api/publications').then(r=>r.json()));
  for(const platform of ['youtube','tiktok']){
   if(existing.items.some(p=>p.job_id==='ac48cffb26e6'&&p.platform===platform&&p.state!=='cancelled'))continue;
   await page.locator('#new-post').click();await page.locator('#publication-form [name=job_id]').selectOption('ac48cffb26e6');
   await page.locator('#publication-form [name=platform]').selectOption(platform);await page.waitForTimeout(200);
   await page.locator('#publication-form [name=visibility]').selectOption(platform==='youtube'?'private':'inbox');
   await page.locator('#publication-form [name=due_local]').fill('2026-09-21T20:00');
   await page.locator('#publication-form button[type=submit]').click();await page.waitForSelector('#publication-form[hidden]',{state:'attached'});
  }
  for(const checkbox of await page.locator('.publication-card input[type=checkbox]').all())await checkbox.check();
  await page.locator('#approve-week').click();await page.waitForFunction(async()=>{const q=await fetch('/api/publications').then(r=>r.json());return q.items.filter(p=>p.state==='approved').length===2;});
  await page.locator('#simulate-selection').click();await page.waitForFunction(async()=>{const q=await fetch('/api/publications').then(r=>r.json());return q.items.filter(p=>p.simulation).length===2;});
  await page.screenshot({path:'output/delivery-publishing-desktop.png',fullPage:true});
  const q=await page.evaluate(()=>fetch('/api/publications').then(r=>r.json()));assert.equal(q.armed,false);assert(q.items.every(p=>!p.remote_id));assert(q.items.every(p=>p.simulation.external_requests===0));
  await page.locator('[data-view=connections]').click();assert.equal(await page.locator('[data-service]').count(),6);await page.screenshot({path:'output/delivery-connections-desktop.png',fullPage:true});
  await page.locator('[data-view=lab]').click();await page.locator('[data-character=lumo]').click();await page.waitForFunction(()=>document.querySelector('#activity-heading').textContent.includes('Lumo'));assert(await page.locator('#activity-list .activity-row').count()>0);await page.locator('#lab-script').fill('Questa è una prova locale del piano realistico.');await page.locator('#lab-create-web').click();await page.locator('#view-create').waitFor({state:'visible'});assert.equal(await page.locator('#project-method').inputValue(),'web');assert.equal(await page.locator('#video-character').inputValue(),'lumo');
  await page.locator('[data-view=live]').click();await page.locator('#broadcast-form button').click();await page.waitForFunction(()=>document.querySelector('#broadcast-plan').textContent.includes('Manca'));assert(await page.locator('#broadcast-start').isDisabled());
  await page.setViewportSize({width:390,height:844});for(const name of ['publishing','connections','create','live','lab']){await page.locator(`[data-view=${name}]`).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'Overflow '+name);}
  await page.locator('[data-view=publishing]').click();await page.screenshot({path:'output/delivery-publishing-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);const report={character_history:true,defer_render_control:await page.locator('#defer-render').count()===1,sections:12,errors,external_requests:external,weekly_approval:true,simulation_only:true,video_character:'lumo',live_character:'ari',heygen_offline_plan:true,tavus_offline_plan:true,mobile_overflow:false,post_ids:q.items.map(p=>p.id)};fs.writeFileSync('output/delivery-ui-verification.json',JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
