"""
Running Form Diagnosis - UI Components
再利用可能なUIコンポーネント
"""
from pathlib import Path

import streamlit as st

from ..config import APP_NAME, APP_VERSION, WEAKNESS_CTA_VARIANTS


def load_css() -> None:
    """スポーツテックHUD風スタイルシート（styles.css）を読み込んで注入する"""
    css_path = Path(__file__).parent / "styles.css"
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


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
    """アプリヘッダーを表示（スポーツテックHUD風ヒーロー）"""
    st.markdown(
        f'<h1 style="text-align:center; font-size:clamp(1.4rem, 6vw, 2.2rem); white-space:nowrap; '
        f'background:linear-gradient(90deg, #22D3EE, #3B82F6); -webkit-background-clip:text; '
        f'-webkit-text-fill-color:transparent; background-clip:text;">{APP_NAME}</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="text-align:center; color:#aaa; font-size:0.9rem; margin-top:-0.5rem;">'
        f'v{APP_VERSION}　|　Powered by Gemini｜AkiRun</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align:center; color:#ccc; margin-bottom:1rem;">'
        'ランニング動画をアップロードすると、バイオメカニクスの観点からフォームを診断します。'
        '</p>',
        unsafe_allow_html=True,
    )
    badges = ["⚡ Powered by Gemini", "🔬 バイオメカニクス解析", "🆓 1日1回無料"]
    chips_html = "".join(
        f'<span style="display:inline-block; margin:0 4px 6px; padding:4px 12px; '
        f'background:rgba(34,211,238,0.10); border:1px solid rgba(34,211,238,0.35); '
        f'color:#7DD3FC; font-size:0.78rem; border-radius:999px;">{badge}</span>'
        for badge in badges
    )
    st.markdown(
        f'<div style="text-align:center; margin-bottom:1rem;">{chips_html}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="height:2px; margin-bottom:1.5rem; '
        'background:linear-gradient(90deg, transparent, #22D3EE, #3B82F6, transparent);"></div>',
        unsafe_allow_html=True,
    )


def render_step_indicator() -> None:
    """利用の流れを1行で示す控えめなステップガイド"""
    st.markdown(
        '<p style="text-align:center; color:#94A3B8; font-size:0.85rem; margin-bottom:1.2rem;">'
        '<span style="color:#38BDF8;">①</span> 動画アップロード '
        '→ <span style="color:#38BDF8;">②</span> AIチェック '
        '→ <span style="color:#38BDF8;">③</span> バイオメカニクス解析'
        '</p>',
        unsafe_allow_html=True,
    )


def render_result(result_text: str) -> None:
    """診断結果を表示"""
    st.markdown("---")
    st.markdown(
        '<div style="display:flex; align-items:center; gap:10px; margin-bottom:0.8rem;">'
        '<span style="display:inline-block; width:4px; height:1.5rem; border-radius:2px; '
        'background:linear-gradient(180deg, #22D3EE, #3B82F6);"></span>'
        '<span style="font-size:1.4rem; font-weight:700; color:#FFFFFF;">診断結果</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(result_text)


def render_footer() -> None:
    """フッターを表示"""
    st.markdown(
        '<div style="height:1px; margin:1.5rem 0 1rem; '
        'background:linear-gradient(90deg, transparent, #22D3EE, #3B82F6, transparent);"></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div style="text-align:center; color:#aaa; font-size:0.85rem;">
    <p>
        <a href="https://akirun.net/" target="_blank" style="color:#38BDF8;">AkiRun｜走りを科学でアップデート</a>
        　|
        <a href="https://akirun.net/lp/marathon-simulator/" target="_blank" style="color:#38BDF8;">マラソンペース計算ツール（MPC）</a>
        　|
        <a href="https://akirun.net/lp/ai-marathon-coach/" target="_blank" style="color:#38BDF8;">マラソントレーニング・プランナー（MTP）</a>
    </p>
    <p style="margin-top:0.5rem;">© 2026 AkiRun</p>
</div>
        """,
        unsafe_allow_html=True,
    )
