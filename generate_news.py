import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from google import genai

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
OUTPUT = Path("docs/feed.json")
REPO_URL = "https://github.com/1p-MAKER/my-first-app"
JST = ZoneInfo("Asia/Tokyo")

PROMPT = r'''
あなたは日本向けの朝のニュース編集者です。Google検索で必ず最新情報を確認し、過去48時間を対象に、Alexaがそのまま自然に読み上げられる日本語ニュースを作ってください。

目的：平日の朝7時15分に、5〜7分程度で「今日の重要な動き」を把握できること。

重要ルール：
- 信頼性の高い一次情報、Reuters、AP、BBC、NHK、主要経済紙、中央銀行、政府、企業公式発表を優先する。
- 沖縄ローカルはNHK沖縄、琉球新報、沖縄タイムス、自治体・県の公式発表などを確認する。
- 重要ニュースは可能なら複数ソースで照合する。
- 噂、リーク、匿名情報、SNS発の未確認情報は必ず「未確認」「噂」「リーク」と明示する。
- 事実と予測、市場の見方を分ける。
- 政治に偏りすぎず、暮らし・経済・技術・新製品も重視する。
- 同じニュースを複数ブロックで繰り返さない。
- 専門用語を避け、短い文で、耳で理解しやすい表現にする。
- URL、脚注、表、Markdown、箇条書き記号は出力しない。
- 数字は「1ドルおよそ145円」「0.2パーセント上昇」のように読み上げやすくする。

出力は必ず次のJSON配列だけにしてください。コードフェンスは禁止です。
[
  {"title":"今朝の3大ニュース","text":"..."},
  {"title":"日本・沖縄","text":"..."},
  {"title":"世界情勢","text":"..."},
  {"title":"マーケット・経済","text":"..."},
  {"title":"新商品・AI・テクノロジー","text":"..."}
]

各ブロックの内容：
1. 今朝の3大ニュース：過去24時間の最重要3件。各件について「何が起きたか」「なぜ重要か」「次に見る点」を簡潔に。冒頭に「おはようございます。今日のニュースです」と日本の日付を入れる。
2. 日本・沖縄：日本国内2〜3件、沖縄1〜3件。暮らし、物価、観光、災害、交通、教育、産業、地域経済、制度変更を優先。重要ニュースがない場合は無理に埋めない。
3. 世界情勢：外交、安全保障、戦争・紛争、貿易、エネルギーなどから3〜5件。日本への影響があれば一言。最後に、今日最も意見が分かれる重要ニュース1件について「一方では」「もう一方では」と2つの主要な視点を公平に説明する。ただし事実と虚偽を同等に扱わない。
4. マーケット・経済：日経平均、TOPIX、S&P500、NASDAQ、ドル円、日本10年国債利回り、米国10年国債利回り、金、原油を確認。大きく動いたものを中心に、理由と時点を簡潔に説明。日銀、FRB、ECB、インフレ、雇用、GDP、関税、主要企業決算で重要な動きがあれば追加。最後に「なぜ重要か」として、家計・企業・日本経済への波及を短く1段落で説明する。
5. 新商品・AI・テクノロジー：過去48時間の注目新商品・新サービス3〜5件とAI・テック2〜4件。AI、Apple、スマートフォン、PC、カメラ、ガジェット、アプリ、ロボット、自動運転、EV、3Dプリンタ、レーザー加工、クリエイター向けツールを優先。「何が新しいか」「価格や発売日」「誰に影響するか」を短く。最後に、最重要ニュースの背景を3〜5局面の時系列で簡潔に説明し、今後24時間の注目予定を最大5件、日本時間で案内し、「今日ひとことで言うと」で全体を1文にまとめる。

各textは目安600〜900文字、最大4000文字。全体で5〜7分程度の読み上げ量にしてください。
'''


def strip_code_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def truncate_for_alexa(text: str, limit: int = 4300) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    for mark in ("。", "！", "？"):
        pos = clipped.rfind(mark)
        if pos >= int(limit * 0.75):
            return clipped[: pos + 1]
    return clipped.rstrip() + "。"


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)
    interaction = client.interactions.create(
        model=MODEL,
        input=PROMPT,
        tools=[{"type": "google_search"}],
    )

    raw = strip_code_fence(interaction.output_text)
    data = json.loads(raw)
    if not isinstance(data, list) or len(data) != 5:
        raise ValueError("Gemini output must be a 5-item JSON array")

    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc.astimezone(JST)
    update_date = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    day_key = now_jst.strftime("%Y%m%d")

    feed = []
    for idx, item in enumerate(data, start=1):
        title = str(item.get("title", f"ニュース {idx}")).strip()
        text = truncate_for_alexa(str(item.get("text", "")).strip())
        if not text:
            raise ValueError(f"Empty text in section {idx}")
        feed.append(
            {
                "uid": f"daily-news-{day_key}-{idx}",
                "updateDate": update_date,
                "titleText": title,
                "mainText": text,
                "redirectionUrl": REPO_URL,
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(feed)} Alexa feed items using {MODEL}")


if __name__ == "__main__":
    main()
