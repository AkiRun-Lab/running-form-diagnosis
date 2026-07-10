"""
Running Form Diagnosis - UI Components
再利用可能なUIコンポーネント
"""
import streamlit as st

from ..config import APP_NAME, APP_VERSION, WEAKNESS_CTA_VARIANTS


def render_gear_cta(weakness: str = "general") -> None:
    """補強メニュー実践用の筋トレ・フィットネスグッズへ誘導するCTAカード

    Args:
        weakness: 診断結果から抽出した弱点カテゴリ（analyzer.extract_weakness_tag() の戻り値）。
                   未知のカテゴリの場合は "general" の文言にフォールバックする。
    """
    variant = WEAKNESS_CTA_VARIANTS.get(weakness, WEAKNESS_CTA_VARIANTS["general"])
    st.markdown(
        f"""
<style>
.akirun-gear-cta {{
    background: linear-gradient(135deg, #F4C66B, #E0A23D);
    border-radius: 14px;
    padding: 22px 20px;
    margin: 18px 0 8px;
    text-align: center;
    box-shadow: 0 4px 14px rgba(0,0,0,0.18);
}}
.akirun-gear-cta .gear-title {{
    color: #1F3A6B;
    font-weight: 700;
    font-size: clamp(1.05rem, 4.2vw, 1.3rem);
    margin: 0 0 6px;
}}
.akirun-gear-cta .gear-sub {{
    color: #4a3b14;
    font-size: clamp(0.85rem, 3.2vw, 0.95rem);
    line-height: 1.6;
    margin: 0 auto 14px;
    max-width: 36em;
}}
.akirun-gear-cta-btn {{
    display: inline-block;
    background: #1F3A6B;
    color: #ffffff !important;
    font-weight: 700;
    font-size: clamp(0.95rem, 3.6vw, 1.1rem);
    text-decoration: none !important;
    padding: 13px 30px;
    border-radius: 9px;
    box-shadow: 0 3px 8px rgba(0,0,0,0.22);
    transition: transform .12s ease, filter .12s ease;
}}
.akirun-gear-cta-btn:hover, .akirun-gear-cta-btn:visited, .akirun-gear-cta-btn:focus {{
    color: #ffffff !important;
    text-decoration: none !important;
    filter: brightness(1.12);
    transform: translateY(-1px);
}}
.akirun-gear-cta .gear-note {{
    color: #5a4a1f;
    font-size: 0.78rem;
    margin: 12px 0 0;
}}
</style>
<div class="akirun-gear-cta">
    <p class="gear-title">{variant["title"]}</p>
    <p class="gear-sub">{variant["sub"]}</p>
    <a class="akirun-gear-cta-btn" href="{variant["url"]}" target="_blank" rel="noopener noreferrer sponsored">筋トレ・補強グッズを見る ›</a>
    <p class="gear-note">ランナーの補強に必要なものを用途別に整理しています</p>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """アプリヘッダーを表示"""
    st.markdown(
        f'<h1 style="text-align:center; font-size:clamp(1.4rem, 6vw, 2.2rem); white-space:nowrap;">{APP_NAME}</h1>',
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
