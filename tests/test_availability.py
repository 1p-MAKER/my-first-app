import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import NOW
from availability import publish_notice
from publication import already_published, validate_manifest


class AvailabilityTests(unittest.TestCase):
    @patch('availability.already_published', return_value=False)
    def test_failure_notice_is_valid_but_never_counts_as_updated_news(self, current):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertTrue(publish_notice(base, NOW))
            feed = json.loads((base / 'feed.json').read_text())
            manifest = json.loads((base / 'manifest.json').read_text())
            validate_manifest(manifest, feed)
            self.assertIn('9月11日', feed[0]['mainText'])
            with patch('publication.fetch_json', side_effect=[manifest, feed]):
                self.assertFalse(already_published('https://example.com/', NOW, manifest['fingerprint']))
            feed[0]['mainText'] = '古いニュース'
            with self.assertRaises(ValueError):
                validate_manifest(manifest, feed)

    @patch('availability.already_published', return_value=True)
    def test_failed_rerun_preserves_healthy_edition(self, current):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'feed.json').write_text('healthy')
            self.assertFalse(publish_notice(base, NOW))
            self.assertEqual((base / 'feed.json').read_text(), 'healthy')
