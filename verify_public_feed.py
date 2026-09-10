"""Check that this run's feed AND manifest are actually public after deployment."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

from news_content import JST

from publication import fetch_json, validate_manifest


def verify(site_url, expected_dir, *, attempts=6):
    expected_feed = json.loads((expected_dir / 'feed.json').read_text(encoding='utf-8'))
    expected_manifest = json.loads((expected_dir / 'manifest.json').read_text(encoding='utf-8'))
    validate_manifest(expected_manifest, expected_feed)
    for attempt in range(attempts):
        try:
            feed = fetch_json(site_url.rstrip('/') + '/feed.json')
            manifest = fetch_json(site_url.rstrip('/') + '/manifest.json')
            validate_manifest(manifest, feed)
            if feed == expected_feed and manifest == expected_manifest:
                print('公開HTTPSフィードと生成日時・原稿が今回の生成物と一致しました。')
                return
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
        if attempt + 1 < attempts:
            time.sleep(10)
    raise RuntimeError('公開JSONが今回の生成物と一致しません。Pages設定・反映待ち・URLを確認してください。')


def preflight(site_url, expected_dir, now=None):
    """A retry of an older run must never roll the live morning edition back."""
    now = now or datetime.now(timezone.utc)
    candidate = json.loads((expected_dir / 'manifest.json').read_text(encoding='utf-8'))
    feed = json.loads((expected_dir / 'feed.json').read_text(encoding='utf-8'))
    validate_manifest(candidate, feed)
    generated = datetime.fromisoformat(candidate['generated_at'].replace('Z', '+00:00'))
    if (generated.astimezone(JST).date() != now.astimezone(JST).date()
            or not -timedelta(minutes=5) <= now - generated <= timedelta(hours=6)):
        raise RuntimeError('生成物が古いため配信しません。Run workflowで最新ニュースを生成してください。')
    try:
        current = fetch_json(site_url.rstrip('/') + '/manifest.json')
    except HTTPError as exc:
        if exc.code == 404:
            return  # First deployment, before a manifest exists.
        raise RuntimeError('現在の公開状態を確認できません。配信を中止します。') from None
    current_time = datetime.fromisoformat(current['generated_at'].replace('Z', '+00:00'))
    if current_time > generated:
        raise RuntimeError('より新しいニュースが公開済みです。古い実行からの上書きを中止します。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-deploy', action='store_true')
    args = parser.parse_args()
    try:
        if args.before_deploy:
            preflight(os.environ['SITE_URL'], Path('expected-news'))
        else:
            verify(os.environ['PAGE_URL'], Path('expected-news'))
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
