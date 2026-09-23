import {languageField,setVoices,usualVoice,languageNames} from './languages.js';
import {Avatar, timelineAt} from './character-renderer.js';
import {initStudio} from './studio.js';
import {initProjects} from './projects.js';
import {initNavigation,navigate} from './navigation.js';
import {initLive} from './live-control.js';
import {initPlatform} from './platform.js';
import {initDelivery} from './delivery.js';
import {initInsights} from './insights.js';
import {initClips} from './clips.js';
import {initActivity} from './activity.js';
import {initBusiness,editorialDraft} from './business.js';
const $ = selector => document.querySelector(selector);
const textSize=$('#text-size');try{const saved=localStorage.getItem('avatar-text-size');if(['18','20','22'].includes(saved))textSize.value=saved;}catch{}document.documentElement.style.fontSize=textSize.value+'px';textSize.onchange=()=>{document.documentElement.style.fontSize=textSize.value+'px';try{localStorage.setItem('avatar-text-size',textSize.value);}catch{}};
const bootstrap = await fetch('/api/bootstrap').then(r => r.json());
let studioConfig = bootstrap.studio_settings;
let projectCharacterSnapshot = null;
let config = bootstrap.settings, videoCharacter=bootstrap.settings.character, avatar, previewAudio, previewProject, previewTicket = 0, speaking = false;
const status = (text, error = false) => {$('#status').hidden = !text; $('#status').textContent = text; $('#status').classList.toggle('error', error);};
async function api(path, data) {
  const response = await fetch('/api/' + path, {method:'POST', headers: {'Content-Type':'application/json','X-Avatar-Token':bootstrap.token}, body:JSON.stringify(data)});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Operazione non riuscita');
  return value;
}
function report(error) {status(error.message || String(error), true);}
try {avatar = new Avatar($('#avatar'), config, 360);} catch (e) {status('Il browser non supporta la scena 3D. Apri lo studio in Chrome.', true);}
const start = performance.now();
let lastFrame = 0;
function animate(now) {
  if (now - lastFrame < 66 || document.hidden || $('#view-create').hidden) {requestAnimationFrame(animate);return;}
  lastFrame = now;
  const time = (performance.now() - start) / 1000;
  if (speaking && previewAudio && previewProject) {const t=previewAudio.currentTime, point=timelineAt(previewProject,t);avatar?.draw(t,point.amplitude,point.caption,point.progress,point.shape);}
  else avatar?.draw(time,0,'La tua prossima idea prende voce.');
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);
const languageLabel=languageField('language');const contentLanguage=languageLabel.querySelector('select');contentLanguage.id='content-language';
$('#voice').parentElement.before(languageLabel);setVoices($('#voice'),bootstrap.voice_catalog,contentLanguage.value,usualVoice(videoCharacter,contentLanguage.value));$('#rate').value=config.rate;
const languageNote=document.createElement('p');languageNote.className='hint';languageNote.textContent='La lingua sceglie la voce e le nuove bozze. Il testo già scritto si traduce solo con il comando dedicato, dopo revisione.';languageLabel.parentElement.after(languageNote);
contentLanguage.onchange=()=>{stopPreview();setVoices($('#voice'),bootstrap.voice_catalog,contentLanguage.value,usualVoice(videoCharacter,contentLanguage.value));saveQuick();updateProvider();updateMeta();};
function updateMeta() {
  const text = $('#script').value.trim(), words = text ? text.split(/\s+/).length : 0;
  $('#word-count').textContent = `${words} parole · ${text.length}/2400`;
  $('#estimate').textContent = `≈ ${Math.round(words / Number($('#rate').value) * 60)} secondi`;
  $('#rate-label').textContent = $('#rate').value;
  $('#project-save').disabled = text.length < 2 || !$('#voice').value;
  $('#preview').disabled = text.length < 2 || !$('#voice').value;
  window.dispatchEvent(new CustomEvent('studio:draft-changed'));
}
function updateProvider() {
  $('#provider-hint').textContent = config.provider === 'local' ? 'AI locale · la bozza può richiedere qualche minuto. Rileggi sempre il risultato.' : config.provider === 'ollama' ? 'Ollama sul Mac · assicurati che sia in esecuzione.' : 'OpenAI · usa la chiave e il budget configurati.';
  $('#engine-footer').textContent = `${config.provider === 'openai' ? 'AI esterna' : 'AI locale'} · ${config.voice.startsWith('piper:') ? 'voce neurale' : 'voce macOS'} · MP4 sul Mac`;
  document.querySelectorAll('[data-color]').forEach(b => b.classList.toggle('selected', b.dataset.color === config.accent));
}
updateProvider();updateMeta();
$('#voice').addEventListener('change',()=>{stopPreview();saveQuick();updateProvider();});
for (const id of ['script','rate','title','topic']) $('#' + id).addEventListener('input', updateMeta);
for (const id of ['script','rate']) $('#' + id).addEventListener('input', stopPreview);
function stopPreview() {delete $('#preview').dataset.loading;previewTicket++;previewAudio?.pause();previewAudio=null;previewProject=null;speaking=false;$('#preview').textContent='▷ Ascolta il testo';}

