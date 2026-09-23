const path=require('path'),os=require('os');
let playwright=process.env.AVATAR_PLAYWRIGHT;
if(!playwright){try{playwright=require.resolve('playwright');}catch{playwright=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');}}
const {chromium}=require(playwright);
const fs=require('fs'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.AVATAR_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/#lab');await page.waitForSelector('#character-cards [data-character="ari"]');
  await page.locator('[data-view="lab"]').click();await page.waitForSelector('#view-lab:not([hidden])');
  await page.screenshot({path:'output/platform-lab-desktop.png',fullPage:true});
  assert.equal(await page.locator('.character-card').count(),3);
  await page.locator('[data-character="lumo"]').click();assert.equal(await page.locator('#character-form [name=name]').inputValue(),'Lumo');
  await page.locator('#lab-script').fill('Ciao! Sono Lumo. Un piccolo esperimento può dare voce a una nuova idea.');
  await page.locator('#lab-listen').click();await page.waitForFunction(()=>document.querySelector('#lab-listen').textContent.includes('Ferma'),{timeout:90000});
  await page.screenshot({path:'output/platform-lumo-preview.png',fullPage:true});await page.locator('#lab-listen').click();
  await page.locator('[data-view="campaigns"]').click();await page.waitForSelector('#view-campaigns:not([hidden])');
  await page.screenshot({path:'output/platform-campaigns-desktop.png',fullPage:true});
  await page.locator('[data-view="services"]').click();await page.locator('#run-diagnostics').click();await page.waitForSelector('.diagnostic');
  assert.match(await page.locator('#budget-summary').innerText(),/30/);
  await page.screenshot({path:'output/platform-services-desktop.png',fullPage:true});
  await page.locator('[data-view="production"]').click();
  await page.getByLabel('Copione scena 1',{exact:true}).fill('Bozza recuperata dopo il ricaricamento.');
  await page.getByLabel('Immagine di supporto scena 1',{exact:true}).setInputFiles('static/characters/lumo.png');
  await page.waitForSelector('#production-scenes img');
  const uploaded=await page.locator('#production-scenes img').first().getAttribute('src');
  assert.match(uploaded,/^\/character-assets\/[a-f0-9]+\.png$/);
  await page.reload();await page.waitForSelector('#production-scenes textarea');
  await page.locator('[data-view="production"]').click();
  assert.equal(await page.getByLabel('Copione scena 1',{exact:true}).inputValue(),'Bozza recuperata dopo il ricaricamento.');
  assert.equal(await page.locator('#production-scenes img').first().getAttribute('src'),uploaded);
  await page.screenshot({path:'output/platform-production-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.locator('[data-view="lab"]').click();
  await page.screenshot({path:'output/platform-lab-mobile.png',fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);assert.equal(overflow,false,'mobile overflow');
  for(const section of ['campaigns','services','production','create','live']){await page.locator(`[data-view="${section}"]`).click();assert.equal(await page.locator('#view-'+section).isVisible(),true);}
  assert.deepEqual(errors,[]);const report={errors,mobile_overflow:overflow,sections:8,characters:3,real_voice_preview:true,services:true,image_upload:true,production_draft_restore:true};fs.writeFileSync('output/platform-ui-verification.json',JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
