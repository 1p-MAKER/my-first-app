import io
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from helpers import NOW, FakeClient, draft, response
from gemini_client import GeminiClient, GeminiError, candidate_text
import generate_news
from news_content import build_feed, collect_research, validate_feed
from publication import validate_manifest


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.research = collect_research(response('架空の確認資料。', True))

    def test_valid_feed_time_and_required_fields(self):
        feed = build_feed(draft(), self.research, NOW)
        validate_feed(feed)
        self.assertEqual(len(feed), 5)
        self.assertEqual(feed[0]['updateDate'], '2026-09-10T21:00:00Z')
        self.assertIn('20260911', feed[0]['uid'])
        self.assertIn('9月11日', feed[0]['mainText'])
        self.assertIn('日本時間9月11日9時00分', feed[-1]['mainText'])
        changed = draft()
        changed['topics']['japan']['text'] += '訂正。'
        self.assertNotEqual(feed[1]['uid'], build_feed(changed, self.research, NOW)[1]['uid'])

    def test_required_coverage_sources_and_dates(self):
        for mutate in [lambda d: d['topics'].pop('okinawa'),
                       lambda d: d['topics']['japan'].update(source_ids=[999]),
                       lambda d: d['topics']['japan'].update(source_ids=[True]),
                       lambda d: d['topics']['japan'].update(source_ids=[]),
                       lambda d: d['events'][0].update(at='2026-09-11T09:00:00'),
                       lambda d: d['events'][0].update(at=NOW.isoformat()),
                       lambda d: d['events'][0].update(at=(NOW + timedelta(hours=25)).isoformat())]:
            value = draft()
            mutate(value)
            with self.assertRaises(ValueError):
                build_feed(value, self.research, NOW)

    def test_unconfirmed_cannot_smuggle_facts(self):
        value = draft()
        value['topics']['okinawa'] = {'status': 'unconfirmed', 'text': '', 'source_ids': []}
        feed = build_feed(value, self.research, NOW)
        self.assertIn('沖縄については、十分な最新情報を確認できませんでした。', feed[1]['mainText'])
        value['topics']['okinawa']['text'] = '未確認の架空のニュースです。'
        with self.assertRaises(ValueError):
            build_feed(value, self.research, NOW)

    def test_plain_text_length_and_duplicates(self):
        for text in ('', 'あ' * 4301, '😀' * 2151, '<speak>声</speak>', 'https://example.com', '本文\x00', '[1]脚注'):
            value = draft()
            value['topics']['japan']['text'] = text
            with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                build_feed(value, self.research, NOW)
        feed = build_feed(draft(), self.research, NOW)
        feed[1]['mainText'] = feed[0]['mainText']
        with self.assertRaises(ValueError):
            validate_feed(feed)

    def test_actual_grounding_support_required(self):
        for field in ('webSearchQueries', 'groundingChunks', 'groundingSupports'):
            value = response('確認資料', True)
            del value['candidates'][0]['groundingMetadata'][field]
            with self.assertRaises(ValueError):
                collect_research(value)
        value = response('確認資料', True)
        value['candidates'][0]['groundingMetadata']['groundingSupports'][0]['segment']['text'] = '本文に存在しない引用'
        with self.assertRaises(ValueError):
            collect_research(value)

    def test_blocked_truncated_and_thought_content(self):
        for reason in ('MAX_TOKENS', 'SAFETY', None):
            value = response('本文')
            value['candidates'][0]['finishReason'] = reason
            with self.assertRaises(ValueError):
                candidate_text(value)
        value = response('本文')
        value['candidates'][0]['content']['parts'].insert(0, {'thought': True, 'text': '内部の思考'})
        self.assertEqual(candidate_text(value)[0], '本文')