function setMode(topic) {
  $('#topic-area').hidden = !topic;
  $('#topic-tab').setAttribute('aria-selected', String(topic));$('#text-tab').setAttribute('aria-selected', String(!topic));
  if (topic) $('#topic').focus();else $('#script').focus();
}
$('#text-tab').onclick = () => setMode(false);$('#topic-tab').onclick = () => setMode(true);
$('#sample').onclick = () => {stopPreview();const italian = 'Ciao! Sono il tuo primo avatar. Per adesso ho un aspetto neutro, ma posso già dare voce alle tue idee. Tu scegli il testo, io lo trasformo in un video. Il mio nome, la voce e i colori possono cambiare. Da quale idea cominciamo?';$('#script').value=({it:italian,en:'Hello! I am your virtual character. Choose an idea, and we can turn it into a short video together.',es:'¡Hola! Soy tu personaje virtual. Elige una idea y podremos convertirla en un vídeo corto.'})[contentLanguage.value];updateMeta();};
$('#preview').onclick = async () => {
  if(speaking || $('#preview').dataset.loading) {delete $('#preview').dataset.loading;stopPreview();return;}
  const ticket=++previewTicket;
  $('#preview').dataset.loading='true';$('#preview').textContent='□ Annulla preparazione';
  status('Preparo la voce selezionata. Il primo ascolto neurale può richiedere qualche secondo.');
  try {
    await saveQuick();const result=await api('preview',{script:$('#script').value,character_id:$('#video-character')?.value,voice:$('#voice').value,rate:Number($('#rate').value),language:contentLanguage.value});
    if(ticket!==previewTicket) return;
    previewProject=result.project;previewAudio=new Audio(result.audio);
    previewAudio.onended=()=>stopPreview();
    await previewAudio.play();speaking=true;$('#preview').textContent='□ Ferma ascolto';
    status('Stai ascoltando la voce usata nel video, con sottotitoli e movimento della bocca sincronizzati.');
  }catch(e){if(ticket===previewTicket){stopPreview();report(e);}}
  finally{if(ticket===previewTicket) delete $('#preview').dataset.loading;}
};
async function saveQuick() {config={...studioConfig,...videoCharacter,character:videoCharacter,voice:$('#voice').value,rate:Number($('#rate').value),language:contentLanguage.value};return config;}
$('#generate').onclick = async () => {
  $('#generate').disabled = true;$('#generate').textContent = 'Scrittura in corso…';
  const draftState=()=>JSON.stringify([contentLanguage.value,videoCharacter.id,videoCharacter.revision,$('#script').value,$('#topic').value,$('#seconds').value,$('#rubric-select').value,$('#rate').value,editorialDraft()]);
  const requestedState=draftState();
  status('Sto preparando una bozza. Con il modello locale può servire qualche minuto.');
  try {await saveQuick(); const result = await api('script', {...editorialDraft(),topic:$('#topic').value, seconds:Number($('#seconds').value),rubric_id:$('#rubric-select').value,character_id:$('#video-character')?.value,language:contentLanguage.value,voice:$('#voice').value,rate:Number($('#rate').value)});if(draftState()!==requestedState)throw Error('Il contenuto è cambiato durante la generazione. La bozza non sostituisce il testo attuale: riprova con le nuove scelte.');stopPreview();$('#script').value = result.script;if($('#title').value === 'Il mio primo video' || !$('#title').value) $('#title').value = $('#topic').value.slice(0,80);updateMeta();status(result.note);}
  catch(e) {report(e);} finally {$('#generate').disabled = false;$('#generate').textContent = '✧ Scrivi una bozza';}
};
const translate=document.createElement('button');translate.type='button';translate.id='translate-script';translate.className='button secondary';translate.textContent='Prepara versione nella lingua scelta';languageNote.after(translate);
const translationDialog=document.createElement('dialog');translationDialog.id='translation-dialog';translationDialog.className='platform-modal';translationDialog.innerHTML='<h2>Rivedi la versione tradotta</h2><p class="hint">Controlla significato, nomi, numeri e completezza. Titolo e argomento restano modificabili separatamente.</p><div class="platform-form"><label>Testo di partenza<textarea id="translation-original" readonly></textarea></label><label>Bozza tradotta<textarea id="translation-draft" maxlength="2400"></textarea></label></div><div class="platform-actions"><button class="button primary" id="translation-use" type="button">Usa questa versione</button><button class="button" id="translation-close" type="button">Conserva il testo originale</button></div>';document.body.append(translationDialog);let translation=null;
translate.onclick=async()=>{const source=$('#script').value,language=contentLanguage.value;if(source.trim().length<2)return status('Scrivi prima il testo da tradurre.',true);translate.disabled=true;status('Preparo una bozza in '+languageNames[language]+'. Il testo originale resta nel copione fino alla tua scelta.');try{const result=await api('translate',{script:source,language,character_id:videoCharacter.id});translation={source,language};$('#translation-original').value=source;$('#translation-draft').value=result.script;translationDialog.showModal();status(result.note);}catch(e){report(e);}finally{translate.disabled=false;}};
$('#translation-close').onclick=()=>translationDialog.close();$('#translation-use').onclick=()=>{if(!translation||$('#script').value!==translation.source||contentLanguage.value!==translation.language)return status('Il copione o la lingua è cambiato: conserva questa bozza e prepara una nuova traduzione.',true);if($('#translation-draft').value.trim().length<2)return status('La traduzione è vuota.',true);try{localStorage.setItem('avatar-before-translation',JSON.stringify({script:translation.source,title:$('#title').value,at:Date.now()}));}catch{}stopPreview();$('#script').value=$('#translation-draft').value;updateMeta();translationDialog.close();status('Versione tradotta nel copione. Puoi ascoltarla e salvarla come un nuovo episodio.');};
const form = $('#settings-form');
function showProviderOptions() {$('#ollama-options').hidden = $('#provider').value !== 'ollama';$('#openai-options').hidden = $('#provider').value !== 'openai';}
$('#provider').onchange = showProviderOptions;
$('#settings-open').onclick = async () => {
  for(const [key,value] of Object.entries(studioConfig)) if(form.elements.namedItem(key)) form.elements.namedItem(key).value = value;
  const latest = await fetch('/api/bootstrap').then(r=>r.json());
  $('#used-budget').textContent = '$' + latest.used_usd.toFixed(4);
  $('#key-status').textContent = latest.has_openai_key ? 'Chiave API disponibile sul server.' : 'Chiave API assente. Imposta OPENAI_API_KEY prima di avviare lo studio; istruzioni nel README.';
  $('#settings-error').textContent = '';showProviderOptions();$('#settings-dialog').showModal();
};
$('#settings-close').onclick = () => $('#settings-dialog').close();
form.onsubmit = async event => {
  event.preventDefault();
  try {studioConfig = await api('settings', Object.fromEntries(new FormData(form).entries()));await saveQuick();avatar?.setAppearance(config);updateProvider();$('#settings-dialog').close();status('Impostazioni dello studio salvate. Il personaggio selezionato resta '+videoCharacter.name+'.');}
  catch(e) {$('#settings-error').textContent = e.message;}
};
function node(tag, className, text) {const el = document.createElement(tag);if(className) el.className = className;if(text != null) el.textContent = text;return el;}
let lastJobs = '';
async function refreshJobs() {
  const response = await fetch('/api/jobs'); if(!response.ok) throw new Error('Studio non raggiungibile. Verifica che sia ancora aperto.');
  const jobs = await response.json(), serialized = JSON.stringify(jobs);
  if(serialized === lastJobs) return;lastJobs = serialized;
  $('#library-count').textContent = `${jobs.length} video`;
  if(!jobs.length) return;
  $('#jobs').replaceChildren();
  for(const job of jobs) {
    const card = node('article','job-card');
    if(job.state === 'done') {const img = node('img','job-poster');img.src = job.cover || job.thumbnail;img.alt = 'Fotogramma del video';card.append(img);} else card.append(node('div','job-poster',job.state === 'error' ? '!' : '◌'));
    const info = node('div','job-info');info.append(node('h3','',job.title));info.append(node('p','', job.state === 'done' ? `${job.duration} s · MP4 con audio · salvato sul Mac` : job.message));
    if(['queued','running'].includes(job.state)) {const progress = node('progress');progress.max=100;progress.value=job.progress;progress.setAttribute('aria-label','Avanzamento video');info.append(progress);}
    card.append(info);const actions = node('div','job-actions');
    if(job.state === 'done') {
      const play = node('button','button secondary','▷ Guarda');play.onclick=()=>{$('#video-player').src=job.video;$('#video-title').textContent=job.title;$('#video-dialog').showModal();$('#video-player').play().catch(()=>{});};actions.append(play);
      const finder = node('button','button','Mostra sul Mac');finder.onclick=()=>api('reveal',{id:job.id}).catch(report);actions.append(finder);
      if(job.packages) {for(const [key,url] of Object.entries(job.packages)){const a=node('a','button package-download','↓ '+({youtube:'YouTube',tiktok:'TikTok',instagram:'Instagram'}[key]));a.href=url;a.download=job.title+'-'+key+'.zip';actions.append(a);}const cover=node('a','button','Copertina');cover.href=job.cover;cover.download=job.title+'-cover.png';actions.append(cover);}
      const download = node('a','button','↓ MP4');download.href=job.video;download.download=job.title+'.mp4';actions.append(download);
      const reuse = node('button','button','Nuovo progetto dal copione');
      reuse.onclick=async()=>{
        try {
          const response=await fetch(`/output/${job.id}/project.json`);
          if(!response.ok)throw Error('Il copione di questo video non è disponibile.');
          const project=await response.json();
          window.dispatchEvent(new CustomEvent('studio:new-project',{detail:{
            title:job.title,script:project.script||'',character_id:project.settings?.character?.id||'ari',
            language:project.settings?.language||'it',voice:project.settings?.voice,rate:project.settings?.rate,
            method:'web'
          }}));
        } catch(error) {report(error);}
      };
      actions.append(reuse);
    } else if(['queued','running'].includes(job.state)) {const cancel = node('button','button','Annulla');cancel.onclick=()=>api('cancel',{id:job.id}).then(refreshJobs).catch(report);actions.append(cancel);}
    if(job.engine==='heygen'&&['error','cancelled'].includes(job.state)){const recover=node('button','button secondary','Recupera da HeyGen');recover.onclick=()=>api('cloud-recover',{id:job.id}).then(refreshJobs).catch(report);actions.append(recover);}
    card.append(actions);$('#jobs').append(card);
  }
}
$('#video-close').onclick = () => $('#video-dialog').close();
$('#video-dialog').addEventListener('close',()=>{$('#video-player').pause();});
refreshJobs().catch(report);
setInterval(()=>refreshJobs().catch(()=>{}), 2000);

