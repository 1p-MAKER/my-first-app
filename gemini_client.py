"""Small, bounded Gemini REST client; no SDK or secret-bearing URLs."""
import json
import re
import time
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiError(RuntimeError):
    pass


class GeminiClient:
    def __init__(self, api_key, model=DEFAULT_MODEL):
        if not api_key or not api_key.strip():
            raise GeminiError("GEMINI_API_KEY が未登録です。Actions Secretに登録してください。")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
            raise GeminiError("GEMINI_MODEL の形式が不正です。")
        self.api_key = api_key.strip()
        self.model = model
        self.usage = []
        self.attempts = 0

    def generate(self, prompt, *, search=False, schema=None):
        config = {"maxOutputTokens": 16384}
        if schema is not None:
            config.update(responseMimeType="application/json", responseJsonSchema=schema)
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": config}
        if search:
            payload["tools"] = [{"google_search": {}}]
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        for attempt in range(3):
            self.attempts += 1
            delay = 2 ** (attempt + 1)
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    result = json.load(response)
                if not isinstance(result, dict) or "error" in result:
                    raise GeminiError("Gemini応答形式が不正です。")
                usage = result.get("usageMetadata") or {}
                self.usage.append({"stage": "research" if search else "edit",
                                   **{k: usage[k] for k in ("promptTokenCount", "candidatesTokenCount",
                                                          "thoughtsTokenCount", "totalTokenCount") if k in usage}})
                return result
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise GeminiError(f"Gemini HTTP {exc.code}。キー・モデル・API制限・課金枠を確認してください。") from None
                retry_after = (exc.headers or {}).get("Retry-After", "")
                if retry_after.isdigit():
                    if int(retry_after) > 60:
                        raise GeminiError("Geminiが長い待機を要求しました。時間をおいて再実行してください。") from None
                    delay = max(delay, int(retry_after))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                if attempt == 2:
                    raise GeminiError("Geminiとの通信に3回失敗しました。") from None
            time.sleep(delay)
        raise GeminiError("Geminiとの通信に失敗しました。")


def candidate_text(response):
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise ValueError("候補本文がありません。")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP":
        raise ValueError("生成が完了していません（停止・出力上限・ブロック）。")
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p["text"] for p in parts if isinstance(p, dict)
                   and not p.get("thought") and isinstance(p.get("text"), str)).strip()
    if not text or len(text) > 60000:
        raise ValueError("本文が空、または長すぎます。")
    return text, candidate
