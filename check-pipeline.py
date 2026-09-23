"""End-to-end local acceptance run. Generates real media, never calls paid APIs."""
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8765'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.load(r)


boot = get('/api/bootstrap')


def post(path, payload, timeout=450):
    req = urllib.request.Request(BASE + path, json.dumps(payload).encode(),
        {'Content-Type': 'application/json', 'X-Avatar-Token': boot['token']})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


config = boot['settings']
assert config['provider'] == 'local' and config['monthly_budget_usd'] == 0
cases = []
post('/api/settings', {**config, 'resolution': 540})
cases.append(post('/api/render', {'title': '01 · Dal testo al video', 'script': 'Ciao! Sono il tuo avatar di prova. Questo video nasce da un testo scritto da te. La voce, i colori e il nome possono cambiare.'}))
print('Primo video in produzione:', cases[-1]['id'], flush=True)
print('Generazione del copione locale...', flush=True)
draft = post('/api/script', {'topic': 'Una piccola abitudine per tenere in ordine la scrivania', 'seconds': 15})
(ROOT / 'output/test-draft.json').write_text(json.dumps(draft, ensure_ascii=False, indent=2))
print('Copione AI:', draft['script'], flush=True)
cases.append(post('/api/render', {'title': '02 · Da un argomento al video', 'script': draft['script']}))
post('/api/settings', {**config, 'resolution': 540, 'accent': '#c5b8ff', 'name': 'NOVA', 'rate': 175})
cases.append(post('/api/render', {'title': '03 · Stesso avatar, nuove impostazioni', 'script': 'Un solo sistema, tante possibilità. Posso cambiare colore, voce e ritmo. Tu puoi partire da un testo, oppure scegliere un argomento e modificare la bozza.'}))
post('/api/settings', config)
deadline = time.time() + 1800
pending = {c['id'] for c in cases}
last = {}
while pending and time.time() < deadline:
    for identity in list(pending):
        job = get('/api/jobs/' + identity)
        key = (job['state'], job['progress'])
        if last.get(identity) != key:
            print(identity, job['state'], job['progress'], job['message'], flush=True)
            last[identity] = key
        if job['state'] in ('error', 'cancelled'):
            raise RuntimeError(job)
        if job['state'] == 'done':
            pending.remove(identity)
    if pending:
        time.sleep(5)
assert not pending, 'Rendering timeout'
result = [get('/api/jobs/' + c['id']) for c in cases]
(ROOT / 'output/acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print('Tre video completati.', flush=True)
