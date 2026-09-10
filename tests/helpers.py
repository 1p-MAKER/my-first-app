import json
from datetime import datetime, timezone
from news_content import TOPICS

NOW = datetime(2026, 9, 10, 21, tzinfo=timezone.utc)


def draft():
    # Fictional, explicitly labeled offline fixtures, never public news.
    filler = 'これは動作確認専用の架空記事です。実際のニュースや価格ではありません。'
    topics = {key: {'status': 'verified', 'text': label + '。' + filler * 4,
                    'source_ids': [1]} for key, label in TOPICS.items()}
    return {'topics': topics, 'events': [{'at': '2026-09-11T09:00:00+09:00',
                                         'text': '架空のテスト予定です。', 'source_ids': [1]}]}


def response(text, grounded=False):
    candidate = {'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}
    if grounded:
        candidate['groundingMetadata'] = {
            'webSearchQueries': ['架空のテスト検索'],
            'groundingChunks': [{'web': {'uri': 'https://example.com/source', 'title': '架空の検証資料'}}],
            'groundingSupports': [{'segment': {'text': text}, 'groundingChunkIndices': [0]}],
            'searchEntryPoint': {'renderedContent': '<a href="https://google.com/search?q=test" target="_blank">Google Search</a>'},
        }
    return {'candidates': [candidate], 'usageMetadata': {'promptTokenCount': 100, 'totalTokenCount': 200}}


class FakeClient:
    def __init__(self, drafts=None, searches=None):
        self.drafts = iter(drafts or [draft()])
        self.searches = iter(searches or [response('架空の確認資料。', True)])
        self.calls = []
        self.attempts = 0
        self.usage = []

    def generate(self, prompt, *, search=False, schema=None):
        self.attempts += 1
        self.calls.append({'search': search, 'schema': schema, 'prompt': prompt})
        return next(self.searches) if search else response(json.dumps(next(self.drafts)))
