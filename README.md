# Alexa Morning News with Gemini

平日の朝に Gemini API + Google Search grounding で最新ニュースを生成し、Alexa Flash Briefing から読み上げるためのプロジェクトです。

## 構成

- 06:00 JST: GitHub Actions が起動
- Gemini 3.8 Flash + Google Search grounding で過去48時間を調査
- `docs/feed.json` を Alexa Flash Briefing 形式で更新
- 07:15 JST: Alexa の定型アクションから Flash Briefing を再生

OpenAI API は使用しません。

## 1. Gemini APIキーをGitHubに登録

GitHub repository > Settings > Secrets and variables > Actions > New repository secret

- Name: `GEMINI_API_KEY`
- Secret: Google AI Studio / Gemini API の有料枠で使用しているAPIキー

APIキーをコードや `feed.json` に直接書かないでください。

## 2. GitHub Pagesを有効化

GitHub repository > Settings > Pages

- Source: Deploy from a branch
- Branch: `main`
- Folder: `/docs`

保存後、Alexaに登録するフィードURLは次の形式になります。

`https://1p-maker.github.io/my-first-app/feed.json`

ブラウザでこのURLを開き、JSONが表示されることを確認してください。

## 3. 最初のニュースを生成

GitHub repository > Actions > Update Alexa morning news > Run workflow

成功すると `docs/feed.json` が5ブロックの最新ニュースに更新されます。

通常の自動実行は毎週、日〜木の21:00 UTCです。日本時間では翌日の月〜金 06:00です。

## 4. Alexa Flash Briefingを登録

Alexa Developer Console で Flash Briefing スキルを作成します。

推奨設定:

- Language: Japanese (JP)
- Feed name: 朝のAIニュース
- Content type: Text
- Feed URL: `https://1p-maker.github.io/my-first-app/feed.json`
- Update frequency: Daily
- Genre: News または Technology

開発中スキルとして自分のAlexaアカウントでテストし、Echoから再生できることを確認します。

## 5. Alexa定型アクション

Alexaアプリで定型アクションを作成します。

- 実行日時: 月〜金 07:15
- アクション: ニュース / フラッシュニュースを再生
- 再生デバイス: 使用するEcho

Flash Briefingのニュース提供元の順番で「朝のAIニュース」が有効になっていることも確認してください。

## ニュース構成

Alexa向けに最大5件のフィードとして出力します。

1. 今朝の3大ニュース
2. 日本・沖縄
3. 世界情勢 + 2つの視点
4. マーケット・経済 + なぜ重要か
5. 新商品・AI・テクノロジー + 背景 + 今後24時間の予定 + 今日ひとことで言うと

各項目はAlexa Flash Briefingのテキスト上限を安全に下回るよう最大4300文字に切り詰めます。

## 使用モデル

デフォルトは `gemini-3.8-flash` です。

変更する場合は `.github/workflows/update-news.yml` の `GEMINI_MODEL` を変更してください。

## 手動実行

ローカルでは次の環境変数を設定して実行できます。

```bash
export GEMINI_API_KEY="YOUR_API_KEY"
pip install -r requirements.txt
python generate_news.py
```

APIキーはGitにコミットしないでください。
