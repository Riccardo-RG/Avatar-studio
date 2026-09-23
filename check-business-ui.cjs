// Run only against an isolated copy: creates strategy/reference/experiment records.
const assert=require('assert'),fs=require('fs');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const base=process.env.AVATAR_TEST_URL;if(!base||process.env.AVATAR_ISOLATED_TEST!=='1')throw Error('Serve una copia isolata esplicitamente dichiarata.');
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],external=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{const u=route.request().url();if(!u.startsWith(base+'/')&&!/^(data|blob):/.test(u)){external.push(u);return route.abort();}return route.continue();});
 async function navigate(name){const tab=page.locator(`.studio-nav [data-view="${name}"]`);await tab.evaluate(node=>{const tools=node.closest('details');if(tools)tools.open=true;});await tab.click();}
 async function save(form,endpoint){const reply=page.waitForResponse(r=>r.url().endsWith('/api/'+endpoint)&&r.request().method()==='POST');await form.locator('button').filter({hasText:/^Salva/}).first().click();const response=await reply;assert(response.ok(),await response.text());return response.json();}
 try{
  await page.goto(base+'/?edition=lab#create');await page.waitForFunction(()=>window.studioReady===true);
  assert(await page.locator('#seconds option[value="90"]').count());
  await navigate('growth');
  const f=page.locator('#growth-strategy-form');
  for(const [k,v] of Object.entries({name:'Test isolato crescita',niche:'Tutorial Mac',audience:'Principianti',promise:'Una procedura verificabile',cta:'Consulta il profilo'}))await f.locator(`[name=${k}]`).fill(v);
  const strategy=await save(f,'growth-strategy');
  await page.locator('[data-business-panel="research"]').click();
  const r=page.locator('#growth-reference-form');await r.locator('[name=strategy_id]').selectOption(strategy.id);
  for(const[k,v]of Object.entries({url:'https://example.com/tutorial',title:'Riferimento manuale',format:'Tutorial',notes:'Osservazione originale senza chiamate web'}))await r.locator(`[name=${k}]`).fill(v);
  await save(r,'growth-reference');
  await page.locator('[data-business-panel="experiments"]').click();
  const e=page.locator('#growth-experiment-form');await e.locator('[name=strategy_id]').selectOption(strategy.id);
  await e.locator('[name=name]').fill('Confronto isolato');await e.locator('[name=hypothesis]').fill('Mostrare subito il risultato migliora la comprensione.');
  const experiment=await save(e,'growth-experiment');await page.waitForFunction(()=>document.querySelector('#growth-report').textContent.includes('Confronto isolato'));
  assert(await page.locator('#growth-report').innerText());
  await page.locator('[data-business-panel="policy"]').click();
  const checked=page.waitForResponse(r=>r.url().endsWith('/api/policy-review'));await page.locator('#growth-policy-form button').filter({hasText:'Esamina il contenuto'}).click();assert((await checked).ok());
  assert((await page.locator('#growth-rules article').count())>10);
  const sections=await page.locator('.studio-nav [data-view]').evaluateAll(nodes=>nodes.map(n=>n.dataset.view));
  for(const width of [1440,390]){await page.setViewportSize({width,height:1100});for(const name of sections){await navigate(name);assert(!(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)),`Overflow ${name} ${width}`);}}
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={isolated:true,strategy_saved:true,reference_saved:true,experiment_saved:true,policy_review:true,sections:sections.length,widths:[1440,390],errors,external_requests:external};
  fs.writeFileSync('output/business-ui-verification.json',JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
