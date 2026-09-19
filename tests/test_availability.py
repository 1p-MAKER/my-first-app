import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import NOW
from availability import publish_notice
from publication import already_published, healthy_edition_published, validate_manifest


class AvailabilityTests(unittest.TestCase):
    @patch('availability.healthy_edition_published', return_value=False)
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

    @patch('availability.healthy_edition_published', return_value=True)
    def test_failed_rerun_preserves_healthy_edition(self, current):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'feed.json').write_text('healthy')
            self.assertFalse(publish_notice(base, NOW))
            self.assertEqual((base / 'feed.json').read_text(), 'healthy')

    @patch('availability.healthy_edition_published', return_value=False)
    def test_notice_uses_configured_site_url(self, current):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertTrue(publish_notice(base, NOW, 'https://news.example.test/feed'))
            feed = json.loads((base / 'feed.json').read_text())
            manifest = json.loads((base / 'manifest.json').read_text())
            self.assertEqual(feed[0]['redirectionUrl'], 'https://news.example.test/feed/')
            validate_manifest(manifest, feed)

    def test_unavailable_notice_rejects_non_https_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertTrue(publish_notice(base, NOW, 'https://news.example.test/feed'))
            feed = json.loads((base / 'feed.json').read_text())
            manifest = json.loads((base / 'manifest.json').read_text())
            feed[0]['redirectionUrl'] = 'http://news.example.test/'
            with self.assertRaises(ValueError):
                validate_manifest(manifest, feed)
