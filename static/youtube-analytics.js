const labels = {
  views: 'Visualizzazioni', engaged_views: 'Visualizzazioni coinvolte',
  estimated_minutes_watched: 'Minuti guardati', average_view_duration_seconds: 'Durata media guardata (s)',
  average_view_percentage: 'Percentuale media guardata', subscribers_gained: 'Iscritti acquisiti',
  estimated_revenue_eur: 'Ricavi stimati (€)',
};
const element = (tag, text, className = '') => {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
};

export function initYouTubeAnalytics({section, api, report}) {
  const box = element('section', '', 'panel platform-form');
  box.id = 'youtube-analytics';
  box.innerHTML = `<h3>YouTube Analytics · approfondisci un video</h3>
    <p class="hint">Scegli un video confermato e un periodo. La lettura usa l’account del post e parte solo quando la richiedi.</p>
    <form id="youtube-analytics-form" class="platform-form">
      <label>Video YouTube<select name="publication_id" required></select></label>
      <div class="form-row"><label>Dal<input name="start_date" type="date" required></label>
        <label>Al<input name="end_date" type="date" required></label></div>
      <label class="checkbox-row"><input name="include_revenue" type="checkbox">Leggi anche i ricavi stimati, se autorizzati</label>
      <p class="hint">Da 1 a 366 giorni di calendario nel fuso Pacifico. I dati recenti possono essere incompleti; questo periodo non equivale alle prime 24 ore o ai primi 7 giorni del post.</p>
      <div class="platform-actions"><button class="button secondary" type="submit">Leggi YouTube Analytics</button>
        <button class="button" id="youtube-analytics-connect" type="button">Permessi in Collegamenti</button></div>
    </form><p id="youtube-analytics-state" class="hint" aria-live="polite"></p>
    <div id="youtube-analytics-result" class="platform-form" hidden aria-live="polite"></div>`;
  section.append(box);
  const form = box.querySelector('form'), state = box.querySelector('#youtube-analytics-state');
  const resultBox = box.querySelector('#youtube-analytics-result'), submit = form.querySelector('[type=submit]');
  const date = new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
  form.elements.start_date.value = date;
  form.elements.end_date.value = date;
  form.elements.start_date.max = date; form.elements.end_date.max = date;
  let rows = [], ticket = 0, running = false;
  const request = () => ({publication_id: form.elements.publication_id.value,
    start_date: form.elements.start_date.value, end_date: form.elements.end_date.value,
    include_revenue: form.elements.include_revenue.checked});
  function invalidate() { ticket++; resultBox.hidden = true; resultBox.replaceChildren(); state.textContent = ''; }
  form.oninput = invalidate;
  box.querySelector('#youtube-analytics-connect').onclick = () => document.querySelector('[data-view="connections"]').click();
  form.onsubmit = async event => {
    event.preventDefault(); const query = request(), current = ++ticket;
    const post = rows.find(row => row.id === query.publication_id);
    if (!post || running) return;
    running = true; submit.disabled = true; resultBox.hidden = true;
    state.textContent = 'Lettura Analytics in corso…';
    try {
      const data = await api('youtube-analytics', query);
      if (ticket !== current || JSON.stringify(request()) !== JSON.stringify(query)) return;
      if (data.publication_id !== post.id || data.profile_id !== (post.connection_id || 'default') || data.channel_id !== post.account_id) throw Error('Il report non corrisponde al video e all’account selezionati. Ricarica i risultati.');
      resultBox.replaceChildren(element('h4', post.title),
        element('p', `${post.connection_name || 'Principale'} · ${data.channel_id}`, 'hint'),
        element('p', `${data.period.start_date} → ${data.period.end_date} · ${data.period.timezone}`, 'hint'));
      const grid = element('div', '', 'metric-grid');
      for (const [key, label] of Object.entries(labels)) {
        const cell = element('div', '', 'metric-value'), number = data.metrics[key];
        cell.dataset.analyticsMetric = key;
        cell.append(element('strong', number == null ? '—' : new Intl.NumberFormat('it-IT', {maximumFractionDigits: 2}).format(number)), element('small', label));
        grid.append(cell);
      }
      resultBox.append(grid, element('p', data.monetary_message, 'hint'));
      for (const note of data.limitations || []) resultBox.append(element('p', note, 'hint'));
      const download = element('button', 'Esporta questo report JSON', 'button secondary');
      download.type = 'button'; download.onclick = () => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
        const link = element('a', ''); link.href = url; link.download = `youtube-analytics-${post.id}.json`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      };
      resultBox.append(download); resultBox.hidden = false;
      state.textContent = ({available: 'Report ricevuto.', partial: 'Report parziale: i dati mancanti restano vuoti.', no_data: 'Nessun dato disponibile per questo periodo.'})[data.data_status] || 'Report ricevuto.';
    } catch (error) { if (ticket === current) { state.textContent = error.message; report(error); } }
    finally { running = false; submit.disabled = !rows.length; }
  };
  return {
    update(items) {
      const old = form.elements.publication_id.value, previous = rows.find(row => row.id === old);
      rows = items.filter(row => row.platform === 'youtube');
      const select = form.elements.publication_id;
      select.replaceChildren(new Option(rows.length ? 'Scegli un video…' : 'Nessun video YouTube confermato', ''));
      for (const row of rows) select.append(new Option(`${row.title} · ${row.connection_name || row.account_id}`, row.id));
      select.value = rows.some(row => row.id === old) ? old : '';
      const current = rows.find(row => row.id === select.value);
      if (previous && (!current || previous.account_id !== current.account_id || previous.connection_id !== current.connection_id)) invalidate();
      submit.disabled = running || !rows.length;
      if (!rows.length) state.textContent = 'Disponibile dopo una pubblicazione YouTube confermata. Puoi predisporre i permessi in Collegamenti.';
    },
  };
}