class ClientTests(unittest.TestCase):
    @patch('gemini_client.urllib.request.urlopen')
    def test_separate_search_and_schema_contract(self, opener):
        opener.side_effect = lambda *a, **kw: io.BytesIO(json.dumps(response('本文')).encode())
        client = GeminiClient('test-secret')
        client.generate('調査', search=True)
        request = opener.call_args.args[0]
        self.assertEqual(json.loads(request.data)['tools'], [{'google_search': {}}])
        self.assertNotIn('test-secret', request.full_url)
        self.assertEqual(request.get_header('X-goog-api-key'), 'test-secret')
        client.generate('編集', schema={'type': 'object'})
        payload = json.loads(opener.call_args.args[0].data)
        self.assertNotIn('tools', payload)
        self.assertEqual(payload['generationConfig']['responseMimeType'], 'application/json')
        self.assertEqual(payload['generationConfig']['responseJsonSchema'], {'type': 'object'})
        self.assertEqual(client.attempts, 2)
        self.assertEqual(len(client.usage), 2)

    @patch('gemini_client.time.sleep')
    @patch('gemini_client.urllib.request.urlopen')
    def test_retry_limits_and_retry_after(self, opener, sleep):
        for code, count in ((429, 3), (503, 3), (403, 1), (404, 1)):
            opener.reset_mock()
            opener.side_effect = HTTPError('https://example.com', code, 'private-error', {}, None)
            with self.assertRaises(GeminiError) as caught:
                GeminiClient('test-secret').generate('test')
            self.assertEqual(opener.call_count, count)
            self.assertNotIn('test-secret', str(caught.exception))
        opener.side_effect = HTTPError('https://example.com', 429, '', {'Retry-After': '120'}, None)
        sleep.reset_mock()
        with self.assertRaises(GeminiError):
            GeminiClient('test-secret').generate('test')
        sleep.assert_not_called()

    def test_missing_secret_and_bad_model(self):
        for key, model in [('', 'gemini-3.8-flash'), ('test', '../bad')]:
            with self.assertRaises(GeminiError):
                GeminiClient(key, model)


class PipelineTests(unittest.TestCase):
    @patch.dict(os.environ, {'GITHUB_REF': 'refs/heads/test'})
    def test_complete_offline_pipeline_and_edit_only_retry(self):
        invalid = draft()
        invalid['topics'].pop('okinawa')
        client = FakeClient([invalid, draft()])
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.assertTrue(generate_news.run(output=base / 'docs', work=base / 'work', now=NOW, client=client))
            self.assertEqual([call['search'] for call in client.calls], [True, False, False])
            self.assertIn('不足', client.calls[-1]['prompt'])
            feed = json.loads((base / 'docs/feed.json').read_text())
            manifest = json.loads((base / 'docs/manifest.json').read_text())
            validate_manifest(manifest, feed)
            self.assertIn('架空の検証資料', (base / 'docs/index.html').read_text())
            self.assertTrue((base / 'work/research.json').exists())

    @patch.dict(os.environ, {'GITHUB_REF': 'refs/heads/test'})
    def test_invalid_draft_does_not_touch_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'docs').mkdir()
            (base / 'docs/feed.json').write_text('previous-feed')
            with self.assertRaises(RuntimeError):
                generate_news.run(output=base / 'docs', work=base / 'work', now=NOW,
                                  client=FakeClient([{}, {}, {}]))
            self.assertEqual((base / 'docs/feed.json').read_text(), 'previous-feed')
            self.assertFalse((base / 'docs/manifest.json').exists())

    @patch.dict(os.environ, {'GITHUB_REF': 'refs/heads/main', 'GEMINI_API_KEY': ''})
    @patch('generate_news.already_published', return_value=True)
    @patch('generate_news.GeminiClient')
    def test_recovery_skips_api_when_published(self, client, published):
        self.assertFalse(generate_news.run(now=NOW))
        client.assert_not_called()

    @patch.dict(os.environ, {'GITHUB_REF': 'refs/heads/main'})
    @patch('generate_news.already_published', return_value=True)
    def test_force_ignores_existing_public_edition(self, published):
        with tempfile.TemporaryDirectory() as temp:
            self.assertTrue(generate_news.run(output=Path(temp) / 'docs', work=Path(temp) / 'work',
                                               force=True, now=NOW, client=FakeClient()))
        published.assert_not_called()
