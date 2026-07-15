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
import json
import re
import time

from google import genai
from google.genai import types

from .config import (
    GEMINI_ANALYZER_MODEL,
    GEMINI_ANALYZER_FALLBACK_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_THINKING_LEVEL,
    GEMINI_SEED,
    UPLOAD_POLL_INTERVAL_SEC,
    UPLOAD_TIMEOUT_SEC,
    MIN_VIDEO_DURATION_SEC,
    MAX_VIDEO_DURATION_SEC,
    SCORE_ITEMS,
    WEAKNESS_CTA_VARIANTS,
    ANALYZE_TIMEOUT_SEC,
    RETRY_503_MAX_ATTEMPTS,
    RETRY_503_WAIT_SEC,
    FALLBACK_503_MAX_ATTEMPTS,
)
from .prompts import ANALYZER_SYSTEM_INSTRUCTION, build_analyzer_prompt

# 弱点連動CTA：診断テキスト末尾のWEAKNESS_TAG行が取りうる値（config.pyの辞書キーと同一に保つ）
VALID_WEAKNESS_TAGS = set(WEAKNESS_CTA_VARIANTS.keys())

_WEAKNESS_TAG_RE = re.compile(r"^\s*WEAKNESS_TAG:\s*([a-zA-Z_]+)\s*$", re.MULTILINE | re.IGNORECASE)

# スコア化：診断テキスト中のSCORES_JSON行（config.pyのSCORE_ITEMSキーと同一に保つ）
_SCORES_JSON_RE = re.compile(r"^\s*SCORES_JSON:\s*(\{.*?\})\s*$", re.MULTILINE | re.IGNORECASE)


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
            cleanup_video(client, video_file)  # 48hの自動削除を待たずbest-effortで削除
            raise RuntimeError(
                f"動画の処理がタイムアウトしました（{UPLOAD_TIMEOUT_SEC}秒）。"
                "短い動画か圧縮された動画をお試しください。"
            )
        time.sleep(UPLOAD_POLL_INTERVAL_SEC)
        elapsed += UPLOAD_POLL_INTERVAL_SEC
        try:
            video_file = client.files.get(name=video_file.name)
        except Exception as e:
            raise RuntimeError(f"動画の処理状況の確認に失敗しました: {e}")

    if video_file.state.name == "FAILED":
        raise RuntimeError("動画の処理に失敗しました。別の動画ファイルをお試しください。")

    # 動画の長さチェック（Files APIのメタデータを使用）
    # 削除はbest-effort（cleanup_video）。削除失敗で長さエラーをマスクしない
    duration = _get_video_duration_seconds(video_file)
    if duration is not None:
        if duration < MIN_VIDEO_DURATION_SEC:
            cleanup_video(client, video_file)
            raise ValueError(f"動画の長さが {duration:.1f} 秒です。{MIN_VIDEO_DURATION_SEC}秒以上の動画をアップロードしてください。")
        if duration > MAX_VIDEO_DURATION_SEC:
            cleanup_video(client, video_file)
            raise ValueError(f"動画の長さが {int(duration // 60)} 分 {int(duration % 60)} 秒です。{MAX_VIDEO_DURATION_SEC // 60}分以内の動画をアップロードしてください。")

    return video_file


class _Exhausted503(Exception):
    """指定モデルで503が最大試行回数まで続いたことを示す内部例外（呼び出し元でフォールバック判断に使う）。"""


