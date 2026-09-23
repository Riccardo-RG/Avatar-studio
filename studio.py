"""Persistent editorial workspace: persona, recurring formats and versioned episodes."""
import copy
import datetime
import difflib
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid

from catalog import PERSONA, RUBRICS, EPISODES
import providers
import languages

ROOT = Path(__file__).resolve().parent
PATH = ROOT / 'data/studio.json'
LOCK = threading.RLock()


def fresh():
    episodes = []
    for item in EPISODES:
        episodes.append({**copy.deepcopy(item), 'topic': item['title'], 'status': 'draft',
                         'planned_date': '', 'revision': 1, 'job_id': None, 'updated': time.time(), 'character_id': 'nova',
                         'source': 'Copione originale preparato per la prima serie; modificabile.'})
    return {'version': 2, 'persona': copy.deepcopy(PERSONA), 'rubrics': copy.deepcopy(RUBRICS), 'episodes': episodes}


def load():
    with LOCK:
        if not PATH.exists():
            providers.atomic_json(PATH, fresh())
        doc = json.loads(PATH.read_text(encoding='utf-8'))
        changed = False
        for e in doc['episodes']:
            if not e.get('character_id'):
                project = ROOT / 'output' / str(e.get('job_id','')) / 'project.json'
                saved = json.loads(project.read_text()) if e.get('job_id') and project.is_file() else {}
                e['character_id'] = saved.get('settings',{}).get('character',{}).get('id') or 'nova'
                changed = True
        if changed: providers.atomic_json(PATH, doc)
        return doc


