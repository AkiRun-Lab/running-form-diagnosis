"""
Running Form Diagnosis - Analyzer
動画のアップロード・ポーリング・Gemini Pro診断・クリーンアップを担当する。

使用パターン（app.py 側）:
    video_file = upload_video(client, video_bytes, filename)
    try:
        screen_result = screen_video(client, video_file)   # screener.py
        if screen_result["ok"]:
            result = analyze_form(client, video_file, context)
    finally:
        cleanup_video(client, video_file)
"""
import io
import time

from google import genai
from google.genai import types

from .config import (
    GEMINI_ANALYZER_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_THINKING_LEVEL,
    UPLOAD_POLL_INTERVAL_SEC,
    UPLOAD_TIMEOUT_SEC,
    MIN_VIDEO_DURATION_SEC,
    MAX_VIDEO_DURATION_SEC,
)
from .prompts import ANALYZER_SYSTEM_INSTRUCTION, build_analyzer_prompt


def _get_video_duration_seconds(video_file) -> float | None:
    """Files APIのメタデータから動画の長さ（秒）を取得する。取得できない場合はNone。"""
    try:
        meta = video_file.video_metadata
        if meta is None:
            return None
        dur = meta.video_duration
        if dur is None:
            return None
        if hasattr(dur, "total_seconds"):
            return dur.total_seconds()
        if hasattr(dur, "seconds"):
            return float(dur.seconds) + getattr(dur, "nanos", 0) / 1e9
        return None
    except Exception:
        return None


# 拡張子 → MIME タイプ
_MIME_MAP = {
    "mp4":  "video/mp4",
    "mov":  "video/quicktime",
    "avi":  "video/x-msvideo",
    "webm": "video/webm",
}


def _get_mime_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MIME_MAP.get(ext, "video/mp4")


def upload_video(client: genai.Client, video_bytes: bytes, filename: str):
    """動画を Gemini Files API にアップロードし、処理完了まで待機する。

    Args:
        client:      初期化済みの genai.Client
        video_bytes: 動画のバイト列（st.file_uploader の .read() など）
        filename:    元ファイル名（MIME タイプ判定に使用）

    Returns:
        処理完了した genai.File オブジェクト

    Raises:
        RuntimeError: アップロード失敗 / 処理タイムアウト / 処理エラー
    """
    mime_type = _get_mime_type(filename)

    try:
        video_file = client.files.upload(
            file=io.BytesIO(video_bytes),
            config=types.UploadFileConfig(
                mime_type=mime_type,
                display_name=filename,
            ),
        )
    except Exception as e:
        raise RuntimeError(f"動画のアップロードに失敗しました: {e}")

    # ACTIVE になるまでポーリング
    elapsed = 0
    while video_file.state.name == "PROCESSING":
        if elapsed >= UPLOAD_TIMEOUT_SEC:
            raise RuntimeError(
                f"動画の処理がタイムアウトしました（{UPLOAD_TIMEOUT_SEC}秒）。"
                "短い動画か圧縮された動画をお試しください。"
            )
        time.sleep(UPLOAD_POLL_INTERVAL_SEC)
        elapsed += UPLOAD_POLL_INTERVAL_SEC
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError("動画の処理に失敗しました。別の動画ファイルをお試しください。")

    # 動画の長さチェック（Files APIのメタデータを使用）
    duration = _get_video_duration_seconds(video_file)
    if duration is not None:
        if duration < MIN_VIDEO_DURATION_SEC:
            client.files.delete(name=video_file.name)
            raise ValueError(f"動画の長さが {duration:.1f} 秒です。{MIN_VIDEO_DURATION_SEC}秒以上の動画をアップロードしてください。")
        if duration > MAX_VIDEO_DURATION_SEC:
            client.files.delete(name=video_file.name)
            raise ValueError(f"動画の長さが {int(duration // 60)} 分 {int(duration % 60)} 秒です。{MAX_VIDEO_DURATION_SEC // 60}分以内の動画をアップロードしてください。")

    return video_file


def analyze_form(client: genai.Client, video_file, context: str) -> str:
    """gemini-3.5-flash でランニングフォームを診断する。

    Args:
        client:     初期化済みの genai.Client
        video_file: upload_video() で取得したファイルオブジェクト
        context:    ユーザーが入力したコンテキスト（空文字も可）

    Returns:
        マークダウン形式の診断テキスト

    Raises:
        RuntimeError: API エラー（レート制限・その他）
    """
    user_prompt = build_analyzer_prompt(context)

    try:
        response = client.models.generate_content(
            model=GEMINI_ANALYZER_MODEL,
            contents=[video_file, user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=ANALYZER_SYSTEM_INSTRUCTION,
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_level=GEMINI_THINKING_LEVEL,
                ),
            ),
        )
        return response.text

    except Exception as e:
        err = str(e)
        if "429" in err or "Resource Exhausted" in err:
            raise RuntimeError("429_RATE_LIMITED: APIのレート制限に達しました。しばらく待ってから再試行してください。")
        if "503" in err or "Service Unavailable" in err:
            raise RuntimeError("503_SERVICE_UNAVAILABLE: APIが一時的に利用できません。しばらく待ってから再試行してください。")
        raise RuntimeError(f"診断中にエラーが発生しました: {err}")


def cleanup_video(client: genai.Client, video_file) -> None:
    """Files API からアップロードした動画を削除する。失敗しても例外を伝播させない。"""
    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass
