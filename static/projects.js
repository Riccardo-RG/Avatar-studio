const $ = selector => document.querySelector(selector);

const METHODS = {web: 'HeyGen dal sito', local: 'Generazione locale', api: 'HeyGen API'};
const EDITOR_STORAGE = 'avatar-project-editor';
const STATES = {
  draft: 'Bozza', materials_ready: 'Materiali pronti', video_imported: 'Video importato',
  rendering: 'Video in produzione', ready: 'Pronto da esportare', failed: 'Produzione da riprovare',
  preparing: 'Preparazione materiali', importing: 'Importazione video',
};
const DRAFT_DEFAULTS = {
  title: '', script: '', topic: '', character_id: '', language: 'it', voice: '', rate: 160,
  rubric_id: '', editor_format: 'explainer', duration_seconds: 30, hook: '', cta: '', method: 'web', episode: null,
};

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function normalizedDraft(value, method = value.method || 'web') {
  const result = {};
  for (const [key, fallback] of Object.entries(DRAFT_DEFAULTS)) result[key] = value[key] ?? fallback;
  result.method = method;
  result.rate = Number(result.rate);
  result.duration_seconds = Number(result.duration_seconds);
  for (const key of ['title', 'script', 'topic', 'rubric_id', 'hook', 'cta']) result[key] = result[key].trim();
  return result;
}

function sameDraft(a, b) {
  return JSON.stringify(normalizedDraft(a)) === JSON.stringify(normalizedDraft(b));
}

function localLink(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return null;
  const url = new URL(value, window.location.origin);
  return url.origin === window.location.origin ? url.pathname + url.search : null;
}

function addDownload(container, label, url, key) {
  const safe = localLink(url);
  if (!safe) return;
  const link = node('a', 'button secondary', label);
  link.href = safe;
  link.download = '';
  if (key) link.dataset.material = key;
  container.append(link);
}

