"""Exercise the real HTTP handler without starting unrelated studio workers."""
import ast
import copy
import http.client
from http.server import SimpleHTTPRequestHandler
import io
import json
import mimetypes
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import unquote, urlparse

import clips
import cloud_avatar
import platform_store
import providers
import video_projects


class VideoProjectHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'static').mkdir()
        (self.root / 'output').mkdir()
        character = copy.deepcopy(platform_store.fresh()['characters'][1])
        self.settings = {**providers.DEFAULTS, 'character': character, 'language': 'it', 'voice': 'Alice'}
        for module, name, value in ((video_projects, 'ROOT', self.root), (clips, 'ROOT', self.root),
                                    (cloud_avatar, 'QUOTES', {})):
            target = patch.object(module, name, value)
            target.start()
            self.addCleanup(target.stop)
        self.jobs = []
        self.enqueue = Mock(side_effect=self._enqueue)
        # Compile the unchanged handler class from app.py. Importing app starts
        # unrelated live workers and touches its real workspace at module scope.
        tree = ast.parse((Path(__file__).parent / 'app.py').read_text(encoding='utf-8'))
        handler = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == 'Handler')
        namespace = dict(SimpleHTTPRequestHandler=SimpleHTTPRequestHandler, ROOT=self.root,
            OUTPUT=self.root / 'output', TOKEN='local-test-token', clips=clips, video_projects=video_projects,
            cloud_avatar=cloud_avatar, json=json, mimetypes=mimetypes, re=re, subprocess=subprocess,
            traceback=traceback, urlparse=urlparse, unquote=unquote, IMPORT_SLOTS=threading.BoundedSemaphore(2),
            JOB_LOCK=threading.RLock(), video_settings=lambda data: copy.deepcopy(self.settings),
            check_capacity=lambda count: None, enqueue=self.enqueue,
            public_job=lambda job: {key: value for key, value in job.items() if key != 'cloud_quote'})
        for name in ('growth', 'policy_intelligence', 'market_research', 'publishing',
                     'service_connections', 'broadcast', 'conversation_bridge'):
            namespace[name] = Mock(name=name)
        exec(compile(ast.Module(body=[handler], type_ignores=[]), 'app.py', 'exec'), namespace)
        self.handler_class = namespace['Handler']
        self.handler_class.log_message = lambda *args: None

    def _enqueue(self, title, script, config, **snapshots):
        identity = f'{len(self.jobs) + 1:012x}'
        job = dict(id=identity, title=title, state='queued', created=1, **snapshots)
        folder = self.root / 'output' / identity
        folder.mkdir()
        providers.atomic_json(folder / 'status.json', {key: value for key, value in job.items() if key != 'cloud_quote'})
        self.jobs.append({'job': job, 'script': script, 'config': config})
        return job

    def request(self, method, path, payload=None, headers=None, authenticated=True):
        fields = {'Host': '127.0.0.1:8765'}
        if authenticated:
            fields['X-Avatar-Token'] = 'local-test-token'
        body = json.dumps(payload).encode() if isinstance(payload, dict) else payload
        if body is not None:
            fields['Content-Length'] = str(len(body))
        fields.update(headers or {})
        raw = (f'{method} {path} HTTP/1.0\r\n' + ''.join(f'{key}: {value}\r\n' for key, value in fields.items()) + '\r\n').encode() + (body or b'')
        output = io.BytesIO()
        # In-memory transport still exercises BaseHTTPRequestHandler parsing,
        # framing, headers and the real route code without opening a TCP port.
        connection = SimpleNamespace(makefile=lambda *args: io.BytesIO(raw),
                                     sendall=output.write, settimeout=lambda seconds: None)
        self.handler_class(connection, ('127.0.0.1', 8766), SimpleNamespace(server_port=8765))
        response = http.client.HTTPResponse(SimpleNamespace(makefile=lambda *args: io.BytesIO(output.getvalue())))
        response.begin()
        content = response.read()
        return response.status, json.loads(content) if response.getheader('Content-Type', '').startswith('application/json') else content

    def save(self, method='web'):
        code, project = self.request('POST', '/api/video-project',
            {'title': 'HTTP project', 'script': 'Un copione salvato.', 'method': method})
        self.assertEqual(code, 200, project)
        return project

    def test_write_requires_session_token_and_valid_host(self):
        for headers, authenticated in (({}, False), ({'X-Avatar-Token': 'wrong'}, True), ({'Host': 'remote.example'}, True)):
            code, _ = self.request('POST', '/api/video-project', {'title': 'No'}, headers, authenticated)
            self.assertEqual(code, 403)
        self.assertEqual(video_projects.catalog()['projects'], [])

    def test_json_shape_and_stale_revision_fail_without_overwrite(self):
        project = self.save()
        code, _ = self.request('POST', '/api/video-project', b'[]')
        self.assertEqual(code, 400)
        code, _ = self.request('POST', '/api/video-project',
            {'id': project['id'], 'revision': 0, 'title': 'Wrong', 'script': 'Old change', 'method': 'web'})
        self.assertEqual(code, 409)
        code, result = self.request('GET', '/api/video-projects')
        self.assertEqual(code, 200)
        self.assertEqual(result['projects'][0]['title'], project['title'])

    def test_binary_upload_checks_project_headers_before_importing(self):
        project = self.save()
        headers = {'X-Project-ID': project['id'], 'X-Recording-Name': 'returned.mp4'}
        with patch.object(clips, 'import_stream') as upload:
            code, _ = self.request('POST', '/api/video-project-import', b'media', headers)
            self.assertEqual(code, 400)
            code, _ = self.request('POST', '/api/video-project-import', b'media', {**headers, 'X-Project-Revision': '0'})
            self.assertEqual(code, 409)
            upload.assert_not_called()
        with patch.object(clips, 'probe', return_value={'duration': 3, 'audio': True, 'width': 320, 'height': 180}):
            code, imported = self.request('POST', '/api/video-project-import', b'media',
                {**headers, 'X-Project-Revision': str(project['revision'])})
        self.assertEqual(code, 201, imported)
        self.assertEqual(imported['source']['subtitle_count'], 0)
        self.assertEqual(imported['status'], 'video_imported')

    def test_asset_endpoint_serves_only_registered_material_names(self):
        project = self.save()
        image = self.root / 'image.png'
        image.write_bytes(b'reference')
        def synthesize(script, settings, folder, progress):
            (folder / 'voice.wav').write_bytes(b'audio')
            clips.write_srt(folder, [{'start': 0, 'end': 2, 'text': script}])
            return {'duration': 3, 'captions': []}
        with patch.object(platform_store, 'asset_file', return_value=image), patch.object(video_projects.media, 'synthesize', side_effect=synthesize):
            code, prepared = self.request('POST', '/api/video-project-prepare', {'id': project['id'], 'revision': project['revision']})
        self.assertEqual(code, 200, prepared)
        code, audio = self.request('GET', prepared['materials']['audio'])
        self.assertEqual((code, audio), (200, b'audio'))
        for file in ('snapshot.json', 'timeline.json', '../project.json'):
            prefix = prepared['materials']['audio'].rsplit('/', 1)[0]
            code, _ = self.request('GET', prefix + '/' + file)
            self.assertEqual(code, 404)

    def test_local_generation_uses_saved_snapshot_and_attaches_job(self):
        project = self.save('local')
        code, result = self.request('POST', '/api/render', {'video_project_id': project['id'],
            'video_project_revision': project['revision'], 'script': 'Unsaved injected script'})
        self.assertEqual(code, 202, result)
        self.assertEqual(self.jobs[0]['script'], project['script'])
        self.assertEqual(self.jobs[0]['config']['voice'], 'Alice')
        self.assertEqual(result['video_project']['job_id'], result['id'])
        self.assertEqual(result['video_project_id'], project['id'])
        code, _ = self.request('POST', '/api/render', {'video_project_id': project['id'], 'video_project_revision': project['revision']})
        self.assertEqual(code, 409)
        self.assertEqual(len(self.jobs), 1)

    def quote(self, project):
        def make_quote(data, config=None):
            cloud_avatar.QUOTES['quote-local'] = {'id': 'quote-local', 'title': data['title'],
                'script': data['script'], 'config': config, 'expires': 9_999_999_999}
            return {'quote_id': 'quote-local', 'duration': 3, 'estimated_eur': 1}
        with patch.object(cloud_avatar, 'quote', side_effect=make_quote):
            code, quote = self.request('POST', '/api/cloud-quote', {'video_project_id': project['id'],
                'video_project_revision': project['revision']})
        self.assertEqual(code, 200, quote)
        return quote

    def test_api_quote_binds_project_and_stale_render_never_consumes_credit(self):
        project = self.save('api')
        quote = self.quote(project)
        self.assertEqual(cloud_avatar.QUOTES[quote['quote_id']]['video_project_id'], project['id'])
        self.assertEqual(cloud_avatar.QUOTES[quote['quote_id']]['config']['voice'], 'Alice')
        code, edited = self.request('POST', '/api/video-project',
            {**project, 'script': 'Una nuova versione.'})
        self.assertEqual(code, 200, edited)
        with patch.object(cloud_avatar, 'consume') as consume:
            code, _ = self.request('POST', '/api/cloud-render', {'quote_id': quote['quote_id']})
        self.assertEqual(code, 409)
        consume.assert_not_called()
        self.enqueue.assert_not_called()

    def test_api_approved_quote_enqueues_exact_saved_project_once(self):
        project = self.save('api')
        quote = self.quote(project)
        with patch.object(cloud_avatar, 'consume', side_effect=lambda identity: cloud_avatar.QUOTES.pop(identity)) as consume:
            code, result = self.request('POST', '/api/cloud-render', {'quote_id': quote['quote_id']})
        self.assertEqual(code, 202, result)
        consume.assert_called_once_with(quote['quote_id'])
        self.assertEqual(result['video_project']['id'], project['id'])
        self.assertEqual(result['video_project']['job_id'], result['id'])
        self.assertEqual(self.jobs[0]['script'], project['script'])
        self.assertEqual(self.jobs[0]['job']['engine'], 'heygen')


if __name__ == '__main__':
    unittest.main()
