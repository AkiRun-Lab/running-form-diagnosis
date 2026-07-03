"""
Running Form Diagnosis - Main App
ランニング動画をアップロードしてGeminiにフォーム診断させるStreamlitアプリ
"""
import hmac
from datetime import timedelta

import streamlit as st
from google import genai
from streamlit_cookies_controller import CookieController

from src.config import APP_NAME, APP_VERSION, SUPPORTED_VIDEO_TYPES, MAX_VIDEO_SIZE_MB, MAX_DIAGNOSES_PER_DAY, jst_now
from src.screener import screen_video
from src.analyzer import upload_video, analyze_form, cleanup_video
from src.ui.components import render_header, render_result, render_gear_cta, render_footer

# =============================================
# ページ設定（最初に呼ぶ）
# =============================================
st.set_page_config(
    page_title=APP_NAME,
    page_icon="🏃",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =============================================
# Cookie コントローラー
# =============================================
_cookie_controller = CookieController()


def _load_cookie_counts(controller: CookieController) -> int:
    """読み込み専用。書き込みは cookie_write_pending ブロックで行う。"""
    today = jst_now().strftime("%Y-%m-%d")
    cookie_date = controller.get("rfd_date") or ""
    if cookie_date != today:
        return 0
    return int(controller.get("rfd_diag_count") or "0")


# =============================================
# セッション状態の初期化
# =============================================
defaults = {
    "diagnosis_count": 0,
    "is_admin": False,
    "counts_loaded": False,
    "cookie_write_pending": False,
    "_first_render_done": False,
    "last_result": None,
    "last_context": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if not st.session_state.counts_loaded:
    if st.session_state._first_render_done:
        try:
            count = _load_cookie_counts(_cookie_controller)
            st.session_state.diagnosis_count = count
            st.session_state.counts_loaded = True
        except Exception:
            pass
    else:
        st.session_state._first_render_done = True

# rerun直前にset()すると書き込みが失われるため、次の描画サイクル先頭でまとめて書く
if st.session_state.get("cookie_write_pending"):
    _cookie_opts = dict(
        same_site='none',
        secure=True,
        partitioned=True,
        expires=jst_now() + timedelta(days=2),
    )
    _cookie_controller.set("rfd_date", jst_now().strftime("%Y-%m-%d"), **_cookie_opts)
    _cookie_controller.set("rfd_diag_count", str(st.session_state.diagnosis_count), **_cookie_opts)
    st.session_state.cookie_write_pending = False

# =============================================
# API クライアント初期化
# =============================================
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    st.error("GEMINI_API_KEY が設定されていません。.streamlit/secrets.toml を確認してください。")
    st.stop()

client = genai.Client(api_key=api_key)

# =============================================
# サイドバー：管理者ログイン
# =============================================
with st.sidebar:
    st.markdown("#### 管理者")
    if st.session_state.is_admin:
        st.success("管理者モード（回数制限なし）")
        if st.button("ログアウト"):
            st.session_state.is_admin = False
            st.rerun()
    else:
        admin_pw = st.text_input("パスワード", type="password", label_visibility="collapsed")
        if st.button("ログイン"):
            expected_pw = st.secrets.get("ADMIN_PASSWORD", "")
            # ADMIN_PASSWORD未設定時は空パスワードが一致してしまうため、未設定なら常に拒否
            if expected_pw and hmac.compare_digest(admin_pw, expected_pw):
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("パスワードが違います")

# =============================================
# UI
# =============================================
render_header()

uploaded_file = st.file_uploader(
    "動画をアップロード",
    type=SUPPORTED_VIDEO_TYPES,
    help=f"対応形式: {', '.join(SUPPORTED_VIDEO_TYPES).upper()}　最大 {MAX_VIDEO_SIZE_MB}MB",
)

if uploaded_file:
    st.video(uploaded_file)

context = st.text_area(
    "練習内容・気になる点など（任意）",
    placeholder=(
        "例1：1000m×5インターバルの5本目後半です。ペースは3分30秒/kmです。\n"
        "例2：100m走のレース動画です。6コースの黄色いランシャツの選手のフォームを診断してください。"
    ),
    height=140,
)

limit_reached = (
    st.session_state.diagnosis_count >= MAX_DIAGNOSES_PER_DAY
    and not st.session_state.is_admin
)
if limit_reached:
    st.warning(
        f"1日あたりの診断回数上限（{MAX_DIAGNOSES_PER_DAY}回）に達しました。"
        "明日またお試しください。"
    )

run_btn = st.button(
    "フォームを診断する",
    type="primary",
    disabled=(uploaded_file is None or limit_reached),
)

_should_rerun = False

if run_btn and uploaded_file:
    video_bytes = uploaded_file.read()
    video_file = None

    try:
        # Step 1: アップロード
        with st.status("動画をアップロード中...", expanded=True) as status:
            video_file = upload_video(client, video_bytes, uploaded_file.name)
            status.update(label="アップロード完了", state="complete")

        # Step 2: スクリーニング
        with st.status("動画をチェック中...", expanded=False) as status:
            screen_result = screen_video(client, video_file)
            if screen_result["ok"]:
                status.update(label="動画チェック完了", state="complete")
            else:
                status.update(label=f"動画チェック: {screen_result['reason']}", state="error")
                st.error(f"この動画は診断できません。\n\n{screen_result['reason']}")
                st.stop()

        # Step 3: 診断
        with st.status("フォームを解析中（30秒〜2分かかります）...", expanded=False) as status:
            result = analyze_form(client, video_file, context)
            status.update(label="診断完了", state="complete")

        st.session_state.last_result = result
        st.session_state.last_context = context.strip()
        st.session_state.diagnosis_count += 1
        st.session_state.cookie_write_pending = True
        _should_rerun = True

    except ValueError as e:
        st.error(str(e))

    except RuntimeError as e:
        err_msg = str(e)
        if "429_RATE_LIMITED" in err_msg:
            st.error("APIのレート制限に達しました。しばらく待ってから再試行してください。")
        elif "503_SERVICE_UNAVAILABLE" in err_msg:
            st.error("APIが一時的に利用できません。しばらく待ってから再試行してください。")
        else:
            st.error(err_msg)

    finally:
        if video_file:
            cleanup_video(client, video_file)

# cleanup完了後にrerun → 次の描画サイクルでcookieを書く
if _should_rerun:
    st.rerun()

# 診断結果の表示（rerun後の描画サイクルで実行）
if st.session_state.get("last_result"):
    render_result(st.session_state.last_result)
    render_gear_cta()

    today = jst_now().strftime("%Y年%m月%d日")
    _ctx = st.session_state.last_context
    context_line = f"\n> コンテキスト：{_ctx}\n" if _ctx else ""
    md_content = (
        f"# ランニングフォーム診断レポート\n\n"
        f"診断日：{today}{context_line}\n\n---\n\n"
        f"{st.session_state.last_result}"
    )
    st.download_button(
        label="診断結果をダウンロード（Markdown）",
        data=md_content.encode("utf-8-sig"),
        file_name=f"running_form_diagnosis_{jst_now().strftime('%Y%m%d')}.md",
        mime="text/markdown",
    )

render_footer()