def text(value, label, limit, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= limit:
        raise ValueError(f'{label}: usa da {minimum} a {limit} caratteri.')
    return value.strip()


def save_persona(data):
    if not isinstance(data, dict):
        raise ValueError('Scheda personaggio non valida.')
    with LOCK:
        doc = load()
        for key in PERSONA:
            if key in data:
                doc['persona'][key] = text(data[key], key, 400)
        providers.atomic_json(PATH, doc)
        return doc['persona']


def save_rubric(data):
    with LOCK:
        doc = load()
        rubric = next((r for r in doc['rubrics'] if r['id'] == data.get('id')), None)
        if not rubric:
            raise ValueError('Rubrica non trovata.')
        for key, limit in [('name', 60), ('description', 220), ('direction', 400)]:
            if key in data:
                rubric[key] = text(data[key], key, limit)
        providers.atomic_json(PATH, doc)
        return rubric


def similarity_warnings(script, episodes, exclude_id=None):
    """Suggest reviewing close wording; this is not plagiarism or quality detection."""
    def words(value):
        return re.findall(r'\w+', value.casefold()) if isinstance(value, str) else []
    candidate = words(script)
    if len(candidate) < 20 or len(' '.join(candidate)) < 120:
        return []
    matches = []
    for previous in episodes:
        if previous.get('id') == exclude_id:
            continue
        other = words(previous.get('script', ''))
        if len(other) < 20 or len(' '.join(other)) < 120:
            continue
        # Cheap upper bound avoids a quadratic comparison for very different lengths.
        if 2 * min(len(candidate), len(other)) / (len(candidate) + len(other)) < .82:
            continue
        ratio = difflib.SequenceMatcher(None, candidate, other, autojunk=False).ratio()
        if ratio >= .82:
            matches.append({'episode_id': previous.get('id'), 'title': previous.get('title', ''),
                            'similarity_percent': round(ratio * 100),
                            'note': 'Testo simile a un episodio del piano. Rivedi apporto nuovo e ripetizioni; è un confronto lessicale, non una verifica di plagio o monetizzazione.'})
    return sorted(matches, key=lambda match: match['similarity_percent'], reverse=True)[:3]


def save_episode(data):
    if not isinstance(data, dict):
        raise ValueError('Episodio non valido.')
    with LOCK:
        doc = load()
        identity = data.get('id')
        episode = next((e for e in doc['episodes'] if e['id'] == identity), None)
        if identity and not episode:
            raise ValueError('Episodio non trovato.')
        if episode and int(data.get('revision', -1)) != episode['revision']:
            raise ValueError('L’episodio è cambiato in un’altra finestra. Riaprilo prima di salvarlo.')
        new = copy.deepcopy(episode) if episode else {'id': uuid.uuid4().hex[:12], 'revision': 0,
              'status': 'draft', 'job_id': None, 'source': 'Creato nello studio', 'hooks': [], 'planned_date': ''}
        for key, limit, default, minimum in [
                ('title', 80, '', 1), ('topic', 500, '', 0), ('script', 2400, '', 2),
                ('cover', 60, data.get('title', ''), 1), ('question', 180, 'Tu cosa ne pensi?', 1),
                ('planned_date', 10, '', 0)]:
            new[key] = text(data.get(key, new.get(key, default)), key, limit, minimum)
        if new['planned_date']:
            try:
                datetime.date.fromisoformat(new['planned_date'])
            except ValueError:
                raise ValueError('Data non valida. Usa anno-mese-giorno.') from None
        new['rubric_id'] = data.get('rubric_id', new.get('rubric_id', 'umani'))
        if new['rubric_id'] not in {r['id'] for r in doc['rubrics']}:
            raise ValueError('Rubrica non valida.')
        hooks = data.get('hooks', new.get('hooks', []))
        if not isinstance(hooks, list) or len(hooks) > 3:
            raise ValueError('Puoi salvare al massimo tre aperture.')
        new['hooks'] = [text(h, 'Apertura', 150) for h in hooks if isinstance(h, str) and h.strip()]
        options = {key: data.get(key, new.get(key, default)) for key, default in
                   [('duration_seconds', 30), ('editor_format', 'explainer'), ('hook', ''), ('cta', '')]}
        if 'seconds' in data and 'duration_seconds' not in data:
            options['duration_seconds'] = data['seconds']
        new.update(providers.editorial_options(options))
        new['similarity_warnings'] = similarity_warnings(new['script'], doc['episodes'], new['id'])
        new['status'] = 'draft'  # Edits require a new explicit ready state; past media stay available.
        import platform_store
        identity = data.get('character_id', new.get('character_id'))
        if identity == '': raise ValueError('Scegli il personaggio dell’episodio.')
        new['character_id'] = platform_store.snapshot(identity)['id']
        new['language']=languages.code(data.get('language',new.get('language','it')))
        new['revision'] += 1
        new['updated'] = time.time()
        if episode:
            doc['episodes'][doc['episodes'].index(episode)] = new
        else:
            doc['episodes'].append(new)
        providers.atomic_json(PATH, doc)
        return new


def set_ready(identity, revision, ready=True):
    with LOCK:
        doc = load()
        episode = next((e for e in doc['episodes'] if e['id'] == identity), None)
        if not episode or episode['revision'] != int(revision):
            raise ValueError('Episodio modificato o non trovato. Ricarica il piano.')
        if episode['status'] == 'rendering':
            raise ValueError('La produzione è già in corso.')
        episode['status'] = 'approved' if ready else 'draft'
        providers.atomic_json(PATH, doc)
        return episode


def claim_episodes(ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or len(set(ids)) != len(ids):
        raise ValueError('Scegli da uno a dieci episodi distinti.')
    with LOCK:
        doc = load()
        selected = []
        for identity in ids:
            item = next((e for e in doc['episodes'] if e['id'] == identity), None)
            if not item or item['status'] != 'approved':
                raise ValueError('La produzione accetta soltanto episodi segnati come pronti.')
            selected.append(item)
        fingerprints = [hashlib.sha256(re.sub(r'\W+', '', e['script']).lower().encode()).hexdigest() for e in selected]
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError('Due episodi selezionati hanno lo stesso copione. Modificali prima di produrre la serie.')
        for item in selected:
            item['status'] = 'rendering'
        providers.atomic_json(PATH, doc)
        return copy.deepcopy(selected), copy.deepcopy(doc['persona']), copy.deepcopy(doc['rubrics'])


def finish_episode(identity, revision, job_id, success):
    with LOCK:
        doc = load()
        item = next((e for e in doc['episodes'] if e['id'] == identity), None)
        if item and item['revision'] == revision:
            item['job_id'] = job_id
            item['status'] = 'ready' if success else 'approved'
            providers.atomic_json(PATH, doc)


def recover_interrupted():
    with LOCK:
        doc = load()
        for e in doc['episodes']:
            if e['status'] == 'rendering':
                e['status'] = 'approved'
        providers.atomic_json(PATH, doc)


def prompt_context(rubric_id=None, character_id=None):
    doc = load()
    persona = doc['persona']
    if character_id:
        import platform_store
        persona = platform_store.snapshot(character_id)['editorial']
    profile = '\n'.join(f'{k}: {v}' for k,v in persona.items())
    rubric = next((r for r in doc['rubrics'] if r['id'] == rubric_id), None)
    if rubric:
        profile += f"\nRubrica: {rubric['name']}. {rubric['direction']}"
    titles = [e['title'] for e in doc['episodes'] if e['status'] == 'ready' and (not character_id or e.get('character_id') == character_id)][-5:]
    if titles:
        profile += '\nEvita di ripetere questi episodi già prodotti: ' + '; '.join(titles)
    return profile
