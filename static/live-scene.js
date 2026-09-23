import {LiveCanvas} from './live-canvas.js';
const $=s=>document.querySelector(s),params=new URLSearchParams(location.search),monitor=params.has('monitor'),obs=params.has('obs');
try{const size=localStorage.getItem('avatar-text-size');if(['18','20','22'].includes(size))document.documentElement.style.fontSize=size+'px';}catch{}
if(monitor)document.body.classList.add('monitor');if(obs)document.body.classList.add('obs');
const boot=await fetch('/api/bootstrap').then(r=>r.json()),client=crypto.randomUUID();
async function api(path,data){const r=await fetch('/api/live/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-Avatar-Token':boot.token},body:JSON.stringify(data)});const v=await r.json();if(!r.ok)throw Error(v.error||'Regia non disponibile');return v;}
const visual=new LiveCanvas($('#program'),boot.settings),audio=new Audio();audio.preload='auto';
let state={phase:'idle',config:{},queue:[]},project=null,itemId=null,owner=false,playing=false,ended=false,blocked=false,loading=false,lastContact=0,lastPoll=0,ticket=0;
let context,recordDestination,recorder,chunks=[],recordBlob=null,recordURL=null;
const note=t=>$('#notice').textContent=t;
function audioGraph(){if(!context){context=new AudioContext();const source=context.createMediaElementSource(audio);recordDestination=context.createMediaStreamDestination();source.connect(context.destination);source.connect(recordDestination);}return context;}
async function activate(force=false){audioGraph();await context.resume();const r=await api('claim',{client,force});owner=r.owner;if(owner){blocked=false;note('Uscita audio attiva · i comandi sono nella regia');$('#activate').hidden=true;$('#record').hidden=obs;$('#controls').classList.add('quiet');}else{note('Un’altra scena controlla l’audio. Premi per trasferirlo qui.');$('#activate').hidden=false;}return owner;}
$('#activate').onclick=()=>activate(true).catch(e=>note(e.message));
audio.onended=()=>{playing=false;ended=true;};audio.onerror=()=>{blocked=true;playing=false;note('Audio non disponibile. Controlla la regia.');};
async function sync(next){
 state=next;
 if(monitor){if(state.current?.id!==itemId){itemId=state.current?.id||null;project=null;if(itemId){const id=itemId;const p=await fetch(state.current.timeline).then(r=>r.json());if(id===itemId)project=p;}}return;}
 if(owner&&state.owner!==client){owner=false;audio.pause();playing=false;note('Il controllo audio è passato a un’altra scena.');$('#activate').hidden=false;$('#controls').classList.remove('quiet');}
 const nextId=state.current?.id||null;
 if(nextId!==itemId){const stamp=++ticket;audio.pause();playing=false;ended=false;project=null;itemId=nextId;loading=false;
  if(itemId){loading=true;try{const p=await fetch(state.current.timeline).then(r=>{if(!r.ok)throw Error('Traccia mancante');return r.json();});if(stamp!==ticket)return;project=p;audio.src=state.current.audio;audio.load();}catch{blocked=true;}finally{if(stamp===ticket)loading=false;}}
 }
 if(!owner||state.phase!=='running'||!itemId){audio.pause();playing=false;return;}
 if(project&&!playing&&!ended&&!loading&&!blocked){try{audio.currentTime=Math.min(state.position||0,Math.max(0,project.duration-.01));await Promise.race([audioGraph().resume(),new Promise((_,reject)=>setTimeout(()=>reject(Error('Attiva audio')),1200))]);await audio.play();playing=true;$('#activate').hidden=true;$('#controls').classList.add('quiet');}catch{blocked=true;$('#activate').hidden=false;$('#controls').classList.remove('quiet');note('Premi Attiva questa uscita audio, poi Riprendi nella regia.');}}
}
async function poll(){try{const r=await fetch('/api/live',{signal:AbortSignal.timeout(1500)});if(!r.ok)throw Error();const next=await r.json();lastContact=performance.now();await sync(next);if(owner){const reply=await api('heartbeat',{client,item:itemId,position:audio.currentTime||0,status:blocked?'blocked':playing?'playing':state.phase==='paused'?'paused':'ready',ended});if(!reply.owner){owner=false;audio.pause();playing=false;}if(ended)ended=false;}}
 catch{audio.pause();playing=false;note('Regia non raggiungibile. Audio interrotto.');$('#controls').classList.remove('quiet');}finally{setTimeout(poll,300);}}
let lastFrame=0;function frame(now){if(now-lastFrame>(monitor?150:owner?40:1000)){lastFrame=now;const disconnected=performance.now()-lastContact>2000;if(disconnected){audio.pause();playing=false;}
 const t=monitor?(state.position||0):audio.currentTime||0;visual.draw(disconnected?{...state,phase:'paused'}:state,project,t,now/1000);}requestAnimationFrame(frame);}requestAnimationFrame(frame);
window.liveRecording={async start(){if(monitor||!owner)throw Error('Attiva questa uscita audio prima di registrare.');await audioGraph().resume();chunks=[];recordBlob=null;const stream=$('#program').captureStream(24);for(const track of recordDestination.stream.getAudioTracks())stream.addTrack(track);const mime=['video/webm;codecs=vp8,opus','video/webm'].find(x=>MediaRecorder.isTypeSupported(x));recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:3500000});recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};recorder.start(1000);$('#record').textContent='Ferma registrazione';$('#download').hidden=true;return true;},stop(){return new Promise(resolve=>{if(!recorder||recorder.state==='inactive')return resolve(false);recorder.onstop=()=>{recordBlob=new Blob(chunks,{type:'video/webm'});$('#record').textContent='Registra prova';$('#download').hidden=false;resolve(true);};recorder.stop();});},async data(){if(!recordBlob)return null;return new Promise(resolve=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.readAsDataURL(recordBlob);});}};
$('#record').onclick=async()=>{try{if(recorder?.state==='recording')await window.liveRecording.stop();else await window.liveRecording.start();}catch(e){note(e.message);}};
$('#download').onclick=()=>{if(!recordBlob)return;if(recordURL)URL.revokeObjectURL(recordURL);recordURL=URL.createObjectURL(recordBlob);const a=document.createElement('a');a.href=recordURL;a.download='avatar-live-'+new Date().toISOString().slice(0,19).replace(/:/g,'-')+'.webm';a.click();};
window.liveDebug=()=>({owner,phase:state.phase,item:itemId,playing,position:audio.currentTime,blocked,ready:!!project,context:context?.state,recording:recorder?.state});
if(!monitor){try{owner=(await api('claim',{client})).owner;if(owner){note('Scena collegata. Avvia dalla regia.');$('#record').hidden=obs;}else note('Scena in ascolto. Un’altra uscita controlla l’audio.');}catch{note('Apri lo studio prima della scena.');}}
setInterval(()=>{if(!owner)return;$('#program').toBlob(blob=>{if(blob&&blob.size<=250000)fetch('/api/live/frame',{method:'POST',headers:{'X-Avatar-Token':boot.token,'X-Scene-Client':client,'Content-Type':'image/jpeg'},body:blob}).catch(()=>{});},'image/jpeg',.55);},1500);
window.sceneReady=true;poll();