window.addEventListener('studio:video-character',e=>{
 let next=e.detail;if(!next)return;
 if(projectCharacterSnapshot?.id===next.id)next=projectCharacterSnapshot;
 const changed=next.id!==videoCharacter?.id||next.revision!==videoCharacter?.revision;
 if(changed)stopPreview();
 const sameVoice=next.id===videoCharacter?.id&&next.voice===videoCharacter.voice&&next.rate===videoCharacter.rate;
 videoCharacter=next;config={...studioConfig,...next,character:next};
 if(changed&&!sameVoice){setVoices($('#voice'),bootstrap.voice_catalog,contentLanguage.value,usualVoice(next,contentLanguage.value));$('#rate').value=next.rate;}
 config.language=contentLanguage.value;config.voice=$('#voice').value;config.rate=Number($('#rate').value);avatar?.setAppearance(config);
 $('#preview-heading').textContent='Anteprima · '+next.name;$('#avatar').setAttribute('aria-label','Anteprima di '+next.name);$('#avatar').dataset.avatarCharacter=next.id;
 updateProvider();updateMeta();
});
window.addEventListener('studio:character-picked',()=>{projectCharacterSnapshot=null;});
window.addEventListener('studio:project-snapshot',event=>{
  projectCharacterSnapshot=event.detail||null;
  if(projectCharacterSnapshot)window.dispatchEvent(new CustomEvent('studio:video-character',{detail:projectCharacterSnapshot}));
});
$('#edit-video-character').onclick=()=>window.dispatchEvent(new CustomEvent('studio:edit-character',{detail:videoCharacter.id}));
$('#reset-video-voice').onclick=()=>{stopPreview();setVoices($('#voice'),bootstrap.voice_catalog,contentLanguage.value,usualVoice(videoCharacter,contentLanguage.value));$('#rate').value=videoCharacter.rate;saveQuick();updateProvider();updateMeta();};
function readDraft() {
  return {...editorialDraft(),title:$('#title').value,script:$('#script').value,topic:$('#topic').value,
    rubric_id:$('#rubric-select').value,language:contentLanguage.value,
    character_id:$('#video-character')?.value,voice:$('#voice').value,rate:Number($('#rate').value)};
}

