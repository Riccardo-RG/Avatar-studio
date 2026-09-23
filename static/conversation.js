const $=s=>document.querySelector(s);
let sdkPromise;
function daily(){
 if(window.Daily)return Promise.resolve(window.Daily);
 if(!sdkPromise)sdkPromise=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='/vendor/daily.js';script.onload=()=>window.Daily?resolve(window.Daily):reject(Error('SDK della conversazione non disponibile.'));script.onerror=()=>{script.remove();sdkPromise=null;reject(Error('Impossibile caricare la conversazione.'));};document.head.append(script);});
 return sdkPromise;
}
export function initConversation({api,report,status}){
 const panel=document.createElement('section');panel.className='platform-form conversation-review';panel.id='conversation-review';
 panel.innerHTML=`<h3>Un intervento dalla chat</h3><p id="conversation-state" class="hint" role="status">Apri una conversazione Tavus attiva per inviare un testo rivisto.</p><p class="hint">Microfono e videocamera partono spenti. Ogni invio raggiunge il servizio esterno della stanza aperta.</p><form id="conversation-form" class="platform-form"><p id="conversation-source" class="publication-copy">Testo manuale · nessun messaggio selezionato</p><label>Come interviene il personaggio<select name="mode"><option value="echo">Pronuncia esattamente il testo rivisto</option><option value="respond">Genera una risposta alla domanda rivista</option></select></label><label>Testo da inviare · massimo 600 caratteri<textarea name="text" maxlength="600" required></textarea></label><p class="hint" id="conversation-mode-note">Il personaggio pronuncerà il testo che scrivi qui.</p><div class="platform-actions"><button type="submit" class="button secondary" id="conversation-send" disabled>Invia testo rivisto</button><button type="button" class="button" id="conversation-clear">Usa un testo manuale</button><button type="button" class="button" id="conversation-interrupt" disabled>Interrompi voce Tavus</button><button type="button" class="button" id="conversation-close" disabled>Chiudi questa finestra della stanza</button></div></form><p class="hint">L’invio al canale non conferma che il personaggio abbia pronunciato la frase. Gli interventi con esito incerto non vengono ritentati automaticamente. Chiudere la finestra non sostituisce “Termina sul servizio”.</p><div id="conversation-log" class="hint"></div>`;
 $('#broadcast-room').after(panel);
 const form=$('#conversation-form'),clientId=crypto.randomUUID();let call=null,identity=null,joined=false,busy=false,opening=false,closing=null,timer=null,source=null,heartbeatBusy=false;
 const base=()=>({id:identity,client_id:clientId});
 const note=text=>$('#conversation-state').textContent=text;
 function controls(){for(const id of ['conversation-send','conversation-interrupt'])$('#'+id).disabled=!joined||busy;$('#conversation-close').disabled=!identity;}
 async function log(){const id=identity;if(!id)return;try{const doc=await fetch('/api/broadcast').then(r=>r.json()),s=doc.sessions.find(s=>s.id===id);if(identity!==id)return;const box=$('#conversation-log');box.replaceChildren();for(const e of (s?.bridge_events||[]).slice(-5).reverse()){const p=document.createElement('p');p.textContent=new Date(e.created*1000).toLocaleTimeString('it-IT')+' · '+({echo:'Testo rivisto',respond:'Domanda rivista',interrupt:'Interruzione'}[e.mode])+' · '+({issued:'esito da verificare',dispatched:'consegnato al canale, ricezione non confermata',uncertain:'esito incerto · nessuna ripetizione'}[e.state]);box.append(p);}}catch{}}
 function close(message='Finestra chiusa. Verifica o termina la sessione sul servizio.'){
  if(closing)return closing;
  const old=call,data=base();call=null;identity=null;joined=false;clearInterval(timer);timer=null;controls();note(message);
  closing=Promise.resolve().then(async()=>{
   if(old){try{await old.destroy();}catch{}}
   $('#broadcast-room').replaceChildren();if(data.id)try{await api('conversation-release',data);}catch{}
  }).finally(()=>{closing=null;});
  return closing;
 }
 async function open(session){
  if(opening)throw Error('Apertura della stanza già in corso.');
  if(identity===session.id&&joined){panel.scrollIntoView({behavior:'smooth'});return;}
  opening=true;
  try{
   if(closing)await closing;
   if(identity)await close();const data={id:session.id,client_id:clientId};const room=await api('conversation-claim',data);identity=session.id;controls();note('Collegamento alla conversazione di '+room.character_name+'…');
   timer=setInterval(async()=>{if(heartbeatBusy||!identity)return;heartbeatBusy=true;const heartbeatData=base();try{await api('conversation-heartbeat',heartbeatData);}catch(e){if(identity===heartbeatData.id)await close(e.message);}finally{heartbeatBusy=false;}},5000);
   const SDK=await daily();if(!identity)throw Error('Apertura interrotta.');
   const frame=SDK.createFrame($('#broadcast-room'),{startAudioOff:true,startVideoOff:true,showLocalVideo:false,iframeStyle:{width:'100%',height:'540px',border:'0',borderRadius:'12px'}});call=frame;
   frame.on('left-meeting',()=>{if(call===frame)close('Collegamento alla stanza terminato. Nessun reinvio automatico.').catch(report);});
   frame.on('error',()=>{if(call===frame)close('Collegamento interrotto. Verifica gli interventi con esito incerto.').catch(report);});
   frame.on('app-message',event=>{if(call!==frame)return;const kind=event.data?.event_type,role=event.data?.properties?.role;if(role==='user')return;if(kind==='conversation.started_speaking')note(room.character_name+' sta parlando nella stanza.');else if(kind==='conversation.stopped_speaking')note('Stanza di '+room.character_name+' collegata. Seleziona e rivedi un intervento.');});
   await frame.join({url:room.url,startAudioOff:true,startVideoOff:true});if(call!==frame)return;
   joined=true;controls();note('Stanza di '+room.character_name+' collegata. Microfono e videocamera inizialmente spenti.');await log();
  }catch(e){await close(e.message);throw e;}finally{opening=false;}
 }
 async function send(mode){
  if(!joined||!call||busy)throw Error('Apri prima la conversazione e attendi il collegamento.');
  if(!Object.values(call.participants()).some(p=>!p.local))throw Error('Attendi che il personaggio sia presente nella stanza.');
  const current=call,data={...base(),mode,text:form.elements.text.value,source_message_id:mode==='interrupt'?'':source?.id||'',confirmed:true};busy=true;controls();let issued=null;
  try{
   issued=await api('conversation-issue',data);
   if(call!==current||!joined)throw Error('La stanza si è scollegata prima dell’invio.');
   await Promise.resolve(current.sendAppMessage(issued.payload,'*'));
   await api('conversation-ack',{...data,event_id:issued.event_id,state:'dispatched'});
   status('Intervento consegnato al canale della stanza. Controlla la risposta del personaggio.');
   if(mode!=='interrupt'&&identity===data.id&&form.elements.text.value===data.text&&(source?.id||'')===data.source_message_id)form.elements.text.value='';
  }catch(error){if(issued){try{await api('conversation-ack',{...data,event_id:issued.event_id,state:'uncertain'});}catch{}status('Esito dell’intervento da verificare nella stanza. Nessun reinvio automatico.',true);}throw error;}
  finally{busy=false;controls();await log();}
 }
 const guard=fn=>async e=>{e?.preventDefault();try{await fn();}catch(error){report(error);}};
 form.onsubmit=guard(()=>send(form.elements.mode.value));$('#conversation-interrupt').onclick=guard(()=>send('interrupt'));$('#conversation-close').onclick=guard(()=>close());
 $('#conversation-clear').onclick=()=>{source=null;form.elements.text.value='';$('#conversation-source').textContent='Testo manuale · nessun messaggio selezionato';};
 form.elements.mode.onchange=()=>{$('#conversation-mode-note').textContent=form.elements.mode.value==='echo'?'Il personaggio pronuncerà il testo che scrivi qui.':'Il servizio genererà una risposta alla domanda: controlla il risultato durante la conversazione.';if(source)form.elements.text.value=form.elements.mode.value==='respond'?source.text:source.reply||'';};
 window.addEventListener('studio:review-conversation',event=>{source=event.detail;form.elements.mode.value='echo';form.elements.mode.onchange();$('#conversation-source').textContent=source.author+' · '+source.text;document.querySelector('[data-view=live]').click();panel.scrollIntoView({behavior:'smooth',block:'start'});form.elements.text.focus({preventScroll:true});});
 controls();return {open,close,ended:async id=>{if(identity===id)await close('Sessione terminata sul servizio.');}};
}
