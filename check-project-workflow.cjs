// End-to-end project workflow. Requires disposable data and a completed local MP4 fixture.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const runtime=require('./runtime_config.cjs');
const {chromium}=require(runtime.playwright);

(async()=>{
 const base=process.env.AVATAR_TEST_URL;
 if(!base||process.env.AVATAR_ISOLATED_TEST!=='1')throw Error('Serve una copia isolata esplicitamente dichiarata.');
 const browser=await chromium.launch({executablePath:runtime.chrome,headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[],external=[],legacyRenders=[],gates=[];
 let checkingWebsiteFlow=true;
 page.on('pageerror',error=>errors.push(error.message));
 page.on('request',request=>{
  if(checkingWebsiteFlow&&request.method()==='POST'&&/^\/api\/(render|series-render|cloud-quote|cloud-render)$/.test(new URL(request.url()).pathname))legacyRenders.push(request.url());
 });
 await page.route('**/*',route=>{
  const url=route.request().url();
  if(!url.startsWith(base+'/')&&!/^(data|blob):/.test(url)){external.push(url);return route.abort();}
  return route.continue();
 });
 async function read(path){const response=await page.request.get(base+'/api/'+path);assert(response.ok(),await response.text());return response.json();}
 async function navigate(name){
  const tab=page.locator(`.studio-nav [data-view="${name}"]`);
  await tab.evaluate(node=>{const tools=node.closest('details');if(tools)tools.open=true;});
  await tab.click();
 }
 async function openProject(id){await navigate('projects');await page.locator(`#project-list [data-project-id="${id}"]`).first().click();await page.locator('#view-create').waitFor({state:'visible'});}
 async function mutate(selector,endpoint,waitEnabled=true){
  const pending=page.waitForResponse(response=>response.url().endsWith('/api/'+endpoint)&&response.request().method()==='POST');
  await page.locator(selector).click();
  const response=await pending;assert(response.ok(),await response.text());
  if(waitEnabled)await page.waitForFunction(selector=>!document.querySelector(selector).disabled,selector);
  return response.json();
 }
 async function hold(endpoint){
  let release,arrived;
  const gate=new Promise(resolve=>release=resolve),seen=new Promise(resolve=>arrived=resolve);
  gates.push(release);
  await page.route('**/api/'+endpoint,async route=>{const response=await route.fetch();arrived();await gate;await route.fulfill({response});},{times:1});
  return{release,seen};
 }
 const savedProject=async id=>(await read('video-projects')).projects.find(project=>project.id===id);
 const waitReady=()=>page.waitForFunction(()=>window.studioReady===true);
 try{
  const originalCount=(await read('video-projects')).projects.length;
  let movie;
  if(process.env.AVATAR_PROJECT_VIDEO)movie=fs.readFileSync(process.env.AVATAR_PROJECT_VIDEO);
  else{
   const fixture=(await read('jobs')).find(job=>job.state==='done'&&job.video&&job.engine!=='heygen'&&job.duration>=1&&job.duration<=180);
   assert(fixture,'Genera prima il piccolo MP4 locale di verifica.');
   const response=await page.request.get(base+fixture.video);assert(response.ok());movie=await response.body();
  }
  await page.goto(base+'/');await waitReady();
  assert(await page.locator('#view-projects').isVisible(),'La pagina iniziale deve essere Progetti.');
  assert.equal(await page.locator('details.studio-tools').evaluate(node=>node.open),false,'Gli strumenti avanzati partono raccolti.');
  await page.locator('#project-new').click();
  await page.locator('#view-create').waitFor({state:'visible'});
  assert.equal(await page.locator('#project-method').inputValue(),'web');
  await page.locator('#video-character').selectOption('ari');
  const bootstrap=await read('bootstrap');
  const nativeVoice=bootstrap.voice_catalog.find(voice=>voice.language==='it'&&!voice.id.startsWith('piper:'));
  assert(nativeVoice,'Voce italiana locale richiesta dal collaudo.');
  await page.locator('#voice').selectOption(nativeVoice.id);
  await page.locator('#title').fill('Progetto isolato · percorso HeyGen');
  await page.locator('#script').fill('Questo video conserva il suo progetto sul Mac.');
  const initial=await mutate('#project-save','video-project');assert(initial.id);assert.equal(initial.method,'web');assert.equal(initial.status,'draft');

  const slowSave=await hold('video-project');
  await page.locator('#title').fill('Titolo inviato al salvataggio');
  await page.locator('#project-save').click();await slowSave.seen;
  await page.locator('#title').fill('Titolo corretto mentre salva');
  await page.locator('#script').fill('Il copione modificato durante il salvataggio deve restare qui.');
  slowSave.release();await page.waitForFunction(()=>!document.querySelector('#project-save').disabled);
  assert.equal(await page.locator('#title').inputValue(),'Titolo corretto mentre salva');
  assert.equal(await page.locator('#script').inputValue(),'Il copione modificato durante il salvataggio deve restare qui.');
  const edited=await mutate('#project-save','video-project');assert.equal(edited.id,initial.id);assert.equal(edited.revision,initial.revision+2);
  await page.goto(base+'/');await waitReady();await openProject(initial.id);
  assert.equal(await page.locator('#title').inputValue(),edited.title);assert.equal(await page.locator('#script').inputValue(),edited.script);
  assert.equal(await page.locator('#video-character').inputValue(),'ari');
  assert.equal((await read('video-projects')).projects.length,originalCount+1,'Aprire e ricaricare lo stesso progetto non deve duplicarlo.');

  // Returning to the editor during the save required by "New video" must keep newer typing.
  await page.locator('#title').fill('Bozza da conservare durante il cambio progetto');
  await navigate('projects');const slowTransition=await hold('video-project');
  await page.locator('#project-new').click();await slowTransition.seen;
  await navigate('create');await page.locator('#script').fill('Queste parole sono state scritte mentre cambiavo progetto.');
  slowTransition.release();await page.waitForFunction(()=>!document.querySelector('#project-save').disabled);
  assert.equal(await page.locator('#title').inputValue(),'Bozza da conservare durante il cambio progetto');
  assert.equal(await page.locator('#script').inputValue(),'Queste parole sono state scritte mentre cambiavo progetto.');
  const retained=await mutate('#project-save','video-project');assert.equal(retained.id,initial.id);

  // A completed preparation response must never make the older audio look current.
  const slowPrepare=await hold('video-project-prepare');
  await page.locator('#project-prepare').click();await slowPrepare.seen;
  await page.locator('#script').fill('Un nuovo copione richiede materiali aggiornati.');
  slowPrepare.release();await page.waitForFunction(()=>!document.querySelector('#project-prepare').disabled);
  assert.equal(await page.locator('#script').inputValue(),'Un nuovo copione richiede materiali aggiornati.');
  assert(!(await page.locator('#project-materials [data-material="audio"]').isVisible()),'Niente audio obsoleto mentre il copione è modificato.');
  await mutate('#project-save','video-project');
  assert.equal((await savedProject(initial.id)).status,'draft');
  const prepared=await mutate('#project-prepare','video-project-prepare');
  assert.equal(prepared.id,initial.id);assert.equal(prepared.status,'materials_ready');assert(prepared.materials.duration>0);
  for(const name of ['audio','character','script','bundle','captions']){
   const link=page.locator(`#project-materials [data-material="${name}"]`);assert(await link.isVisible(),`Materiale ${name}`);
   const response=await page.request.get(new URL(await link.getAttribute('href'),base).href);assert(response.ok(),`Download ${name}`);
   const bytes=await response.body();assert(bytes.length>0);
   if(name==='bundle')assert.equal(bytes.subarray(0,2).toString(),'PK');
   if(name==='script')assert(bytes.toString('utf8').includes('Un nuovo copione richiede materiali aggiornati.'));
  }
  const heygen=page.locator('#project-open-heygen');
  assert.equal(await heygen.getAttribute('target'),'avatar-studio-heygen');assert.match(await heygen.getAttribute('rel'),/noopener/);
  assert.equal(new URL(await heygen.getAttribute('href')).hostname,'app.heygen.com');
  assert.equal(await page.locator('iframe[src*="heygen"]').count(),0);

  const importedResponse=page.waitForResponse(response=>response.url().endsWith('/api/video-project-import'));
  await page.locator('#project-file').setInputFiles({name:'ritorno-da-heygen.mp4',mimeType:'video/mp4',buffer:movie});
  const importResult=await importedResponse;assert(importResult.ok(),await importResult.text());
  const imported=await importResult.json();assert.equal(imported.id,initial.id);assert.equal(imported.status,'video_imported');assert(imported.source.source_id);
  await page.locator('#project-source').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.querySelector('#project-source').readyState>=1);
  assert(await page.locator('#project-source').evaluate(video=>video.duration>=1));
  await page.locator('#project-source').evaluate(async video=>{video.muted=true;await video.play();});
  await page.waitForFunction(()=>document.querySelector('#project-source').currentTime>=.1);
  await page.locator('#project-source').evaluate(video=>video.pause());
  assert(!(await page.locator('#project-finish-form [name="use_prepared_captions"]').isChecked()),'I tempi del copione non devono essere applicati automaticamente al video esterno.');
  await page.goto(base+'/');await waitReady();await openProject(initial.id);
  assert(await page.locator('#project-source').isVisible(),'La sorgente importata deve restare collegata dopo il riavvio della pagina.');
  assert.equal((await savedProject(initial.id)).source.source_id,imported.source.source_id);
  const subtitles=await page.request.post(base+'/api/clip-subtitles',{headers:{'X-Avatar-Token':bootstrap.token},data:{id:imported.source.id,text:'1\n00:00:00,100 --> 00:00:01,000\nSottotitolo importato in seguito.\n'}});
  assert(subtitles.ok(),await subtitles.text());
  await navigate('projects');await openProject(initial.id);
  assert.equal((await savedProject(initial.id)).source.subtitle_count,1,'Il progetto deve rileggere gli SRT aggiunti dopo l’importazione.');
  assert(await page.locator('#project-finish-form [name="burn_captions"]').isEnabled());
  const cutStart=.2,cutEnd=Number((imported.source.duration-.2).toFixed(2));
  await page.locator('#project-finish-form [name="start"]').fill(String(cutStart));
  await page.locator('#project-finish-form [name="end"]').fill(String(cutEnd));
  await page.locator('#project-finish-form [name="format"]').selectOption('landscape');
  await page.locator('#project-finish-form [name="fit"]').selectOption('cover');
  await page.goto(base+'/');await waitReady();await openProject(initial.id);
  async function assertCutPreserved(){
   assert.equal(Number(await page.locator('#project-finish-form [name="start"]').inputValue()),cutStart);
   assert.equal(Number(await page.locator('#project-finish-form [name="end"]').inputValue()),cutEnd);
   assert.equal(await page.locator('#project-finish-form [name="format"]').inputValue(),'landscape');
   assert.equal(await page.locator('#project-finish-form [name="fit"]').inputValue(),'cover');
  }
  await assertCutPreserved();
  await page.locator('#title').fill('Progetto HeyGen · taglio conservato');
  const renamed=await mutate('#project-save','video-project');assert.equal(renamed.source.source_id,imported.source.source_id);
  await assertCutPreserved();
  assert(!(await page.locator('#project-finish-form [name="burn_captions"]').isChecked()));
  const exporting=await mutate('#project-export','video-project-render',false);assert(exporting.job.id);
  let completed;
  const deadline=Date.now()+150000;
  while(Date.now()<deadline){
   completed=await read('jobs/'+exporting.job.id);
   if(['done','error','cancelled'].includes(completed.state))break;
   await page.waitForTimeout(400);
  }
  assert.equal(completed.state,'done',completed.message);
  await page.locator('#project-final-download').waitFor({state:'visible',timeout:12000});
  const final=await savedProject(initial.id);assert.equal(final.status,'ready');assert.equal(final.job.id,exporting.job.id);
  const result=await page.request.get(base+completed.video);assert(result.ok());assert((await result.body()).length>1000);
  await page.goto(base+'/');await waitReady();await openProject(initial.id);
  assert(await page.locator('#project-final-download').isVisible(),'L’esportazione completata resta nel progetto.');
  await page.waitForFunction(()=>document.querySelector('#project-source').readyState>=1);
  await page.locator('#project-source').evaluate(video=>{video.currentTime=.1;});
  await page.waitForFunction(()=>document.querySelector('#project-source').readyState>=2);

  for(const width of [1440,390]){
   await page.setViewportSize({width,height:1100});
   for(const view of ['projects','create','guide']){
    await navigate(view);
    assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)),`Overflow ${view} ${width}`);
    if(view==='create'){
     const positions=await page.evaluate(()=>({header:document.querySelector('.project-workflow-header').getBoundingClientRect().toJSON(),chooser:document.querySelector('.video-character-chooser').getBoundingClientRect().toJSON()}));
     assert(positions.header.bottom<=positions.chooser.top+1,`Il selettore personaggio copre il workflow a ${width}px.`);
     if(width===1440)await page.locator('#view-create').screenshot({path:'output/project-workflow-desktop.png'});
    }
   }
  }
  const guide=(await page.locator('#view-guide').innerText()).toLowerCase();
  for(const word of ['prepara','heygen','importa','completa'])assert(guide.includes(word),`Guida incompleta: ${word}`);
  await page.locator('#view-guide').screenshot({path:'output/project-workflow-guide-mobile.png'});
  await navigate('create');await page.locator('#view-create').screenshot({path:'output/project-workflow-mobile.png'});
  assert.deepEqual(legacyRenders,[],'Il workflow web non deve avviare le vecchie azioni locali o API.');

  // The alternative methods must still bind their output to a saved project.
  checkingWebsiteFlow=false;
  await page.setViewportSize({width:1440,height:1100});await navigate('projects');await page.locator('#project-new').click();
  await page.locator('#title').fill('Progetto locale isolato');await page.locator('#script').fill('Ciao dal progetto locale.');
  await page.locator('#project-method').selectOption('local');await page.locator('#voice').selectOption(nativeVoice.id);
  const localProject=await mutate('#project-save','video-project');assert.notEqual(localProject.id,initial.id);
  assert.equal((await read('video-projects')).projects.length,originalCount+2);
  const localJob=await mutate('#project-generate','render',false);assert.equal(localJob.video_project.id,localProject.id);
  const localDeadline=Date.now()+150000;
  let localResult;
  while(Date.now()<localDeadline){localResult=await read('jobs/'+localJob.id);if(['done','error','cancelled'].includes(localResult.state))break;await page.waitForTimeout(400);}
  assert.equal(localResult.state,'done',localResult.message);
  assert.equal((await savedProject(localProject.id)).status,'ready');
  await page.goto(base+'/');await waitReady();await openProject(localProject.id);
  assert(await page.locator('#project-final-download').isVisible());
  assert(await page.locator('#project-source').isVisible(),'Anche il risultato locale deve essere completabile nello stesso progetto.');
  const localSource=(await savedProject(localProject.id)).source;
  assert.equal(localSource.source_id,'job:'+localJob.id);
  const localTrimJobs=[];
  for(const end of [Math.min(1.2,localSource.duration),1]){
   await page.locator('#project-finish-form [name="end"]').fill(String(end));
   await page.locator('#project-finish-form [name="format"]').selectOption('landscape');
   const trimmed=await mutate('#project-export','video-project-render',false);
   assert.equal(trimmed.project.id,localProject.id);assert.equal(trimmed.project.source.source_id,localSource.source_id);
   const trimDeadline=Date.now()+120000;
   let trimResult;
   while(Date.now()<trimDeadline){trimResult=await read('jobs/'+trimmed.job.id);if(['done','error','cancelled'].includes(trimResult.state))break;await page.waitForTimeout(400);}
   assert.equal(trimResult.state,'done',trimResult.message);
   const rendered=await page.request.get(base+'/output/'+trimmed.job.id+'/project.json');assert(rendered.ok());
   const renderedProject=await rendered.json();assert.equal(renderedProject.source_reference.source_id,localSource.source_id);assert(Math.abs(renderedProject.duration-end)<.02);
   localTrimJobs.push(trimmed.job.id);
   await page.goto(base+'/');await waitReady();await openProject(localProject.id);
   assert.equal((await savedProject(localProject.id)).source.source_id,localSource.source_id,'Un nuovo taglio deve continuare a usare il filmato originale.');
   assert.equal((await savedProject(localProject.id)).job.id,trimmed.job.id);
  }

  // Intercept both paid endpoints. No cloud quote or generation reaches the server.
  const quotes=[],submissions=[];
  let quoteGate=null;
  await page.route('**/api/cloud-quote',async route=>{
   quotes.push(route.request().postDataJSON());
   if(quoteGate){const current=quoteGate;quoteGate=null;current.arrived();await current.wait;}
   await route.fulfill({json:{quote_id:'cccccccccccc',character:'Ari',duration:2,estimated_eur:1,engine:'Avatar IV',note:'Preventivo simulato esclusivamente per il test.'}});
  });
  let apiProject;
  await page.route('**/api/cloud-render',async route=>{
   submissions.push(route.request().postDataJSON());
   const job={id:'dddddddddddd',title:apiProject.title,state:'queued',progress:0,message:'Generazione simulata',engine:'heygen'};
   await route.fulfill({json:{...job,video_project:{...apiProject,job,job_id:job.id,status:'rendering'}}});
  });
  await navigate('projects');await page.locator('#project-new').click();
  await page.locator('#title').fill('Progetto API simulato');await page.locator('#script').fill('Questo preventivo non deve consumare credito.');
  await page.locator('#project-method').selectOption('api');await page.locator('#video-character').selectOption('ari');
  apiProject=await mutate('#project-save','video-project');
  assert.equal((await read('video-projects')).projects.length,originalCount+3);
  let releaseQuote,arrivedQuote;
  const waitQuote=new Promise(resolve=>releaseQuote=resolve),seenQuote=new Promise(resolve=>arrivedQuote=resolve);
  gates.push(releaseQuote);quoteGate={wait:waitQuote,arrived:arrivedQuote};
  await page.locator('#project-generate').click();await seenQuote;
  await page.locator('#script').fill('Il preventivo precedente non rappresenta questo nuovo testo.');
  releaseQuote();await page.waitForFunction(()=>!document.querySelector('#project-generate').disabled);
  assert.equal(await page.locator('dialog[open]').count(),0,'Un preventivo per la bozza superata non deve essere confermabile.');
  assert.equal(submissions.length,0);
  apiProject=await mutate('#project-save','video-project');
  await page.locator('#project-generate').click();
  const confirmation=page.getByRole('button',{name:'Invia immagine e audio a HeyGen',exact:true});await confirmation.waitFor({state:'visible'});
  assert.equal(submissions.length,0,'Il preventivo non autorizza automaticamente la spesa.');
  assert.equal(quotes.at(-1).video_project_id,apiProject.id);assert.equal(quotes.at(-1).video_project_revision,apiProject.revision);
  await page.locator('dialog[open]').getByRole('button',{name:'Annulla',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('#project-generate').disabled);assert.equal(submissions.length,0);
  await page.locator('#project-generate').click();await confirmation.waitFor({state:'visible'});
  const simulatedSubmission=page.waitForResponse(response=>response.url().endsWith('/api/cloud-render'));
  await confirmation.click();assert((await simulatedSubmission).ok());
  assert.deepEqual(submissions,[{quote_id:'cccccccccccc'}]);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={isolated:true,default_projects_home:true,advanced_tools_collapsed:true,project_id:initial.id,save_while_editing:true,reload_persists_draft:true,transition_preserves_new_typing:true,stale_preparation_hidden:true,local_material_downloads:true,external_editor_link_only:true,video_import_persists:true,imported_video_plays:true,caption_alignment_explicit:true,later_srt_hydrated:true,provisional_cut_survives_reload:true,rename_preserves_source_and_cut:true,export_job_id:exporting.job.id,real_local_export:true,completed_project_persists:true,local_generation_bound_to_project:true,local_job_id:localJob.id,local_trim_job_ids:localTrimJobs,local_trim_preserves_original_source:true,stale_api_quote_discarded:true,api_confirmation_required:true,api_cancellation_free:true,paid_endpoints_mocked:true,guide:true,header_and_character_do_not_overlap:true,widths:[1440,390],errors,external_requests:external,unexpected_legacy_renders:legacyRenders};
  fs.writeFileSync('output/project-workflow-verification.json',JSON.stringify(report,null,2));console.log(report);
 }catch(error){
  await page.screenshot({path:'output/project-workflow-failure.png',fullPage:true}).catch(()=>{});
  console.error({url:page.url(),errors,external});throw error;
 }finally{for(const release of gates)release();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
