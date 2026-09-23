"""Regression cases found in the pre-user-test audit; no external requests."""
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import agent_team
import cloud_avatar
import platform_store
import providers
import render_process
import studio


class AuditRenderTests(unittest.TestCase):
    def test_deadline_closes_stdout_held_by_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);time.sleep(30)"
            before=time.monotonic()
            with self.assertRaisesRegex(ValueError, 'tempo massimo'):
                render_process.run([sys.executable, '-c', code], Path(tmp), os.environ.copy(),
                                   lambda _: None, lambda _: None, timeout=.3)
            self.assertLess(time.monotonic()-before, 3)

    def test_occupied_port_fails_before_loading_workspace_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Only app.py is present: the old import-first order fails on media,
            # while a safe second launch exits before importing application state.
            entry=Path(tmp)/'app.py'
            entry.write_text((Path(__file__).parent/'app.py').read_text())
            code="from unittest.mock import patch;import runpy;\nwith patch('http.server.ThreadingHTTPServer',side_effect=OSError('busy')):runpy.run_path('app.py',run_name='__main__')"
            result=subprocess.run([sys.executable,'-c',code],cwd=tmp,capture_output=True,text=True,timeout=5)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('porta già occupata',result.stderr)
            self.assertNotIn('ModuleNotFoundError',result.stderr)
            self.assertFalse((Path(tmp)/'data').exists())

    def test_cloud_poll_deadline_counts_time_spent_in_remote_requests(self):
        now = [0]
        def request(*args, **kwargs):
            now[0] += 301
            return {'status': 'waiting'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(cloud_avatar.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(cloud_avatar.time, 'sleep', side_effect=lambda n: now.__setitem__(0,now[0]+n)), \
             patch.object(cloud_avatar, 'request', side_effect=request) as remote:
            with self.assertRaisesRegex(ValueError, '15 minuti'):
                cloud_avatar.wait_video('existing123', Path(tmp), lambda: False, lambda *args: None)
            self.assertEqual(remote.call_count, 3)
            self.assertTrue(all(c.args[0]=='/videos/existing123' for c in remote.call_args_list))

    def test_large_stderr_cannot_block_progress_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            progress = []
            children = []
            code = ("import sys,pathlib;sys.stderr.write('E'*2000000);"
                    "sys.stderr.flush();print('PROGRESS 1',flush=True);"
                    "pathlib.Path(sys.argv[1]).write_bytes(b'test')")
            render_process.run([sys.executable, '-c', code, str(folder/'video.mp4')],
                               folder, os.environ.copy(), children.append, progress.append, timeout=5)
            self.assertEqual(progress, [1.0])
            self.assertEqual(children[0].returncode, 0)
            self.assertEqual((folder/'render-error.log').stat().st_size, 2000000)

    def test_callback_cancellation_waits_for_child_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            children = []
            def cancelled(_):
                raise ValueError('Produzione annullata.')
            with self.assertRaisesRegex(ValueError, 'annullata'):
                render_process.run([sys.executable, '-c', "import time;print('PROGRESS 0',flush=True);time.sleep(30)"],
                    Path(tmp), os.environ.copy(), children.append, cancelled, timeout=5)
            self.assertIsNotNone(children[0].returncode)

    def test_nonresponsive_renderer_has_finite_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            children = []
            with self.assertRaisesRegex(ValueError, 'tempo massimo'):
                render_process.run([sys.executable, '-c', 'import time;time.sleep(30)'],
                    Path(tmp), os.environ.copy(), children.append, lambda _: None, timeout=.1)
            self.assertIsNotNone(children[0].returncode)


class AuditCharacterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        catalog = [{'id': 'Alice', 'language': 'it'}, {'id': 'Samantha', 'language': 'en'},
                   {'id': 'Mónica', 'language': 'es'}, {'id': 'piper:paola', 'language': 'it'}]
        for obj, name, value in [(platform_store, 'PATH', self.root/'platform.json'),
                                 (studio, 'PATH', self.root/'studio.json'),
                                 (providers, 'DATA', self.root)]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch('media.voice_catalog', return_value=catalog)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_clearing_foreign_voice_restores_automatic_selection(self):
        c = platform_store.snapshot('lumo')
        voices = ['Alice', 'piper:paola', 'Samantha', 'Mónica']
        c = platform_store.save_character({**c, 'voice_en': 'Samantha', 'voice_es': 'Mónica'}, voices)
        c = platform_store.save_character({**c, 'voice_en': ''}, voices)
        self.assertNotIn('en', c['voices_by_language'])
        self.assertEqual(c['voices_by_language']['es'], 'Mónica')
        self.assertNotIn('en', platform_store.snapshot('lumo')['voices_by_language'])

    def test_reviewed_draft_keeps_original_character_after_campaign_edit(self):
        campaign = platform_store.save_campaign({'name': 'Demo', 'topic': 'Idee', 'audience': 'Adulti',
            'objective': 'Spiegare', 'character_id': 'lumo', 'language': 'en'})
        item = {'id': 'draft', 'title': 'Idea', 'script': 'One useful idea.', 'status': 'reviewed',
                'character_id': 'lumo', 'language': 'en'}
        platform_store.change_campaign(campaign['id'], lambda c: c['contents'].append(item))
        platform_store.save_campaign({**campaign, 'character_id': 'nova', 'language': 'it'})
        result = agent_team.to_plan({'campaign_id': campaign['id'], 'content_id': 'draft'})
        episode = next(e for e in studio.load()['episodes'] if e['id'] == result['episode_id'])
        self.assertEqual(episode['character_id'], 'lumo')
        self.assertEqual(episode['language'], 'en')
        self.assertEqual(result['character_id'], 'lumo')


class AuditRenderCompletionTests(unittest.TestCase):
    def render_at_completion(self, cancel):
        # Importing app starts runtime services. Compile only the two real
        # functions under review and supply isolated media/filesystem fixtures.
        import ast
        import threading
        import traceback
        from types import SimpleNamespace
        source = ast.parse((Path(__file__).parent/'app.py').read_text())
        functions = [node for node in source.body
                     if isinstance(node, ast.FunctionDef) and node.name in ('render_job', 'update_job')]
        self.assertEqual(len(functions), 2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root/'audit'
            folder.mkdir()
            (folder/'video.mp4').write_bytes(b'completed-local-fixture')
            persisted = []
            env = {
                'OUTPUT': root, 'JOB_LOCK': threading.RLock(), 'LIVE': None,
                'wait_for_live': lambda *args: None,
                'persist_job': lambda job: persisted.append(dict(job)),
                'traceback': traceback,
                'clips': SimpleNamespace(render=lambda *args: {'duration': 1}),
                'packages': SimpleNamespace(make_packages=lambda *args: {}),
                'studio': SimpleNamespace(finish_episode=lambda *args: None),
            }
            exec(compile(ast.Module(body=functions, type_ignores=[]), 'isolated-render-completion', 'exec'), env)
            original_update = env['update_job']

            def update_and_interrupt(job, percent, message):
                original_update(job, percent, message)
                if percent == 100 and cancel:
                    # Simulate /api/cancel after the last progress write, before
                    # the worker enters its final state transition lock.
                    with env['JOB_LOCK']:
                        self.assertEqual(job['state'], 'running')
                        job['cancelled'] = True

            env['update_job'] = update_and_interrupt
            job = {'id': 'audit', 'state': 'queued', 'title': 'Fixture', 'clip': {'source': 'mock'}}
            env['render_job'](job, '', {})
            return dict(job), (folder/'video.mp4').exists(), persisted[-1]

    def test_cancel_after_last_progress_is_not_overwritten_by_done(self):
        job, exists, persisted = self.render_at_completion(cancel=True)
        self.assertTrue(job['cancelled'])
        self.assertEqual(job['state'], 'cancelled')
        self.assertEqual(persisted['state'], 'cancelled')
        self.assertFalse(exists)

    def test_finished_render_without_cancel_preserves_video_and_done(self):
        job, exists, persisted = self.render_at_completion(cancel=False)
        self.assertEqual(job['state'], 'done')
        self.assertEqual(persisted['state'], 'done')
        self.assertTrue(exists)


if __name__ == '__main__':
    unittest.main()
