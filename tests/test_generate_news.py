import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError

import generate_news as news

NOW = datetime(2026, 9, 10, 21, tzinfo=timezone.utc)


def sections():
    return [{'title': f'ニュース{i}', 'text': str(i) + '確認されたニュースです。' * 34} for i in range(5)]


def response():
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(sections())}]},
        'groundingMetadata': {'webSearchQueries': ['今日のニュース'],
            'groundingChunks': [{'web': {'uri': 'https://example.com', 'title': '出典'}}],
            'groundingSupports': [{'segment': {'text': 'ニュース'}, 'groundingChunkIndices': [0]}]}}]}


class NewsTests(unittest.TestCase):
    def test_valid_feed_and_jst_day(self):
        feed = news.build_feed(sections(), NOW)
        self.assertEqual(len(feed), 5)
        self.assertTrue(feed[0]['uid'].startswith('daily-news-20260911-1-'))
        self.assertEqual(feed[0]['updateDate'], '2026-09-10T21:00:00Z')
        self.assertEqual(set(feed[0]), {'uid', 'updateDate', 'titleText', 'mainText', 'redirectionUrl'})
        self.assertEqual(len({x['uid'] for x in feed}), 5)

    def test_uid_changes_when_content_changes(self):
        data = sections()
        before = news.build_feed(data, NOW)
        data[0]['text'] += '訂正。'
        self.assertNotEqual(before[0]['uid'], news.build_feed(data, NOW)[0]['uid'])

    def test_invalid_sections(self):
        cases = [[], {}, sections()[:4], sections() + sections()[:1], [None] * 5]
        for field, value in [('text', None), ('text', ''), ('text', 'あ' * 4301),
                             ('text', '😀' * 2151), ('text', '<speak>ニュース</speak>'),
                             ('text', 'https://example.com'), ('title', 123), ('title', '')]:
            data = sections()
            data[0][field] = value
            cases.append(data)
        cases.append([{'title': '短い', 'text': '短い。'}] * 5)
        cases.append([sections()[0]] * 5)
        for data in cases:
            with self.subTest(data=str(data)[:60]), self.assertRaises(ValueError):
                news.build_feed(data, NOW)

    def test_grounding_and_completion_required(self):
        data, metadata = news.parse_response(response())
        self.assertEqual(len(data), 5)
        for field in ('webSearchQueries', 'groundingChunks', 'groundingSupports'):
            bad = response()
            del bad['candidates'][0]['groundingMetadata'][field]
            with self.assertRaises(ValueError):
                news.parse_response(bad)
        for reason in ('MAX_TOKENS', 'SAFETY', None):
            bad = response()
            bad['candidates'][0]['finishReason'] = reason
            with self.assertRaises(ValueError):
                news.parse_response(bad)

    def test_thought_parts_are_not_json(self):
        data = response()
        data['candidates'][0]['content']['parts'].insert(0, {'thought': True, 'text': 'thinking'})
        self.assertEqual(len(news.parse_response(data)[0]), 5)

    @patch('generate_news.urllib.request.urlopen')
    def test_rest_contract(self, opener):
        opener.return_value.__enter__.return_value = io.BytesIO(json.dumps(response()).encode())
        news.request_gemini('test-secret', '現在時刻付き原稿')
        request = opener.call_args.args[0]
        self.assertNotIn('test-secret', request.full_url)
        self.assertTrue(request.full_url.endswith(':generateContent'))
        self.assertEqual(json.loads(request.data)['tools'], [{'google_search': {}}])
        self.assertEqual(request.get_header('X-goog-api-key'), 'test-secret')

    @patch('generate_news.time.sleep')
    @patch('generate_news.urllib.request.urlopen')
    def test_retry_transient_not_auth(self, opener, sleep):
        for code, count in [(429, 3), (503, 3), (403, 1), (400, 1)]:
            opener.reset_mock()
            opener.side_effect = HTTPError('https://example.com', code, 'private', {}, None)
            with self.assertRaises(RuntimeError) as caught:
                news.request_gemini('test-secret', 'prompt')
            self.assertEqual(opener.call_count, count)
            self.assertNotIn('test-secret', str(caught.exception))

    @patch.dict(os.environ, {'GEMINI_API_KEY': ''})
    @patch('generate_news.request_gemini')
    def test_missing_key_never_calls_api(self, request):
        with self.assertRaises(RuntimeError):
            news.main()
        request.assert_not_called()

    @patch.dict(os.environ, {'GEMINI_API_KEY': 'test'})
    @patch('generate_news.write_outputs')
    @patch('generate_news.request_gemini', return_value={})
    def test_failure_preserves_feed(self, request, write):
        with self.assertRaises(RuntimeError):
            news.main()
        self.assertEqual(request.call_count, 2)
        write.assert_not_called()

    def test_write_roundtrip(self):
        feed = news.build_feed(sections(), NOW)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'feed.json'
            news.write_outputs(feed, response()['candidates'][0]['groundingMetadata'], output)
            self.assertEqual(json.loads(output.read_text()), feed)
            self.assertTrue((output.parent / 'index.html').exists())
            self.assertFalse(output.with_suffix('.json.tmp').exists())


if __name__ == '__main__':
    unittest.main()
