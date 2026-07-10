"""
Running Form Diagnosis - Configuration
アプリケーション全体の設定値を管理
"""
from datetime import datetime
from zoneinfo import ZoneInfo


def jst_now() -> datetime:
    """日本時間の現在時刻（naive）。Streamlit Cloud（UTC）での日付ズレ防止用。"""
    return datetime.now(ZoneInfo("Asia/Tokyo")).replace(tzinfo=None)


# =============================================
# アプリ情報
# =============================================
APP_NAME = "ランニングフォーム診断アプリ"
APP_VERSION = "1.6.0"

# Amazonおすすめリスト⑦（ランナーの補強・筋トレ）の送客先URL。
# 公開情報（シークレットではない）。リスト未確定時はストアトップにフォールバック。
AMAZON_FITNESS_LIST_URL = "https://amzn.to/4o3iHCx"

# 弱点連動CTA：診断結果の弱点カテゴリごとにCTA文言を切り替える。
# URLは当面全カテゴリ共通（リスト⑦）。カテゴリ別リストを作ったら "url" を差し替える。
WEAKNESS_CTA_VARIANTS = {
    "glute_core": {
        "title": "💪 殿筋・体幹を、自宅で強化する",
        "sub": "診断で挙がった殿筋・体幹の補強種目に使える用品をAmazonのおすすめリストにまとめました。ミニバンドや体幹トレーニング用品で、骨盤の安定と股関節伸展の土台をつくれます。",
        "url": AMAZON_FITNESS_LIST_URL,
    },
    "mobility": {
        "title": "🧘 硬さをほぐして、可動域を広げる",
        "sub": "診断で挙がった股関節・足首の硬さには、フォームローラーやストレッチ用品が役立ちます。可動域を広げるためのグッズをAmazonのおすすめリストにまとめました。",
        "url": AMAZON_FITNESS_LIST_URL,
    },
    "elasticity": {
        "title": "⚡ 接地のバネを、鍛え直す",
        "sub": "診断で挙がった接地のバネ・弾性の不足には、縄跳びやプライオメトリクス用品が効果的です。地面反力を活かすための用品をAmazonのおすすめリストにまとめました。",
        "url": AMAZON_FITNESS_LIST_URL,
    },
    "upper_body": {
        "title": "🏋️ 腕振りと上半身を、整える",
        "sub": "診断で挙がった腕振り・上半身の課題には、トレーニングチューブなどが役立ちます。肩まわりと上下半身の連動性を高める用品をAmazonのおすすめリストにまとめました。",
        "url": AMAZON_FITNESS_LIST_URL,
    },
    "general": {
        "title": "💪 補強メニューを、自宅で実践する",
        "sub": "上の診断で挙がった補強種目に必要な用品を、用途別にAmazonのおすすめリストにまとめました。殿筋・体幹・足首の安定づくりと弾性の強化に役立つグッズを揃えています。",
        "url": AMAZON_FITNESS_LIST_URL,
    },
}

# =============================================
# Gemini API Configuration
# =============================================
# スクリーニング用：高速・低コスト
GEMINI_SCREENER_MODEL = "gemini-3.1-flash-lite"

# メイン診断用：深いバイオメカニクス推論
GEMINI_ANALYZER_MODEL = "gemini-3.5-flash"

# 注: thinkingトークンも max_output_tokens を消費するため、診断本文の必要量に
# 思考分（thinking_level="high"）の余裕を上乗せした床値にする（AMCと同基準）
GEMINI_MAX_OUTPUT_TOKENS = 24576

# 注: temperature / top_p / top_k は全 Gemini 3.x モデルで非推奨となり削除（公式: デフォルト設定が最適化済み）
# Thinking Config（thinking_level: minimal/low/medium/high）
# バイオメカニクスの物理的因果関係の深い推論のため high を指定
GEMINI_THINKING_LEVEL = "high"

# =============================================
# 動画アップロード設定
# =============================================
SUPPORTED_VIDEO_TYPES = ["mp4", "mov", "avi", "webm"]
MAX_VIDEO_SIZE_MB = 200
MAX_DIAGNOSES_PER_DAY = 1

# Files API ポーリング設定
UPLOAD_POLL_INTERVAL_SEC = 2
UPLOAD_TIMEOUT_SEC = 120

# 動画長さ制限（秒）
MIN_VIDEO_DURATION_SEC = 5
MAX_VIDEO_DURATION_SEC = 300  # 5分
