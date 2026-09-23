# Alexa Morning News

平日05:45にGoogle Cloud SchedulerがGitHub Actionsを起動し、Gemini API + Google Searchで5〜7分を目安に日本語ニュースを作成します。GitHub Actionsにも06:00・06:25・06:45 JSTの回復実行があり、GitHub Pagesの `feed.json` をAlexaが07:15に読み上げる構成です。OpenAI APIは使いません。

プロジェクトフォルダ: `/Users/the1/projects/alexa-morning-news`

## 現在の運用

- GitHub Actions Secret `GEMINI_API_KEY` を使い、Gemini APIだけで生成します。
- GitHub PagesはActionsから `docs/` を配信します。公開先は [feed.json](https://1p-maker.github.io/my-first-app/feed.json)、出典付きの原稿は[ニュースページ](https://1p-maker.github.io/my-first-app/)です。
- Google Cloud Schedulerの `alexa-news-dispatch` が平日05:45 JSTに `repository_dispatch` を送り、Actionsの予備スケジュールは06:00・06:25・06:45 JSTです。
- AlexaのフィードURLは **https://1p-maker.github.io/my-first-app/feed.json**、再生は平日07:15の定型アクションです。

### SchedulerのGitHub認証

`repository_dispatch` に使うFine-grained personal access tokenは、GitHub公式仕様上、このリポジトリの **Contents: read and write** が必要です。[GitHubのRepository Dispatch仕様](https://docs.github.com/en/rest/repos/repos#create-a-repository-dispatch-event)を参照してください。対象リポジトリを `1p-MAKER/my-first-app` に限定し、有効期限を設定した専用トークンを使ってください。個人の `gh` CLI認証トークンや他用途と共用する広い権限のトークンは使わないでください。

Cloud SchedulerのHTTPターゲットに設定した任意の `Authorization` ヘッダーは、Secret Manager参照ではなくジョブ設定の一部です。Cloud Schedulerの閲覧・編集権限を絞り、専用トークンへの置き換えと期限前の更新を管理してください。Secret Managerにだけ保管する構成にするには、SchedulerからOIDCで呼び出すCloud Run等の中継処理が別途必要です。

再構築時は、GitHub側に `GEMINI_API_KEY` を登録し、PagesのSourceを **GitHub Actions** に設定します。`Deploy from a branch` は選びません。Actionsの手動実行は [Update Alexa morning news](https://github.com/1p-MAKER/my-first-app/actions/workflows/update-news.yml) からmainを選び、通常はforceをオフにします。Alexa Developer ConsoleのフィードはContent type **Text**、Update frequency **Daily**、Genre **News** を使います。開発テストとEcho実機の読み上げ確認後、必要なら月〜金07:15の定型アクションを設定します。一般公開には別途申請が必要です。

Alexa側のキャッシュで更新反映に時間がかかる場合があります。URLに `/docs` は付きません。ほかのニュース提供元を有効にすると総再生時間が増えます。

## 仕組み

```text
05:45 JST ─ Cloud Schedulerから起動。公開済みの当日版があるか確認
               ├ 有効な当日版あり → APIを使わず終了
               └ 未更新 → Gemini検索調査 → 検索なしでJSON原稿編集
                           → 検証 → 生成物保存 → Pages配信 → 公開結果照合
                           → 公開済み原稿をGitに保存
06:00 / 06:25 / 06:45 JST ─ GitHub Actionsの回復実行。未更新の場合だけ生成・配信
07:15 JST ─ Alexa定型アクションで読み上げ
```

- 平日は月〜金。祝日も実行します。Cloud Schedulerが05:45に起動し、06:00・06:25・06:45にGitHub Actionsが回復確認します。正常な当日版の再生成はしません。
- 通常は **調査1回 + 編集1回** のGemini呼び出し。文字数・出典ID・日時等に不備があれば、失敗した原稿そのものと具体的な修正理由を渡し、同じ検索根拠で最大4回再編集します。分野別の文字数を指定し、機械的な途中切断はしません。
- 検索根拠がない場合の調査再試行は1回。一時的な通信障害は各リクエスト最大3試行。全体の生成ジョブは15分で打ち切ります。再試行も課金対象になり得ます。
- 当日版の判定は、公開日時・本文のハッシュ・生成コード・モデル・配信URLの一致で行います。古い本文を新しい日付に付け替えません。forceをオンにすると公開済みでも再生成します。
- 同じブランチの実行は直列化。main以外での手動実行は生成物の保存までで、Pages配信・mainへの書き込みはしません。
- **配信はGitへの保存に依存しません。** `archive` のpushに失敗しても、成功した配信は取り消しません。
- GitHubのscheduleは遅延や取りこぼしがあり、07:15までの完了を保証しません。Cloud Schedulerを主起動、GitHub scheduleを回復用として併用しています。公開リポジトリでは60日間活動がないと停止される場合があります。ActionsとSchedulerの有効状態を定期的に確認してください。

### 外部スケジューラからの起動

ワークフローは `update-news` タイプの `repository_dispatch` を受け付けます。現在はGoogle Cloud Schedulerが平日05:45 JSTに次のGitHub APIを呼びます。正常な当日版が既にあれば、追加のGemini API呼び出しは行いません。

```text
POST https://api.github.com/repos/1p-MAKER/my-first-app/dispatches
Accept: application/vnd.github+json
Authorization: Bearer <repository-scoped fine-grained GitHub token>
Content-Type: application/json

{"event_type":"update-news"}
```

Cloud SchedulerのカスタムヘッダーはSecret Managerからの参照ではなく、ジョブ設定に値を持ちます。ジョブ閲覧・編集権限を限定し、期限付きの専用トークンを使ってください。GitHub scheduleには遅延・欠落リスクが残ります。

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

**生成失敗**ならmainでは日付付きの更新失敗案内（1項目）を公開します。当日版が正常なら、コードやモデルの指紋が変わっていてもそれを保持します。案内は `status: unavailable` であり、当日ニュースの成功判定から除外するため後続実行で再生成します。案内のリンク・指紋にはActions Variablesの `SITE_URL` を使います。`health` ジョブは失敗にしてGitHubの失敗通知を維持します。ローカル・作業ブランチでは失敗案内を公開しません。`deploy` で公開照合だけが失敗した場合は、配信自体は完了している可能性があります。

Cloud Schedulerが停止した場合もGitHub Actionsのscheduleが回復機会になりますが、両方のスケジューラが停止・遅延すると更新されません。静的Pagesには前回版が残るため、定時到着を完全保証する構成ではありません。

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
