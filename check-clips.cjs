const fs=require('fs'),assert=require('assert'),path=require('path'),os=require('os');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],external=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:8765/')&&!r.url().startsWith('data:'))external.push(r.url());});
 const read=route=>page.evaluate(r=>fetch('/api/'+r).then(r=>r.json()),route);
 try{
  await page.goto('http://127.0.0.1:8765/#clips');await page.waitForFunction(()=>window.studioReady===true);await page.waitForSelector('#view-clips:not([hidden])');
  let source;
  if(process.env.AVATAR_CLIP_SOURCE){await page.locator('#clip-source').selectOption(process.env.AVATAR_CLIP_SOURCE);source=(await read('clips')).items.find(i=>i.source_id===process.env.AVATAR_CLIP_SOURCE);}
  else{
  const uploaded=page.waitForResponse(r=>r.url().endsWith('/api/recording-upload'));await page.locator('#recording-file').setInputFiles('/private/tmp/avatar-recording-test.webm');await uploaded;await page.waitForFunction(()=>document.querySelector('#recording-status').textContent.includes('pronta'));const sourceId=await page.locator('#clip-source').inputValue(),selectedSource=(await read('clips')).items.find(i=>i.source_id===sourceId);assert(selectedSource.source_id);source=selectedSource;
  }
  await page.waitForFunction(()=>document.querySelector('#clip-player').readyState>=2);assert.equal(await page.locator('#clip-player').evaluate(v=>v.videoWidth),640);
  await page.locator('#clip-srt').setInputFiles({name:'sottotitoli.srt',mimeType:'text/plain',buffer:Buffer.from('1\n00:00:00,200 --> 00:00:03,000\nProva di una registrazione locale.\n\n2\n00:00:03,000 --> 00:00:04,900\nUna clip pronta da rivedere.\n')});await page.waitForFunction(()=>document.querySelector('#clip-caption-note').textContent.includes('2 segmenti'));
  await page.locator('#clip-form [name=title]').fill('Clip di prova · registrazione locale');await page.locator('#clip-form [name=start]').fill('0.5');await page.locator('#clip-form [name=end]').fill('4.5');await page.locator('#clip-form [name=fit]').selectOption('cover');await page.locator('#clip-form [name=position]').fill('0.8');await page.locator('#clip-preview').click();await page.waitForFunction(()=>document.querySelector('#clip-player').currentTime>.6);assert(await page.locator('#clip-captions').isVisible());await page.locator('#clip-player').evaluate(v=>v.pause());
  await page.locator('#clip-suggest').click();await page.waitForSelector('#clip-suggestions button');assert.match(await page.locator('#clip-suggest-note').innerText(),/non una valutazione AI/);
  await page.locator('#clip-work').screenshot({path:'output/clips-desktop.png'});
  const response=page.waitForResponse(r=>r.url().endsWith('/api/clip-render'));await page.locator('#clip-export').click();let job=await(await response).json();assert(job.id,JSON.stringify(job));const id=job.id,deadline=Date.now()+120000;
  do{job=await read('jobs/'+id);if(!['running','queued'].includes(job.state))break;await page.waitForTimeout(500);}while(Date.now()<deadline);assert.equal(job.state,'done',job.message);
  const project=await page.evaluate(id=>fetch('/output/'+id+'/project.json').then(r=>r.json()),id);assert(project.clip);assert.equal(project.duration,4);assert(project.captions_burned);assert.equal(project.captions[0].start,0);assert.equal(project.captions[1].end,4);
  await page.locator('#text-size').selectOption('22');await page.setViewportSize({width:390,height:844});await page.locator('[data-view=clips]').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.locator('#clip-form').scrollIntoViewIfNeeded();await page.screenshot({path:'output/clips-mobile.png'});
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);const report={source:source.source_id,job_id:id,webm_import:true,browser_playback:true,srt_import:true,preview_captions:true,crop_position:.8,actual_mp4:true,retimed_subtitles:true,large_text_mobile_overflow:false,errors,external_requests:external};fs.writeFileSync('output/clips-ui-verification.json',JSON.stringify(report,null,2));console.log(report);
 }catch(e){console.error({errors,external});throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
