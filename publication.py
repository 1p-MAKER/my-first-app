"""Public-feed freshness and byte-for-byte deployment verification helpers."""
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from news_content import JST, https_url, validate_feed

ROOT = Path(__file__).resolve().parent
MAX_PUBLIC_BYTES = 1_000_000


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fingerprint(model, site_url):
    digest = hashlib.sha256((model + "\n" + site_url).encode())
    for name in ("generate_news.py", "gemini_client.py", "news_content.py", "publication.py", "availability.py"):
        digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()


def fetch_json(url):
    if not https_url(url):
        raise ValueError("公開URLはHTTPSが必要です。")
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=15) as response:
        if not https_url(response.geturl()) or response.headers.get_content_type() != "application/json":
            raise ValueError("公開先のHTTPSまたはContent-Typeが不正です。")
        data = response.read(MAX_PUBLIC_BYTES + 1)
    if len(data) > MAX_PUBLIC_BYTES:
        raise ValueError("公開JSONが1MBを超えています。")
    return json.loads(data)


def validate_manifest(manifest, feed):
    if not isinstance(manifest, dict) or manifest.get("version") != 2:
        raise ValueError("公開マニフェストの版が不正です。")
    if manifest.get('status') == 'unavailable':
        from availability import notice_feed
        generated = datetime.fromisoformat(manifest['generated_at'].replace('Z', '+00:00'))
        try:
            notice_url = feed[0]['redirectionUrl']
        except (IndexError, KeyError, TypeError):
            raise ValueError('更新失敗の案内が不正です。') from None
        if not https_url(notice_url):
            raise ValueError('更新失敗の案内URLはHTTPSが必要です。')
        if feed != notice_feed(generated, notice_url):
            raise ValueError('更新失敗の案内が不正です。')
    else:
        validate_feed(feed)
    expected = hashlib.sha256(json_bytes(feed)).hexdigest()
    if manifest.get("feed_sha256") != expected:
        raise ValueError("公開フィードとマニフェストが一致しません。")
    if any(x["updateDate"] != manifest.get("generated_at") for x in feed):
        raise ValueError("生成日時が一致しません。")


def _current_edition(site_url, now):
    """Return the validated public edition and timestamp, or ``None`` on any doubt."""
    try:
        manifest = fetch_json(site_url.rstrip('/') + '/manifest.json')
        feed = fetch_json(site_url.rstrip('/') + '/feed.json')
        validate_manifest(manifest, feed)
        generated = datetime.fromisoformat(manifest['generated_at'].replace('Z', '+00:00'))
        if (manifest.get('status') == 'unavailable'
                or generated.astimezone(JST).date() != now.astimezone(JST).date()
                or not -timedelta(minutes=5) <= now - generated <= timedelta(hours=18)):
            return None
        return manifest, feed, generated
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def healthy_edition_published(site_url, now):
    """Check freshness without tying preservation to the current code fingerprint.

    A valid edition already read by Alexa must survive a later failed retry, even
    when the code or model changed after that edition was generated.
    """
    return _current_edition(site_url, now) is not None


def already_published(site_url, now, expected_fingerprint):
    """Check whether today's public edition matches this generator exactly."""
    current = _current_edition(site_url, now)
    return bool(current and current[0].get('fingerprint') == expected_fingerprint)