async function loadDraft(draft) {
  stopPreview();
  contentLanguage.value=draft.language in languageNames ? draft.language : 'it';
  projectCharacterSnapshot=null;
  if(draft.character_id)window.dispatchEvent(new CustomEvent('studio:select-video',{detail:draft.character_id}));
  if(draft.character)window.dispatchEvent(new CustomEvent('studio:project-snapshot',{detail:draft.character}));
  setVoices($('#voice'),bootstrap.voice_catalog,contentLanguage.value,draft.voice||usualVoice(videoCharacter,contentLanguage.value));
  $('#rate').value=draft.rate||videoCharacter.rate;
  for(const key of ['title','script','topic'])$('#'+key).value=draft[key]||'';
  $('#title').value ||= 'Nuovo video';
  $('#rubric-select').value=draft.rubric_id||'';
  $('#seconds').value=String(draft.duration_seconds||30);
  $('#editor-format').value=draft.editor_format||'explainer';
  $('#editor-hook').value=draft.hook||'';
  $('#editor-cta').value=draft.cta||'';
  await saveQuick();updateProvider();updateMeta();
}

// API generation is a separate, explicitly confirmed path; the website path never calls it.
async function renderProjectApi(project) {
  const fingerprint = () => JSON.stringify([readDraft(), $('#project-method')?.value]);
  const requested = fingerprint();
  const quote=await api('cloud-quote',{video_project_id:project.id,video_project_revision:project.revision});
  if (fingerprint() !== requested) throw Error('Il progetto è cambiato durante il preventivo. Salva le modifiche e richiedi una nuova stima.');
  const dialog=node('dialog','platform-modal');
  dialog.append(node('h2','','Genera tramite HeyGen API'),
    node('p','',`${quote.character} · ${quote.duration.toFixed(1)} secondi`),
    node('p','platform-budget',`Costo stimato: € ${quote.estimated_eur.toFixed(2)}`),
    node('p','hint',quote.note),
    node('p','','Questa operazione usa il credito API, separato dall’abbonamento al sito HeyGen.'));
  const actions=node('div','platform-actions');
  const confirm=node('button','button primary','Invia immagine e audio a HeyGen');
  const cancel=node('button','button','Annulla');
  confirm.type=cancel.type='button';actions.append(confirm,cancel);dialog.append(actions);document.body.append(dialog);
  return new Promise((resolve,reject)=>{
    let settled=false;
    function finish(value,error) {
      if(settled)return;settled=true;dialog.close();dialog.remove();
      if(error)reject(error);else resolve(value);
    }
    cancel.onclick=()=>finish(null);
    dialog.addEventListener('cancel',event=>{event.preventDefault();if(!confirm.disabled)finish(null);});
    confirm.onclick=async()=>{
      confirm.disabled=cancel.disabled=true;
      try{
        if (fingerprint() !== requested) throw Error('Il progetto è cambiato. Salvalo e richiedi una nuova stima.');
        finish(await api('cloud-render',{quote_id:quote.quote_id}));
      }
      catch(error){finish(null,error);}
    };
    dialog.showModal();
  });
}
window.addEventListener('studio:view',event=>{if(event.detail!=='create')stopPreview();});

await initLive({api,report,status,bootstrap});
await initPlatform({api,report,status,bootstrap,refreshJobs});
await initDelivery({api,report,status,bootstrap});
await initActivity({api,report,status});
await initInsights({api,report,status});
await initClips({api,report,status,bootstrap,refreshJobs});
await initBusiness({api,report,status});
await initStudio({api,report,status,saveQuick,refreshJobs,readDraft});
await initProjects({api,report,status,bootstrap,refreshJobs,readDraft,loadDraft,navigate,
  renderLocal:project=>api('render',{video_project_id:project.id,video_project_revision:project.revision}),
  renderApi:renderProjectApi
});
initNavigation();

window.studioReady=true;
