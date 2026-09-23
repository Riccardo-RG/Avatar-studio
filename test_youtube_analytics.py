"""YouTube Analytics contract checks: mocked HTTP only, no real channel access."""
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import publishing
import service_connections as services
import youtube_analytics as analytics


def table(values, order=None):
    names = order or list(values)
    return {'kind': 'youtubeAnalytics#resultTable',
            'columnHeaders': [{'name': name, 'columnType': 'METRIC', 'dataType': 'FLOAT'} for name in names],
            'rows': [[values[name] for name in names]]}


class YouTubeAnalyticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for module, key, value in [(publishing, 'PATH', self.root / 'publications.json'),
                                   (services, 'PATH', self.root / 'connections.json'),
                                   (services, 'VAULT', {'youtube:profileA': {'access_token': 'test-only-token-A'}}),
                                   (services, 'DISCONNECTED', set()), (services, 'OPERATIONS', set()),
                                   (services, 'BOUND', ContextVar('analytics-test-profile', default=None))]:
            p = patch.object(module, key, value); p.start(); self.addCleanup(p.stop)
        p = patch.object(analytics, '_today', return_value=dt.date(2026, 9, 20))
        p.start(); self.addCleanup(p.stop)
        self.post = {'id': '012345abcdef', 'revision': 3, 'platform': 'youtube', 'state': 'published',
                     'connection_id': 'profileA', 'account_id': 'UCchannelAAAA', 'remote_id': 'dQw4w9WgXcQ',
                     'language': 'it', 'url': 'https://untrusted.example/ignored'}
        self.write_post()
        self.connections = {'version': 2, 'youtube': {'active_profile': 'other', 'profiles': [
            {'id': 'profileA', 'nickname': 'Canale A', 'revision': 7, 'account_id': self.post['account_id'], 'verified': 1},
            {'id': 'other', 'nickname': 'Altro canale', 'revision': 2, 'account_id': 'UCchannelBBBB'}]}}
        self.write_connections()
        self.request = {'publication_id': self.post['id'], 'start_date': '2026-09-01', 'end_date': '2026-09-15'}
        self.basic = table({'views': 100, 'averageViewPercentage': 72.5, 'subscribersGained': 2,
                            'estimatedMinutesWatched': 25.5, 'engagedViews': 80, 'averageViewDuration': 19.125})
        self.money = table({'estimatedRevenue': 1.25})
        self.calls = []
        p = patch.object(services, 'http', side_effect=self.http)
        self.http_mock = p.start(); self.addCleanup(p.stop)
        p = patch.object(publishing, 'write')
        self.publication_write = p.start(); self.addCleanup(p.stop)

    def write_post(self):
        publishing.PATH.write_text(json.dumps({'version': 2, 'items': [self.post], 'events': []}))

    def write_connections(self):
        services.PATH.write_text(json.dumps(self.connections))

    def http(self, url, method='GET', body=None, headers=None, **kwargs):
        self.calls.append({'url': url, 'method': method, 'body': body, 'headers': headers})
        self.assertEqual(method, 'GET'); self.assertIsNone(body)
        self.assertEqual(headers, {'Authorization': 'Bearer test-only-token-A'})
        parsed = urlsplit(url)
        if parsed.hostname == 'www.googleapis.com':
            self.assertEqual(parsed.path, '/youtube/v3/channels')
            return {'items': [{'id': self.post['account_id'], 'snippet': {'title': 'Canale A'}}]}, {}, 200
        self.assertEqual(parsed.hostname, 'youtubeanalytics.googleapis.com')
        self.assertEqual(parsed.path, '/v2/reports')
        self.assertEqual(services.BOUND.get(), ('youtube', 'profileA'))
        self.assertIn('youtube:profileA', services.OPERATIONS)
        query = parse_qs(parsed.query)
        self.assertEqual(query['ids'], ['channel==MINE'])
        self.assertEqual(query['filters'], ['video==' + self.post['remote_id']])
        self.assertNotIn('dimensions', query)
        payload = self.money if query['metrics'] == ['estimatedRevenue'] else self.basic
        if isinstance(payload, Exception):
            raise payload
        return copy.deepcopy(payload), {}, 200

    def test_reads_exact_saved_profile_and_maps_headers_without_index_assumptions(self):
        before = publishing.PATH.read_bytes()
        result = analytics.fetch_report(self.request)
        self.assertEqual(result['profile_id'], 'profileA')
        self.assertEqual(result['channel_id'], self.post['account_id'])
        self.assertEqual(result['metrics'], {'views': 100, 'engaged_views': 80,
            'estimated_minutes_watched': 25.5, 'average_view_duration_seconds': 19.125,
            'average_view_percentage': 72.5, 'subscribers_gained': 2, 'estimated_revenue_eur': None})
        self.assertEqual(result['data_status'], 'available')
        self.assertEqual(result['monetary_status'], 'not_requested')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result['source_url'], 'https://www.youtube.com/watch?v=' + self.post['remote_id'])
        self.assertNotIn('test-only-token', json.dumps(result))
        self.publication_write.assert_not_called(); self.assertEqual(before, publishing.PATH.read_bytes())
        self.assertFalse(services.OPERATIONS); self.assertIsNone(services.BOUND.get())

    def test_calendar_period_is_explicit_and_not_a_growth_window(self):
        result = analytics.fetch_report(self.request)
        self.assertEqual(result['period']['timezone'], 'America/Los_Angeles')
        self.assertEqual(result['period']['start_date'], self.request['start_date'])
        self.assertEqual(result['period']['end_date'], self.request['end_date'])
        self.assertIn('23 o 25', result['period']['note'])
        self.assertIn('24 ore', result['limitations'][0])
        self.assertNotIn('window', result)
        self.assertNotIn('rpm', result['metrics'])

    def test_revenue_is_an_opt_in_separate_query_in_eur_and_zero_is_valid(self):
        self.money = table({'estimatedRevenue': 0})
        result = analytics.fetch_report({**self.request, 'include_revenue': True})
        self.assertEqual(result['monetary_status'], 'available')
        self.assertEqual(result['metrics']['estimated_revenue_eur'], 0)
        self.assertEqual(len(self.calls), 3)
        base_query = parse_qs(urlsplit(self.calls[1]['url']).query)
        money_query = parse_qs(urlsplit(self.calls[2]['url']).query)
        self.assertNotIn('currency', base_query)
        self.assertEqual(money_query['currency'], ['EUR'])
        self.assertEqual(money_query['metrics'], ['estimatedRevenue'])
        self.assertEqual(money_query['startDate'], [self.request['start_date']])
        self.assertEqual(money_query['endDate'], [self.request['end_date']])

    def test_no_rows_omitted_or_empty_never_become_zero(self):
        self.money.pop('rows')
        for rows in (None, []):
            with self.subTest(rows=rows):
                self.basic.pop('rows', None)
                if rows is not None:
                    self.basic['rows'] = rows
                result = analytics.fetch_report({**self.request, 'include_revenue': True})
                self.assertEqual(result['data_status'], 'no_data')
                self.assertEqual(result['monetary_status'], 'no_data')
                self.assertTrue(all(value is None for value in result['metrics'].values()))

    def test_missing_or_bad_metrics_remain_null_but_real_zero_is_preserved(self):
        self.basic = table({'views': 0, 'engagedViews': None, 'subscribersGained': True,
                            'averageViewDuration': float('nan'), 'averageViewPercentage': '145.5'})
        result = analytics.fetch_report(self.request)
        self.assertEqual(result['data_status'], 'partial')
        self.assertEqual(result['metrics']['views'], 0)
        self.assertEqual(result['metrics']['average_view_percentage'], 145.5)
        for key in ('engaged_views', 'subscribers_gained', 'average_view_duration_seconds', 'estimated_minutes_watched'):
            self.assertIsNone(result['metrics'][key])

    def test_invalid_or_non_aggregate_tables_are_rejected(self):
        for payload in (None, {'rows': None}, {'rows': [[1]], 'columnHeaders': []},
                        {'columnHeaders': [{'name': 'views', 'columnType': 'METRIC'}], 'rows': [[1], [2]]},
                        {'columnHeaders': [{'name': 'views', 'columnType': 'METRIC'}] * 2, 'rows': [[1, 2]]},
                        {'columnHeaders': [{'name': 'day', 'columnType': 'DIMENSION'}], 'rows': [['2026-09-01']]},
                        {'columnHeaders': [{'name': 'views', 'columnType': 'METRIC'}], 'rows': [[1, 2]]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                analytics.parse_report(payload, analytics.BASIC_METRICS)

    def test_basic_permission_failure_is_an_error_not_an_empty_success(self):
        self.basic = services.RemoteError('HTTP 403')
        with self.assertRaisesRegex(ValueError, 'yt-analytics.readonly'):
            analytics.fetch_report({**self.request, 'include_revenue': True})
        self.assertEqual(len(self.calls), 2)
        self.publication_write.assert_not_called(); self.assertFalse(services.OPERATIONS)

    def test_monetary_permission_failure_preserves_basic_metrics(self):
        self.money = services.RemoteError('HTTP 403')
        result = analytics.fetch_report({**self.request, 'include_revenue': True})
        self.assertEqual(result['data_status'], 'available')
        self.assertEqual(result['metrics']['views'], 100)
        self.assertIsNone(result['metrics']['estimated_revenue_eur'])
        self.assertEqual(result['monetary_status'], 'unavailable')
        self.assertIn('Programma partner', result['monetary_message'])
        self.assertEqual(len(self.calls), 3)

    def test_malformed_monetary_report_preserves_basic_metrics(self):
        self.money = {'columnHeaders': [], 'rows': [[123]]}
        result = analytics.fetch_report({**self.request, 'include_revenue': True})
        self.assertEqual(result['metrics']['engaged_views'], 80)
        self.assertIsNone(result['metrics']['estimated_revenue_eur'])
        self.assertEqual(result['monetary_status'], 'unavailable')

    def test_wrong_locally_selected_channel_is_rejected_before_network(self):
        self.connections['youtube']['profiles'][0]['account_id'] = 'UCunexpected'
        self.write_connections()
        with self.assertRaisesRegex(ValueError, 'diverso'):
            analytics.fetch_report(self.request)
        self.http_mock.assert_not_called()

    def test_wrong_remote_identity_stops_before_analytics(self):
        def http(url, **kwargs):
            self.assertIn('/youtube/v3/channels', url)
            return {'items': [{'id': 'UCunexpected', 'snippet': {'title': 'Altro'}}]}, {}, 200
        self.http_mock.side_effect = http
        with self.assertRaisesRegex(ValueError, 'identità'):
            analytics.fetch_report(self.request)
        self.assertEqual(self.http_mock.call_count, 1)
        self.assertFalse(services.OPERATIONS)

    def test_missing_channel_permissions_do_not_reach_analytics(self):
        self.http_mock.side_effect = services.RemoteError('HTTP 403')
        with self.assertRaises(services.RemoteError):
            analytics.fetch_report(self.request)
        self.assertEqual(self.http_mock.call_count, 1)

    def test_unverified_or_disconnected_profile_is_not_used(self):
        self.connections['youtube']['profiles'][0].pop('verified')
        self.write_connections()
        with self.assertRaisesRegex(ValueError, 'verifica'):
            analytics.fetch_report(self.request)
        self.connections['youtube']['profiles'][0]['verified'] = 1
        self.write_connections(); services.VAULT.clear()
        with self.assertRaisesRegex(ValueError, 'Collega'):
            analytics.fetch_report(self.request)
        self.http_mock.assert_not_called()

    def test_profile_edits_and_disconnect_are_blocked_during_read_but_switch_is_safe(self):
        def http(url, **kwargs):
            if urlsplit(url).hostname == 'youtubeanalytics.googleapis.com':
                with self.assertRaisesRegex(ValueError, 'in uso'):
                    services.save({'service': 'youtube', 'profile_id': 'profileA', 'access_token': 'replacement'})
                with self.assertRaisesRegex(ValueError, 'in uso'):
                    services.disconnect('youtube', 'profileA')
                services.switch_profile({'service': 'youtube', 'profile_id': 'other'})
            return self.http(url, **kwargs)
        self.http_mock.side_effect = http
        result = analytics.fetch_report({**self.request, 'include_revenue': True})
        self.assertEqual(result['profile_id'], 'profileA')
        self.assertEqual(services.secret('youtube', 'access_token', 'profileA'), 'test-only-token-A')

    def test_profile_revision_change_before_binding_is_rejected(self):
        original_bound = services.bound
        @contextmanager
        def changed_binding(name, profile_id):
            self.connections['youtube']['profiles'][0]['revision'] += 1
            self.write_connections()
            with original_bound(name, profile_id) as identity:
                yield identity
        with patch.object(services, 'bound', changed_binding):
            with self.assertRaisesRegex(ValueError, 'cambiato'):
                analytics.fetch_report(self.request)
        self.http_mock.assert_not_called()

    def test_profile_revision_change_during_monetary_failure_is_not_swallowed(self):
        def http(url, **kwargs):
            if 'estimatedRevenue' in url:
                cfg = services.load(); cfg['youtube']['profiles'][0]['revision'] += 1
                services.PATH.write_text(json.dumps(cfg))
                raise services.RemoteError('HTTP 403')
            return self.http(url, **kwargs)
        self.http_mock.side_effect = http
        with self.assertRaisesRegex(ValueError, 'profilo YouTube è cambiato'):
            analytics.fetch_report({**self.request, 'include_revenue': True})

    def test_publication_changed_while_reading_cannot_receive_report(self):
        def http(url, **kwargs):
            response = self.http(url, **kwargs)
            if urlsplit(url).hostname == 'youtubeanalytics.googleapis.com':
                self.post['revision'] += 1; self.write_post()
            return response
        self.http_mock.side_effect = http
        with self.assertRaisesRegex(ValueError, 'pubblicazione è cambiata'):
            analytics.fetch_report(self.request)

    def test_payload_date_bounds_and_arbitrary_destinations_are_rejected_before_network(self):
        invalid = [None, [], {}, {**self.request, 'publication_id': '../post'},
            {**self.request, 'start_date': '20260901'}, {**self.request, 'start_date': '2026-02-30'},
            {**self.request, 'start_date': '2026-09-16'}, {**self.request, 'end_date': '2026-09-21'},
            {**self.request, 'start_date': '2025-09-19', 'end_date': '2026-09-20'},
            {**self.request, 'include_revenue': 1}, {**self.request, 'include_revenue': 'false'},
            {**self.request, 'url': 'https://evil.example'}, {**self.request, 'metrics': 'otherMetric'},
            {**self.request, 'channel_id': 'UCchannelBBBB'}, {**self.request, 'profile_id': 'other'}]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(ValueError):
                analytics.fetch_report(request)
        self.http_mock.assert_not_called()
        valid = {**self.request, 'start_date': '2025-09-20', 'end_date': '2026-09-20'}
        self.assertEqual(analytics.validate_request(valid), {**valid, 'include_revenue': False})

    def test_requires_a_published_youtube_post_and_safe_saved_remote_ids(self):
        for updates in ({'state': 'processing'}, {'platform': 'tiktok'}, {'remote_id': None},
                        {'remote_id': 'dQw4w9WgXcQ;country==US'}, {'account_id': 'https://evil.example'}):
            original = copy.deepcopy(self.post)
            self.post.update(updates); self.write_post()
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                analytics.fetch_report(self.request)
            self.post = original
        self.http_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
