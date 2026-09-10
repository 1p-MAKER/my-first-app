# Alexa Morning News with Gemini

Gemini API + Google Searchで過去48時間のニュースを調べ、日本語のAlexa Flash Briefingを生成します。OpenAI APIは使用しません。

## 最短セットアップ

修正ブランチをレビューし、mainへマージしてから進めてください。ブランチのpushだけでは定期実行や本番配信は変わりません。

1. [Actions Secrets](https://github.com/1p-MAKER/my-first-app/settings/secrets/actions) → New repository secret → 名前を `GEMINI_API_KEY` にし、有料枠のGemini APIキーを登録。キーをチャットやファイルに貼らないでください。
2. [Pages設定](https://github.com/1p-MAKER/my-first-app/settings/pages) → Build and deployment → Sourceを **GitHub Actions** に設定。以前の「Deploy from a branch / main / docs」は使いません。配信対象は引き続き `docs/` です。GITHUB_TOKENでのコミットは通常のPagesビルドを起動しないため、専用のPagesデプロイ処理を使います。
3. [Actions](https://github.com/1p-MAKER/my-first-app/actions/workflows/update-news.yml) → **Update Alexa morning news** → Run workflow → `main` → Run workflow。
4. `update-news` と `deploy` の両方が成功し、[feed.json](https://1p-maker.github.io/my-first-app/feed.json) が最新の5項目になったことを確認。デプロイ後にも公開JSONと今回の生成物の一致を自動検証します。
5. [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask) → Create Skill → Japanese (JP) → Flash Briefing。フィードを追加し、Content typeはText、Update frequencyはDaily、GenreはNews、Feed URLは次を入力します。

   `https://1p-maker.github.io/my-first-app/feed.json`

6. Consoleで必要な名前・説明・エラーメッセージ等を入力し、開発テストを有効にします。同じAmazonアカウントのAlexaアプリで開発中のスキルを有効にし、フラッシュニュースの提供元に追加。まずEchoで手動再生を確認します。一般公開には別途申請が必要です。
7. Alexaアプリの定型アクションを **月〜金 07:15 → ニュース／フラッシュニュースを再生 → 使用するEcho** に設定。ほかの提供元も有効なら合計の再生時間は長くなります。

Alexaはフィードをキャッシュするため、更新が再生に反映されるまで最大30分程度を見込んでください。公開URLには `/docs` を付けません。カスタムドメインを設定する場合は生成コードの `REPO_URL` も変更してください。

## 動作と時刻

- cron `0 21 * * 0-4`：日〜木21:00 UTC = 月〜金06:00 JST。祝日も動きます。
- GitHubのscheduleはmain上で動きます。混雑時の遅延・取りこぼしがあり、06:00開始や07:15までの完了は保証されません。公開リポジトリでは60日間活動がないと定期実行が停止される場合もあります。Actionsの失敗通知を有効にしてください。
- workflow_dispatchで手動実行できます。main以外では生成物を `alexa-news` artifactとして保存するだけで、コミット・本番配信しません。新しいworkflow_dispatch設定はmainにマージ後に利用します。
- mainでは検証済みのfeed・出典ページ・grounding情報をコミットし、同じ `docs/` をPagesに配信。同一ブランチの実行を直列化します。
- mainのブランチ保護がbotのpushを禁止する場合、保存ステップで失敗します。保護ルールは自動変更しません。キー登録だけではこの制限を回避できません。
- 生成・検証失敗時は既存feedを維持してジョブを失敗にします。古いニュースを新しい日付に付け替えません。Alexaは7日より古い項目を無視します。

## APIと原稿

2026-09-10にGoogle公式資料で `gemini-3.8-flash` とGoogle Search対応を確認。Python 3.12の標準ライブラリで、公式に掲載されているREST `v1beta/models/{model}:generateContent` に `tools: [{"google_search": {}}]` を送信します。認証は `x-goog-api-key` ヘッダー。SDKバージョンへの依存はありません。Generate Contentは公式資料上Legacy分類ですが、掲載中のAPIを明示して使用しています。元のInteractions形式そのものが誤りという意味ではありません。

モデルはActions Variablesの `GEMINI_MODEL` で変更可能。互換性は変更時に再確認してください。タイムアウトは1リクエスト120秒、429・一時的なサーバー／ネットワーク障害を最大3回試行。原稿不正時の再生成は最大1回です。再試行には追加料金が発生し得ます。

現在の日本時間、過去48時間の範囲、今後24時間の終端を毎回プロンプトに付与します。検索クエリ・Web出典・引用対応情報がない応答や未完了応答を拒否します。ただし検索根拠の存在は個々の事実や全カテゴリの取材品質を保証しないため、初回は出典ページと読み上げを確認してください。

1. 今朝の3大ニュース
2. 日本・沖縄
3. 世界情勢と重要な論点の2つの視点
4. 株・為替・金利・金・原油、経済への影響
5. 新商品・新サービス・AI／テック、背景、今後24時間の予定（日本時間）

全体1,800〜2,400文字を検証し、毎分約350文字として約5〜7分を目指します。実際の長さはEchoの読み方・項目間の音で変わります。短い文で説明し、休場・未確認値・不明な予定を推測で埋めないよう指定しています。

## 出力と検証

- `docs/feed.json`：常に5件。必須項目 `uid`, `updateDate`, `titleText`, `mainText`, `redirectionUrl`。UTC日時、内容変更時に変わるUID、HTTPSリンク。
- `mainText`：各4,300文字以内（UTF-16換算でも上限確認）。空文字・不正型・URL・HTML等・重複本文を拒否。長すぎる原稿は切り捨てず再生成するため、末尾の予定が消えません。
- `docs/index.html`：原稿、出典リンク、APIが返すGoogle Search Suggestionsを表示。AlexaのRead Moreリンク先。
- `docs/grounding.json`：APIの検索・引用対応情報。生成JSONの元テキストに対する対応情報であり、整形後本文の文字位置とは限りません。
- `tests/`：通信を模したテスト。実API・料金・実機再生の成功とは別です。

## ローカル確認

```sh
python3 -m unittest discover -s tests -v
# GEMINI_API_KEY を安全な環境変数管理で設定した上で実行
python3 generate_news.py
```

追加パッケージのインストールは不要です。APIキーをコードやGit履歴に保存しないでください。

## 困った場合

- Secret missing：Secret名と登録先を確認。
- HTTP 400 / 403 / 404：モデル名、キーのAPI制限、対象プロジェクト・APIの有効化を確認。
- HTTP 429：クォータ・課金状態・実行頻度を確認。無制限な再実行はしません。
- Invalid grounded news：検索根拠、JSON、文字数等の検証に不合格。既存feedは保持。手動実行してartifactを確認。
- Pages deploy失敗：SourceがGitHub Actionsか、github-pages環境のmain配信許可、Pagesの利用条件を確認。
- 公開検証失敗：配信自体が成功している可能性があります。URLのJSON、Content-Type、生成artifactを確認してから再実行。

## 公式資料

- [Gemini Google Search / REST](https://ai.google.dev/gemini-api/docs/generate-content/google-search)
- [GITHUB_TOKENとPagesビルド](https://docs.github.com/en/actions/concepts/security/github_token)
- [Pagesカスタムワークフロー](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Actionsスケジュール](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [Alexa Feed仕様](https://developer.amazon.com/en-US/docs/alexa/flashbriefing/flash-briefing-skill-api-feed-reference.html)