/** A saved project owns the material snapshot, imported source and export job. */
export async function initProjects({api, report, status, bootstrap, refreshJobs, readDraft, loadDraft, navigate, renderLocal, renderApi}) {
  let project = null;
  let projects = [];
  let busy = false;
  let generation = 0;
  let listRequest = 0;
  let sourceKey = '';
  let visible = 'projects';
  let episode = null;
  let conflict = false;
  let restoring = true;
  const cutDrafts = new Map();

  const nav = $('.studio-nav');
  for (const [name, label] of [['projects', 'Progetti'], ['guide', 'Come si usa']]) {
    const button = node('button', '', label);
    button.type = 'button';
    button.dataset.view = name;
    nav.append(button);
  }

  const dashboard = node('section', 'project-dashboard');
  dashboard.id = 'view-projects';
  dashboard.hidden = true;
  dashboard.setAttribute('aria-labelledby', 'projects-heading');
  dashboard.innerHTML = `
    <div class="section-heading project-heading"><div><p class="eyebrow">DAL COPIONE AL VIDEO FINITO</p>
      <h2 id="projects-heading">I tuoi progetti video</h2>
      <p class="hint">Riprendi ogni video dal punto in cui eri rimasto. Copione, materiali e risultato restano insieme sul Mac.</p></div>
      <button id="project-new" class="button primary" type="button">＋ Nuovo video</button></div>
    <div class="project-home-note"><p>Prepara nello studio → anima su HeyGen → importa e completa.</p>
      <button class="text-button" data-project-view="guide" type="button">Leggi il workflow completo ↗</button></div>
    <div id="project-unsaved" class="project-resume" hidden><p>Nel tuo editor c’è una bozza da salvare.</p>
      <button class="button secondary" data-project-view="create" type="button">Riprendi la bozza</button></div>
    <p id="project-list-note" class="hint" role="status"></p><div id="project-list" class="project-grid"></div>`;
  $('#view-create').before(dashboard);

  const create = $('#view-create');
  create.classList.add('project-workspace');
  const header = node('section', 'project-workflow-header');
  header.setAttribute('aria-labelledby', 'project-heading');
  header.innerHTML = `
    <div class="project-heading"><div><p class="eyebrow">UN PROGETTO, TUTTI I PASSAGGI</p>
      <h2 id="project-heading">Il tuo prossimo video</h2>
      <p><span id="project-state" class="project-badge">Bozza</span> <span id="project-save-state" class="hint" role="status">Da salvare sul Mac</span></p></div>
      <button class="button secondary" data-project-view="projects" type="button">Tutti i progetti</button></div>
    <label class="project-method-label" for="project-method">Come vuoi animare il personaggio?</label>
    <select id="project-method"><option value="web">HeyGen dal sito · abbonamento web</option><option value="local">Generazione locale · sul Mac</option><option value="api">HeyGen API · integrazione a consumo</option></select>
    <p id="project-method-note" class="hint"></p>
    <p id="project-error" class="error" role="alert" hidden></p>
    <div id="project-conflict" class="project-resume" hidden><p>Il progetto è stato aggiornato in un’altra scheda. Conserva le tue modifiche in una copia prima di aprire la versione aggiornata.</p><button id="project-save-copy" class="button secondary" type="button">Salva una copia con le mie modifiche</button></div>
    <ol id="project-steps" class="project-steps" aria-label="Passaggi del progetto">
      <li data-step="prepare"><span>1</span><strong>Prepara</strong><small>Personaggio, testo e voce</small></li>
      <li data-step="materials"><span>2</span><strong>Porta su HeyGen</strong><small>Scarica i materiali</small></li>
      <li data-step="import"><span>3</span><strong>Importa</strong><small>Riporta l’MP4 nello studio</small></li>
      <li data-step="finish"><span>4</span><strong>Completa</strong><small>Taglio, sottotitoli, export</small></li>
    </ol>`;
  create.prepend(header);

  const workflow = node('section', 'project-workflow');
  workflow.innerHTML = `
    <section id="project-web-work" class="panel project-panel" aria-labelledby="project-material-heading">
      <div class="panel-heading"><h2 id="project-material-heading">2. Porta il personaggio su HeyGen</h2></div>
      <p class="hint">Scegli un personaggio con un’immagine, rileggi e ascolta il copione. Prepariamo sul Mac l’audio con la voce scelta, il ritratto e il testo.</p>
      <div class="project-actions"><button id="project-prepare" class="button primary" type="button">Prepara materiali per HeyGen</button>
        <button id="project-copy-script" class="button secondary" type="button">Copia copione</button></div>
      <p id="project-material-note" class="hint" role="status"></p>
      <div id="project-materials" class="project-actions"></div>
      <audio id="project-audio" controls preload="none" hidden aria-label="Audio preparato per HeyGen"></audio>
      <div class="project-external"><div><strong>Continua nell’editor HeyGen</strong>
        <p class="hint">Accedi sul sito, carica il ritratto e l’audio, genera il video e scarica l’MP4. Le operazioni sul sito restano manuali; qui non servono chiavi API.</p></div>
        <a id="project-open-heygen" class="button secondary" href="https://app.heygen.com/" target="avatar-studio-heygen" rel="noopener noreferrer">Apri HeyGen ↗</a></div>
    </section>
    <section id="project-other-work" class="panel project-panel" hidden aria-labelledby="project-other-heading">
      <h2 id="project-other-heading">Genera il video</h2><p id="project-other-note" class="hint"></p>
      <button id="project-generate" class="button primary" type="button">Genera video</button>
    </section>
    <section id="project-import-work" class="panel project-panel" aria-labelledby="project-import-heading">
      <h2 id="project-import-heading">3. Importa il risultato</h2>
      <p class="hint">Trascina qui l’MP4 scaricato da HeyGen. Lo copiamo sul Mac e lo associamo a questo progetto, senza modificare l’originale.</p>
      <label id="project-dropzone" class="project-dropzone" for="project-file"><strong>Scegli o trascina il tuo video MP4</strong><span>Un file fino a 2 GB</span>
        <input id="project-file" type="file" accept=".mp4,video/mp4"></label>
      <progress id="project-import-progress" max="100" value="0" hidden aria-label="Avanzamento importazione video"></progress>
      <p id="project-import-note" class="hint" role="status"></p>
    </section>
    <section id="project-finish-work" class="panel project-panel" hidden aria-labelledby="project-finish-heading">
      <h2 id="project-finish-heading">4. Completa ed esporta</h2>
      <div class="project-finish-grid"><div><div class="project-video-stage"><video id="project-source" controls playsinline preload="metadata"></video></div>
        <p id="project-source-note" class="hint"></p><div id="project-source-download" class="project-actions"></div></div>
      <form id="project-finish-form">
        <div class="project-form-row"><label>Inizio · secondi<input name="start" type="number" min="0" step="0.01" value="0" required></label>
          <label>Fine · secondi<input name="end" type="number" min="1" step="0.01" required></label></div>
        <div class="project-actions"><button id="project-mark-start" class="button" type="button">Qui inizia</button><button id="project-mark-end" class="button" type="button">Qui finisce</button></div>
        <div class="project-form-row"><label>Formato<select name="format"><option value="portrait">Verticale · 9:16</option><option value="square">Quadrato · 1:1</option><option value="landscape">Orizzontale · 16:9</option></select></label>
          <label>Inquadratura<select name="fit"><option value="contain">Mantieni tutta l’immagine</option><option value="cover">Riempi e ritaglia al centro</option></select></label></div>
        <label class="checkbox-row"><input name="source_captions_burned" type="checkbox">Il video ha già sottotitoli visibili</label>
        <label id="project-prepared-captions-label" class="checkbox-row"><input name="use_prepared_captions" type="checkbox">Ho usato l’audio preparato, senza modificare testo o tempi</label>
        <label class="checkbox-row"><input name="burn_captions" type="checkbox">Aggiungi i sottotitoli disponibili al video</label>
        <p id="project-caption-note" class="hint"></p><p id="project-cut-note" class="hint" role="status"></p>
        <button id="project-export" class="button primary" type="submit">Esporta il video sul Mac</button>
      </form></div>
    </section>
    <section id="project-result" class="panel project-panel" hidden aria-labelledby="project-result-heading">
      <h2 id="project-result-heading">Il risultato del progetto</h2><p id="project-result-note" class="hint" role="status"></p>
      <div id="project-result-actions" class="project-actions"></div>
    </section>
    <details id="project-history" class="panel project-panel" hidden><summary>Versioni precedenti salvate</summary>
      <p class="hint">I file delle versioni precedenti restano disponibili. Scaricali per consultarli; il progetto continua a usare la versione corrente.</p>
      <div id="project-history-items"></div></details>`;
  create.append(workflow);
  $('#project-save').textContent = 'Salva progetto';
  const guide = node('section', 'project-guide');
  guide.id = 'view-guide';
  guide.hidden = true;
  guide.setAttribute('aria-labelledby', 'guide-heading');
  guide.innerHTML = guideMarkup();
  $('.library').before(guide);

  const method = $('#project-method');
  const finish = $('#project-finish-form');
  const video = $('#project-source');
  const field = name => finish.elements.namedItem(name);
  const draft = () => normalizedDraft({...readDraft(), episode}, method.value);
  const dirty = () => project ? !sameDraft(draft(), project) : Boolean(draft().script.trim() || draft().topic.trim());
  const guard = action => async event => {
    event?.preventDefault();
    try { await action(event); } catch (error) { report(error); }
  };

  function persistEditor() {
    if (restoring) return;
    try {
      localStorage.setItem(EDITOR_STORAGE, JSON.stringify({
        version: 1, project_id: project?.id || null, revision: project?.revision || null,
        baseline: project ? normalizedDraft(project) : null,
        draft: {...readDraft(), method: method.value, episode}, dirty: dirty(),
        cuts: [...cutDrafts.values()],
      }));
    } catch { /* Explicit server saves and the unsaved-exit warning remain available. */ }
  }

  async function restoreEditor() {
    let stored = null;
    let legacy = null;
    try {
      stored = JSON.parse(localStorage.getItem(EDITOR_STORAGE) || 'null');
      legacy = JSON.parse(localStorage.getItem('avatar-draft') || 'null');
    } catch { /* A malformed old browser draft must not prevent opening saved projects. */ }
    if (stored?.version === 1 && stored.draft && typeof stored.draft === 'object') {
      for (const entry of Array.isArray(stored.cuts) ? stored.cuts.slice(-50) : []) {
        const owner = projects.find(item => item.id === entry?.project_id);
        const source = owner?.source;
        if (!source || source.source_id !== entry?.source_id) continue;
        const fields = validCutFields(entry.fields, source);
        if (fields) cutDrafts.set(`${owner.id}:${source.source_id}`, {project_id: owner.id, source_id: source.source_id, fields});
      }
      const saved = projects.find(item => item.id === stored.project_id);
      let restoredDraft = stored.draft;
      if (saved) {
        project = saved;
        if (!stored.dirty) restoredDraft = saved;
        else if (stored.revision !== saved.revision && !sameDraft(stored.draft, saved)) {
          // Keep the original optimistic revision so a remote edit cannot be overwritten.
          project = {...saved, ...(stored.baseline || {}), revision: stored.revision,
            materials: null, source: null, job: null, job_id: null, status: 'draft'};
          conflict = true;
        }
      }
      method.value = METHODS[restoredDraft.method] ? restoredDraft.method : 'web';
      episode = restoredDraft.episode || null;
      await loadDraft(restoredDraft);
    } else if (legacy && typeof legacy === 'object') {
      await loadDraft({...readDraft(), ...legacy, method: 'web'});
    }
    restoring = false;
    persistEditor();
    try { localStorage.removeItem('avatar-draft'); } catch { /* Storage can be disabled. */ }
  }

  function validCutFields(value, source) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const fields = {};
    for (const name of ['start', 'end']) {
      const raw = value[name];
      if (typeof raw !== 'string' || raw.length > 20) continue;
      if (raw === '' || (/^\d*(?:\.\d*)?$/.test(raw) && Number.isFinite(Number(raw)) && Number(raw) >= 0 && Number(raw) <= source.duration + 0.02)) fields[name] = raw;
    }
    if (['portrait', 'square', 'landscape'].includes(value.format)) fields.format = value.format;
    if (['contain', 'cover'].includes(value.fit)) fields.fit = value.fit;
    for (const name of ['source_captions_burned', 'use_prepared_captions', 'burn_captions']) {
      if (typeof value[name] === 'boolean') fields[name] = value[name];
    }
    return fields;
  }

  function rememberCut() {
    if (restoring || !project?.source || project.source.source_id !== sourceKey) return;
    const fields = {};
    for (const name of ['start', 'end', 'format', 'fit']) fields[name] = field(name).value;
    for (const name of ['source_captions_burned', 'use_prepared_captions', 'burn_captions']) fields[name] = field(name).checked;
    const key = `${project.id}:${sourceKey}`;
    cutDrafts.delete(key);
    cutDrafts.set(key, {project_id: project.id, source_id: sourceKey, fields: validCutFields(fields, project.source)});
    while (cutDrafts.size > 50) cutDrafts.delete(cutDrafts.keys().next().value);
    persistEditor();
  }

  function restoreCut(source) {
    const fields = validCutFields(cutDrafts.get(`${project.id}:${source.source_id}`)?.fields, source);
    for (const [name, value] of Object.entries(fields || {})) {
      if (typeof value === 'boolean') field(name).checked = value;
      else field(name).value = value;
    }
    if (source.captions_burned) field('source_captions_burned').checked = true;
  }

  function setBusy(value) {
    busy = value;
    for (const element of document.querySelectorAll('#project-new, [data-project-id], #project-prepare, #project-file, #project-generate, #project-method, #project-export, #project-save-copy, #project-save')) element.disabled = value;
    create.setAttribute('aria-busy', String(value));
    draw();
  }

  async function mutate(action) {
    if (busy) throw Error('Attendi la fine dell’operazione in corso prima di cambiare progetto.');
    setBusy(true);
    try { return await action(); }
    catch (error) {
      // A failed long operation can advance its revision when releasing its claim.
      await refresh().catch(() => {});
      throw error;
    } finally { setBusy(false); }
  }

  async function saveCurrent() {
    const snapshot = draft();
    if (!snapshot.title.trim()) throw Error('Dai un titolo al progetto prima di salvarlo.');
    const ticket = generation;
    let saved;
    try {
      saved = await api('video-project', {...snapshot, ...(project ? {id: project.id, revision: project.revision} : {})});
    } catch (error) {
      if (/progetto.*cambiato|versione.*cambiata/i.test(error.message)) conflict = true;
      draw();
      throw error;
    }
    if (ticket !== generation) return null;
    project = saved;
    conflict = false;
    if (saved.character && sameDraft(draft(), saved)) {
      window.dispatchEvent(new CustomEvent('studio:project-snapshot', {detail: saved.character}));
    }
    draw();
    await refresh();
    return saved;
  }

  async function preserveDraft() {
    if (dirty()) await saveCurrent();
    if (dirty()) throw Error('Hai aggiunto modifiche durante il salvataggio. Salvale prima di aprire un altro progetto.');
  }

  async function openProject(id) {
    await mutate(async () => {
      await preserveDraft();
      await refresh();
      if (dirty()) throw Error('Hai aggiunto modifiche mentre aprivo il progetto. Salvale prima di continuare.');
      const next = projects.find(item => item.id === id);
      if (!next) throw Error('Questo progetto non è più disponibile. Aggiorna l’elenco e riprova.');
      generation++;
      video.pause();
      project = next;
      episode = next.episode || null;
      conflict = false;
      method.value = next.method;
      await loadDraft(next);
      sourceKey = '';
      draw();
      navigate('create');
    });
  }

  async function openDraft(value = {}) {
    const episodeProject = value.episode && projects.find(item =>
      item.episode?.id === value.episode.id && item.episode.revision === value.episode.revision);
    if (episodeProject) return openProject(episodeProject.id);
    await mutate(async () => {
      await preserveDraft();
      generation++;
      video.pause();
      const current = draft();
      project = null;
      episode = value.episode || null;
      conflict = false;
      method.value = METHODS[value.method] ? value.method : 'web';
      const characterId = value.character_id || (method.value === 'web' ? 'ari' : current.character_id);
      const keepVoice = characterId === current.character_id;
      await loadDraft({...DRAFT_DEFAULTS, character_id: characterId, language: current.language,
        voice: keepVoice ? current.voice : '', rate: keepVoice ? current.rate : null,
        title: 'Nuovo video', ...value, method: method.value});
      sourceKey = '';
      draw();
      navigate('create');
      $('#title').focus();
    });
  }

  function drawList() {
    const list = $('#project-list');
    list.replaceChildren();
    $('#project-list-note').textContent = projects.length ? `${projects.length} progetti salvati sul Mac` : 'Il primo progetto parte da un personaggio e da un’idea.';
    if (!projects.length) {
      const empty = node('div', 'project-empty');
      empty.append(node('h3', '', 'Un posto per ogni video.'), node('p', 'hint', 'Crea un progetto, prepara i materiali e ritrova qui il lavoro anche dopo aver chiuso lo studio.'));
      list.append(empty);
    }
    for (const item of projects) {
      const card = node('article', 'panel project-card');
      card.append(node('span', 'project-badge', STATES[item.status] || 'Bozza'), node('h3', '', item.title),
        node('p', 'hint', METHODS[item.method] || METHODS.web), node('p', 'project-excerpt', item.script?.slice(0, 150) || 'Il copione è ancora da scrivere.'));
      const open = node('button', 'button secondary', 'Apri progetto');
      open.type = 'button';
      open.dataset.projectId = item.id;
      open.disabled = busy;
      open.onclick = guard(() => openProject(item.id));
      card.append(open);
      list.append(card);
    }
  }

  async function refresh() {
    const request = ++listRequest;
    const response = await fetch('/api/video-projects', {cache: 'no-store'});
    if (!response.ok) throw Error('Non riesco a leggere i progetti salvati. Riprova tra poco.');
    const result = await response.json();
    if (request !== listRequest) return;
    projects = result.projects;
    const latest = project && projects.find(item => item.id === project.id);
    // Status updates may arrive while the user types. Never replace the editor draft.
    if (latest && latest.revision >= project.revision && sameDraft(latest, project)) project = latest;
    drawList();
    draw();
  }

  function draw() {
    persistEditor();
    const changed = dirty();
    const current = project && !changed;
    const web = method.value === 'web';
    $('#project-heading').textContent = readDraft().title || 'Il tuo prossimo video';
    $('#project-state').textContent = changed ? 'Bozza modificata' : STATES[project?.status] || 'Bozza';
    $('#project-save-state').textContent = busy ? 'Operazione in corso…' : changed ? 'Modifiche da salvare' : project ? 'Salvato sul Mac' : 'Da salvare sul Mac';
    $('#project-conflict').hidden = !conflict;
    $('#project-error').hidden = !project?.error;
    $('#project-error').textContent = project?.error || '';
    $('#project-unsaved').hidden = !changed;
    $('#project-method-note').textContent = web
      ? 'Usa il tuo abbonamento sul sito HeyGen. Questo studio prepara i file e completa il video importato; non consuma crediti API.'
      : method.value === 'local' ? 'Produzione sul Mac. Il risultato dipende dal personaggio: un ritratto realistico locale resta una foto narrata.'
        : 'Integrazione a consumo separata dall’abbonamento web. Richiede chiave, budget e conferma del preventivo prima di inviare i materiali.';
    $('#project-web-work').hidden = !web;
    $('#project-other-work').hidden = web;
    $('#project-import-work').hidden = !web;
    $('#project-steps').hidden = !web;
    $('#project-other-heading').textContent = method.value === 'local' ? '2. Genera sul Mac' : '2. Genera con HeyGen API';
    $('#project-other-note').textContent = method.value === 'local' ? 'Salviamo il progetto e mettiamo il video nella coda locale. Al termine puoi scaricarlo o completare il taglio.' : 'Salviamo il progetto e apriamo il preventivo HeyGen. L’invio parte solo dopo la tua conferma.';
    $('#project-generate').textContent = method.value === 'local' ? 'Genera video sul Mac' : 'Vedi preventivo HeyGen API';
    $('#project-prepare').disabled = busy || !draft().script.trim() || !draft().voice;
    $('#project-generate').disabled = busy || !draft().script.trim() || !draft().voice;
    $('#project-save').disabled = busy;

    const materials = current && project.materials;
    const downloads = $('#project-materials');
    downloads.replaceChildren();
    if (materials) {
      for (const [key, label] of [['bundle', '↓ Tutti i materiali · ZIP'], ['audio', '↓ Audio'], ['character', '↓ Ritratto'], ['script', '↓ Copione'], ['captions', '↓ Sottotitoli SRT']]) addDownload(downloads, label, materials[key], key);
    }
    $('#project-material-note').textContent = materials ? `Materiali salvati con questa versione del progetto${materials.duration ? ` · audio ${Number(materials.duration).toFixed(1)} s` : ''}.` : changed && project?.materials ? 'Hai modificato il progetto. Salva e prepara di nuovo i materiali prima di usarli su HeyGen.' : 'I file compariranno qui dopo la preparazione. Non viene contattato HeyGen.';
    const audio = $('#project-audio');
    const audioUrl = materials && localLink(materials.audio);
    audio.hidden = !audioUrl;
    if (audioUrl && audio.getAttribute('src') !== audioUrl) audio.src = audioUrl;
    if (!audioUrl && audio.hasAttribute('src')) { audio.pause(); audio.removeAttribute('src'); }
    const source = current && project.source;
    $('#project-finish-work').hidden = !source;
    $('#project-import-note').textContent = source ? `Associato al progetto: ${source.title || 'Video importato'}. Un nuovo import sostituisce la sorgente di lavoro e conserva la precedente nella cronologia.` : changed && project?.source ? 'Le modifiche richiedono una nuova versione del video. Salva il progetto prima di importare il risultato aggiornato.' : 'Puoi tornare qui dopo aver generato il video sul sito.';
    if (source && sourceKey !== source.source_id) {
      sourceKey = source.source_id;
      video.pause();
      video.src = localLink(source.url) || '';
      finish.reset();
      field('source_captions_burned').checked = Boolean(source.captions_burned);
      field('source_captions_burned').disabled = Boolean(source.captions_burned);
      field('end').value = Math.min(180, source.duration).toFixed(2);
      field('end').max = source.duration;
      field('start').max = Math.max(0, source.duration - 1);
      restoreCut(source);
      $('#project-source-note').textContent = `${source.title || 'Video del progetto'} · ${Number(source.duration).toFixed(2)} secondi`;
      $('#project-source-download').replaceChildren();
      addDownload($('#project-source-download'), '↓ Video sorgente', source.url);
    }
    if (!source && sourceKey) { video.pause(); video.removeAttribute('src'); sourceKey = ''; }
    const activeStep = !project || changed ? 'prepare' : project.status === 'ready' || source ? 'finish' : materials ? 'import' : 'materials';
    for (const item of $('#project-steps').children) {
      if (item.dataset.step === activeStep) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');
    }
    drawFinish();
    drawResult(current && project.job);
    drawHistory();
  }

  function drawHistory() {
    const history = project?.history || [];
    $('#project-history').hidden = !history.length;
    const container = $('#project-history-items');
    const key = `${project?.id || ''}:${project?.revision || 0}:${history.map(item => item.job?.state || '').join(',')}`;
    if (container.dataset.revision === key) return;
    container.dataset.revision = key;
    container.replaceChildren();
    for (const previous of [...history].reverse()) {
      const entry = node('section', 'project-history-entry');
      entry.append(node('h3', '', `${previous.title || 'Progetto'} · versione ${previous.revision}`),
        node('p', 'hint', previous.script || ''));
      const links = node('div', 'project-actions');
      if (previous.materials?.bundle) addDownload(links, '↓ Materiali di questa versione', previous.materials.bundle);
      if (previous.source?.url) addDownload(links, '↓ Video sorgente di questa versione', previous.source.url);
      if (previous.job?.state === 'done') addDownload(links, '↓ MP4 esportato in questa versione', `/output/${previous.job.id}/video.mp4`);
      entry.append(links);
      container.append(entry);
    }
  }

  function drawFinish() {
    if (!project?.source || dirty()) return;
    const source = project.source;
    const start = Number(field('start').value);
    const end = Number(field('end').value);
    const valid = Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end <= source.duration + 0.02 && end - start >= 1 && end - start <= 180;
    $('#project-cut-note').textContent = valid ? `Taglio di ${(end - start).toFixed(2)} secondi. L’esportazione usa la coda locale.` : 'Scegli un intervallo tra 1 e 180 secondi, entro la durata della sorgente.';
    $('#project-export').disabled = busy || !valid;
    const hasPrepared = Boolean(project.materials?.captions);
    const burned = Boolean(source.captions_burned || field('source_captions_burned').checked);
    $('#project-prepared-captions-label').hidden = !hasPrepared;
    field('use_prepared_captions').disabled = burned || !hasPrepared;
    const captions = source.subtitle_count > 0 || (hasPrepared && field('use_prepared_captions').checked);
    field('burn_captions').disabled = burned || !captions;
    if (burned || !captions) field('burn_captions').checked = false;
    $('#project-caption-note').textContent = burned ? 'I sottotitoli già nel filmato restano visibili. Non ne aggiungiamo un secondo livello.' : captions ? 'Controlla i tempi nell’MP4 esportato. I sottotitoli preparati sono validi soltanto se l’audio usato su HeyGen è rimasto identico.' : 'Per usare l’SRT preparato conferma di aver mantenuto l’audio originale. Se hai cambiato voce o testo su HeyGen, usa i suoi sottotitoli o completa l’SRT in Clip e registrazioni.';
    $('.project-video-stage').style.aspectRatio = {portrait: '9 / 16', square: '1', landscape: '16 / 9'}[field('format').value];
    video.style.objectFit = field('fit').value;
  }

  function drawResult(job) {
    $('#project-result').hidden = !job;
    const actions = $('#project-result-actions');
    actions.replaceChildren();
    if (!job) return;
    const complete = job.state === 'done' || project.status === 'ready';
    $('#project-result-note').textContent = complete ? 'Video pronto. Scarica l’MP4 oppure prosegui con la pubblicazione.' : job.error || job.message || 'Il video è in coda o in produzione. Puoi continuare a lavorare: il progetto conserva lo stato.';
    if (complete) {
      const url = job.video_url || job.url || `/output/${job.id}/video.mp4`;
      addDownload(actions, '↓ Scarica MP4 finale', url);
      const link = actions.querySelector('a');
      if (link) link.id = 'project-final-download';
      const publish = node('button', 'button secondary', 'Apri Pubblicazione');
      publish.type = 'button';
      publish.dataset.projectView = 'publishing';
      actions.append(publish);
    }
  }

  async function prepare() {
    await mutate(async () => {
      const saved = await saveCurrent();
      if (!saved) return;
      if (dirty()) throw Error('Il progetto è cambiato durante il salvataggio. Salva le ultime modifiche prima di preparare i materiali.');
      const ticket = generation;
      status('Preparo audio, ritratto e copione sul Mac. La prima voce locale può richiedere qualche istante.');
      const result = await api('video-project-prepare', {id: saved.id, revision: saved.revision});
      if (ticket !== generation) return;
      project = result;
      await refresh();
      status(dirty() ? 'Materiali preparati per la versione salvata. Il testo è cambiato nel frattempo: salva e preparali di nuovo.' : 'Materiali pronti. Scaricali e continua nell’editor HeyGen.');
    });
  }

  async function importVideo(file) {
    if (!file) return;
    if (!/\.mp4$/i.test(file.name)) throw Error('Importa il file MP4 scaricato da HeyGen.');
    if (file.size === 0 || file.size > 2_000_000_000) throw Error('Scegli un MP4 non vuoto, fino a 2 GB.');
    await mutate(async () => {
      const saved = await saveCurrent();
      if (!saved) return;
      if (dirty()) throw Error('Il progetto è cambiato durante il salvataggio. Salva le ultime modifiche prima di importare il video.');
      const ticket = generation;
      $('#project-import-progress').hidden = false;
      $('#project-import-progress').value = 0;
      try {
        const result = await new Promise((resolve, reject) => {
          const request = new XMLHttpRequest();
          request.open('POST', '/api/video-project-import');
          request.setRequestHeader('X-Avatar-Token', bootstrap.token);
          request.setRequestHeader('X-Project-ID', saved.id);
          request.setRequestHeader('X-Project-Revision', String(saved.revision));
          request.setRequestHeader('X-Recording-Name', encodeURIComponent(file.name));
          request.upload.onprogress = event => {
            if (event.lengthComputable) $('#project-import-progress').value = event.loaded / event.total * 100;
          };
          request.onerror = () => reject(Error('Importazione interrotta. Controlla che lo studio sia aperto e riprova.'));
          request.onabort = () => reject(Error('Importazione annullata.'));
          request.onload = () => {
            try {
              const body = JSON.parse(request.responseText);
              if (request.status < 200 || request.status >= 300) throw Error(body.error || 'Importazione non riuscita.');
              resolve(body);
            } catch (error) { reject(error); }
          };
          request.send(file);
        });
        if (ticket !== generation) return;
        project = result;
        sourceKey = '';
        await refresh();
        status(dirty() ? 'Video importato nella versione salvata. Ci sono modifiche al copione ancora da salvare.' : 'Video associato al progetto. Controlla il taglio e prepara l’esportazione.');
      } finally {
        $('#project-import-progress').hidden = true;
        $('#project-file').value = '';
      }
    });
  }

  $('#project-save').onclick = guard(() => mutate(async () => {
    await saveCurrent();
    status(dirty() ? 'Versione salvata. Restano nuove modifiche nell’editor.' : 'Progetto salvato sul Mac.');
  }));
  $('#project-new').onclick = guard(() => openDraft());
  $('#project-save-copy').onclick = guard(() => mutate(async () => {
    // Omitting the old identity resolves conflicts without overwriting either draft.
    const snapshot = {...draft(), episode: null};
    const saved = await api('video-project', snapshot);
    project = saved;
    episode = null;
    conflict = false;
    sourceKey = '';
    await refresh();
    status('Le tue modifiche sono conservate in un nuovo progetto. La versione precedente resta nell’elenco.');
  }));
  $('#project-prepare').onclick = guard(prepare);
  $('#project-copy-script').onclick = guard(async () => {
    if (!draft().script.trim()) throw Error('Scrivi prima il copione.');
    await navigator.clipboard.writeText(draft().script);
    status('Copione copiato. Usando l’audio preparato conserverai la voce scelta nello studio.');
  });
  $('#project-file').onchange = guard(() => importVideo($('#project-file').files[0]));
  const drop = $('#project-dropzone');
  for (const name of ['dragenter', 'dragover']) drop.addEventListener(name, event => {
    event.preventDefault();
    if (!busy) drop.classList.add('dragging');
  });
  for (const name of ['dragleave', 'drop']) drop.addEventListener(name, event => {event.preventDefault(); drop.classList.remove('dragging');});
  drop.addEventListener('drop', guard(event => {
    if (event.dataTransfer.files.length !== 1) throw Error('Trascina un solo MP4 per questo progetto.');
    return importVideo(event.dataTransfer.files[0]);
  }));
  finish.oninput = finish.onchange = () => {drawFinish(); rememberCut();};
  finish.onsubmit = guard(async () => {
    if (!finish.reportValidity() || !project?.source || dirty()) return;
    const snapshot = {id: project.id, revision: project.revision, start: Number(field('start').value), end: Number(field('end').value),
      format: field('format').value, fit: field('fit').value,
      burn_captions: field('burn_captions').checked && !field('burn_captions').disabled,
      source_captions_burned: field('source_captions_burned').checked,
      use_prepared_captions: field('use_prepared_captions').checked && !field('use_prepared_captions').disabled};
    await mutate(async () => {
      video.pause();
      const result = await api('video-project-render', snapshot);
      project = result.project;
      await Promise.all([refreshJobs(), refresh()]);
      status('Esportazione avviata sul Mac. Il risultato comparirà in questo progetto e nella libreria video.');
    });
  });
  $('#project-mark-start').onclick = () => {field('start').value = video.currentTime.toFixed(2); drawFinish(); rememberCut();};
  $('#project-mark-end').onclick = () => {field('end').value = video.currentTime.toFixed(2); drawFinish(); rememberCut();};
  video.onplay = () => {
    if (video.currentTime < Number(field('start').value) || video.currentTime >= Number(field('end').value)) video.currentTime = Number(field('start').value);
  };
  video.ontimeupdate = () => {if (!video.paused && video.currentTime >= Number(field('end').value)) video.pause();};
  video.onerror = () => {if (video.getAttribute('src')) $('#project-source-note').textContent = 'Il browser non riesce a riprodurre questo video. Usa un MP4 H.264/AAC oppure controlla il file scaricato.';};
  $('#project-generate').onclick = guard(() => mutate(async () => {
    const saved = await saveCurrent();
    if (!saved) return;
    if (dirty()) throw Error('Il progetto è cambiato durante il salvataggio. Salva le ultime modifiche prima di generare il video.');
    const render = saved.method === 'local' ? renderLocal : renderApi;
    if (typeof render !== 'function') throw Error('La generazione non è disponibile. Ricarica lo studio e riprova.');
    const job = await render(saved);
    if (job?.video_project) project = job.video_project;
    await Promise.all([refreshJobs(), refresh()]);
  }));

  method.onchange = draw;
  create.addEventListener('input', event => {if (!finish.contains(event.target)) draw();});
  create.addEventListener('change', event => {if (!finish.contains(event.target)) draw();});
  window.addEventListener('studio:draft-changed', draw);
  for (const section of [dashboard, create, guide]) section.addEventListener('click', event => {
    const button = event.target.closest('button[data-project-view]');
    if (button) navigate(button.dataset.projectView);
  });
  window.addEventListener('studio:new-project', guard(event => openDraft(event.detail || {})));
  window.addEventListener('studio:view', event => {
    visible = event.detail;
    if (visible === 'projects' || visible === 'create') refresh().catch(report);
    if (visible !== 'create') {video.pause(); $('#project-audio').pause();}
  });
  window.addEventListener('beforeunload', event => {
    if (dirty() || busy) {event.preventDefault(); event.returnValue = '';}
  });
  // One inexpensive status poll while a relevant screen is visible; no external service calls.
  window.setInterval(() => {
    if (!document.hidden && !busy && ['projects', 'create'].includes(visible) && projects.some(item => ['rendering', 'preparing', 'importing'].includes(item.status))) refresh().catch(report);
  }, 5000);
  setBusy(true);
  try {
    await refresh();
    await restoreEditor();
  } finally {
    restoring = false;
    setBusy(false);
  }
  return {refresh, openDraft, saveCurrent: () => mutate(saveCurrent), getCurrentProject: () => project};
}

