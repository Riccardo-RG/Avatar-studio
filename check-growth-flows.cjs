// Stateful browser regressions, only against disposable local data.
const assert=require('assert'),fs=require('fs');
const runtime=require('./runtime_config.cjs'),{chromium}=require(runtime.playwright);
(async()=>{
 const base=process.env.AVATAR_TEST_URL;if(!base||process.env.AVATAR_ISOLATED_TEST!=='1')throw Error('Serve una copia isolata.');
 const browser=await chromium.launch({executablePath:runtime.chrome,headless:true}),page=await browser.newPage(),errors=[],external=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const url=route.request().url();if(!url.startsWith(base+'/')&&!/^(data|blob):/.test(url)){external.push(url);return route.abort();}return route.continue();});
 async function navigate(name){const tab=page.locator(`.studio-nav [data-view="${name}"]`);await tab.evaluate(node=>{const tools=node.closest('details');if(tools)tools.open=true;});await tab.click();}
 const state=async()=>page.request.get(base+'/api/growth').then(r=>r.json());
 async function save(form,endpoint){const response=page.waitForResponse(r=>r.url().endsWith('/api/'+endpoint)&&r.request().method()==='POST');await form.locator('button').first().click();const r=await response;assert(r.ok(),await r.text());await form.locator('button').first().waitFor({state:'visible'});await page.waitForFunction(selector=>!document.querySelector(selector+' button').disabled,await form.getAttribute('id').then(id=>'#'+id));return r.json();}
 async function hold(endpoint){let release,arrived;const gate=new Promise(r=>release=r),seen=new Promise(r=>arrived=r);await page.route('**/api/'+endpoint,async route=>{const response=await route.fetch();arrived();await gate;await route.fulfill({response});},{times:1});return{release,seen};}
 const ready=async form=>page.waitForFunction(id=>!document.querySelector(id+' button').disabled,'#'+await form.getAttribute('id'));
 try{
  await page.goto(base+'/?edition=lab');await page.waitForFunction(()=>window.studioReady===true);await navigate('growth');
  await page.locator('#growth-strategies').getByText('Test isolato crescita',{exact:true}).click();
  const strategy=page.locator('#growth-strategy-form');await strategy.locator('[name=audience]').fill('Prima del salvataggio');
  const slowStrategy=await hold('growth-strategy');await strategy.locator('button').first().click();await slowStrategy.seen;await strategy.locator('[name=audience]').fill('Modifica durante il salvataggio');slowStrategy.release();await ready(strategy);
  assert.equal(await strategy.locator('[name=audience]').inputValue(),'Modifica durante il salvataggio');const savedStrategy=await save(strategy,'growth-strategy');assert.equal(savedStrategy.revision,3);
  await page.locator('[data-business-panel=research]').click();await page.locator('#growth-reference-form [name=strategy_id]').selectOption(savedStrategy.id);await page.locator('#growth-references').getByText('Modifica riferimento',{exact:true}).click();
  const reference=page.locator('#growth-reference-form'),saveReference=reference.getByText('Salva riferimento',{exact:true});
  await reference.locator('[name=notes]').fill('Osservazione aggiornata');const firstReference=page.waitForResponse(r=>r.url().endsWith('/api/growth-reference'));await saveReference.click();assert((await firstReference).ok());await page.waitForFunction(()=>!document.querySelector('#growth-reference-form .button.primary').disabled);
  await reference.locator('[name=notes]').fill('Secondo aggiornamento');const secondReference=page.waitForResponse(r=>r.url().endsWith('/api/growth-reference'));await saveReference.click();assert((await secondReference).ok());assert.equal((await state()).references.length,1,'Aggiornare la fonte non deve duplicarla');
  await page.locator('#growth-new-reference').click();assert.equal(await reference.locator('[name=url]').inputValue(),'');
  await page.locator('[data-business-panel=experiments]').click();
  await page.locator('#growth-experiments').getByText('Confronto isolato',{exact:true}).click();
  const experiment=page.locator('#growth-experiment-form');await experiment.locator('[name=hypothesis]').fill('Prima ipotesi');
  const slowExperiment=await hold('growth-experiment');await experiment.locator('button').first().click();await slowExperiment.seen;await experiment.locator('[name=hypothesis]').fill('Ipotesi rivista durante il salvataggio');slowExperiment.release();await ready(experiment);
  assert.equal(await experiment.locator('[name=hypothesis]').inputValue(),'Ipotesi rivista durante il salvataggio');assert.equal((await save(experiment,'growth-experiment')).revision,3);
  const link=page.locator('#growth-link-form'),obs=page.locator('#growth-observation-form');
  const local=new Date(Date.now()-25*3600e3);local.setMinutes(local.getMinutes()-local.getTimezoneOffset());const date=local.toISOString().slice(0,16);
  await link.locator('[name=publication_id]').selectOption('aaaaaaaaaaaa');await link.locator('[name=published_at]').fill(date);
  const slowLink=await hold('growth-link');await link.locator('button').first().click();await slowLink.seen;
  await link.locator('[name=publication_id]').selectOption('bbbbbbbbbbbb');assert.equal(await link.locator('[name=published_at]').inputValue(),'');
  await link.locator('[name=published_at]').fill(date);await link.locator('[name=variant]').selectOption('B');slowLink.release();await ready(link);
  assert.equal(await link.locator('[name=publication_id]').inputValue(),'bbbbbbbbbbbb');assert.equal(await link.locator('[name=published_at]').inputValue(),date);assert.equal(await link.locator('[name=variant]').inputValue(),'B');
  await save(link,'growth-link');await link.locator('[name=publication_id]').selectOption('aaaaaaaaaaaa');assert.equal(await link.locator('[name=variant]').inputValue(),'A');assert.equal(await link.locator('[name=published_at]').inputValue(),date);
  await obs.locator('[name=publication_id]').selectOption('aaaaaaaaaaaa');await obs.locator('[name=views]').fill('100');
  const slowObservation=await hold('growth-observation');await obs.locator('button').click();await slowObservation.seen;await obs.locator('[name=views]').fill('101');slowObservation.release();await ready(obs);
  assert.equal(await obs.locator('[name=views]').inputValue(),'101');const saved=await save(obs,'growth-observation');assert.equal(saved.revision,2);assert.equal(saved.views,101);
  await obs.locator('[name=publication_id]').selectOption('bbbbbbbbbbbb');await obs.locator('[name=views]').fill('999');
  await page.locator('#growth-experiment-work details summary').click();const csv=`publication_id,window_hours,observed_at,revision,views\naaaaaaaaaaaa,24,${new Date().toISOString()},2,150\n`;await page.locator('#growth-csv').fill(csv);
  const slowImport=await hold('growth-import');await page.locator('#growth-import').click();await slowImport.seen;
  await obs.locator('[name=publication_id]').selectOption('aaaaaaaaaaaa');await obs.locator('[name=views]').fill('300');slowImport.release();await page.waitForFunction(()=>!document.querySelector('#growth-import').disabled);
  assert.equal(await obs.locator('[name=views]').inputValue(),'300');const edited=await save(obs,'growth-observation');assert.equal(edited.revision,4);assert.equal(edited.views,300);
  await obs.locator('[name=publication_id]').selectOption('bbbbbbbbbbbb');assert.equal(await obs.locator('[name=views]').inputValue(),'999');
  const before=(await state()).observations;const rejected=page.waitForResponse(r=>r.url().endsWith('/api/growth-import'));await page.locator('#growth-import').click();assert.equal((await rejected).status(),400);assert.deepEqual((await state()).observations,before);
  await page.waitForFunction(()=>!document.querySelector('#growth-import').disabled);
  const download=page.waitForEvent('download');await page.locator('#growth-export-observations').click();const file=await download;const exported=fs.readFileSync(await file.path(),'utf8');assert(exported.includes('revision'));assert(exported.includes(',4,'));
  await page.locator('#growth-csv').fill(exported);const imported=page.waitForResponse(r=>r.url().endsWith('/api/growth-import'));await page.locator('#growth-import').click();assert((await imported).ok());await page.waitForFunction(()=>!document.querySelector('#growth-import').disabled);
  assert.equal(await obs.locator('[name=views]').inputValue(),'999');assert.equal((await state()).observations[0].revision,5);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  fs.writeFileSync('output/growth-flows-verification.json',JSON.stringify({strategy_and_experiment_edit_during_save:true,reference_update_without_duplicates:true,date_isolated_per_post:true,draft_preserved_during_link_save:true,observation_edit_during_save:true,observation_edit_during_import:true,unrelated_draft_preserved:true,stale_csv_rejected:true,csv_export_reimport:true,errors,external_requests:external},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
