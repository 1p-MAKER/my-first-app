"""Publish an explicit dated notice when today's news cannot be validated."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from news_content import JST, SITE_URL, iso_utc
from publication import already_published, fingerprint, json_bytes
from gemini_client import DEFAULT_MODEL


def notice_feed(now):
    local = now.astimezone(JST)
    text = (f'{local.month}月{local.day}日の朝のAIニュースは、更新処理に問題があり、'
            '最新の原稿を用意できませんでした。古いニュースの再放送は行いません。'
            '復旧後にもう一度フラッシュニュースをお試しください。')
    return [{'uid': 'news-unavailable-' + now.strftime('%Y%m%dT%H%M%SZ'),
             'updateDate': iso_utc(now), 'titleText': '朝ニュースの更新状況',
             'mainText': text, 'redirectionUrl': SITE_URL}]


def publish_notice(output=Path('docs'), now=None):
    now = now or datetime.now(timezone.utc)
    identity = fingerprint(os.getenv('GEMINI_MODEL', DEFAULT_MODEL), SITE_URL)
    if already_published(SITE_URL, now, identity):
        return False  # A failed forced rerun must not replace today's valid news.
    feed = notice_feed(now)
    manifest = {'version': 2, 'status': 'unavailable', 'generated_at': iso_utc(now),
                'fingerprint': identity, 'feed_sha256': hashlib.sha256(json_bytes(feed)).hexdigest()}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'feed.json').write_bytes(json_bytes(feed))
    (output / 'manifest.json').write_bytes(json_bytes(manifest))
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>更新状況</title>'
                                     + '<h1>朝ニュースの更新状況</h1><p>' + feed[0]['mainText'] + '</p>', encoding='utf-8')
    return True


if __name__ == '__main__':
    changed = publish_notice()
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f'changed={str(changed).lower()}\n')