function guideMarkup() {
  return `<div class="section-heading"><div><p class="eyebrow">DALLA PRIMA IDEA ALL’MP4</p><h2 id="guide-heading">Come usare Avatar Studio</h2>
    <p class="hint">Il percorso principale usa HeyGen dal sito. Lo studio conserva ogni progetto e prepara il materiale; tu scegli e generi l’animazione nell’editor HeyGen.</p></div>
    <button class="button primary" data-project-view="projects" type="button">Vai ai progetti</button></div>
    <div class="project-guide-intro panel"><h3>Prima di iniziare</h3><p>Per scrivere, scegliere un personaggio e preparare l’audio bastano lo studio e i suoi motori locali configurati. Per l’animazione sul sito servono un account HeyGen e i crediti del tuo piano web. Non devi collegare una chiave API.</p>
      <p>Il browser resta aperto accanto allo studio. I materiali non vengono inviati automaticamente a HeyGen e aprire il sito non avvia una generazione.</p>
      <a class="button secondary" href="/docs/WORKFLOW-GUIDA.md" download>↓ Scarica la guida completa</a></div>
    <ol class="project-guide-steps">
      <li class="panel"><h3>1. Crea un progetto e scegli il personaggio</h3><p>Apri <strong>Progetti → Nuovo video</strong>. Dai un titolo al lavoro e mantieni il metodo <strong>HeyGen dal sito</strong>. Scegli un personaggio con un ritratto, oppure preparalo nella sezione <strong>Personaggi</strong>. Il robot 3D locale richiede un’immagine di riferimento per questo percorso.</p></li>
      <li class="panel"><h3>2. Scrivi, rileggi e ascolta</h3><p>Scrivi il copione o parti da un’idea per ottenere una bozza. Controlla il testo, la lingua, la voce e il ritmo. Premi <strong>Ascolta il testo</strong> e poi <strong>Salva progetto</strong>. Il piano contenuti ti aiuta a organizzare gli episodi; ogni video mantiene un progetto distinto.</p></li>
      <li class="panel"><h3>3. Prepara e scarica i materiali</h3><p>Premi <strong>Prepara materiali per HeyGen</strong>. Scarica il pacchetto ZIP oppure audio, ritratto e copione separatamente. Il pacchetto include anche i sottotitoli preparati. Estrai lo ZIP sul Mac prima di caricare i singoli file sul sito.</p><p>Se cambi copione, voce, personaggio o metodo, salva e prepara una nuova versione: i vecchi materiali non rappresentano più il progetto corrente.</p></li>
      <li class="panel"><h3>4. Genera l’animazione su HeyGen</h3><p>Premi <strong>Apri HeyGen</strong>, accedi e crea un video usando il ritratto e l’audio scaricati. Scegli il formato e controlla il consumo di crediti mostrato dal sito. Avvia la generazione e scarica il video in MP4.</p><p><strong>Per mantenere la voce dello studio, carica il nostro audio.</strong> Se invece incolli il copione e scegli una voce su HeyGen, il timbro e i tempi cambieranno: l’SRT preparato nello studio potrebbe non essere più sincronizzato. In quel caso puoi aggiungere i sottotitoli su HeyGen prima di scaricare il video.</p></li>
      <li class="panel"><h3>5. Importa l’MP4 nello stesso progetto</h3><p>Torna allo studio e trascina l’MP4 nell’area <strong>Importa il risultato</strong>. Il file viene copiato sul Mac e collegato al progetto. Puoi chiudere e riaprire lo studio: in <strong>Progetti</strong> ritroverai copione, materiali e video.</p></li>
      <li class="panel"><h3>6. Controlla taglio, formato e sottotitoli</h3><p>Guarda l’anteprima, scegli inizio e fine del taglio e imposta verticale, quadrato oppure orizzontale. <strong>Mantieni tutta l’immagine</strong> può aggiungere bande; <strong>Riempi</strong> ritaglia i lati. Controlla che il viso e le scritte restino leggibili.</p><p>Se hai usato esattamente l’audio preparato, confermalo per rendere disponibili i nostri sottotitoli. Se il filmato contiene già scritte visibili, seleziona l’apposita casella per evitare un secondo livello. Questo passaggio non trascrive né riconosce automaticamente l’audio.</p></li>
      <li class="panel"><h3>7. Esporta e prepara la pubblicazione</h3><p>Premi <strong>Esporta il video sul Mac</strong>. La coda locale produce il taglio, da 1 a 180 secondi. Attendi lo stato <strong>Pronto da esportare</strong>, scarica l’MP4 finale e guardalo per intero, con l’audio, prima di pubblicarlo. Il risultato resta anche nella libreria video.</p><p>La sezione <strong>Pubblicazione</strong> raccoglie i passaggi successivi. La creazione del video non pubblica nulla sui tuoi canali.</p></li>
    </ol>
    <div class="project-guide-options"><section class="panel"><h3>Riprendere un lavoro</h3><p>Apri il progetto dalla pagina iniziale. Lo stato distingue bozza, materiali pronti, video importato, produzione e risultato finale. Prima di aprire un altro progetto lo studio salva la bozza corrente; se il salvataggio fallisce rimani nel lavoro attuale.</p><p>Un errore non segna il video come completato. Correggi la causa e riprova. Se il progetto è stato modificato in un’altra scheda, ricarica la versione salvata prima di sovrascriverla.</p></section>
    <section class="panel"><h3>Gli altri metodi</h3><p><strong>Generazione locale:</strong> produce direttamente sul Mac. Robot e cartoon usano la loro animazione locale; un ritratto realistico resta una foto narrata.</p><p><strong>HeyGen API:</strong> usa un’integrazione automatica distinta dal sito, con chiave e budget dedicati. Prima dell’invio compare un preventivo da confermare. L’abbonamento web non paga queste chiamate.</p><p>Dirette, campagne e configurazioni specialistiche rimangono tra gli strumenti avanzati; non sono necessari per questo workflow.</p></section></div>`;
}
