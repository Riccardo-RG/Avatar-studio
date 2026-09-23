const {chromium}=require(process.env.AVATAR_PLAYWRIGHT || 'playwright');
const fs=require('fs');
(async()=>{const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true,args:['--enable-unsafe-swiftshader','--autoplay-policy=no-user-gesture-required']});try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8765');await page.waitForSelector('.episode-card',{state:'attached'});
 await page.screenshot({path:'output/v2-create.png',fullPage:true});
 await page.locator('[data-view="persona"]').click();await page.waitForSelector('.rubric-card');
 const profile=await page.locator('#persona-form [name="concept"]').inputValue();
 await page.locator('#persona-form [name="concept"]').fill(profile+' ');
 await page.locator('#persona-form button').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Personalità di ')&&document.querySelector('#status').textContent.includes('salvata'));
 await page.locator('.rubric-card').first().locator('button').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Rubrica salvata'));
 await page.screenshot({path:'output/v2-persona.png',fullPage:true});
 await page.locator('[data-view="plan"]').click();
 if(await page.locator('.episode-card').count()!==10)throw Error('Episodes not ten');
 await page.locator('#plan-filter').selectOption('domanda');if(await page.locator('.episode-card').count()!==3)throw Error('Filter broken');await page.locator('#plan-filter').selectOption('');
 await page.locator('[data-episode="s01e02"]').getByRole('button',{name:'Modifica',exact:true}).click();
 const old=await page.locator('#episode-form [name="script"]').inputValue();
 await page.locator('#hook-options button').first().click();const changed=await page.locator('#episode-form [name="script"]').inputValue();if(changed===old)throw Error('Hook no-op');
 await page.locator('#episode-form [name="script"]').fill(old);
 await page.locator('#episode-form').getByRole('button',{name:'Salva bozza',exact:true}).click();await page.waitForSelector('#episode-dialog',{state:'hidden'});
 await page.screenshot({path:'output/v2-plan.png',fullPage:true});
 await page.locator('[data-view="create"]').click();await page.locator('#script').fill('Ciao! Una piccola idea può diventare un video.');
 await page.locator('#preview').click();await page.waitForFunction(()=>document.querySelector('#preview').textContent.includes('Ferma ascolto'),{timeout:120000});
 await page.screenshot({path:'output/v2-voice-preview.png',fullPage:false});await page.locator('#preview').click();
 await page.setViewportSize({width:390,height:844});for(const view of ['create','plan','persona']){await page.locator('[data-view="'+view+'"]').click();await page.screenshot({path:'output/v2-mobile-'+view+'.png',fullPage:true});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Overflow '+view);}
 fs.writeFileSync('output/v2-ui-check.json',JSON.stringify({errors,persona:true,rubric:true,plan_filter:true,episode_save:true,hook:true,voice_preview:true,mobile_overflow:false},null,2));if(errors.length)throw Error(JSON.stringify(errors));console.log('UI V2 verified');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
