// Read-only chat connectors. No endpoint for sending messages or starting streams.
const platform=process.argv[2];let closing=false,socket,handoff,watchdog,validating=false;
const emit=(type,data={})=>process.stdout.write(JSON.stringify({type,...data})+'\n');
const fail=(message)=>{emit('error',{message});process.exitCode=1;closing=true;socket?.close();handoff?.close();handoff=null;clearInterval(watchdog);};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function request(url,options={}){const response=await fetch(url,{...options,signal:AbortSignal.timeout(15000)});if(!response.ok){const error=new Error('HTTP '+response.status);error.status=response.status;throw error;}return response.json();}
function twitchEvent(data){if(data.metadata?.subscription_type!=='channel.chat.message')return null;const e=data.payload?.event;if(!e||typeof e.message?.text!=='string')return null;return {author:e.chatter_user_name||e.chatter_user_login||'Spettatore',text:e.message.text,event_id:e.message_id||data.metadata.message_id,user_id:e.chatter_user_id};}
function youtubeEvents(data){return (data.items||[]).filter(i=>i.snippet?.type==='textMessageEvent').map(i=>({author:i.authorDetails?.displayName||'Spettatore',text:i.snippet.textMessageDetails?.messageText||i.snippet.displayMessage||'',event_id:i.id,user_id:i.authorDetails?.channelId}));}
function reconnectURL(raw){const u=new URL(raw);if(u.protocol!=='wss:'||u.hostname!=='eventsub.wss.twitch.tv'||(u.port&&u.port!=='443')||u.username||u.password)throw Error('Reconnect non valido');return u.href;}
async function twitch(){
 const token=(process.env.AVATAR_CHAT_TOKEN||'').replace(/^oauth:/,'');
 const validate=()=>request('https://id.twitch.tv/oauth2/validate',{headers:{Authorization:'OAuth '+token}});
 let auth=await validate();if(!auth.user_id||!auth.client_id||!auth.scopes?.includes('user:read:chat'))throw Error('È necessario un token utente con permesso user:read:chat.');
 let attempts=0,last=Date.now(),timeout=30000,lastValidation=Date.now(),channel=auth.user_id;
 const connect=(url='wss://eventsub.wss.twitch.tv/ws',reconnecting=false)=>{
  const previous=socket,ws=new WebSocket(url);socket=ws;handoff=reconnecting?previous:null;
  // Twitch keeps delivering notifications on the old socket until the new
  // welcome arrives. Preserve that handover window, then ignore the old socket.
  ws.onmessage=async event=>{if(ws!==socket&&ws!==handoff)return;last=Date.now();let data;try{data=JSON.parse(event.data);}catch{return;}
   try{
    const kind=data.metadata?.message_type;
    if(kind==='session_welcome'){
     if(ws!==socket)return;
     timeout=((data.payload.session.keepalive_timeout_seconds||30)+8)*1000;
     if(!reconnecting)await request('https://api.twitch.tv/helix/eventsub/subscriptions',{method:'POST',headers:{Authorization:'Bearer '+token,'Client-Id':auth.client_id,'Content-Type':'application/json'},body:JSON.stringify({type:'channel.chat.message',version:'1',condition:{broadcaster_user_id:channel,user_id:auth.user_id},transport:{method:'websocket',session_id:data.payload.session.id}})});
     if(ws!==socket||closing)return;handoff=null;previous?.close();attempts=0;emit('status',{message:'Twitch collegato · '+(auth.login||'canale autorizzato')});
    }else if(kind==='notification'){const m=twitchEvent(data);if(m&&data.payload.event.broadcaster_user_id===channel)emit('message',m);}
    else if(kind==='session_reconnect'&&ws===socket)connect(reconnectURL(data.payload.session.reconnect_url),true);
    else if(kind==='revocation')fail('Autorizzazione Twitch revocata. Ricollega il canale.');
   }catch(e){fail(e.status===401?'Token Twitch scaduto. Ricollega il canale.':'Impossibile attivare la lettura Twitch. Verifica token e permessi.');}
  };
  ws.onerror=()=>{};
  ws.onclose=async()=>{if(ws!==socket||closing)return;handoff?.close();handoff=null;if(++attempts>5)return fail('Twitch disconnesso dopo cinque tentativi.');emit('status',{message:'Riconnessione Twitch…'});await pause(Math.min(30000,1000*2**attempts));if(!closing){last=Date.now();connect();}};
 };
 connect();watchdog=setInterval(async()=>{if(Date.now()-last>timeout){last=Date.now();socket?.close();}if(!validating&&Date.now()-lastValidation>3600000){validating=true;try{auth=await validate();lastValidation=Date.now();}catch{fail('Token Twitch non più valido. Ricollega il canale.');}finally{validating=false;}}},2000);
}
async function youtube(){
 const token=process.env.AVATAR_CHAT_TOKEN||'',chat=process.env.AVATAR_CHAT_ID||'';
 if(!/^[\w-]{4,300}$/.test(chat))throw Error('Inserisci l’ID della chat live YouTube.');
 let next='',first=true,requests=0;
 while(!closing&&requests<100){
  const q=new URLSearchParams({liveChatId:chat,part:'snippet,authorDetails',maxResults:'200'});if(next)q.set('pageToken',next);
  const data=await request('https://www.googleapis.com/youtube/v3/liveChat/messages?'+q,{headers:{Authorization:'Bearer '+token}});requests++;
  if(!first)for(const m of youtubeEvents(data))emit('message',m); // Do not answer old chat history on connection.
  first=false;next=data.nextPageToken||'';
  emit('status',{message:'YouTube collegato · sola lettura ('+requests+'/100 richieste)'});
  if(data.offlineAt)return fail('La diretta YouTube è terminata.');
  await pause(Math.max(15000,Number(data.pollingIntervalMillis)||15000));
 }
 if(!closing)fail('Raggiunto il limite di 100 letture YouTube. Ricollega quando necessario.');
}
if(require.main===module){process.on('SIGTERM',()=>{closing=true;socket?.close();handoff?.close();clearInterval(watchdog);process.exit(0);});
 (platform==='twitch'?twitch():platform==='youtube'?youtube():Promise.reject(Error('Piattaforma non valida'))).catch(e=>fail(e.status===401?'Token scaduto o non valido.':e.status===403?'Accesso negato: verifica permessi, chat attiva e quota API.':e.status?'Servizio non disponibile (HTTP '+e.status+').':e.message.includes('token')||e.message.includes('ID')?e.message:'Collegamento non riuscito. Controlla connessione e credenziali.'));
}
module.exports={twitchEvent,youtubeEvents,reconnectURL};
