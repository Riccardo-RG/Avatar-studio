const {chromium} = require(process.env.AVATAR_PLAYWRIGHT || 'playwright');
const fs = require('fs');
const path = require('path');
(async()=>{
  const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true,args:['--enable-unsafe-swiftshader']});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1050}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto('http://127.0.0.1:8765');
    await page.waitForFunction(()=>document.querySelectorAll('.job-card').length===3);
    await page.getByRole('button',{name:'▷ Guarda'}).first().click();
    await page.waitForFunction(()=>document.querySelector('#video-player').currentTime>.2);
    console.log('Riproduzione MP4 verificata:',await page.locator('#video-player').evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration,currentTime:v.currentTime})));
    await page.getByRole('button',{name:'Chiudi video'}).click();
    await page.getByRole('tab',{name:/Parto da un/}).click();
    await page.locator('#topic').fill('Prendersi una pausa dallo schermo');
    await page.locator('#seconds').selectOption('15');
    const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/script'),{timeout:420000});
    await page.getByRole('button',{name:'✧ Scrivi una bozza'}).click();
    const response=await responsePromise;
    const data=await response.json();
    if(!response.ok())throw new Error(JSON.stringify(data));
    await page.waitForFunction(()=>document.querySelector('#generate').disabled===false);
    const value=await page.locator('#script').inputValue();
    if(value.length<20)throw new Error('Copione vuoto');
    fs.writeFileSync(path.join(__dirname,'output/final-draft.json'),JSON.stringify(data,null,2));
    console.log('Nuovo copione:',value);
    await page.screenshot({path:path.join(__dirname,'output/studio-final.png'),fullPage:true});
    console.log('Errori UI:',JSON.stringify(errors));
    if(errors.length)process.exitCode=1;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
