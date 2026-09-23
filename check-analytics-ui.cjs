// UI contract test with deterministic reports, no external requests or accounts.
const assert=require('assert'),fs=require('fs');
const runtime=require('./runtime_config.cjs'),{chromium}=require(runtime.playwright);
(async()=>{
 const base=process.env.AVATAR_TEST_URL;if(!base||process.env.AVATAR_ISOLATED_TEST!=='1')throw Error('Serve una copia isolata.');
 const browser=await chromium.launch({executablePath:runtime.chrome,headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],external=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const url=route.request().url();if(!url.startsWith(base+'/')&&!/^(data|blob):/.test(url)){external.push(url);return route.abort();}return route.continue();});
 async function navigate(name){const tab=page.locator(`.studio-nav [data-view="${name}"]`);await tab.evaluate(node=>{const tools=node.closest('details');if(tools)tools.open=true;});await tab.click();}
 let deferred=null;
 const report=q=>({publication_id:q.publication_id,profile_id:'default',channel_id:'channel-test',period:{start_date:q.start_date,end_date:q.end_date,timezone:'America/Los_Angeles'},metrics:{views:0,engaged_views:null,average_view_duration_seconds:12.25,estimated_revenue_eur:null},monetary_message:'Ricavi non disponibili per questo account.',data_status:'partial',limitations:['I dati recenti possono essere incompleti.']});
 await page.route('**/api/youtube-analytics',async route=>{const q=route.request().postDataJSON();requests.push(q);if(deferred){const d=deferred;deferred=null;d.seen();await d.wait;}await route.fulfill({json:report(q)});});
 const read=async()=>{const response=page.waitForResponse(r=>r.url().endsWith('/api/youtube-analytics'));await page.locator('#youtube-analytics-form [type=submit]').click();await response;await page.locator('#youtube-analytics-result').waitFor({state:'visible'});};
 try{
  await page.goto(base+'/?edition=lab');await page.waitForFunction(()=>window.studioReady===true);
  await navigate('insights');
  const f=page.locator('#youtube-analytics-form');await f.locator('[name=publication_id] option[value="aaaaaaaaaaaa"]').waitFor({state:'attached'});
  assert.equal(requests.length,0,'Analytics deve partire solo con un clic esplicito');
  await f.locator('[name=publication_id]').selectOption('aaaaaaaaaaaa');await f.locator('[name=start_date]').fill('2026-09-01');await f.locator('[name=end_date]').fill('2026-09-02');await f.locator('[name=include_revenue]').check();
  await read();assert.equal(requests[0].include_revenue,true);
  assert.equal(await page.locator('[data-analytics-metric=views] strong').innerText(),'0');
  assert.equal(await page.locator('[data-analytics-metric=engaged_views] strong').innerText(),'—');
  assert.equal(await page.locator('[data-analytics-metric=estimated_revenue_eur] strong').innerText(),'—');
  assert((await page.locator('#youtube-analytics-result').innerText()).includes('America/Los_Angeles'));
  const download=page.waitForEvent('download');await page.getByText('Esporta questo report JSON',{exact:true}).click();const file=await download;const exported=JSON.parse(fs.readFileSync(await file.path(),'utf8'));assert.equal(exported.metrics.views,0);assert.equal(exported.metrics.engaged_views,null);
  let release,seen;const wait=new Promise(r=>release=r),arrived=new Promise(r=>seen=r);deferred={wait,seen};
  await f.locator('[type=submit]').click();await arrived;await f.locator('[name=publication_id]').selectOption('bbbbbbbbbbbb');release();
  await page.waitForFunction(()=>!document.querySelector('#youtube-analytics-form [type=submit]').disabled);
  assert(await page.locator('#youtube-analytics-result').isHidden(),'La risposta tardiva del post A non deve apparire sul post B');
  await read();assert.equal(requests.at(-1).publication_id,'bbbbbbbbbbbb');assert((await page.locator('#youtube-analytics-result').innerText()).includes('Post di prova B'));
  for(const width of [1440,390]){await page.setViewportSize({width,height:1100});assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)),`Analytics overflow ${width}`);}
  await page.locator('#youtube-analytics').screenshot({path:'output/analytics-mobile-verification.png'});
  await page.locator('#youtube-analytics-connect').click();const connection=page.locator('[data-service=youtube]');
  assert(!(await connection.locator('[name=oauth_analytics]').isChecked()));assert(!(await connection.locator('[name=oauth_revenue]').isChecked()));
  await connection.locator('[name=oauth_revenue]').check();assert(await connection.locator('[name=oauth_analytics]').isChecked());
  await connection.locator('[name=oauth_analytics]').uncheck();assert(!(await connection.locator('[name=oauth_revenue]').isChecked()));
  let oauth;await page.route('**/api/oauth-youtube',route=>{oauth=route.request().postDataJSON();return route.fulfill({json:{url:'https://accounts.google.com/o/oauth2/v2/auth?test-only=1'}});});
  await connection.locator('[name=oauth_analytics]').check();await connection.getByText('Accedi con Google',{exact:true}).click();await connection.locator('[data-oauth-login]').waitFor();
  assert.deepEqual(oauth,{profile_id:'default',analytics:true,revenue:false});assert.equal(requests.length,3);
  await connection.locator('[name=oauth_revenue]').check();assert.equal(await connection.locator('[data-oauth-login]').count(),0);
  let releaseOAuth,oauthSeen;const oauthGate=new Promise(r=>releaseOAuth=r),oauthArrived=new Promise(r=>oauthSeen=r);
  await page.route('**/api/oauth-youtube',async route=>{oauthSeen();await oauthGate;await route.fulfill({json:{url:'https://accounts.google.com/o/oauth2/v2/auth?test-only=2'}});},{times:1});
  await connection.getByText('Accedi con Google',{exact:true}).click();await oauthArrived;await connection.locator('[name=oauth_analytics]').uncheck();releaseOAuth();
  await page.waitForFunction(()=>![...document.querySelectorAll('[data-service=youtube] button')].find(b=>b.textContent==='Accedi con Google').disabled);
  assert.equal(await connection.locator('[data-oauth-login]').count(),0,'Login con permessi ormai cambiati');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  fs.writeFileSync('output/analytics-ui-verification.json',JSON.stringify({manual_only:true,zero_and_missing_distinct:true,revenue_failure_preserves_basic:true,stale_response_discarded:true,json_export:true,optional_oauth_scopes:true,widths:[1440,390],errors,external_requests:external},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
