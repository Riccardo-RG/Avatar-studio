import {navigate as view} from './navigation.js';
import {languageField,languageNames} from './languages.js';
const $=s=>document.querySelector(s);
function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;}
export async function initStudio({api,report,status,saveQuick,refreshJobs,readDraft}) {
  $('#episode-form .dialog-heading').after(languageField('language'));

  let doc, edit=null, fingerprint='', characters=await fetch('/api/platform').then(r=>r.json()), personaRevision=null;
  const personaSelect=node('select');personaSelect.id='persona-character';const personaLabel=node('label','','Personalità del personaggio');personaLabel.append(personaSelect);$('#persona-form').prepend(personaLabel);
  function fillPersonas(){const old=personaSelect.value;personaSelect.replaceChildren();for(const c of characters.characters){const o=node('option','',c.name);o.value=c.id;personaSelect.append(o);}personaSelect.value=characters.characters.some(c=>c.id===old)?old:($('#video-character').value||characters.active_character);}
  function drawPersona(){const c=characters.characters.find(c=>c.id===personaSelect.value);personaRevision=c.revision;for(const[k,v]of Object.entries(c.editorial))$('#persona-form').elements.namedItem(k).value=v;}
  personaSelect.onchange=drawPersona;
  window.addEventListener('studio:characters-updated',e=>{characters=e.detail;fillPersonas();drawPlan();});
  window.addEventListener('studio:view',e=>{if(e.detail==='persona'){fetch('/api/platform').then(r=>r.json()).then(d=>{characters=d;fillPersonas();drawPersona();}).catch(report);}});
  const labels={draft:'Bozza',approved:'Testo approvato',rendering:'In produzione',ready:'Video pronto'};
  function button(label,action,cls='button'){const b=node('button',cls,label);b.type='button';b.onclick=async()=>{b.disabled=true;try{await action();}catch(e){report(e);}finally{b.disabled=false;}};return b;}
  function drawPlan(){
    $('#plan-badge').textContent=doc.episodes.length;
    const approved=doc.episodes.filter(e=>e.status==='approved'), completed=doc.episodes.filter(e=>e.status==='ready');
    $('#plan-summary').textContent=`${completed.length} video locali completati · ${approved.length} testi approvati`;
    $('#render-series').disabled=!approved.length;$('#export-series').disabled=!completed.length;
    $('#episodes').replaceChildren();
    for(const e of doc.episodes.filter(e=>!$('#plan-filter').value||e.rubric_id===$('#plan-filter').value)) {
      const r=doc.rubrics.find(r=>r.id===e.rubric_id),card=node('article','episode-card');card.dataset.episode=e.id;card.style.setProperty('--episode-color',r.color);
      const top=node('div','episode-top');top.append(node('span','episode-rubric',r.name),node('span','episode-state',labels[e.status]));
      card.append(top,node('h3','',e.title),node('p','episode-excerpt',e.script.slice(0,130)+(e.script.length>130?'…':'')),node('p','episode-meta',`${characters.characters.find(c=>c.id===e.character_id)?.name||'Personaggio da scegliere'} · ${languageNames[e.language||'it']} · Versione ${e.revision} · ${e.script.split(/\s+/).length} parole · ${e.planned_date||'Data libera'}`));
      for(const warning of e.similarity_warnings||[])card.append(node('p','hint',`Somiglianza con ${warning.title}: ${warning.similarity_percent}%. Rivedi la differenza del contenuto; non è una verifica dei diritti.`));
      const actions=node('div','episode-actions');actions.append(button('Modifica',()=>openEpisode(e)));
      if(e.status!=='rendering'&&e.status!=='ready')actions.append(button(e.status==='approved'?'Rimetti in bozza':'Segna pronto',async()=>{await api('episode-ready',{id:e.id,revision:e.revision,ready:e.status!=='approved'});await refresh();}));
      if(e.status!=='rendering')actions.append(button('Apri progetto video',()=>{
        window.dispatchEvent(new CustomEvent('studio:new-project',{detail:{...e,id:undefined,revision:undefined,
          method:'web',episode:{id:e.id,revision:e.revision}}}));
      },'button secondary'));
      if(e.status==='ready'&&e.job_id){const a=node('a','button secondary','↓ YouTube');a.href=`/output/${e.job_id}/youtube.zip`;a.download=e.title+'-youtube.zip';actions.append(a);actions.append(button('Vedi in libreria',()=>$('#library-heading').scrollIntoView({behavior:'smooth'})));}
      if(e.status==='rendering')actions.append(node('span','hint','Avanzamento nella libreria ↓'));
      card.append(actions);$('#episodes').append(card);
    }
  }
  async function refresh(force=false){const next=await fetch('/api/studio').then(r=>{if(!r.ok)throw Error('Piano non disponibile');return r.json();});const serial=JSON.stringify(next);doc=next;if(force||serial!==fingerprint){fingerprint=serial;drawPlan();}}
  function fillRubrics(){for(const id of ['rubric-select','plan-filter','episode-rubric']){const select=$('#'+id),old=select.value;select.replaceChildren();if(id==='plan-filter'||id==='rubric-select'){const o=node('option','',id==='plan-filter'?'Tutte le rubriche':'Nessuna rubrica');o.value='';select.append(o);}for(const r of doc.rubrics){const o=node('option','',r.name);o.value=r.id;select.append(o);}if([...select.options].some(o=>o.value===old))select.value=old;}}
  function drawPersonality(){fillPersonas();drawPersona();
    $('#rubrics').replaceChildren();for(const r of doc.rubrics){const f=node('form','panel rubric-card');f.dataset.rubric=r.id;f.style.setProperty('--episode-color',r.color);f.append(node('h3','',r.name));for(const [k,label,max] of [['name','Nome',60],['description','Il tema',220],['direction','Come costruire il copione',400]]){const l=node('label','',label),field=node(k==='name'?'input':'textarea');field.name=k;field.maxLength=max;field.required=true;field.value=r[k];l.append(field);f.append(l);}const b=node('button','button secondary','Salva rubrica');b.type='submit';f.append(b);f.onsubmit=async ev=>{ev.preventDefault();b.disabled=true;try{await api('rubric',{id:r.id,...Object.fromEntries(new FormData(f))});await refresh(true);fillRubrics();f.querySelector('h3').textContent=f.elements.name.value;status('Rubrica salvata per le prossime bozze e produzioni.');}catch(e){report(e);}finally{b.disabled=false;}};$('#rubrics').append(f);}}
  $('#persona-form').onsubmit=async ev=>{ev.preventDefault();const b=ev.target.querySelector('button');b.disabled=true;try{const saved=await api('persona',{...Object.fromEntries(new FormData(ev.target)),character_id:personaSelect.value,revision:personaRevision});characters.characters=characters.characters.map(c=>c.id===saved.id?saved:c);drawPersona();window.dispatchEvent(new CustomEvent('studio:characters-updated',{detail:characters}));status('Personalità di '+saved.name+' salvata. Verrà usata per le sue nuove bozze AI.');}catch(e){report(e);}finally{b.disabled=false;}};
  $('#plan-filter').onchange=drawPlan;
  function openEpisode(episode){edit=structuredClone(episode);const f=$('#episode-form');f.elements.language.value=edit.language||'it';for(const key of ['title','rubric_id','planned_date','cover','script','question','character_id','duration_seconds','editor_format','hook','cta'])f.elements.namedItem(key).value=edit[key]||(key==='character_id'?$('#video-character').value:key==='duration_seconds'?30:key==='editor_format'?'explainer':'');$('#episode-heading').textContent=edit.id?'Modifica episodio':'Nuovo episodio';$('#episode-error').textContent='';$('#hook-options').replaceChildren();for(const hook of edit.hooks||[])$('#hook-options').append(button(hook,()=>{f.elements.script.value=f.elements.script.value.replace(/^[\s\S]*?[.!?](?:\s+|$)/,hook+' ');if(!/[.!?]/.test(f.elements.script.value))f.elements.script.value=hook+' '+f.elements.script.value;}));if(!edit.hooks?.length)$('#hook-options').append(node('p','hint','Scrivi liberamente l’apertura nel copione.'));$('#episode-dialog').showModal();}
  $('#episode-close').onclick=()=>$('#episode-dialog').close();
  async function saveEpisode(ready){const f=$('#episode-form');if(!f.reportValidity())return;const buttons=[...f.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);try{const saved=await api('episode',{...edit,...Object.fromEntries(new FormData(f))});edit=saved;if(ready)await api('episode-ready',{id:saved.id,revision:saved.revision,ready:true});await refresh();$('#episode-dialog').close();view('plan');status(ready?'Testo approvato. Apri il progetto video per scegliere come generarlo.':'Bozza salvata nel piano.');}catch(e){$('#episode-error').textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}}
  $('#episode-form').onsubmit=ev=>{ev.preventDefault();saveEpisode(false);};$('#episode-save-ready').onclick=()=>saveEpisode(true);
  $('#save-to-plan').onclick=()=>{const draft=readDraft();if(draft.script.trim().length<2)return status('Scrivi prima il copione da aggiungere al piano.',true);openEpisode({...draft,cover:draft.title.slice(0,60),question:({it:'Tu cosa ne pensi?',en:'What do you think?',es:'¿Qué opinas?'})[draft.language||'it'],hooks:[]});};
  async function produce(ids){await saveQuick();await api('series-render',{ids});await refresh();await refreshJobs();status(`${ids.length} ${ids.length===1?'episodio in produzione':'episodi in produzione'}. Tieni aperto il terminale dello studio fino al completamento.`);}
  $('#render-series').onclick=async()=>{const b=$('#render-series');b.disabled=true;try{await produce(doc.episodes.filter(e=>e.status==='approved').slice(0,10).map(e=>e.id));}catch(e){report(e);drawPlan();}};
  $('#export-series').onclick=async()=>{const b=$('#export-series');b.disabled=true;try{status('Preparo lo ZIP con i video completati e i testi per le piattaforme…');const result=await api('series-export',{});const a=node('a');a.href=result.url;a.download='avatar-studio-serie.zip';document.body.append(a);a.click();a.remove();status(`Serie esportata: ${result.count} episodi. Lo ZIP è disponibile nei download.`);}catch(e){report(e);}finally{b.disabled=false;}};
  await refresh();fillRubrics();drawPersonality();setInterval(()=>refresh().catch(()=>{}),2500);
}
