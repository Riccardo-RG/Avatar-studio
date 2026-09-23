"""Failure-path audit: isolated fixtures only, never real provider requests."""
import datetime as dt
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import publishing as pub
import service_connections as services
import social_adapters as adapters
import storage_upload as storage


class PublicationAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for module, key, value in [(pub, 'ROOT', self.root), (pub, 'PATH', self.root / 'publications.json'),
                                   (services, 'PATH', self.root / 'connections.json')]:
            guard = patch.object(module, key, value)
            guard.start()
            self.addCleanup(guard.stop)
        for module, key, value in [(services, 'VAULT', {}), (services, 'DISCONNECTED', set()),
                                   (services, 'OPERATIONS', set()), (storage, 'PLANS', {}),
                                   (storage, 'BUSY', set()), (pub, 'BUSY', set()), (pub, 'ARMED', False)]:
            guard = patch.object(module, key, value)
            guard.start()
            self.addCleanup(guard.stop)
        self.raw = b'audit-approved-video'
        self.media = self.root / 'output/publish-media/111111111111/instagram/video.mp4'
        self.media.parent.mkdir(parents=True)
        self.media.write_bytes(self.raw)
        guard = patch.object(pub, 'prepare_media', return_value=(self.media, {'duration': 5}, {'title': 'Audit', 'description': 'Test'}))
        guard.start()
        self.addCleanup(guard.stop)
        guard = patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
        guard.start()
        self.addCleanup(guard.stop)
        # A forgotten mock must fail before touching the network.
        guard = patch.object(services, 'http', side_effect=AssertionError('Unexpected network request'))
        self.http = guard.start()
        self.addCleanup(guard.stop)

    def instagram(self, processing=False):
        services.save({'service': 'instagram', 'account_id': '123456', 'access_token': 'fixture-token'})
        post = pub.save({'job_id': '1' * 12, 'platform': 'instagram', 'visibility': 'public',
                         'due_at': dt.datetime.fromtimestamp(time.time() + 600, dt.timezone.utc).isoformat()})
        pub.approve({'items': [{'id': post['id'], 'revision': post['revision']}]})
        if processing:
            pub.patch(post['id'], {'state': 'processing', 'attempted_at': time.time(), 'container_id': 'container123', 'stage': 'container'})
        return pub.find(pub.load(), post['id'])

    def check_with_interruption(self, interrupt):
        post = self.instagram(processing=True)
        pub.ARMED = True
        requests = []

        def remote(url, method='GET', *args, **kwargs):
            requests.append((url, method))
            if method == 'GET':
                interrupt(post)
                return {'status_code': 'FINISHED'}, {}, 200
            return {'id': 'published123'}, {}, 200

        self.http.side_effect = remote
        with patch.object(services, 'verify', return_value={'account_id': post['account_id']}):
            with self.assertRaises(ValueError):
                pub.check({'id': post['id']})
        self.assertFalse(any(method == 'POST' for _, method in requests))
        saved = pub.find(pub.load(), post['id'])
        self.assertNotEqual(saved.get('stage'), 'publish_requested')
        self.assertNotEqual(saved['state'], 'published')
        self.assertEqual(pub.BUSY, set())

    def test_instagram_disarm_while_polling_prevents_new_publish(self):
        self.check_with_interruption(lambda post: pub.set_armed({'enabled': False}))

    def test_instagram_cancel_while_polling_prevents_new_publish(self):
        self.check_with_interruption(lambda post: pub.cancel({'id': post['id']}))

    def test_instagram_shutdown_while_polling_prevents_new_publish(self):
        self.addCleanup(pub.STOP.clear)
        self.check_with_interruption(lambda post: pub.STOP.set())

    def test_manual_access_token_does_not_refresh_previous_identity(self):
        services.save({'service': 'youtube', 'client_id': 'client', 'access_token': 'old-access'})
        services.VAULT['youtube'].update(refresh_token='old-refresh', expires_at=0)
        services.save({'service': 'youtube', 'access_token': 'new-manual-access'})
        self.assertEqual(services.token('youtube'), 'new-manual-access')
        self.http.assert_not_called()
        self.assertNotIn('expires_at', services.VAULT['youtube'])
        self.assertFalse(services.secret('youtube', 'refresh_token'))

    def test_explicit_new_refresh_token_is_preserved_with_manual_access(self):
        services.save({'service': 'youtube', 'client_id': 'client', 'access_token': 'old-access'})
        services.VAULT['youtube'].update(refresh_token='old-refresh', expires_at=0)
        services.save({'service': 'youtube', 'access_token': 'new-access', 'refresh_token': 'new-refresh'})
        self.assertEqual(services.token('youtube'), 'new-access')
        self.assertEqual(services.secret('youtube', 'refresh_token'), 'new-refresh')
        self.http.assert_not_called()

    def test_manual_replacement_cannot_inherit_environment_refresh_token(self):
        with patch.dict(os.environ, {'AVATAR_YOUTUBE_REFRESH_TOKEN': 'old-environment-refresh'}):
            services.save({'service': 'youtube', 'access_token': 'new-manual-access'})
            self.assertEqual(services.secret('youtube', 'refresh_token'), '')
            self.assertEqual(services.token('youtube'), 'new-manual-access')
        self.http.assert_not_called()

    def test_uncertain_instagram_publish_is_never_repeated_by_state_check(self):
        post = self.instagram(processing=True)
        pub.ARMED = True
        writes = []

        def remote(url, method='GET', *args, **kwargs):
            if method == 'GET':
                return {'status_code': 'FINISHED'}, {}, 200
            writes.append(url)
            self.assertEqual(pub.find(pub.load(), post['id'])['stage'], 'publish_requested')
            raise services.RemoteError('Simulated lost response')

        self.http.side_effect = remote
        with patch.object(services, 'verify', return_value={'account_id': post['account_id']}):
            with self.assertRaises(services.RemoteError):
                pub.check({'id': post['id']})
            pub.check({'id': post['id']})
        self.assertEqual(len(writes), 1)
        self.assertNotEqual(pub.find(pub.load(), post['id'])['state'], 'published')

    def test_tiktok_multiple_posts_cannot_report_arbitrary_first_post_metrics(self):
        post = {'platform': 'tiktok', 'remote_id': 'inbox123', 'post_ids': ['111', '222']}
        self.http.side_effect = None
        self.http.return_value = ({'data': {'videos': [{'id': '222', 'view_count': 99}, {'id': '111', 'view_count': 5}]}}, {}, 200)
        with patch.object(services, 'auth', return_value={}):
            with self.assertRaisesRegex(ValueError, 'più post'):
                adapters.metrics(post)
        self.http.assert_not_called()

    def test_tiktok_numeric_status_ids_are_queried_as_strings_and_matched(self):
        post = {'platform': 'tiktok', 'post_ids': [12345]}
        self.http.side_effect = None
        self.http.return_value = ({'data': {'videos': [{'id': 'other', 'view_count': 999}, {'id': '12345', 'view_count': 5}]}}, {}, 200)
        with patch.object(services, 'auth', return_value={}):
            result = adapters.metrics(post)
        self.assertEqual(self.http.call_args.args[2]['filters']['video_ids'], ['12345'])
        self.assertEqual(result['values']['views'], 5)

    def test_youtube_private_restriction_is_explained_as_actual_visibility(self):
        post = {'platform': 'youtube', 'remote_id': 'video123', 'visibility': 'public'}
        self.http.side_effect = None
        self.http.return_value = ({'items': [{'status': {'uploadStatus': 'processed', 'privacyStatus': 'private'}}]}, {}, 200)
        with patch.object(services, 'auth', return_value={}):
            result = adapters.reconcile(post, lambda fields: None)
        self.assertEqual(result['actual_visibility'], 'private')
        self.assertIn('Visibilità effettiva: privato', result['message'])
        self.assertIn('richiesto pubblico', result['message'])

    def test_storage_credentials_cannot_change_during_verified_upload(self):
        post = self.instagram()
        services.save({'service': 'r2', 'r2_account_id': 'a' * 32, 'bucket': 'audit-media',
                       'public_base': 'https://media.example.com', 'access_key_id': 'old-key', 'secret_access_key': 'old-secret'})
        quote = storage.plan({'id': post['id']})
        s3 = Mock()
        s3.head_object.return_value = {'Metadata': {'sha256': post['media_sha256']}, 'ContentLength': len(self.raw)}

        def make_client(config):
            with self.assertRaisesRegex(ValueError, 'in uso'):
                services.save({'service': 'r2', 'secret_access_key': 'replacement'})
            with self.assertRaisesRegex(ValueError, 'in uso'):
                services.disconnect('r2')
            self.assertEqual(services.secret('r2', 'secret_access_key'), 'old-secret')
            return s3

        with patch.object(storage, 'client', side_effect=make_client), patch.object(storage, 'read_public', return_value=(self.raw, {}, '')):
            result = storage.upload({'plan_id': quote['id'], 'confirmed': True})
        self.assertTrue(result['reused'])
        self.assertEqual(services.OPERATIONS, set())

    def test_storage_object_created_after_head_is_not_overwritten(self):
        post = self.instagram()
        services.save({'service': 'r2', 'r2_account_id': 'a' * 32, 'bucket': 'audit-media',
                       'public_base': 'https://media.example.com', 'access_key_id': 'key', 'secret_access_key': 'secret'})
        quote = storage.plan({'id': post['id']})
        s3 = Mock()
        missing = Exception('Absent at HEAD')
        missing.response = {'Error': {'Code': '404'}}
        s3.head_object.side_effect = missing
        remote_bytes = b'concurrently-created-object'

        def put(**kwargs):
            nonlocal remote_bytes
            if kwargs.get('IfNoneMatch') == '*':
                conflict = Exception('Precondition failed: object now exists')
                conflict.response = {'Error': {'Code': 'PreconditionFailed'}}
                raise conflict
            remote_bytes = kwargs['Body'].read()

        s3.put_object.side_effect = put
        with patch.object(storage, 'client', return_value=s3), patch.object(storage, 'read_public') as public_read:
            with self.assertRaisesRegex(ValueError, 'incerto'):
                storage.upload({'plan_id': quote['id'], 'confirmed': True})
        self.assertEqual(remote_bytes, b'concurrently-created-object')
        self.assertEqual(pub.find(pub.load(), post['id'])['source_url'], '')
        self.assertEqual(s3.put_object.call_count, 1)
        public_read.assert_not_called()
        self.assertEqual(services.OPERATIONS, set())


if __name__ == '__main__':
    unittest.main()
