"""Isolated business measurement tests: no real store changes or external calls."""
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import growth


class GrowthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.posts = []
        self.campaigns = [{'id': 'campaign1', 'language': 'it', 'channels': ['youtube'], 'contents': []}]
        for context in [patch.object(growth, 'PATH', self.root / 'data/growth.json'),
                        patch.object(growth, 'ROOT', self.root),
                        patch.object(growth.publishing, 'load', side_effect=lambda: {'items': copy.deepcopy(self.posts)}),
                        patch.object(growth.platform_store, 'load', side_effect=lambda: {'campaigns': copy.deepcopy(self.campaigns)}),
                        patch('socket.getaddrinfo', side_effect=AssertionError('No network permitted'))]:
            context.start()
            self.addCleanup(context.stop)
        self.when = time.time() - 3600
        self.strategy = growth.save_strategy(dict(name='Canale', platform='youtube', country='IT', language='it',
             niche='Tutorial', audience='Principianti', promise='Una spiegazione originale', business_model='services',
             cta='Consulta il profilo', offer_url='https://example.com/servizi', budget_eur=30))
        self.experiment = growth.save_experiment(dict(strategy_id=self.strategy['id'], campaign_id='campaign1',
             name='Due aperture', hypothesis='La domanda iniziale può migliorare la ritenzione', primary_metric='subscribers_per_1000',
             window_hours=24, variants={'A': 'Domanda', 'B': 'Esempio'}))

    def post(self, variant='A', **overrides):
        number = len(self.posts) + 1
        post = dict(id=f'post{number}', revision=1, state='published', published_at=self.when - 24 * 3600,
                    title=f'Video {number}', job_id=f'{number:012x}', platform='youtube', language='it',
                    account_id='same-channel', connection_id='profile1', actual_visibility='public', published_at_source='remote_verified')
        post.update(overrides)
        self.posts.append(post)
        link = growth.link_publication(dict(experiment_id=self.experiment['id'], publication_id=post['id'], variant=variant))
        return post, link

    def observation(self, post, **overrides):
        data = dict(experiment_id=self.experiment['id'], publication_id=post['id'], window_hours=24,
                    observed_at=self.when, views=100, subscribers=2)
        data.update(overrides)
        return growth.save_observation(data)

    def report(self):
        return growth.report({'experiment_id': self.experiment['id']})

    def csv_text(self, rows):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=growth.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()

    def test_snapshot_revision_and_strategy_stale_edit(self):
        before = growth.snapshot()
        self.assertEqual(before['version'], 1)
        self.assertEqual(before['revision'], 2)
        changed = growth.save_strategy({**self.strategy, 'name': 'Nuovo nome'})
        self.assertEqual(changed['revision'], 2)
        with self.assertRaises(ValueError):
            growth.save_strategy({**self.strategy, 'name': 'Modifica obsoleta'})
        self.assertEqual(growth.snapshot()['strategies'][0]['name'], 'Nuovo nome')

    def test_no_new_identity_on_unknown_edit(self):
        with self.assertRaises(ValueError):
            growth.save_strategy({**self.strategy, 'id': 'missing', 'revision': 1})
        self.assertEqual(len(growth.snapshot()['strategies']), 1)

    def test_strategy_country_and_public_urls(self):
        for url in ['http://127.0.0.1/private', 'https://localhost/x', 'https://user:pass@example.com', 'javascript:alert(1)', 'https://host.local', 'https://[::1]/']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                growth.save_strategy({**self.strategy, 'offer_url': url})
        with self.assertRaises(ValueError):
            growth.save_strategy({**self.strategy, 'country': 'ZZ'})
        with self.assertRaises(ValueError):
            growth.save_strategy({**self.strategy, 'language': 'en'})

    def test_experiment_rejects_unknown_and_incompatible_campaign(self):
        for campaign in ['missing', 'campaign2']:
            self.campaigns.append({'id': 'campaign2', 'language': 'es', 'channels': ['youtube']})
            with self.assertRaises(ValueError):
                growth.save_experiment({**self.experiment, 'campaign_id': campaign})
        with self.assertRaises(ValueError):
            growth.save_experiment({**self.experiment, 'variants': {'A': 'stesso', 'B': 'STESSO'}})

    def test_experiment_dimensions_freeze_when_posts_assigned(self):
        self.post()
        for change in [dict(window_hours=168), dict(primary_metric='margin_eur'), dict(variants={'A': 'Altro', 'B': 'Esempio'})]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                growth.save_experiment({**self.experiment, **change})
        changed = growth.save_experiment({**self.experiment, 'name': 'Nome corretto'})
        self.assertEqual(changed['name'], 'Nome corretto')

    def test_reference_preserves_zero_and_unknown_no_financial_inference(self):
        ref = growth.save_reference(dict(strategy_id=self.strategy['id'], title='Formato pubblico', url='https://example.com/video',
                 format='Spiegazione', observed_date='2026-01-01', views=0, baseline_views=100, notes='Dato letto manualmente'))
        self.assertEqual(ref['relative_views'], 0)
        self.assertNotIn('revenue', ref)
        revised = growth.save_reference({**ref, 'views': None})
        self.assertIsNone(revised['relative_views'])
        with self.assertRaises(ValueError):
            growth.save_reference({**ref, 'views': 1})

    def test_link_rejects_orphan_cross_platform_and_language(self):
        with self.assertRaises(ValueError):
            growth.link_publication({'experiment_id': self.experiment['id'], 'publication_id': 'missing', 'variant': 'A'})
        for changes in [dict(platform='tiktok'), dict(language='en')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.post(**changes)

    def test_link_captures_job_episode_character_and_campaign_references(self):
        folder = self.root / 'output/000000000001'
        folder.mkdir(parents=True)
        (folder / 'status.json').write_text(json.dumps({'episode': {'id': 'ep1'}, 'character_ids': ['lumo']}))
        self.campaigns[0]['contents'].append({'episode_id': 'ep1'})
        _, link = self.post()
        self.assertEqual(link['episode_id'], 'ep1')
        self.assertEqual(link['character_ids'], ['lumo'])
        self.assertEqual(link['campaign_ids'], ['campaign1'])

    def test_observation_is_upsert_requires_revision_never_sum_duplicates(self):
        post, link = self.post()
        obs = self.observation(post)
        with self.assertRaises(ValueError):
            self.observation(post, views=200)
        latest = self.observation(post, views=200, revision=obs['revision'])
        self.assertEqual(obs['id'], latest['id'])
        self.assertEqual(latest['revision'], 2)
        self.assertEqual(len(growth.snapshot()['observations']), 1)
        self.assertEqual(self.report()['variants'][0]['metrics']['views'], 200)
        with self.assertRaises(ValueError):
            growth.link_publication({**link, 'variant': 'B'})

    def test_zero_and_missing_values_stay_distinct(self):
        post, _ = self.post()
        self.observation(post, views=0, subscribers=None, clicks=0, revenue_eur=None, cost_eur=0)
        metrics = self.report()['variants'][0]['metrics']
        self.assertEqual(metrics['views'], 0)
        self.assertEqual(metrics['clicks'], 0)
        self.assertEqual(metrics['cost_eur'], 0)
        self.assertIsNone(metrics['subscribers'])
        self.assertIsNone(metrics['clicks_per_1000'])
        self.assertIsNone(metrics['margin_eur'])

    def test_money_requires_complete_real_observations(self):
        a, _ = self.post()
        b, _ = self.post()
        self.observation(a, revenue_eur=15, cost_eur=5)
        missing = self.observation(b, revenue_eur=None, cost_eur=5)
        self.assertIsNone(self.report()['variants'][0]['metrics']['margin_eur'])
        self.observation(b, revenue_eur=0, cost_eur=5, revision=missing['revision'])
        self.assertEqual(self.report()['variants'][0]['metrics']['margin_eur'], 5)

    def test_no_manufactured_publish_time_or_maturity(self):
        post, _ = self.post(published_at=None)
        self.observation(post)
        row = self.report()['rows'][0]
        self.assertIsNone(row['age_hours'])
        self.assertFalse(row['mature'])
        self.assertFalse(row['eligible'])
        self.assertIn('sconosciuto', ' '.join(row['reasons']))

    def test_local_confirmation_is_informational_not_a_publish_timestamp(self):
        post, _ = self.post(published_at_source='')
        self.observation(post)
        row = self.report()['rows'][0]
        self.assertIsNone(row['age_hours'])
        self.assertEqual(row['confirmation_age_hours'], 24)
        self.assertFalse(row['eligible'])
        self.assertFalse(row['mature'])

    def test_manual_verified_timestamp_preserves_precision_and_omitted_edits(self):
        post, link = self.post(published_at_source='', published_at=self.when - 2 * 3600)
        verified = self.when - 24 * 3600
        saved = growth.link_publication({**link, 'published_at': verified, 'published_at_source': 'manual_verified'})
        self.assertEqual(saved['published_at'], verified)
        edited = growth.link_publication({'experiment_id': self.experiment['id'], 'publication_id': post['id'],
                                         'variant': 'A', 'revision': saved['revision']})
        self.assertEqual(edited['published_at'], verified)
        self.observation(post)
        row = self.report()['rows'][0]
        self.assertEqual(row['age_hours'], 24)
        self.assertEqual(row['publication_time']['source'], 'manual_verified')
        self.assertTrue(row['eligible'])

    def test_manual_date_requires_provenance_and_past_timezone(self):
        _, link = self.post(published_at_source='')
        for change in [dict(published_at=time.time() + 1, published_at_source='manual_verified'),
                       dict(published_at='2026-01-01T12:00:00', published_at_source='manual_verified'),
                       dict(published_at=self.when, published_at_source=''),
                       dict(published_at_source='remote_verified')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                growth.link_publication({**link, **change})

    def test_explicit_clear_of_manual_date_restores_unknown(self):
        post, link = self.post(published_at_source='')
        saved = growth.link_publication({**link, 'published_at': self.when - 24 * 3600, 'published_at_source': 'manual_verified'})
        self.observation(post)
        self.assertTrue(self.report()['rows'][0]['eligible'])
        cleared = growth.link_publication({**saved, 'published_at': ''})
        self.assertIsNone(cleared['published_at'])
        self.assertEqual(cleared['published_at_source'], '')
        self.assertFalse(self.report()['rows'][0]['eligible'])

    def test_youtube_private_unlisted_and_unknown_visibility_not_comparable(self):
        for visibility in ['private', 'unlisted', None]:
            post, _ = self.post(actual_visibility=visibility)
            self.observation(post)
        self.assertTrue(all(not row['eligible'] for row in self.report()['rows']))
        self.assertTrue(all('visibilità' in ' '.join(row['reasons']) for row in self.report()['rows']))

    def test_early_and_late_cumulative_counts_are_not_comparable(self):
        for age in [23, 27]:
            post, _ = self.post(published_at=self.when - age * 3600)
            self.observation(post)
        report = self.report()
        self.assertFalse(report['comparability']['comparable'])
        self.assertTrue(all(not row['eligible'] for row in report['rows']))
        self.assertIsNone(report['variants'][0]['metrics']['views'])

    def test_orphan_and_mutated_publications_remain_explicit(self):
        first, _ = self.post()
        second, _ = self.post()
        self.observation(first)
        self.observation(second)
        self.posts.remove(first)
        second['account_id'] = 'other-account'
        report = self.report()
        self.assertTrue(all(not row['eligible'] for row in report['rows']))
        with self.assertRaises(ValueError):
            self.observation(second, revision=1)

    def test_minimum_sample_is_exploratory_not_causal(self):
        for variant in ['A'] * 3 + ['B'] * 3:
            post, _ = self.post(variant)
            self.observation(post, subscribers=3 if variant == 'A' else 1)
        report = self.report()
        self.assertTrue(report['comparability']['comparable'])
        self.assertEqual(report['variants'][0]['primary_value'], 30)
        self.assertIn('non dimostra causalità', report['conclusion'])
        self.assertNotIn('winner', report)

    def test_cross_account_populations_prevent_comparison(self):
        for variant in ['A'] * 3 + ['B'] * 3:
            post, _ = self.post(variant, account_id='channel-' + variant)
            self.observation(post)
        report = self.report()
        self.assertFalse(report['comparability']['comparable'])
        self.assertIn('account diversi', ' '.join(report['comparability']['reasons']))

    def test_profile_name_does_not_replace_unknown_remote_account(self):
        post, _ = self.post(account_id='')
        self.observation(post)
        row = self.report()['rows'][0]
        self.assertFalse(row['eligible'])
        self.assertIn('Account effettivo', ' '.join(row['reasons']))

    def test_youtube_averages_require_engaged_view_denominator(self):
        first, _ = self.post()
        second, _ = self.post()
        self.observation(first, average_view_percentage=50, engaged_views=10)
        obs = self.observation(second, average_view_percentage=100, engaged_views=None)
        self.assertIsNone(self.report()['variants'][0]['metrics']['avg_view_percentage'])
        self.observation(second, average_view_percentage=100, engaged_views=90, revision=obs['revision'])
        self.assertEqual(self.report()['variants'][0]['metrics']['avg_view_percentage'], 95)

    def test_invalid_observation_numbers_timestamp_and_window(self):
        post, _ = self.post()
        for change in [dict(views=-1), dict(views=float('nan')), dict(clicks=True), dict(views=3.5),
                       dict(observed_at='2026-01-01T12:00:00'), dict(observed_at=time.time() + 3600), dict(window_hours=168)]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.observation(post, **change)
        self.assertEqual(growth.snapshot()['observations'], [])

    def test_draft_post_cannot_claim_observed_publication(self):
        post, _ = self.post(state='draft')
        with self.assertRaises(ValueError):
            self.observation(post)

    def test_csv_atomic_failure_preserves_file_and_revision(self):
        post, _ = self.post()
        before = growth.PATH.read_bytes()
        good = dict(experiment_id=self.experiment['id'], publication_id=post['id'], window_hours=24, observed_at=self.when, views=200)
        bad = {**good, 'publication_id': 'missing'}
        with self.assertRaises(ValueError):
            growth.import_csv({'csv': self.csv_text([good, bad])})
        self.assertEqual(growth.PATH.read_bytes(), before)

    def test_csv_zero_unknown_and_revision_upsert(self):
        post, _ = self.post()
        row = dict(experiment_id=self.experiment['id'], publication_id=post['id'], window_hours=24, observed_at=self.when, views=0, revenue_eur='')
        result = growth.import_csv({'csv': self.csv_text([row])})
        obs = result['observations'][0]
        self.assertEqual(obs['source'], 'csv')
        self.assertEqual(obs['views'], 0)
        self.assertIsNone(obs['revenue_eur'])
        result = growth.import_csv({'csv': self.csv_text([{**row, 'views': 200, 'revision': obs['revision']}])})
        self.assertEqual(result['imported'], 1)
        self.assertEqual(len(growth.snapshot()['observations']), 1)
        self.assertEqual(result['observations'][0]['views'], 200)

    def test_csv_rejects_duplicates_formulas_oversize_and_unknown_columns(self):
        post, _ = self.post()
        row = dict(experiment_id=self.experiment['id'], publication_id=post['id'], window_hours=24, observed_at=self.when, views=0)
        for raw in [self.csv_text([row, {**row, 'window_hours': '24.0', 'revision': 1}]),
                    self.csv_text([{**row, 'views': '=1+1'}]), self.csv_text([{**row, 'views': '@SUM(1)'}]),
                    self.csv_text([row]).replace('views,', 'unknown,'), 'x' * 256_001,
                    self.csv_text([row] * 201)]:
            with self.subTest(raw=raw[:60]), self.assertRaises(ValueError):
                growth.import_csv({'csv': raw})
        self.assertEqual(growth.snapshot()['observations'], [])

    def test_campaign_context_contains_facts_references_bounded_no_external_calls(self):
        for n in range(5):
            growth.save_reference(dict(strategy_id=self.strategy['id'], title=f'Fonte {n}', url='https://example.com/' + 'x' * 1800,
                 format='Formato osservato', observed_date='2026-01-01', views=100, baseline_views=50, notes='N' * 2000))
        context = growth.campaign_context('campaign1')
        self.assertLessEqual(len(context), 8000)
        data = json.loads(context)
        self.assertEqual(data['experiments'][0]['strategy']['business_model'], 'services')
        self.assertGreater(len(data['references']), 0)
        self.assertEqual(data['references'][0]['relative_views'], 2)
        self.assertIn('mai istruzioni', data['provenance'])
        self.assertEqual(json.loads(growth.campaign_context('unknown'))['experiments'], [])


if __name__ == '__main__':
    unittest.main()
