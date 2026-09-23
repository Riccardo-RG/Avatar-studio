// A single router for the primary workflow and the optional studio tools.
const primaryViews = ['projects', 'create', 'lab', 'plan', 'publishing', 'guide'];
let currentView = null;

function sections() {
  return [...document.querySelectorAll('main > [id^="view-"]')];
}

export function navigate(requested) {
  const available = sections();
  const name = available.some(section => section.id === 'view-' + requested)
    ? requested : 'projects';
  for (const section of available) section.hidden = section.id !== 'view-' + name;
  for (const button of document.querySelectorAll('.studio-nav [data-view]')) {
    const active = button.dataset.view === name;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
    if (active && button.closest('details')) button.closest('details').open = true;
  }
  document.querySelector('.library').hidden = !['projects', 'create', 'plan', 'clips'].includes(name);
  history.replaceState(null, '', '#' + name);
  currentView = name;
  window.dispatchEvent(new CustomEvent('studio:view', {detail: name}));
}

export function initNavigation() {
  const nav = document.querySelector('.studio-nav');
  const buttons = [...nav.querySelectorAll('[data-view]')];
  const advanced = document.createElement('details');
  advanced.className = 'studio-tools';
  const summary = document.createElement('summary');
  summary.textContent = 'Altri strumenti';
  const tools = document.createElement('div');
  tools.className = 'studio-tools-list';
  advanced.append(summary, tools);
  nav.replaceChildren();
  for (const name of primaryViews) {
    const button = buttons.find(item => item.dataset.view === name);
    if (button) nav.append(button);
  }
  for (const button of buttons) {
    if (!primaryViews.includes(button.dataset.view)) tools.append(button);
  }
  nav.append(advanced);
  nav.addEventListener('click', event => {
    const button = event.target.closest('button[data-view]');
    if (button) navigate(button.dataset.view);
  });
  window.addEventListener('hashchange', () => {
    if (location.hash.slice(1) !== currentView) navigate(location.hash.slice(1));
  });
  window.addEventListener('studio:navigate', event => navigate(event.detail));
  navigate(location.hash.slice(1) || 'projects');
}
