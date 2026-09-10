"""Verify deployed content rather than treating a deployment banner as success."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request


def main():
    expected = json.loads(Path('expected-news/feed.json').read_text(encoding='utf-8'))
    url = os.environ['PAGE_URL'].rstrip('/') + '/feed.json'
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                if response.headers.get_content_type() == 'application/json' and json.load(response) == expected:
                    print('Public HTTPS JSON feed matches the generated artifact.')
                    return
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        if attempt < 5:
            time.sleep(10)
    raise RuntimeError('Public feed is unavailable, has the wrong MIME type, or differs from this run')


if __name__ == '__main__':
    main()
