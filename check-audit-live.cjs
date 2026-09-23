// No backend writes or external calls: exercise actual WebGL avatar switching.
const fs=require('node:fs'),assert=require('node:assert/strict');
const runtime=require('./runtime_config.cjs'),{chromium}=require(runtime.playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:runtime.chrome,headless:true,args:['--enable-unsafe-swiftshader']});
 const page=await browser.newPage(),errors=[],external=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/*',route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!=='http://127.0.0.1:8765'&&!['data:','blob:'].includes(url.protocol)){external.push(request.url());return route.abort();}
  if(request.method()!=='GET')return route.abort();
  return route.continue();
 });
 try{
  await page.goto('http://127.0.0.1:8765/api/bootstrap');
  await page.setContent('<!doctype html><html><body></body></html>');
  const result=await page.evaluate(async()=>{
   const {Avatar}=await import('/character-renderer.js');
   const canvas=document.createElement('canvas');
   const settings={name:'Test',color:'#3b6ab0',accent:'#b4fa86',background:'#162226',character:{id:'first',kind:'robot',revision:1}};
   const avatar=new Avatar(canvas,settings,90),robot=avatar.robot;
   avatar.draw(0,0);
   for(let i=0;i<40;i++){
    avatar.setAppearance({...settings,name:'Robot '+i,character:{id:'robot-'+i,kind:'robot',revision:i}});
    avatar.draw(i,.2);
    if(avatar.robot!==robot)throw Error('Robot switch recreated a WebGL context');
   }
   let geometryDisposed=0,materialsDisposed=0;
   const geometries=new Set(),materials=new Set();
   robot.scene.traverse(object=>{if(object.geometry)geometries.add(object.geometry);if(object.material)materials.add(object.material);});
   geometries.forEach(g=>g.addEventListener('dispose',()=>geometryDisposed++));
   materials.forEach(m=>m.addEventListener('dispose',()=>materialsDisposed++));
   const gl=robot.renderer.getContext();
   const image='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="blue"/></svg>');
   avatar.setAppearance({...settings,character:{id:'portrait',kind:'portrait',revision:1,image}});
   await avatar.ready;avatar.draw(0,0);
   if(geometryDisposed!==geometries.size||materialsDisposed!==materials.size)throw Error('GPU resources were not fully disposed');
   if(!gl.isContextLost())throw Error('Unused WebGL context remained active');
   if(avatar.robot||!avatar.image)throw Error('Portrait did not replace robot');
   avatar.setAppearance(settings);avatar.draw(0,.2);
   if(!avatar.robot||avatar.robot===robot)throw Error('Returning to robot did not restore rendering');
   avatar.robot.dispose();
   return {robot_switches:40,reused_context:true,disposed_geometries:geometryDisposed,disposed_materials:materialsDisposed,old_context_released:true,portrait_and_robot_playback:true};
  });
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  const report={...result,errors,external_requests:external,backend_writes:0};
  fs.writeFileSync('output/audit-live-ui-verification.json',JSON.stringify(report,null,2));
  console.log(report);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
