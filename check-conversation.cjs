const fs=require('fs'),assert=require('assert'),path=require('path'),os=require('os');
const {chromium}=require(require('./runtime_config.cjs').playwright);
(async()=>{
 const browser=await chromium.launch({executablePath:require('./runtime_config.cjs').chrome,headless:true});const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],external=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
 const session={id:'test-session',state:'active',deadline:Date.now()/1000+300,remote_id:'test-remote',character_name:'Ari',bridge_events:[]};let controller=null;
 await page.addInitScript(()=>{window.fakeDaily={sent:[],options:null,join:null,destroyed:0,remote:true,fail:false,handlers:{}};window.Daily={createFrame:(parent,options)=>{window.fakeDaily.options=options;parent.textContent='Stanza simulata · nessuna chiamata esterna';return {on:(event,fn)=>window.fakeDaily.handlers[event]=fn,join:async data=>{window.fakeDaily.join=data;},participants:()=>window.fakeDaily.remote?{local:{local:true},avatar:{local:false}}:{local:{local:true}},sendAppMessage:(payload,recipient)=>{if(window.fakeDaily.fail)throw Error('Connessione interrotta simulata');window.fakeDaily.sent.push({payload,recipient});},destroy:async()=>{window.fakeDaily.destroyed++;if(window.fakeDaily.delayDestroy)await new Promise(resolve=>setTimeout(resolve,window.fakeDaily.delayDestroy));}};}};});
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!=='http://127.0.0.1:8765'&&!req.url().startsWith('data:')){external.push(req.url());return route.abort();}const json=data=>route.fulfill({json:data});
  if(u.pathname==='/api/broadcast')return json({sessions:[session]});
  if(u.pathname==='/api/live'){const response=await route.fetch(),data=await response.json();data.messages=[{id:'chat-reference',state:'review',author:'Spettatore di prova',source:'test',text:'Di cosa parli oggi?',reason:'Da rivedere'}];return json(data);}
  if(u.pathname.startsWith('/api/conversation-')){const data=req.postDataJSON();writes.push({path:u.pathname,data});
   if(u.pathname.endsWith('claim')){controller=data.client_id;return json({url:'https://tavus.daily.co/test?t=fake',character_name:'Ari',deadline:session.deadline});}
   if(u.pathname.endsWith('release')){controller=null;return json({ok:true});}
   assert.equal(data.client_id,controller);
   if(u.pathname.endsWith('heartbeat'))return json({ok:true,deadline:session.deadline});
   if(u.pathname.endsWith('issue')){const id='event-'+session.bridge_events.length;session.bridge_events.push({id,mode:data.mode,source_message_id:data.source_message_id,created:Date.now()/1000,state:'issued'});return json({event_id:id,payload:{message_type:'conversation',conversation_id:'test-remote',event_type:'conversation.'+data.mode,...(data.mode==='interrupt'?{}:{properties:data.mode==='echo'?{modality:'text',text:data.text,done:true}:{text:data.text}})}});}
   if(u.pathname.endsWith('ack')){session.bridge_events.find(e=>e.id===data.event_id).state=data.state;return json({state:data.state});}
   throw Error('Route inattesa');
  }
  if(req.method()==='POST'&&u.pathname!=='/api/clip-details')throw Error('Mutazione non simulata: '+u.pathname);return route.continue();
 });
 try{
  await page.goto('http://127.0.0.1:8765/#live');await page.waitForFunction(()=>window.studioReady===true);assert(await page.locator('#conversation-send').isDisabled());assert.equal(writes.length,0);
  await page.getByRole('button',{name:'Prepara per Tavus',exact:true}).click();assert.equal(writes.length,0);assert.match(await page.locator('#conversation-source').innerText(),/Spettatore/);assert.equal(await page.locator('#conversation-form [name=text]').inputValue(),'');
  await page.getByRole('button',{name:'Apri conversazione',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#conversation-send').disabled);
  const opts=await page.evaluate(()=>window.fakeDaily.options);assert.equal(opts.startAudioOff,true);assert.equal(opts.startVideoOff,true);assert.equal(await page.evaluate(()=>window.fakeDaily.sent.length),0);
  await page.locator('#conversation-form [name=text]').fill('Oggi parlo di creatività.');await page.locator('#conversation-send').click();await page.waitForFunction(()=>window.fakeDaily.sent.length===1);await page.waitForFunction(()=>document.querySelector('#conversation-log').textContent.includes('ricezione non confermata'));
  const first=await page.evaluate(()=>window.fakeDaily.sent[0]);assert.equal(first.payload.properties.text,'Oggi parlo di creatività.');assert.equal(first.payload.event_type,'conversation.echo');assert.equal(first.recipient,'*');assert.equal(writes.find(w=>w.path.endsWith('issue')).data.source_message_id,'chat-reference');
  await page.locator('#conversation-clear').click();await page.locator('#conversation-form [name=mode]').selectOption('respond');await page.locator('#conversation-form [name=text]').fill('Un consiglio creativo?');await page.locator('#conversation-send').click();await page.waitForFunction(()=>window.fakeDaily.sent.length===2);assert.equal(await page.evaluate(()=>window.fakeDaily.sent[1].payload.event_type),'conversation.respond');
  await page.locator('#conversation-interrupt').click();await page.waitForFunction(()=>window.fakeDaily.sent.length===3);assert.equal(await page.evaluate(()=>window.fakeDaily.sent[2].payload.event_type),'conversation.interrupt');
  await page.evaluate(()=>window.fakeDaily.remote=false);await page.locator('#conversation-form [name=text]').fill('Aspetto il personaggio.');const count=writes.filter(w=>w.path.endsWith('issue')).length;await page.locator('#conversation-send').click();await page.waitForTimeout(200);assert.equal(writes.filter(w=>w.path.endsWith('issue')).length,count);
  await page.evaluate(()=>{window.fakeDaily.remote=true;window.fakeDaily.fail=true;});await page.locator('#conversation-send').click();await page.waitForFunction(()=>document.querySelector('#conversation-log').textContent.includes('esito incerto'));assert.equal(session.bridge_events.at(-1).state,'uncertain');assert.equal(await page.evaluate(()=>window.fakeDaily.sent.length),3);
  await page.locator('#text-size').selectOption('22');await page.setViewportSize({width:390,height:844});await page.locator('#conversation-review').scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.screenshot({path:'output/conversation-review-mobile.png'});
  await page.locator('#conversation-close').click();await page.waitForFunction(()=>document.querySelector('#conversation-send').disabled);assert.equal(await page.evaluate(()=>window.fakeDaily.destroyed),1);
  await page.getByRole('button',{name:'Apri conversazione',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#conversation-send').disabled);
  await page.evaluate(()=>window.fakeDaily.delayDestroy=300);
  await page.locator('#conversation-close').click();
  await page.getByRole('button',{name:'Apri conversazione',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('#conversation-send').disabled);
  assert.equal(await page.locator('#broadcast-room').innerText(),'Stanza simulata · nessuna chiamata esterna');
  assert(controller,'Previous close must not release the reopened controller');
  const lastRelease=writes.findLastIndex(w=>w.path.endsWith('release')),lastClaim=writes.findLastIndex(w=>w.path.endsWith('claim'));
  assert(lastRelease<lastClaim,'Release must complete before the next claim');
  await page.locator('#conversation-close').click();
  await page.waitForTimeout(350);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);const report={mock_sdk:true,close_reopen_serialized:true,real_sessions:false,review_before_send:true,selected_chat_reference:true,mic_camera_initially_off:true,echo:true,respond:true,interrupt:true,absent_participant_blocks:true,uncertain_not_retried:true,mobile_font22_overflow:false,errors,external_requests:external};fs.writeFileSync('output/conversation-ui-verification.json',JSON.stringify(report,null,2));console.log(report);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
