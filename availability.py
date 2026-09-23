"""Publish an explicit dated notice when today's news cannot be validated."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from news_content import JST, SITE_URL, iso_utc
from publication import healthy_edition_published, fingerprint, json_bytes
from gemini_client import DEFAULT_MODEL


def notice_feed(now, site_url=SITE_URL):
    local = now.astimezone(JST)
    text = (f'{local.month}月{local.day}日の朝のAIニュースは、更新処理に問題があり、'
            '最新の原稿を用意できませんでした。古いニュースの再放送は行いません。'
            '復旧後にもう一度フラッシュニュースをお試しください。')
    return [{'uid': 'news-unavailable-' + now.strftime('%Y%m%dT%H%M%SZ'),
             'updateDate': iso_utc(now), 'titleText': '朝ニュースの更新状況',
             'mainText': text, 'redirectionUrl': site_url}]


def publish_notice(output=Path('docs'), now=None, site_url=None):
    now = now or datetime.now(timezone.utc)
    site_url = (site_url or os.getenv('SITE_URL', SITE_URL)).rstrip('/') + '/'
    identity = fingerprint(os.getenv('GEMINI_MODEL', DEFAULT_MODEL), site_url)
    if healthy_edition_published(site_url, now):
        return False  # Never replace a valid edition with a failure notice.
    feed = notice_feed(now, site_url)
    manifest = {'version': 2, 'status': 'unavailable', 'generated_at': iso_utc(now),
                'fingerprint': identity, 'feed_sha256': hashlib.sha256(json_bytes(feed)).hexdigest()}
    files = {
        'index.html': ('<!doctype html><meta charset="utf-8"><title>更新状況</title>'
                       + '<h1>朝ニュースの更新状況</h1><p>' + feed[0]['mainText'] + '</p>').encode('utf-8'),
        'manifest.json': json_bytes(manifest),
        'feed.json': json_bytes(feed),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='news-notice-', dir=output.parent) as temporary:
        stage = Path(temporary)
        for name, content in files.items():
            (stage / name).write_bytes(content)
        output.mkdir(parents=True, exist_ok=True)
        # Prepare every file before replacing existing output; replace feed last.
        for name in ('index.html', 'manifest.json', 'feed.json'):
            (stage / name).replace(output / name)
    return True


if __name__ == '__main__':
    changed = publish_notice()
    if output_path := os.environ.get('GITHUB_OUTPUT'):
        with open(output_path, 'a', encoding='utf-8') as output:
            output.write(f'changed={str(changed).lower()}\n')
