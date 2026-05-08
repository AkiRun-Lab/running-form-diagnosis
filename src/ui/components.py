"""
Running Form Diagnosis - UI Components
再利用可能なUIコンポーネント
"""
import streamlit as st

from ..config import APP_NAME, APP_VERSION


def render_header() -> None:
    """アプリヘッダーを表示"""
    st.markdown(
        f'<h1 style="text-align:center; font-size:2.2rem;">{APP_NAME}</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="text-align:center; color:#aaa; font-size:0.9rem; margin-top:-0.5rem;">'
        f'v{APP_VERSION}　|　Powered by Gemini｜AkiRun</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align:center; color:#ccc; margin-bottom:1.5rem;">'
        'ランニング動画をアップロードすると、バイオメカニクスの観点からフォームを診断します。'
        '</p>',
        unsafe_allow_html=True,
    )


def render_result(result_text: str) -> None:
    """診断結果を表示"""
    st.markdown("---")
    st.subheader("診断結果")
    st.markdown(result_text)


def render_footer() -> None:
    """フッターを表示"""
    st.markdown("---")
    st.markdown(
        """
<div style="text-align:center; color:#aaa; font-size:0.85rem;">
    <p>
        <a href="https://akirun.net/" target="_blank" style="color:#FF4B4B;">AkiRun｜走りを科学でアップデート</a>
        　|
        <a href="https://akirun.net/lp/marathon-simulator/" target="_blank" style="color:#FF4B4B;">マラソンペース計算ツール（MPC）</a>
        　|
        <a href="https://akirun.net/lp/ai-marathon-coach/" target="_blank" style="color:#FF4B4B;">マラソントレーニング・プランナー（MTP）</a>
    </p>
    <p style="margin-top:0.5rem;">© 2026 AkiRun</p>
</div>
        """,
        unsafe_allow_html=True,
    )
