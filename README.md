# Alexa Morning News

平日06:00にGemini API + Google Searchでニュースを調査し、5〜7分を目安に日本語原稿を作成。GitHub Pagesの `feed.json` をAlexaが07:15に読み上げる構成です。OpenAI APIは使いません。

プロジェクトフォルダ: `/Users/the1/projects/alexa-morning-news`

## 最短セットアップ

1. 作業ブランチ `codex/alexa-news-reliability` をレビューし、mainへ反映します。ブランチのpushだけでは本番や定期実行は変わりません。
2. [GitHub Actions Secrets](https://github.com/1p-MAKER/my-first-app/settings/secrets/actions) → New repository secret → **GEMINI_API_KEY** に、有料枠のGemini APIキーを登録。キーをチャット・コード・Git履歴に貼らないでください。
3. [Pages設定](https://github.com/1p-MAKER/my-first-app/settings/pages) → Build and deployment → Sourceを **GitHub Actions** にします。配信元は `docs/` ですが、「Deploy from a branch」は選びません。
4. [Actions](https://github.com/1p-MAKER/my-first-app/actions/workflows/update-news.yml) → **Update Alexa morning news** → Run workflow → **main**。初回はforceをオフのまま実行できます。
5. `generate` と `deploy` の成功、および [feed.json](https://1p-maker.github.io/my-first-app/feed.json) の更新日時と5項目を確認。出典と原稿は[ニュースページ](https://1p-maker.github.io/my-first-app/)で確認できます。
6. [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)で日本語の **Flash Briefing** スキルを作成し、フィードを追加します。

   - Content type: **Text**
   - Update frequency: **Daily**
   - Genre: **News**
   - Feed URL: **https://1p-maker.github.io/my-first-app/feed.json**

7. Consoleの必要項目を保存し、開発テストを有効にします。同じAmazonアカウントのAlexaアプリで開発中スキルを有効にし、フラッシュニュースの提供元へ追加。Echoで手動再生を確認してから、**月〜金07:15 → ニュースを再生 → 使用するEcho** の定型アクションを設定します。一般公開は別途申請が必要です。

Alexa側のキャッシュにより、更新反映に30分程度かかることがあります。URLに `/docs` は付きません。ほかのニュース提供元を有効にすると総再生時間が増えます。

## 仕組み

```text
06:00 JST ─ 公開済みの当日版があるか確認
               ├ 有効な当日版あり → APIを使わず終了
               └ 未更新 → Gemini検索調査 → 検索なしでJSON原稿編集
                           → 検証 → 生成物保存 → Pages配信 → 公開結果照合
                           → 公開済み原稿をGitに保存
06:25 JST ─ もう一度公開を確認。未更新の場合だけ生成・配信
07:15 JST ─ Alexa定型アクションで読み上げ
```

- 平日は月〜金。祝日も実行します。UTC cronは `0 21 * * 0-4` と `25 21 * * 0-4`。
- 通常は **調査1回 + 編集1回** のGemini呼び出し。文字数・出典ID・日時等に不備があれば、同じ検索根拠を使って編集だけを最大2回やり直します。
- 検索根拠がない場合の調査再試行は1回。一時的な通信障害は各リクエスト最大3試行。全体の生成ジョブは15分で打ち切ります。再試行も課金対象になり得ます。
- 当日版の判定は、公開日時・本文のハッシュ・生成コード・モデル・配信URLの一致で行います。古い本文を新しい日付に付け替えません。forceをオンにすると公開済みでも再生成します。
- 同じブランチの実行は直列化。main以外での手動実行は生成物の保存までで、Pages配信・mainへの書き込みはしません。
- **配信はGitへの保存に依存しません。** `archive` のpushに失敗しても、成功した配信は取り消しません。
- GitHubのscheduleは遅延や取りこぼしがあり、06:00開始・07:15までの完了を保証しません。公開リポジトリでは60日間活動がないと停止される場合があります。公開後のGit保存は履歴維持にも使いますが、Actionsの失敗通知と有効状態も確認してください。

## 原稿の内容と検証

1. 今朝の3大ニュース
2. 日本・沖縄
3. 世界情勢と同じ重要論点に対する2つの視点
4. 株・為替・金利・金・原油と経済への影響
5. 新商品・新サービス・AI／テック・背景・今後24時間の予定

各分野を必須フィールドにし、確認済みとする原稿には実際の検索出典IDを要求します。根拠不足なら定型の「確認できませんでした」に置き換えます。予定は日時と時差を検査して日本時間の案内を組み立てます。

Alexaフィードは5項目、必須5フィールド、UTC日時、重複しないUID、HTTPSリンク。各本文はUTF-16換算でも4,300文字以下、全体1,800〜2,400文字を検証します。長すぎる原稿を切り捨てません。5〜7分は毎分約350文字からの目安で、実際の長さはEchoで確認してください。

検索出典の存在・ID・項目・文字数・時刻範囲はコードで検証できますが、記事の正確さ、選定の良さ、各原稿と出典の意味上の一致までは保証できません。初回は出典ページと読み上げを確認してください。

## 出力と復旧

| ファイル・ジョブ | 用途 |
|---|---|
| `docs/feed.json` | Alexa向け原稿 |
| `docs/index.html` | 原稿、分野別出典、調査時の引用、Google Search Suggestions |
| `docs/manifest.json` | 生成日時・本文ハッシュ・モデル・未確認分野・API使用量 |
| `work/research.json` | ローカル調査結果。Git対象外 |
| `work/draft.json` | ローカルの検証済み構造化原稿。Git対象外 |
| `alexa-news` artifact | 検証済み生成物。7日保持 |
| `news-diagnostics` artifact | 生成失敗時に取得済みの調査情報。3日保持 |

**公開だけ失敗した場合**はActionsの **Re-run failed jobs** を使います。成功した生成ジョブのartifactを再利用し、検索からやり直しません。生成物が当日の6時間以内で、より新しい版が公開されていない場合に限り再配信します。古い場合はRun workflowで再生成してください。

**generate失敗**なら既存の公開版を維持。Secret、APIの課金・制限、Actionsログを確認します。`deploy` で公開照合だけが失敗した場合は、配信自体は完了している可能性があります。

**archiveだけ失敗**ならニュース配信は確認済みです。mainのブランチ保護・書き込み権限・他のpushとの競合を確認し、そのジョブだけ再実行してください。保護設定は自動変更しません。

## ローカル作業

Python 3.12、追加パッケージ不要です。

```sh
cd /Users/the1/projects/alexa-morning-news
python3 -m unittest discover -s tests -v
# GEMINI_API_KEYを安全な環境変数管理で設定後
python3 generate_news.py
```

`GEMINI_MODEL` でモデルを変更できます。標準は `gemini-3.8-flash`。カスタムドメインの場合はローカルの `SITE_URL` とActions Variablesの `SITE_URL`を実際のPages URLに合わせてください。

詳細な設計・失敗時の扱いは [SPEC.md](SPEC.md)、作業ルールは [AGENTS.md](AGENTS.md) に記載しています。

## APIの確認根拠

2026-09-10にGoogle公式モデル資料とAPIのDiscovery定義を確認。公式掲載の `v1beta/models/{model}:generateContent` を使います。調査は `google_search`、編集は `responseMimeType: application/json` + `responseJsonSchema`。APIキーは `x-goog-api-key` ヘッダーのみ。Generate Contentは公式資料でLegacyに分類されていますが、現在掲載されているAPIを使用しています。

- [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
- [Google Search grounding](https://ai.google.dev/gemini-api/docs/generate-content/google-search)
- [構造化出力](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [API Discovery定義](https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta)
- [Pagesカスタムワークフロー](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Actionsスケジュールの制約](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Alexa Feed仕様](https://developer.amazon.com/en-US/docs/alexa/flashbriefing/flash-briefing-skill-api-feed-reference.html)
