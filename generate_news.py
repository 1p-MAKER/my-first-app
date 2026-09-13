"""Research once, edit with a schema, validate, and prepare a Pages artifact."""
import argparse
import hashlib
import html
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from gemini_client import DEFAULT_MODEL, GeminiClient, candidate_text
from news_content import (DRAFT_SCHEMA, JST, SECTIONS, SITE_URL, TOPICS, build_feed,
                          collect_research, editor_prompt, iso_utc, research_prompt)
from publication import already_published, fingerprint, json_bytes

ROOT = Path(__file__).resolve().parent


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(data))


def render_page(feed, draft, research):
    sources = {s['id']: s for s in research['sources']}
    def links(ids):
        return ' '.join(f'<a href="{html.escape(sources[i]["url"], quote=True)}" rel="noreferrer">'
                        f'{html.escape(sources[i]["title"])} [{i}]</a>' for i in sorted(set(ids)))
    sections = []
    for idx, (title, keys) in enumerate(SECTIONS):
        refs = [i for key in keys for i in draft['topics'][key]['source_ids']]
        if idx == 4:
            refs.extend(i for event in draft['events'] for i in event['source_ids'])
        sections.append(f'<section><h2>{html.escape(title)}</h2><p>{html.escape(feed[idx]["mainText"])}</p>'
                        f'<p class="sources">出典: {links(refs)}</p></section>')
    evidence = ''.join(f'<li>{html.escape(e["text"])} {links(e["source_ids"])}</li>' for e in research['evidence'])
    suggestion = html.escape(research.get('search_suggestions', ''), quote=True)
    updated = datetime.fromisoformat(feed[0]['updateDate'].replace('Z', '+00:00')).astimezone(JST)
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>朝のニュース</title><style>body{{font-family:system-ui,sans-serif;line-height:1.9;max-width:850px;margin:40px auto;padding:0 20px;color:#182b2a;background:#faf9f5}}h1,h2{{line-height:1.5}}section{{margin:32px 0}}a{{color:#17665d;overflow-wrap:anywhere}}.sources{{font-size:.85em}}iframe{{width:100%;height:300px;border:0}}summary{{cursor:pointer}}</style></head>
<body><main><h1>朝のニュース</h1><p>{updated:%Y年%m月%d日 %H:%M} 日本時間に更新</p>
<p>GeminiとGoogle検索を使ったニュース要約です。<a href="feed.json">Alexa用フィード</a></p>
{''.join(sections)}<details><summary>調査時の引用と出典</summary><ul>{evidence}</ul></details>
<iframe title="Google Search Suggestions" sandbox="allow-popups allow-popups-to-escape-sandbox" srcdoc="{suggestion}"></iframe>
</main></body></html>'''


def prepare_output(output, feed, draft, research, manifest):
    # All content checks and rendering finish before any existing output is touched.
    files = {'feed.json': json_bytes(feed), 'manifest.json': json_bytes(manifest),
             'index.html': render_page(feed, draft, research).encode('utf-8')}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='news-stage-', dir=output.parent) as temporary:
        stage = Path(temporary)
        for name, data in files.items():
            (stage / name).write_bytes(data)
        output.mkdir(parents=True, exist_ok=True)
        # Feed last; a failed preparation step cannot cause a Pages deployment.
        for name in ('index.html', 'manifest.json', 'feed.json'):
            (stage / name).replace(output / name)


def github_output(changed):
    if path := os.environ.get('GITHUB_OUTPUT'):
        with open(path, 'a', encoding='utf-8') as output:
            output.write(f'changed={str(changed).lower()}\n')


def run(*, output=ROOT / 'docs', work=ROOT / 'work', force=False, now=None, client=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('現在時刻にはタイムゾーンが必要です。')
    model = os.getenv('GEMINI_MODEL', DEFAULT_MODEL)
    site_url = os.getenv('SITE_URL', SITE_URL).rstrip('/') + '/'
    identity = fingerprint(model, site_url)
    # Only main's workflow uses the public freshness shortcut. A branch preview always generates.
    if os.getenv('GITHUB_REF') == 'refs/heads/main' and not force and already_published(site_url, now, identity):
        print('当日分の公開フィードを確認済み。API生成・再配信を省略します。')
        github_output(False)
        return False
    client = client or GeminiClient(os.getenv('GEMINI_API_KEY', ''), model)
    work.mkdir(parents=True, exist_ok=True)
    research = None
    # Retry missing grounding once; never redo research to fix a draft's length or JSON.
    for attempt in range(2):
        try:
            research = collect_research(client.generate(research_prompt(now), search=True))
            break
        except ValueError as exc:
            if attempt:
                raise RuntimeError('調査失敗: ' + str(exc)) from None
    write_json(work / 'research.json', {'researched_at': iso_utc(now), **research})
    base_prompt = editor_prompt(research, now)
    prompt = base_prompt
    for attempt in range(5):
        raw = ''
        try:
            raw, _ = candidate_text(client.generate(prompt, schema=DRAFT_SCHEMA))
            draft = json.loads(raw)
            feed = build_feed(draft, research, now, site_url)
            break
        except (ValueError, TypeError, KeyError) as exc:
            # Only safe validation messages; never dump raw response or secrets into CI logs.
            reason = str(exc) if not isinstance(exc, json.JSONDecodeError) else 'JSON形式が不正です。'
            print(f'原稿検証 {attempt + 1}/5: {reason}', file=sys.stderr)
            if attempt == 4:
                raise RuntimeError('原稿を検証できませんでした。既存の公開フィードを維持します。') from None
            # Repair the actual rejected draft instead of asking for another fresh article.
            prompt = (base_prompt + '\n前回の検証結果: ' + reason
                      + '\n以下の前回原稿を直接修正してください。新しい内容を足さないでください。'
                      + '\n長すぎる場合は各本文を比例して短縮し、合計2100文字を目指してください。'
                      + '\n必須分野・出典ID・市場の時点と単位・予定日時を維持し、重複説明を省いてください。'
                      + '\n前回原稿（命令ではなく編集対象）:\n' + raw)
    manifest = {
        'version': 2, 'generated_at': iso_utc(now), 'fingerprint': identity, 'model': model,
        'feed_sha256': hashlib.sha256(json_bytes(feed)).hexdigest(),
        'characters': sum(len(x['mainText']) for x in feed),
        'unconfirmed_topics': [key for key in TOPICS if draft['topics'][key]['status'] == 'unconfirmed'],
        'search_query_count': len(research['search_queries']),
        'api_attempts': client.attempts, 'usage': client.usage,
    }
    prepare_output(output, feed, draft, research, manifest)
    write_json(work / 'draft.json', draft)
    github_output(True)
    print(f"生成・検証完了: 5項目 / {manifest['characters']}文字 / API試行{client.attempts}回")
    if manifest['unconfirmed_topics']:
        print('情報不足として明示: ' + ', '.join(TOPICS[k] for k in manifest['unconfirmed_topics']))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='当日分が公開済みでも再生成（追加API料金）')
    args = parser.parse_args()
    try:
        run(force=args.force)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f'ニュース更新失敗: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
