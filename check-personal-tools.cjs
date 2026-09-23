const fs=require('fs'),assert=require('assert'),path=require('path'),os=require('os');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],external=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 const now=Date.now()/1000,metrics={enabled:false,running:false,last_run:0,interval_minutes:60,errors:{},note:'Contatori reali. Dati simulati esclusivamente in questo collaudo.',items:[
  {id:'metric-one',title:'Lumo · prima clip',platform:'youtube',account_id:'test-channel',character_ids:['lumo'],published_at:now-86400,latest_at:now,previous_at:now-3600,values:{views:120,likes:0,comments:null},delta:{views:20},samples:2},
  {id:'metric-two',title:'Lumo · seconda clip',platform:'youtube',account_id:'test-channel',character_ids:['lumo'],published_at:now-86400,latest_at:now,previous_at:now-3600,values:{views:90,likes:2,comments:1},delta:{views:-2},samples:2},
  {id:'metric-three',title:'Ari · terza clip',platform:'instagram',account_id:'test-account',character_ids:['ari'],values:{},delta:{},samples:0}
 ]};
 const post={id:'test-storage',revision:1,job_id:'17f20462bc28',title:'Clip da caricare',description:'Solo fixture del browser',platform:'instagram',state:'draft',visibility:'public',timezone:'Europe/Rome',due_at:new Date(Date.now()+86400000).toISOString(),week:'2026-W39',preview_url:'/output/17f20462bc28/video.mp4',poster_url:'/output/17f20462bc28/cover.png',readiness:[],message:'Da revisionare'};
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!=='http://127.0.0.1:8765'&&!req.url().startsWith('data:')){external.push(req.url());return route.abort();}
  const json=data=>route.fulfill({json:data});
  if(u.pathname==='/api/insights')return json(metrics);
  if(u.pathname==='/api/insights-settings'){const data=req.postDataJSON();writes.push({route:u.pathname,data});Object.assign(metrics,data);return json(metrics);}
  if(u.pathname==='/api/insights-collect'){writes.push({route:u.pathname});metrics.last_run=now;return json({message:'Lettura simulata completata'});}
  if(u.pathname==='/api/publications')return json({items:[post],armed:false});
  if(u.pathname==='/api/storage-plan'){writes.push({route:u.pathname});return json({id:'test-plan',bytes:2000000,note:'Il file diventa pubblico sul tuo storage.',missing:[],destination:{bucket:'test-bucket',url:'https://media.example.com/test.mp4'}});}
  if(u.pathname==='/api/storage-upload'){assert.deepEqual(req.postDataJSON(),{plan_id:'test-plan',confirmed:true});writes.push({route:u.pathname});post.source_url='https://media.example.com/test.mp4';post.revision++;return json({message:'Caricamento simulato verificato. Post da revisionare.'});}
  if(req.method()==='POST'&&u.pathname!=='/api/clip-details'){throw Error('Mutazione non simulata: '+u.pathname);}return route.continue();
 });
 try{
  await page.goto('http://127.0.0.1:8765/#insights');await page.waitForFunction(()=>window.studioReady===true);
  assert.equal(await page.locator('[data-view]').count(),12);assert.equal(await page.locator('[data-service]').count(),6);
  assert.equal(await page.locator('[data-metric-post]').count(),3);
  assert.equal(await page.locator('[data-metric-post=metric-one] .metric-value strong').allTextContents().then(v=>v.join('|')),'120|0|—|—');
  await page.locator('#insights-character').selectOption('lumo');assert.equal(await page.locator('[data-metric-post]').count(),2);
  for(const c of await page.locator('[data-metric-post] input[type=checkbox]').all())await c.check();
  assert(await page.locator('#insights-compare').isVisible());assert.match(await page.locator('#insights-compare').innerText(),/-2/);
  await page.locator('#insights-settings [name=interval_minutes]').fill('30');await page.locator('#insights-settings [name=enabled]').check();await page.locator('#insights-settings button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('#insights-state').textContent.includes('automatici attivi'));
  await page.locator('#insights-collect').click();await page.waitForFunction(()=>document.querySelector('#insights-state').textContent.includes('Ultimo ciclo'));
  await page.screenshot({path:'output/insights-desktop.png'});
  await page.locator('#text-size').selectOption('22');await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.locator('#insights-compare').scrollIntoViewIfNeeded();await page.screenshot({path:'output/insights-mobile.png'});
  await page.locator('[data-view=publishing]').click();await page.getByRole('button',{name:'Prepara file sul mio storage',exact:true}).click();await page.waitForSelector('#storage-dialog[open]');assert(!writes.some(w=>w.route==='/api/storage-upload'));assert.match(await page.locator('#storage-summary').innerText(),/test-bucket/);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.locator('#storage-confirm').click();await page.waitForSelector('#storage-dialog:not([open])',{state:'attached'});assert.equal(writes.filter(w=>w.route==='/api/storage-upload').length,1);
  await page.locator('[data-view=connections]').click();assert(await page.locator('[data-service=r2]').isVisible());assert.equal(await page.locator('[data-service=r2] input[type=password]').count(),2);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);const report={fixtures_only:true,missing_vs_zero:true,negative_delta:true,character_filter:true,comparison:true,optional_metrics_controls:true,storage_review_then_explicit_upload:true,no_publication:true,sections:12,connections:6,mobile_font22_overflow:false,errors,external_requests:external};fs.writeFileSync('output/personal-tools-ui-verification.json',JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
