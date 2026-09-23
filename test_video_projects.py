"""Project lineage, operation races and local HeyGen hand-off in disposable data."""
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

import clips
import export_m1
import platform_store
import providers
import video_projects as projects


class VideoProjectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.image = self.root / 'reference.png'
        self.image.write_bytes(b'original-character')
        character = copy.deepcopy(platform_store.fresh()['characters'][1])
        self.settings = {**providers.DEFAULTS, 'character': character, 'language': 'it', 'voice': 'Alice'}
        for module, name, value in [(projects, 'ROOT', self.root), (clips, 'ROOT', self.root),
                                    (providers, 'DATA', self.root / 'config')]:
            setting = patch.object(module, name, value)
            setting.start()
            self.addCleanup(setting.stop)
        reference = patch.object(platform_store, 'asset_file', return_value=self.image)
        reference.start()
        self.addCleanup(reference.stop)
        character_patch = patch.object(platform_store, 'snapshot', return_value=character)
        character_patch.start()
        self.addCleanup(character_patch.stop)
        self.timeline = {'duration': 3.0, 'captions': [{'start': .25, 'end': 2.7, 'text': 'Un copione locale.'}]}

    def data(self, **extra):
        return {'title': 'Un progetto', 'script': 'Un copione locale.', 'method': 'web', **extra}

    def save(self, **extra):
        return projects.save(self.data(**extra), self.settings)

    def synthesize(self, script, settings, folder, progress):
        (folder / 'voice.wav').write_bytes(b'local-audio')
        clips.write_srt(folder, self.timeline['captions'])
        return copy.deepcopy(self.timeline)

    def prepared(self):
        project = self.save()
        with patch.object(projects.media, 'synthesize', side_effect=self.synthesize):
            return projects.prepare(project['id'], project['revision'])

    def imported(self, project, duration=3):
        with patch.object(clips, 'probe', return_value={'duration': duration, 'audio': True, 'width': 320, 'height': 180}):
            return projects.import_video(project['id'], project['revision'], io.BytesIO(b'video'), 5, 'result.mp4')

    def enqueue(self, project, clip=None):
        folder = self.root / 'output' / ('b' * 12)
        folder.mkdir(parents=True, exist_ok=True)
        job = {'id': folder.name, 'title': project['title'], 'state': 'queued', 'created': 1}
        providers.atomic_json(folder / 'status.json', job)
        return job

    def render_data(self, project, **extra):
        return {'id': project['id'], 'revision': project['revision'], 'start': 0, 'end': 3,
                'format': 'portrait', 'fit': 'contain', 'burn_captions': True, **extra}

    def test_draft_roundtrip_preserves_editorial_and_snapshot_without_assets(self):
        result = self.save(topic='Un tema', rubric_id='umani', hook='Apertura', cta='Domanda',
                           duration_seconds=45, editor_format='story')
        self.assertEqual(result['revision'], 1)
        self.assertEqual(result['status'], 'draft')
        self.assertEqual(result['hook'], 'Apertura')
        self.assertEqual(result['duration_seconds'], 45)
        self.assertEqual(result['character_id'], 'ari')
        self.assertNotIn('settings', result)
        self.settings['voice'] = 'Modified'
        self.assertEqual(projects._read(result['id'])['settings']['voice'], 'Alice')
        self.assertEqual(projects.catalog()['projects'][0]['id'], result['id'])

    def test_revision_rejects_stale_save_and_boolean_revision(self):
        project = self.save()
        for revision in (0, True, '1'):
            with self.assertRaises(projects.Conflict):
                self.save(id=project['id'], revision=revision, script='Modificato.')
        same = self.save(id=project['id'], revision=1)
        self.assertEqual(same['revision'], 1)

    def test_prepare_copies_immutable_materials_and_only_exports_safe_files(self):
        project = self.prepared()
        self.assertEqual(project['revision'], 2)
        self.assertEqual(project['status'], 'materials_ready')
        self.assertEqual(project['materials']['duration'], 3)
        self.image.write_bytes(b'edited-character')
        self.assertEqual(projects.asset_file(project['materials']['character']).read_bytes(), b'original-character')
        with zipfile.ZipFile(projects.asset_file(project['materials']['bundle'])) as archive:
            self.assertEqual(set(archive.namelist()), {'voice.wav', 'script.txt', 'captions.srt', 'character.png'})
            self.assertEqual(archive.read('script.txt').decode(), 'Un copione locale.\n')
        prefix = project['materials']['audio'].rsplit('/', 1)[0]
        for name in ('snapshot.json', 'timeline.json', '../project.json', 'materials.zip/extra'):
            self.assertIsNone(projects.asset_file(prefix + '/' + name))
        self.assertIsNone(projects.asset_file('/video-project-assets/' + project['id'] + '/aaaaaaaaaaaa/voice.wav'))

    def test_prepare_error_keeps_previous_materials_and_allows_retry(self):
        project = self.prepared()
        with patch.object(projects.media, 'synthesize', side_effect=ValueError('Voce assente')):
            with self.assertRaisesRegex(ValueError, 'Voce assente'):
                projects.prepare(project['id'], project['revision'])
        current = projects.catalog()['projects'][0]
        self.assertEqual(current['materials'], project['materials'])
        self.assertNotIn('operation', current)
        self.assertEqual(current['revision'], project['revision'] + 1)
        self.assertEqual(current['error'], 'Voce assente')
        self.assertEqual(len(list((projects.project_folder(project['id']) / 'materials').iterdir())), 1)

    def test_edits_invalidate_active_lineage_but_keep_old_assets_and_history(self):
        prepared = self.prepared()
        imported = self.imported(prepared)
        updated = self.save(id=imported['id'], revision=imported['revision'], script='Una nuova bozza.')
        self.assertEqual(updated['status'], 'draft')
        self.assertIsNone(updated['materials'])
        self.assertIsNone(updated['source'])
        self.assertTrue(projects.asset_file(prepared['materials']['audio']).exists())
        self.assertEqual(updated['history'][-1]['source']['source_id'], imported['source']['source_id'])
        self.assertTrue(clips.source(imported['source']['source_id'])[0].exists())

    def test_import_keeps_external_audio_captions_unknown(self):
        prepared = self.prepared()
        imported = self.imported(prepared)
        self.assertEqual(imported['status'], 'video_imported')
        self.assertEqual(imported['source']['subtitle_count'], 0)
        self.assertEqual(imported['source']['materials_id'], prepared['materials']['id'])
        callback = Mock(side_effect=self.enqueue)
        result = projects.render(self.render_data(imported), callback)
        self.assertEqual(callback.call_args.args[1]['captions'], [])
        self.assertFalse(callback.call_args.args[1]['burn_captions'])
        self.assertEqual(result['project']['status'], 'rendering')

    def test_prepared_captions_require_explicit_confirmation_and_match_duration(self):
        imported = self.imported(self.prepared())
        callback = Mock(side_effect=self.enqueue)
        projects.render(self.render_data(imported, use_prepared_captions=True), callback)
        clip = callback.call_args.args[1]
        self.assertEqual(clip['captions'], self.timeline['captions'])
        self.assertTrue(clip['burn_captions'])

    def test_different_duration_does_not_reuse_prepared_captions(self):
        imported = self.imported(self.prepared(), duration=5)
        callback = Mock(side_effect=self.enqueue)
        with self.assertRaisesRegex(ValueError, 'durata diversa'):
            projects.render(self.render_data(imported, use_prepared_captions=True), callback)
        callback.assert_not_called()

    def test_existing_visible_captions_are_not_burned_twice(self):
        imported = self.imported(self.prepared())
        callback = Mock(side_effect=self.enqueue)
        projects.render(self.render_data(imported, use_prepared_captions=True, source_captions_burned=True), callback)
        self.assertFalse(callback.call_args.args[1]['burn_captions'])

    def test_stale_import_is_rejected_before_reading_stream(self):
        project = self.save()
        stream = Mock()
        with self.assertRaises(projects.Conflict):
            projects.import_video(project['id'], 0, stream, 5, 'video.mp4')
        stream.read.assert_not_called()

    def test_parallel_save_cannot_overtake_preparation(self):
        project = self.save()
        entered, release = threading.Event(), threading.Event()
        results = []
        def delayed(*args):
            entered.set()
            self.assertTrue(release.wait(5))
            return self.synthesize(*args)
        def prepare():
            try:
                results.append(projects.prepare(project['id'], project['revision']))
            except Exception as exc:
                results.append(exc)
        with patch.object(projects.media, 'synthesize', side_effect=delayed):
            thread = threading.Thread(target=prepare)
            thread.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(projects.catalog()['projects'][0]['status'], 'preparing')
                with self.assertRaises(projects.Conflict):
                    self.save(id=project['id'], revision=project['revision'], script='Altra bozza.')
            finally:
                release.set()
                thread.join(5)
        self.assertEqual(results[0]['status'], 'materials_ready')

    def test_startup_recovery_clears_busy_operation_and_increments_revision(self):
        project = self.save()
        projects._claim(project['id'], project['revision'], 'importing')
        projects.recover_interrupted()
        recovered = projects.catalog()['projects'][0]
        self.assertEqual(recovered['revision'], 2)
        self.assertEqual(recovered['status'], 'draft')
        self.assertIn('interrotta', recovered['error'])
        self.assertNotIn('operation', recovered)

    def test_job_completion_is_visible_after_restart_without_mutating_revision(self):
        project = self.save(method='local')
        result = projects.enqueue_generation(project['id'], project['revision'], 'local', self.enqueue)
        path = self.root / 'output' / result['id'] / 'status.json'
        providers.atomic_json(path, {**result, 'state': 'done', 'video': '/output/' + result['id'] + '/video.mp4'})
        providers.atomic_json(path.parent / 'project.json', {'duration': 3, 'captions': []})
        (path.parent / 'video.mp4').write_bytes(b'video')
        current = projects.catalog()['projects'][0]
        self.assertEqual(current['status'], 'ready')
        self.assertEqual(current['revision'], result['video_project']['revision'])
        self.assertEqual(current['job']['video'], '/output/' + result['id'] + '/video.mp4')

    def test_completed_local_video_becomes_editable_and_source_stays_on_original(self):
        project = self.save(method='local')
        result = projects.enqueue_generation(project['id'], project['revision'], 'local', self.enqueue)
        folder = self.root / 'output' / result['id']
        (folder / 'video.mp4').write_bytes(b'original-video')
        providers.atomic_json(folder / 'project.json', {'duration': 3, 'captions': self.timeline['captions'],
            'captions_burned': True, 'settings': self.settings})
        providers.atomic_json(folder / 'status.json', {**result, 'state': 'done'})
        current = projects.catalog()['projects'][0]
        self.assertEqual(current['source']['source_id'], 'job:' + result['id'])
        self.assertEqual(current['source']['subtitle_count'], 1)
        self.assertTrue(current['source']['captions_burned'])
        def enqueue_clip(project, clip):
            target = self.root / 'output' / ('c' * 12)
            target.mkdir()
            job = {'id': target.name, 'title': project['title'], 'state': 'queued', 'created': 2}
            providers.atomic_json(target / 'status.json', job)
            self.assertEqual(clip['source_id'], 'job:' + result['id'])
            self.assertFalse(clip['burn_captions'])
            return job
        exported = projects.render(self.render_data(current), enqueue_clip)
        self.assertEqual(exported['project']['source']['source_id'], 'job:' + result['id'])
        self.assertEqual(projects._read(project['id'])['source']['source_id'], 'job:' + result['id'])
        self.assertEqual(exported['project']['history'][-1]['job']['state'], 'done')

    def test_subtitles_added_in_clip_editor_become_available_in_project(self):
        imported = self.imported(self.prepared())
        self.assertEqual(imported['source']['subtitle_count'], 0)
        clips.subtitles({'id': imported['source']['id'],
            'text': '1\n00:00:00,250 --> 00:00:02,700\nUn SRT importato.\n'})
        current = projects.catalog()['projects'][0]
        self.assertEqual(current['source']['subtitle_count'], 1)
        callback = Mock(side_effect=self.enqueue)
        projects.render(self.render_data(current), callback)
        self.assertTrue(callback.call_args.args[1]['burn_captions'])
        self.assertEqual(callback.call_args.args[1]['captions'][0]['text'], 'Un SRT importato.')

    def test_stale_or_wrong_method_never_reaches_enqueue_or_quote(self):
        project = self.save(method='api')
        callback = Mock(side_effect=self.enqueue)
        for method, revision in (('api', 0), ('local', 1)):
            with self.assertRaises(ValueError):
                projects.enqueue_generation(project['id'], revision, method, callback)
        with self.assertRaises(projects.Conflict):
            projects.quote_generation(project['id'], 0, callback)
        callback.assert_not_called()

    def test_quote_uses_saved_settings_and_rejects_old_revision_before_consumption(self):
        project = self.save(method='api')
        quote = projects.quote_generation(project['id'], project['revision'], lambda p: p)
        self.assertEqual(quote['settings']['voice'], 'Alice')
        self.save(id=project['id'], revision=project['revision'], method='api', script='Testo modificato.')
        callback = Mock()
        with self.assertRaises(projects.Conflict):
            projects.enqueue_generation(quote['id'], quote['revision'], 'api', callback)
        callback.assert_not_called()

    def test_episode_provenance_deduplicates_new_project_creation(self):
        episode = {'id': 'a' * 12, 'revision': 4}
        first = self.save(episode=episode)
        second = self.save(episode=episode, title='Nuovo click')
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(projects.catalog()['projects']), 1)

    def test_running_job_cannot_be_enqueued_twice(self):
        project = self.save(method='local')
        first = projects.enqueue_generation(project['id'], 1, 'local', self.enqueue)
        callback = Mock()
        with self.assertRaises(projects.Conflict):
            projects.enqueue_generation(project['id'], first['video_project']['revision'], 'local', callback)
        callback.assert_not_called()

    def test_editorial_rename_keeps_imported_video_but_character_revision_invalidates(self):
        project = self.imported(self.prepared())
        renamed = self.save(id=project['id'], revision=project['revision'], title='Un titolo migliore', topic='Un tema')
        self.assertEqual(renamed['source'], project['source'])
        self.assertEqual(renamed['materials'], project['materials'])
        self.settings['character']['revision'] += 1
        self.settings['character']['image'] = '/characters/lumo.png'
        refreshed = self.save(id=renamed['id'], revision=renamed['revision'], title=renamed['title'], topic='Un tema')
        self.assertIsNone(refreshed['source'])
        self.assertIsNone(refreshed['materials'])
        self.assertEqual(refreshed['character']['revision'], self.settings['character']['revision'])
        self.assertEqual(refreshed['history'][-1]['source']['source_id'], project['source']['source_id'])

    def test_quote_synthesis_does_not_lock_other_projects_and_rechecks_revision(self):
        project = self.save(method='api')
        entered, release = threading.Event(), threading.Event()
        results = []
        def delayed(snapshot):
            entered.set()
            release.wait(5)
            return {'quote_id': 'prepared-locally'}
        def quote():
            try:
                results.append(projects.quote_generation(project['id'], project['revision'], delayed))
            except Exception as exc:
                results.append(exc)
        worker = threading.Thread(target=quote)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            modified = self.save(id=project['id'], revision=project['revision'], method='api', script='Un altro copione.')
            self.assertGreater(modified['revision'], project['revision'])
        finally:
            release.set()
            worker.join(5)
        self.assertIsInstance(results[0], projects.Conflict)

    def test_transfer_includes_project_history_and_materials_with_the_recording(self):
        prepared = self.prepared()
        imported = self.imported(prepared)
        self.save(id=imported['id'], revision=imported['revision'], script='Una versione diversa.')
        ignored = projects.project_folder(imported['id']) / 'private.bin'
        ignored.write_bytes(b'not a project asset')
        with patch.object(export_m1, 'ROOT', self.root):
            members = export_m1.members()
            self.assertIn(projects.project_folder(imported['id']) / 'project.json', members)
            self.assertIn(projects.asset_file(prepared['materials']['bundle']), members)
            self.assertIn(clips.source(imported['source']['source_id'])[0], members)
            self.assertNotIn(ignored, members)
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                for path in members:
                    export_m1.write_member(archive, path)
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            self.assertTrue(any(name.endswith('/materials.zip') for name in names))
            self.assertTrue(any(name.endswith('/source.mp4') for name in names))

    def test_material_download_rejects_symlink_to_unrelated_local_file(self):
        prepared = self.prepared()
        path = projects.asset_file(prepared['materials']['audio'])
        path.unlink()
        path.symlink_to(self.image)
        self.assertIsNone(projects.asset_file(prepared['materials']['audio']))

    def test_restart_recovers_enqueue_attachment_without_creating_another_job(self):
        project = self.save(method='local')
        job = self.enqueue(project)
        job.update(video_project_id=project['id'], video_project_revision=project['revision'])
        providers.atomic_json(self.root / 'output' / job['id'] / 'status.json', job)
        projects.recover_interrupted()
        recovered = projects.catalog()['projects'][0]
        self.assertEqual(recovered['job_id'], job['id'])
        self.assertEqual(recovered['revision'], 2)
        self.assertEqual(recovered['status'], 'rendering')
        projects.recover_interrupted()
        self.assertEqual(projects.catalog()['projects'][0]['revision'], 2)


if __name__ == '__main__':
    unittest.main()
