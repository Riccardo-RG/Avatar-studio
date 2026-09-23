const fs=require('fs'),assert=require('assert'),path=require('path'),os=require('os');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto('http://127.0.0.1:8765/#lab');await page.waitForFunction(()=>window.studioReady===true);
  let doc=await page.evaluate(()=>fetch('/api/platform').then(r=>r.json()));const original=structuredClone(doc.characters);let saved=null;
  await page.route('**/api/platform',r=>r.fulfill({json:doc}));
  await page.route('**/api/character',r=>{const d=r.request().postDataJSON();saved={...d,id:'qa-avatar',revision:1,rate:Number(d.rate),history:[]};doc.characters.push(saved);return r.fulfill({json:saved});});
  await page.locator('[data-character=lumo]').click();await page.locator('#character-duplicate').click();
  await page.locator('#character-form [name=name]').fill('Personaggio di prova');await page.locator('#character-form [name=rate]').fill('185');await page.locator('#character-form [name=background]').fill('#112233');
  await page.locator('[data-character=nova]').click();assert.equal(await page.locator('#character-form [name=name]').inputValue(),'Personaggio di prova');
  await page.locator('#character-form button[type=submit]').click();await page.waitForSelector('[data-character=qa-avatar]');assert(saved);assert.equal(saved.kind,'illustrated');assert.equal(saved.background,'#112233');assert.equal(saved.rate,185);assert.deepEqual(doc.characters.slice(0,3),original.slice(0,3));
  await page.locator('#character-use').click();await page.waitForFunction(()=>document.querySelector('#avatar').dataset.avatarCharacter==='qa-avatar');assert.equal(await page.locator('#video-character').inputValue(),'qa-avatar');assert.equal(await page.locator('#rate').inputValue(),'185');
  await page.locator('[data-view=production]').click();assert(await page.locator('[data-production-character] option[value=qa-avatar]').count()>0);
  await page.locator('[data-view=lab]').click();await page.locator('#new-character').click();await page.locator('#character-form [name=kind]').selectOption('photo');assert(await page.locator('#character-body-color').isHidden());assert(await page.locator('#character-image-fields').isVisible());assert(await page.locator('#character-mouth-fields').isHidden());await page.locator('#character-reset').click();
  const imageRace=await page.evaluate(async()=>{const {Avatar}=await import('/character-renderer.js');const chars=await fetch('/api/platform').then(r=>r.json()),NativeImage=window.Image,pending=[];window.Image=class{constructor(){pending.push(this);}set src(v){this.source=v;}};try{const one=chars.characters.find(c=>c.id==='lumo'),two=chars.characters.find(c=>c.id==='ari'),avatar=new Avatar(document.createElement('canvas'),{...one,character:one});avatar.setAppearance({...two,character:two});pending[1].onload();pending[0].onload();return avatar.image===pending[1]&&avatar.character.id==='ari';}finally{window.Image=NativeImage;}});assert(imageRace);
  assert.deepEqual(errors,[]);const report={editor_save_simulated:true,duplicate_independent:true,voice_and_background:true,unsaved_changes_protected:true,new_avatar_available_in_video_and_montage:true,style_specific_controls:true,late_image_cannot_replace_selection:imageRace,errors};fs.writeFileSync('output/character-editor-verification.json',JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
