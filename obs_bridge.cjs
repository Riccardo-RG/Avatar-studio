const crypto=require('crypto');
function authentication(password,salt,challenge){const secret=crypto.createHash('sha256').update(password+salt).digest('base64');return crypto.createHash('sha256').update(secret+challenge).digest('base64');}
async function run(config){
 const socket=new WebSocket(`ws://127.0.0.1:${config.port||4455}`),pending=new Map();let identify,fail;
 const ready=new Promise((resolve,reject)=>{identify=resolve;fail=reject;});
 const timer=setTimeout(()=>{fail(Error('OBS non risponde. Abilita WebSocket nelle impostazioni di OBS.'));socket.close();},12000);
 socket.addEventListener('error',()=>fail(Error('OBS non raggiungibile su questo Mac.')));
 socket.addEventListener('close',()=>{for(const p of pending.values())p.reject(Error('Collegamento OBS interrotto.'));pending.clear();});
 socket.addEventListener('message',event=>{try{const m=JSON.parse(event.data);if(m.op===0){const d={rpcVersion:1,eventSubscriptions:0};if(m.d.authentication)d.authentication=authentication(config.password||'',m.d.authentication.salt,m.d.authentication.challenge);socket.send(JSON.stringify({op:1,d}));}else if(m.op===2){clearTimeout(timer);identify();}else if(m.op===7){const p=pending.get(m.d.requestId);if(p){pending.delete(m.d.requestId);m.d.requestStatus.result?p.resolve(m.d.responseData||{}):p.reject(Error('OBS ha rifiutato '+m.d.requestType+' (codice '+m.d.requestStatus.code+').'));}}}catch{fail(Error('Risposta OBS non valida.'));}});
 const call=(requestType,requestData={})=>new Promise((resolve,reject)=>{const id=crypto.randomUUID();const t=setTimeout(()=>{pending.delete(id);reject(Error('Comando OBS scaduto: verifica lo stato prima di ripetere.'));},15000);pending.set(id,{resolve:v=>{clearTimeout(t);resolve(v);},reject:e=>{clearTimeout(t);reject(e);}});socket.send(JSON.stringify({op:6,d:{requestType,requestId:id,requestData}}));});
 try{await ready;
  if(config.action==='status')return {version:await call('GetVersion'),stream:await call('GetStreamStatus'),record:await call('GetRecordStatus')};
  if(config.action==='setup'){
   const sceneName='Avatar Studio',inputName='Avatar Studio · scena locale',scene=await call('GetSceneList');
   if(!scene.scenes.some(s=>s.sceneName===sceneName))await call('CreateScene',{sceneName});
   const inputs=await call('GetInputList'),inputSettings={url:config.scene_url,width:1280,height:720,fps:30,reroute_audio:true,restart_when_active:false,shutdown:false};
   if(inputs.inputs.some(i=>i.inputName===inputName)){
    await call('SetInputSettings',{inputName,inputSettings,overlay:true});
    const items=await call('GetSceneItemList',{sceneName});
    if(!items.sceneItems.some(i=>i.sourceName===inputName))await call('CreateSceneItem',{sceneName,sourceName:inputName,sceneItemEnabled:true});
   }
   else await call('CreateInput',{sceneName,inputName,inputKind:'browser_source',inputSettings,sceneItemEnabled:true});
   return {scene:sceneName,input:inputName,message:'Scena preparata. Selezionala e controlla il mixer in OBS prima della trasmissione.'};
  }
  const commands={start_record:'StartRecord',stop_record:'StopRecord',start_stream:'StartStream',stop_stream:'StopStream'};
  if(!commands[config.action])throw Error('Comando OBS non consentito.');
  return await call(commands[config.action]);
 }finally{clearTimeout(timer);socket.close();}
}
module.exports={authentication,run};
if(require.main===module){let input='';process.stdin.on('data',c=>input+=c);process.stdin.on('end',async()=>{try{const result=await run(JSON.parse(input));process.stdout.write(JSON.stringify(result));}catch(e){process.stdout.write(JSON.stringify({error:e.message}));process.exitCode=1;}});}
