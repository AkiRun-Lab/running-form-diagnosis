"""
Running Form Diagnosis - Screener
gemini-3.1-flash で動画の品質チェックを行う。
アップロード済みの Files API ファイルオブジェクトを受け取り、診断可否を返す。
"""
import json

from google import genai
from google.genai import types

from .config import (
    GEMINI_SCREENER_MODEL,
    SCREEN_TIMEOUT_SEC,
)
from .prompts import (
    SCREENER_SYSTEM_INSTRUCTION,
    SCREENER_USER_PROMPT,
)


def screen_video(client: genai.Client, video_file) -> dict:
    """動画が診断に使用できるか高速チェックする

    Args:
        client: 初期化済みの genai.Client
        video_file: client.files.upload() で取得したファイルオブジェクト

    Returns:
        {"ok": bool, "reason": str}
        ok=True  → 診断可
        ok=False → 診断不可（reason に理由）
    """
    try:
        response = client.models.generate_content(
            model=GEMINI_SCREENER_MODEL,
            contents=[video_file, SCREENER_USER_PROMPT],
            config=types.GenerateContentConfig(
                system_instruction=SCREENER_SYSTEM_INSTRUCTION,
                max_output_tokens=256,
                http_options=types.HttpOptions(timeout=SCREEN_TIMEOUT_SEC * 1000),
            ),
        )

    except Exception as e:
        err = str(e)
        if "429" in err or "Resource Exhausted" in err:
            raise RuntimeError("429_RATE_LIMITED: APIのレート制限に達しました。しばらく待ってから再試行してください。")
        if "503" in err or "Service Unavailable" in err:
            raise RuntimeError("503_SERVICE_UNAVAILABLE: APIが一時的に利用できません。しばらく待ってから再試行してください。")
        raise RuntimeError(f"スクリーニング中にエラーが発生しました: {err}")

    # 応答の解釈に失敗した場合は通過させる（診断優先）。
    # 空レスポンス・不正なコードブロック・JSONパース失敗をすべて同じ扱いにする
    raw = (response.text or "").strip()

    try:
        # Geminiがコードブロックで囲んで返す場合を考慮
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)

    except (json.JSONDecodeError, IndexError):
        return {"ok": True, "reason": "スクリーニングをスキップして診断に進みます。"}

    # 最低限のキー保証
    if "ok" not in result:
        return {"ok": False, "reason": "スクリーニング結果の形式が不正でした。"}

    return {"ok": bool(result["ok"]), "reason": result.get("reason", "")}
