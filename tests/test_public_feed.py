import copy
import hashlib
import io
import json
import tempfile
import unittest
from datetime import timedelta
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from helpers import NOW, draft, response
from news_content import build_feed, collect_research
from publication import already_published, fetch_json, json_bytes
from verify_public_feed import verify


class PublicTests(unittest.TestCase):
    def setUp(self):
        self.feed = build_feed(draft(), collect_research(response('架空の資料', True)), NOW)
        self.manifest = {'version': 2, 'generated_at': self.feed[0]['updateDate'], 'fingerprint': 'current',
                         'feed_sha256': hashlib.sha256(json_bytes(self.feed)).hexdigest()}

    @patch('publication.fetch_json')
    def test_skip_requires_same_day_same_code_and_matching_feed(self, fetch):
        for when, identity, result in [(NOW, 'current', True),
                                       (NOW + timedelta(days=1), 'current', False),
                                       (NOW, 'changed-code', False),
                                       (NOW - timedelta(hours=1), 'current', False)]:
            fetch.side_effect = [self.manifest, self.feed]
            self.assertEqual(already_published('https://example.com/', when, identity), result)
        damaged = copy.deepcopy(self.feed)
        damaged[0]['mainText'] += '変更。'
        fetch.side_effect = [self.manifest, damaged]
        self.assertFalse(already_published('https://example.com/', NOW, 'current'))
        fetch.side_effect = OSError('unavailable')
        self.assertFalse(already_published('https://example.com/', NOW, 'current'))

    @patch('publication.urllib.request.urlopen')
    def test_https_json_and_size_are_required(self, opener):
        for mime, final_url, body, passes in [
            ('application/json', 'https://example.com/', b'[]', True),
            ('text/html', 'https://example.com/', b'[]', False),
            ('application/json', 'http://example.com/', b'[]', False),
            ('application/json', 'https://example.com/', b' ' * 1_000_001, False),
        ]:
            stream = io.BytesIO(body)
            stream.headers = Message()
            stream.headers['Content-Type'] = mime
            stream.geturl = lambda: final_url
            opener.return_value = stream
            if passes:
                self.assertEqual(fetch_json('https://example.com/feed.json'), [])
            else:
                with self.assertRaises(ValueError):
                    fetch_json('https://example.com/feed.json')

    @patch('verify_public_feed.time.sleep')
    @patch('verify_public_feed.fetch_json')
    def test_deployment_verifies_feed_and_manifest(self, fetch, sleep):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'feed.json').write_bytes(json_bytes(self.feed))
            (base / 'manifest.json').write_bytes(json_bytes(self.manifest))
            fetch.side_effect = [self.feed, self.manifest]
            verify('https://example.com/', base, attempts=1)
            old_manifest = dict(self.manifest, fingerprint='old')
            fetch.side_effect = [self.feed, old_manifest]
            with self.assertRaises(RuntimeError):
                verify('https://example.com/', base, attempts=1)

    @patch('verify_public_feed.fetch_json')
    def test_old_run_cannot_overwrite_newer_edition(self, fetch):
        from verify_public_feed import preflight
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'feed.json').write_bytes(json_bytes(self.feed))
            (base / 'manifest.json').write_bytes(json_bytes(self.manifest))
            fetch.return_value = self.manifest
            preflight('https://example.com/', base, NOW)
            fetch.return_value = dict(self.manifest, generated_at=(NOW + timedelta(minutes=30)).isoformat())
            with self.assertRaises(RuntimeError):
                preflight('https://example.com/', base, NOW + timedelta(hours=1))
            with self.assertRaises(RuntimeError):
                preflight('https://example.com/', base, NOW + timedelta(hours=7))
            fetch.side_effect = HTTPError('https://example.com', 404, '', {}, None)
            preflight('https://example.com/', base, NOW)
