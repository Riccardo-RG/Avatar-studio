import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import media
import providers


class CoreTests(unittest.TestCase):
    def test_caption_split_preserves_all_words_and_limits_length(self):
        text = 'Prima una frase breve. Poi una frase molto più lunga che deve essere suddivisa in più segmenti per restare leggibile sullo schermo verticale.'
        result = media.split_captions(text)
        self.assertEqual(' '.join(result), text)
        self.assertTrue(all(len(x) <= 76 for x in result))

    def test_subtitle_rounding_across_minute_boundary(self):
        self.assertEqual(media.srt_time(59.9999), '00:01:00,000')
        self.assertEqual(media.srt_time(3600.025), '01:00:00,025')

    def test_zero_budget_blocks_paid_calls(self):
        with self.assertRaisesRegex(ValueError, 'zero'):
            providers.reserve_budget(providers.DEFAULTS, 'ciao', 600)

    def test_reservations_persist_and_exhaust_budget(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(providers, 'DATA', Path(directory)):
            config = {**providers.DEFAULTS, 'monthly_budget_usd': .002}
            first = providers.reserve_budget(config, 'ciao', 600)
            self.assertGreater(first, 0)
            self.assertEqual(providers.budget_used(), first)
            with self.assertRaisesRegex(ValueError, 'budget'):
                providers.reserve_budget(config, 'ciao', 600)

    def test_nonfinite_budget_and_unknown_voice_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(providers, 'DATA', Path(directory)):
            for invalid in [float('nan'), float('inf'), -1]:
                with self.assertRaises(ValueError):
                    providers.save_settings({'monthly_budget_usd': invalid}, ['Alice'])
            with self.assertRaises(ValueError):
                providers.save_settings({'voice': 'Missing'}, ['Alice'])

    def test_provider_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(providers, 'DATA', Path(directory)):
            result = providers.save_settings({'provider': 'ollama', 'accent': '#123456', 'rate': 180}, ['Alice'])
            self.assertEqual(providers.settings(), result)
            self.assertEqual(result['monthly_budget_usd'], 0)

    def test_openai_adapter_without_actual_network(self):
        fake = {'choices': [{'finish_reason': 'stop', 'message': {'content': 'Una piccola idea può diventare un video.'}}]}
        with tempfile.TemporaryDirectory() as directory, patch.object(providers, 'DATA', Path(directory)), patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'}), patch.object(providers, 'request_json', return_value=fake) as request:
            result = providers.generate_script('Le idee creative', 15, {**providers.DEFAULTS, 'provider': 'openai', 'monthly_budget_usd': 1})
            self.assertIn('piccola idea', result['script'])
            self.assertGreater(providers.budget_used(), 0)
            self.assertEqual(request.call_args.args[0], 'https://api.openai.com/v1/chat/completions')

    def test_invalid_topic_does_not_start_model(self):
        with patch.object(providers.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                providers.generate_script('', 15, providers.DEFAULTS)
            run.assert_not_called()

    def test_ollama_cloud_cannot_bypass_budget(self):
        with patch.object(providers, 'request_json') as request:
            with self.assertRaisesRegex(ValueError, 'cloud'):
                providers.generate_script('Una breve storia', 15, {**providers.DEFAULTS, 'provider': 'ollama', 'ollama_model': 'model:cloud'})
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