def _generate_with_retry(client, model, contents, config, progress_state, max_attempts):
    """指定モデルで generate_content を最大 max_attempts 回まで試行する。

    分類ロジック：
        429              → 即座に RuntimeError（リトライしない）
        503              → max_attempts 回まで10秒間隔でリトライ。尽きたら _Exhausted503
        timeout/deadline → RuntimeError（リトライしない）
        その他           → RuntimeError（リトライしない）

    Args:
        client:         初期化済みの genai.Client
        model:          使用するモデル名
        contents:       generate_content に渡す contents
        config:         generate_content に渡す GenerateContentConfig
        progress_state: 呼び出し側と共有する進捗辞書。503リトライ時に "attempt" を更新する。不要なら None
        max_attempts:   このモデルでの最大試行回数

    Returns:
        成功時の response オブジェクト

    Raises:
        _Exhausted503: 503が max_attempts 回続いた場合
        RuntimeError:  429・タイムアウト・その他のAPIエラー
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        except Exception as e:
            err = str(e)
            if "429" in err or "Resource Exhausted" in err:
                raise RuntimeError("429_RATE_LIMITED: APIのレート制限に達しました。しばらく待ってから再試行してください。")
            if "503" in err or "Service Unavailable" in err:
                if attempt < max_attempts:
                    if progress_state is not None:
                        progress_state["attempt"] = attempt + 1
                    time.sleep(RETRY_503_WAIT_SEC)
                    continue
                raise _Exhausted503()
            if "timeout" in err.lower() or "timed out" in err.lower() or "deadline" in err.lower():
                raise RuntimeError(
                    "TIMEOUT_EXCEEDED: 解析が5分を超えたため中断しました。動画を短くする・圧縮するなどして再試行してください。"
                )
            raise RuntimeError(f"診断中にエラーが発生しました: {err}")


def analyze_form(
    client: genai.Client,
    video_file,
    context: str,
    progress_state: dict | None = None,
    measurements: dict | None = None,
) -> str:
    """gemini-3.5-flash でランニングフォームを診断する。

    503（モデル高負荷）時は RETRY_503_MAX_ATTEMPTS 回まで自動リトライする。
    プライマリが503で尽きた場合は GEMINI_ANALYZER_FALLBACK_MODEL（Gemini 3系）に自動で切り替え、
    FALLBACK_503_MAX_ATTEMPTS 回まで試行する（progress_state に "fallback": True をセット）。
    フォールバックも503で尽きた場合は従来どおり RuntimeError("503_SERVICE_UNAVAILABLE: ...") をraiseする。
    モデルはこの関数呼び出し単位で選ばれるため、次回の診断は常にプライマリから始まる。
    ワーカースレッドから呼ばれるため、この関数内で streamlit（st.*）を呼ばないこと。

    Args:
        client:         初期化済みの genai.Client
        video_file:     upload_video() で取得したファイルオブジェクト
        context:        ユーザーが入力したコンテキスト（空文字も可）
        progress_state: 呼び出し側と共有する進捗辞書（例: {"attempt": 1}）。
                        リトライ時に "attempt" を更新する。フォールバックに入ったら "fallback" を True にする。不要なら None。
        measurements:   src.measurement.measure_running_form() の結果を dataclasses.asdict()
                        した辞書（フェーズ2 測定層）。未計測・計測失敗時はNone。

    Returns:
        マークダウン形式の診断テキスト

    Raises:
        RuntimeError: API エラー（レート制限・タイムアウト・503連続失敗・その他）
    """
    user_prompt = build_analyzer_prompt(context, measurements)
    contents = [video_file, user_prompt]
    config = types.GenerateContentConfig(
        system_instruction=ANALYZER_SYSTEM_INSTRUCTION,
        max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        thinking_config=types.ThinkingConfig(
            thinking_level=GEMINI_THINKING_LEVEL,
        ),
        http_options=types.HttpOptions(timeout=ANALYZE_TIMEOUT_SEC * 1000),
        seed=GEMINI_SEED,
    )

    try:
        response = _generate_with_retry(
            client, GEMINI_ANALYZER_MODEL, contents, config, progress_state, RETRY_503_MAX_ATTEMPTS
        )
    except _Exhausted503:
        if progress_state is not None:
            progress_state["fallback"] = True
        try:
            response = _generate_with_retry(
                client, GEMINI_ANALYZER_FALLBACK_MODEL, contents, config, progress_state, FALLBACK_503_MAX_ATTEMPTS
            )
        except _Exhausted503:
            raise RuntimeError(
                "503_SERVICE_UNAVAILABLE: APIが一時的に利用できません。混雑が続いています。しばらく待ってから再試行してください。"
            )

    # 空レスポンスガード：本文が無いまま返すと、結果非表示のまま診断枠だけ消費される
    text = response.text
    if not text or not text.strip():
        finish_reason = ""
        try:
            finish_reason = response.candidates[0].finish_reason.name
        except Exception:
            pass
        detail = f"（finish_reason: {finish_reason}）" if finish_reason else ""
        raise RuntimeError(
            f"AIが診断テキストを返しませんでした{detail}。"
            "診断回数は消費されていません。時間をおいて再試行してください。"
        )
    return text


def extract_weakness_tag(text: str) -> tuple[str, str]:
    """診断テキスト末尾のWEAKNESS_TAG行を抽出し、本文から除去する。

    Args:
        text: analyze_form() が返す診断テキスト全文

    Returns:
        (タグ行を除去した本文, 弱点カテゴリ文字列)
        タグが見つからない、または不正なカテゴリの場合はカテゴリを "general" とする。
    """
    # 末尾側の行を優先するため、複数マッチがあれば最後のものを採用する
    matches = list(_WEAKNESS_TAG_RE.finditer(text))
    if not matches:
        return text, "general"
    match = matches[-1]

    tag = match.group(1).strip().lower()
    if tag not in VALID_WEAKNESS_TAGS:
        tag = "general"

    body = text[:match.start()] + text[match.end():]
    return body.rstrip(), tag


def extract_scores_json(text: str) -> tuple[str, dict | None]:
    """診断テキスト中のSCORES_JSON行を抽出し、本文から除去する。

    Args:
        text: analyze_form() が返す診断テキスト全文（またはextract_weakness_tag適用後の本文）

    Returns:
        (SCORES_JSON行を除去した本文, {SCORE_ITEMSキー: 1〜10の整数} または None)
        行が無い、JSONとして壊れている、必須キーの欠落・非数値がある場合は None。
        行らしきものが見つかった場合は、パース失敗時も本文からは除去する。
    """
    matches = list(_SCORES_JSON_RE.finditer(text))
    if not matches:
        return text, None
    match = matches[-1]

    body = (text[:match.start()] + text[match.end():]).rstrip()

    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return body, None

    if not isinstance(data, dict):
        return body, None

    scores: dict[str, int] = {}
    for key in SCORE_ITEMS:
        value = data.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return body, None
        scores[key] = max(1, min(10, round(value)))

    return body, scores


def cleanup_video(client: genai.Client, video_file) -> None:
    """Files API からアップロードした動画を削除する。失敗しても例外を伝播させない。"""
    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass
