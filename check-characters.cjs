const fs=require('fs'),assert=require('assert'),path=require('path'),os=require('os');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],external=[],overflows=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=route.request().url();if(u.startsWith('http://127.0.0.1:8765/')||u.startsWith('data:'))return route.continue();external.push(u);return route.abort();});
 async function navigate(name){const tab=page.locator(`.studio-nav [data-view="${name}"]`);await tab.evaluate(n=>{const d=n.closest('details');if(d)d.open=true;});await tab.click();}
 const read=route=>page.evaluate(r=>fetch('/api/'+r).then(r=>r.json()),route);
 try{
  await page.goto('http://127.0.0.1:8765/#create');await page.waitForFunction(()=>window.studioReady===true);
  const initialLive=await read('live');
  await page.locator('#video-character').selectOption('lumo');
  await page.waitForFunction(()=>document.querySelector('#avatar').dataset.avatarCharacter==='lumo');
  assert.equal(await page.locator('.video-character-choice[aria-pressed=true]').innerText(),'Lumo');
  const chooserBox=await page.locator('.video-character-chooser').boundingBox(),editorBox=await page.locator('.editor.panel').boundingBox();assert(chooserBox.y<editorBox.y);
  await page.locator('#rate').fill('175');await page.locator('#voice').selectOption('Alice');
  await page.locator('#settings-open').click();assert.equal(await page.locator('#settings-form [name=name],#settings-form [name=color],#settings-form [name=voice]').count(),0);
  const save=page.waitForResponse(r=>r.url().endsWith('/api/settings')&&r.request().method()==='POST');
  await page.locator('#settings-form button[type=submit]').click();await save;
  assert.equal(await page.locator('#video-character').inputValue(),'lumo');assert.equal(await page.locator('#avatar').getAttribute('data-avatar-character'),'lumo');assert.equal(await page.locator('#voice').inputValue(),'Alice');assert.equal(await page.locator('#rate').inputValue(),'175');
  await navigate('live');assert.equal(await page.locator('#live-character').inputValue(),initialLive.config.character_id);const planResponse=page.waitForResponse(r=>r.url().endsWith('/api/broadcast-plan'));await page.locator('#broadcast-form button[type=submit]').click();const plan=await(await planResponse).json();assert.equal(plan.character_id,initialLive.config.character_id);assert(plan.missing.length>0);assert(await page.locator('#broadcast-start').isDisabled());
  await navigate('create');await page.locator('#reset-video-voice').click();
  assert.equal(await page.locator('#voice').inputValue(),'piper:paola');
  await page.locator('#edit-video-character').click();await page.waitForFunction(()=>!document.querySelector('#view-lab').hidden&&document.querySelector('#character-form [name=name]').value==='Lumo');
  assert(await page.locator('#character-body-color').isHidden());assert.equal(await page.locator('#character-form [name=rate]').inputValue(),'160');
  await page.locator('[data-character=nova]').click();assert(await page.locator('#character-body-color').isVisible());
  await page.locator('[data-character=ari]').click();await page.locator('#character-use').click();await page.waitForSelector('#view-create:not([hidden])');
  assert.equal(await page.locator('#video-character').inputValue(),'ari');assert.equal(await page.locator('#avatar').getAttribute('data-avatar-character'),'ari');
  await page.locator('#video-character').selectOption('lumo');await page.reload();await page.waitForFunction(()=>window.studioReady===true&&document.querySelector('#avatar')?.dataset.avatarCharacter==='lumo');
  assert.equal(await page.locator('#video-character').inputValue(),'lumo');
  await navigate('persona');await page.waitForSelector('#persona-character');await page.locator('#persona-character').selectOption('lumo');const lumoConcept=await page.locator('#persona-form [name=concept]').inputValue();await page.locator('#persona-character').selectOption('nova');assert.notEqual(await page.locator('#persona-form [name=concept]').inputValue(),lumoConcept);
  await navigate('plan');await page.locator('.episode-card .episode-actions button').first().click();assert(await page.locator('#episode-form [name=character_id]').inputValue());assert.equal(await page.locator('#episode-form [name=character_id] option[value=""]').count(),0);await page.locator('#episode-close').click();
  for(const size of ['18','22']){await page.locator('#text-size').selectOption(size);for(const width of [1440,390]){await page.setViewportSize({width,height:1050});for(const tab of await page.locator('[data-view]').evaluateAll(ns=>ns.map(n=>n.dataset.view))){await navigate(tab);await page.waitForTimeout(100);const overflowing=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,elements:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&e.getBoundingClientRect().width>0).slice(0,10).map(e=>({tag:e.tagName,id:e.id,cls:e.className,rect:e.getBoundingClientRect().toJSON()}))}));if(overflowing.scroll>width+1)overflows.push({size,tab,...overflowing});}}}
  await page.locator('#text-size').selectOption('18');await page.setViewportSize({width:1440,height:1050});await navigate('create');await page.locator('.video-character-chooser').scrollIntoViewIfNeeded();await page.screenshot({path:'output/characters-create-desktop.png'});
  await page.setViewportSize({width:390,height:844});await page.locator('.video-character-chooser').scrollIntoViewIfNeeded();await page.screenshot({path:'output/characters-create-mobile.png'});
  await page.locator('#script').fill('Ciao, sono Lumo. Ogni personaggio ha la propria voce.');
  const preview=page.waitForResponse(r=>r.url().endsWith('/api/preview'));await page.locator('#preview').click();const r=await(await preview).json();assert.equal(r.project.settings.character.id,'lumo');assert.equal(r.project.settings.name,'Lumo');assert.equal(r.project.settings.character.kind,'illustrated');await page.locator('#preview').click();
  let job=null;
  if(process.env.AVATAR_RENDER_CHECK==='1'){
   await page.locator('#title').fill('Verifica personaggi · Lumo');const rendering=page.waitForResponse(r=>r.url().endsWith('/api/render'));await page.locator('#project-method').selectOption('local');await page.locator('#project-generate').click();job=await(await rendering).json();
  }else if(process.env.AVATAR_RENDER_JOB)job={id:process.env.AVATAR_RENDER_JOB};
  if(job){
   const id=job.id,deadline=Date.now()+180000;
   do{job=(await read('jobs')).find(j=>j.id===id);if(!['queued','running'].includes(job.state))break;await page.waitForTimeout(500);}while(Date.now()<deadline);
   assert.equal(job.state,'done',job.message);
   const project=await page.evaluate(id=>fetch('/output/'+id+'/project.json').then(r=>r.json()),job.id);assert.equal(project.settings.character.id,'lumo');assert.equal(project.settings.character.kind,'illustrated');
  }
  const finalLive=await read('live');assert.equal(finalLive.config.character_id,initialLive.config.character_id);
  const report={video_selection:'lumo',settings_keep_selection:true,reload_keeps_selection:true,per_character_editor:true,per_character_persona:true,explicit_episode_cast:true,live_unchanged:true,tavus_plan_matches_selected_character:true,font_sizes:[18,22],viewports:[1440,390],overflows,errors,external_requests:external,render:job};
  fs.writeFileSync('output/characters-ui-verification.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));assert.deepEqual(errors,[]);assert.deepEqual(external,[]);assert.deepEqual(overflows,[]);
 }catch(error){console.error({errors,external,overflows});throw error;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
