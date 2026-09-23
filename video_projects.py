"""Persistent video workspaces; the website hand-off uses local files only.

Draft revisions protect every write. Long preparation/import operations claim one
project, while unrelated projects remain editable. Generated assets are immutable.
"""
import copy
import json
from pathlib import Path
import re
import shutil
import threading
import time
import uuid
import zipfile

import clips
import media
import platform_store
import providers


ROOT = Path(__file__).resolve().parent
LOCK = threading.RLock()
METHODS = ('web', 'local', 'api')
ASSET_NAMES = frozenset(('voice.wav', 'script.txt', 'captions.srt', 'character.png', 'materials.zip'))


class Conflict(ValueError):
    """The caller must refresh the current project before trying again."""


def project_folder(identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{12}', identity):
        raise ValueError('Progetto non valido.')
    return ROOT / 'data/video-projects' / identity


def _read(identity):
    path = project_folder(identity) / 'project.json'
    if not path.is_file():
        raise ValueError('Progetto non trovato.')
    return json.loads(path.read_text(encoding='utf-8'))


def _write(project):
    folder = project_folder(project['id'])
    folder.mkdir(parents=True, exist_ok=True)
    providers.atomic_json(folder / 'project.json', project)


def _current(identity, revision):
    project = _read(identity)
    if type(revision) is not int or revision != project['revision']:
        raise Conflict('Il progetto è cambiato. Ricaricalo prima di continuare.')
    if project.get('operation'):
        raise Conflict('Questo progetto ha già un’operazione in corso. Attendi il completamento.')
    return project


def _job(identity):
    if not identity:
        return None
    path = ROOT / 'output' / identity / 'status.json'
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _source(project, job=None):
    """Keep an imported/original generated source stable across later exports."""
    saved = project.get('source')
    if not saved:
        job = job or _job(project.get('job_id'))
        if not job or job.get('state') != 'done':
            return None
        saved = {'source_id': 'job:' + job['id'], 'id': job['id'],
                 'url': f'/output/{job["id"]}/video.mp4', 'title': job['title'],
                 'created': job['created'], 'materials_id': None}
    _, info, source_project = clips.source(saved['source_id'])
    # SRT files may have been added through Clip e registrazioni since import.
    return {**saved, 'duration': info['duration'], 'subtitle_count': len(info.get('captions', [])),
            'captions_burned': bool(source_project.get('captions_burned', bool(source_project.get('captions'))))}


def public(project):
    result = copy.deepcopy(project)
    result['character'] = copy.deepcopy(project.get('settings', {}).get('character'))
    result.pop('settings', None)
    result['job'] = _job(project.get('job_id'))
    result['source'] = _source(project, result['job'])
    for previous in result.get('history', []):
        previous['job'] = _job(previous.get('job_id'))
    if project.get('operation'):
        result['status'] = project['operation']['kind']
    elif result['job']:
        state = result['job']['state']
        if state == 'done':
            result['status'] = 'ready'
        elif state in ('queued', 'running'):
            result['status'] = 'rendering'
        else:
            result['status'] = 'video_imported' if project.get('source') else 'draft'
            result['error'] = result['job'].get('message', 'Produzione interrotta. Puoi riprovare.')
    return result


def catalog():
    with LOCK:
        projects = [public(json.loads(path.read_text(encoding='utf-8')))
                    for path in (ROOT / 'data/video-projects').glob('*/project.json')]
    return {'projects': sorted(projects, key=lambda p: p['updated'], reverse=True)}


def recover_interrupted():
    """Only called on server startup, after exclusive ownership of its port."""
    with LOCK:
        jobs = []
        for status in (ROOT / 'output').glob('*/status.json'):
            try:
                job = json.loads(status.read_text(encoding='utf-8'))
                if isinstance(job, dict) and re.fullmatch(r'[a-f0-9]{12}', str(job.get('id', ''))):
                    jobs.append(job)
            except (OSError, ValueError):
                continue
        for path in (ROOT / 'data/video-projects').glob('*/project.json'):
            project = json.loads(path.read_text(encoding='utf-8'))
            operation = project.pop('operation', None)
            if operation:
                if operation['kind'] == 'preparing':
                    shutil.rmtree(project_folder(project['id']) / 'materials' / operation['id'], ignore_errors=True)
                project.update(error='Operazione interrotta dalla chiusura dello studio. Puoi riprovare.',
                               revision=project['revision'] + 1, updated=time.time())
                _write(project)
            # A process may stop between enqueue's durable job write and the
            # project link write. Recover that exact revision without a new job.
            pending = [job for job in jobs if job.get('video_project_id') == project['id']
                       and job.get('video_project_revision') == project['revision']
                       and job['id'] != project.get('job_id')]
            if pending:
                _attach(project, max(pending, key=lambda job: job.get('created', 0)))


def _archive(project):
    if project.get('materials') or project.get('source') or project.get('job_id'):
        previous = {key: copy.deepcopy(project.get(key)) for key in
                    ('revision', 'title', 'script', 'character_id', 'language', 'voice', 'rate',
                     'method', 'materials', 'source', 'job_id', 'updated')}
        project.setdefault('history', []).append(previous)


def save(data, settings):
    title = platform_store.text(data.get('title', ''), 80, True)
    script = platform_store.text(data.get('script', ''), 2400)
    method = data.get('method', 'web')
    if method not in METHODS:
        raise ValueError('Scegli HeyGen dal sito, generazione locale o HeyGen API.')
    editorial = providers.editorial_options(data)
    episode = data.get('episode')
    if episode is not None:
        if (not isinstance(episode, dict) or not re.fullmatch(r'[a-f0-9]{12}', str(episode.get('id', '')))
                or type(episode.get('revision')) is not int or episode['revision'] < 1):
            raise ValueError('Riferimento al piano non valido.')
        episode = {key: episode[key] for key in ('id', 'revision')}
    fields = dict(title=title, script=script, method=method,
                  character_id=settings['character']['id'], language=settings['language'],
                  voice=settings['voice'], rate=settings['rate'],
                  topic=platform_store.text(data.get('topic', ''), 500),
                  rubric_id=platform_store.text(data.get('rubric_id', ''), 64),
                  episode=episode, **editorial)
    with LOCK:
        if data.get('id'):
            project = _current(data['id'], data.get('revision'))
        else:
            if episode:
                for path in (ROOT / 'data/video-projects').glob('*/project.json'):
                    existing = json.loads(path.read_text(encoding='utf-8'))
                    if existing.get('episode') == episode:
                        return public(existing)
            project = dict(id=uuid.uuid4().hex[:12], revision=0, created=time.time(),
                           history=[], materials=None, source=None, job_id=None)
        # Editorial labels do not change the performed audio or character. Keep
        # their media attached; invalidate only when generation inputs change.
        changed = any(project.get(key) != value for key, value in fields.items())
        generation_keys = ('script', 'method', 'character_id', 'language', 'voice', 'rate')
        snapshot_keys = ('character', 'resolution', 'format', 'color', 'accent', 'background')
        generation_changed = (any(project.get(key) != fields[key] for key in generation_keys)
            or any(project.get('settings', {}).get(key) != settings.get(key) for key in snapshot_keys))
        if generation_changed:
            _archive(project)
            project.update(materials=None, source=None, job_id=None, status='draft')
        if not changed and not generation_changed and project.get('revision'):
            return public(project)
        project.update(fields, settings=copy.deepcopy(settings), error='',
                       revision=project['revision'] + 1, updated=time.time())
        _write(project)
        return public(project)


def _claim(identity, revision, kind):
    with LOCK:
        project = _current(identity, revision)
        operation = {'id': uuid.uuid4().hex[:12], 'kind': kind, 'started': time.time()}
        project['operation'] = operation
        project['error'] = ''
        _write(project)
        return copy.deepcopy(project), operation['id']


def _finish(identity, operation, changes=None, error=''):
    with LOCK:
        project = _read(identity)
        if project.get('operation', {}).get('id') != operation:
            raise Conflict('Operazione superata da una versione più recente del progetto.')
        project.pop('operation')
        if changes:
            _archive(project)
            project.update(changes)
        project.update(error=error, revision=project['revision'] + 1, updated=time.time())
        _write(project)
        return public(project)


def prepare(identity, revision):
    # All preparation is local: no provider, cloud quote, upload or API request.
    with LOCK:
        project = _current(identity, revision)
        if project['method'] != 'web':
            raise ValueError('Il pacchetto materiali serve per HeyGen dal sito.')
        if len(project['script']) < 2:
            raise ValueError('Completa il copione prima di preparare i materiali.')
        image = platform_store.asset_file(project['settings']['character'].get('image'))
        if not image or not image.is_file():
            raise ValueError('Per HeyGen scegli un personaggio con immagine, come Ari o Lumo.')
        project, operation = _claim(identity, revision, 'preparing')
    folder = project_folder(identity) / 'materials' / operation
    try:
        folder.mkdir(parents=True)
        # Copy the reference first so later character edits cannot alter this package.
        shutil.copyfile(image, folder / 'character.png')
        timeline = media.synthesize(project['script'], project['settings'], folder, lambda *_: None)
        if not 0 < clips.number(timeline.get('duration')) <= 180:
            raise ValueError('L’audio supera tre minuti. Accorcia il copione prima di continuare.')
        (folder / 'script.txt').write_text(project['script'] + '\n', encoding='utf-8')
        providers.atomic_json(folder / 'timeline.json', timeline)
        providers.atomic_json(folder / 'snapshot.json', project)
        with zipfile.ZipFile(folder / 'materials.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(ASSET_NAMES - {'materials.zip'}):
                archive.write(folder / name, name)
        prefix = f'/video-project-assets/{identity}/{operation}/'
        materials = dict(id=operation, created=time.time(), duration=timeline['duration'],
                         audio=prefix + 'voice.wav', script=prefix + 'script.txt',
                         captions=prefix + 'captions.srt', character=prefix + 'character.png',
                         bundle=prefix + 'materials.zip')
        return _finish(identity, operation, dict(materials=materials, source=None, job_id=None,
                                                status='materials_ready'))
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        _finish(identity, operation, error=str(exc))
        raise


def import_video(identity, revision, stream, size, filename):
    with LOCK:
        project = _current(identity, revision)
        if project['method'] != 'web':
            raise ValueError('Importa il risultato nel progetto HeyGen dal sito.')
        project, operation = _claim(identity, revision, 'importing')
    imported = None
    try:
        imported = clips.import_stream(stream, size, filename)
        # Unknown external audio must not silently inherit the prepared subtitles.
        imported['materials_id'] = (project.get('materials') or {}).get('id')
        return _finish(identity, operation, dict(source=imported, job_id=None, status='video_imported'))
    except Exception as exc:
        if imported:
            shutil.rmtree(clips.recording_path(imported['id']).parent, ignore_errors=True)
        _finish(identity, operation, error=str(exc))
        raise


def asset_file(url):
    match = re.fullmatch(r'/video-project-assets/([a-f0-9]{12})/([a-f0-9]{12})/([a-z.]+)', url)
    if not match or match[3] not in ASSET_NAMES:
        return None
    with LOCK:
        try:
            project = _read(match[1])
        except ValueError:
            return None
        versions = [project, *project.get('history', [])]
        if not any((p.get('materials') or {}).get('id') == match[2] for p in versions):
            return None
        folder = project_folder(match[1]) / 'materials' / match[2]
        path = folder / match[3]
        base = (ROOT / 'data/video-projects').resolve()
        return path if (path.is_file() and not path.is_symlink() and path.resolve().parent == folder.resolve()
                        and path.resolve().is_relative_to(base)) else None


def _renderable(project):
    job = _job(project.get('job_id'))
    if job and job.get('state') in ('queued', 'running'):
        raise Conflict('Un video di questo progetto è già in produzione.')


def _attach(project, job):
    _archive(project)
    project.update(job_id=job['id'], status='rendering', error='',
                   revision=project['revision'] + 1, updated=time.time())
    _write(project)
    return public(project)


def render(data, enqueue):
    """Validate and enqueue atomically; enqueue must take the job lock second."""
    with LOCK:
        project = _current(data.get('id'), data.get('revision'))
        _renderable(project)
        project['source'] = _source(project)
        if not project.get('source'):
            raise ValueError('Importa prima il video da completare.')
        options = {key: data[key] for key in ('start', 'end', 'format', 'fit', 'position',
                   'burn_captions', 'source_captions_burned') if key in data}
        options.update(source_id=project['source']['source_id'], title=project['title'],
                       character_ids=[project['character_id']])
        clip = clips.prepare(options)
        if data.get('use_prepared_captions') is True:
            materials = project.get('materials')
            if not materials or project['source'].get('materials_id') != materials['id']:
                raise ValueError('Mancano i sottotitoli preparati per questa importazione.')
            _, source, _ = clips.source(clip['source_id'])
            if abs(source['duration'] - materials['duration']) > .25:
                raise ValueError('Il video ha una durata diversa dall’audio preparato. Importa un SRT sincronizzato nella sezione Clip e registrazioni.')
            timeline_path = project_folder(project['id']) / 'materials' / materials['id'] / 'timeline.json'
            timeline = json.loads(timeline_path.read_text(encoding='utf-8'))
            clip['captions'] = clips.trim_captions(timeline['captions'], clip['start'], clip['end'])
            clip['burn_captions'] = (data.get('burn_captions') is True and
                                     not clip['captions_burned'] and bool(clip['captions']))
        job = enqueue(project, clip)
        return {'project': _attach(project, job), 'job': job}


def enqueue_generation(identity, revision, method, enqueue):
    with LOCK:
        project = _current(identity, revision)
        _renderable(project)
        if project['method'] != method:
            raise ValueError('Il metodo di generazione non corrisponde al progetto salvato.')
        if len(project['script']) < 2:
            raise ValueError('Completa il copione prima di generare il video.')
        job = enqueue(copy.deepcopy(project))
        return {**job, 'video_project': _attach(project, job)}


def quote_generation(identity, revision, quote):
    """The slow local voice preview does not block unrelated project edits."""
    with LOCK:
        project = _current(identity, revision)
        _renderable(project)
        if project['method'] != 'api':
            raise ValueError('Scegli esplicitamente HeyGen API nel progetto.')
        snapshot = copy.deepcopy(project)
    result = quote(snapshot)
    with LOCK:
        _current(identity, revision)
    return result
