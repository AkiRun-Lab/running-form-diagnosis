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
APP_VERSION = "1.12.2"

# 測定層（MediaPipe姿勢推定）の緊急停止フラグ。Cloud等でmediapipeが動かない場合にFalseにする。
# Falseにすると計測ステップ自体をスキップし、v1.11.0相当の診断フローに戻る
MEASUREMENT_ENABLED = True

# 診断スコアの5項目（キー: Geminiに出力させる英語キー、値: 表示ラベル）
SCORE_ITEMS = {
    "foot_strike": "接地",
    "pelvis_core": "骨盤・体幹",
    "arm_swing": "腕振り",
    "hip_extension": "股関節伸展",
    "vertical_osc": "上下動",
}

# Amazonおすすめリスト⑦（ランナーの補強・筋トレ）の送客先URL。
# 公開情報（シークレットではない）。リスト未確定時はストアトップにフォールバック。
AMAZON_FITNESS_LIST_URL = "https://amzn.to/4o3iHCx"

# カテゴリ別Amazonアイデアリスト（2026-07-15発行・トラッキングID akirun-rfd-22）。
# generalは網羅型のリスト⑦（AMAZON_FITNESS_LIST_URL）を継続。
AMAZON_LIST_GLUTE_CORE = "https://amzn.to/4fxnEAV"  # 臀筋・体幹
AMAZON_LIST_MOBILITY = "https://amzn.to/4aS5UgW"    # 可動域ケア・ストレッチ
AMAZON_LIST_ELASTICITY = "https://amzn.to/3RdloWg"  # 接地バネ・プライオ
AMAZON_LIST_UPPER_BODY = "https://amzn.to/4pmRxr3"  # 腕振り・上半身補強

# 弱点連動CTA：診断結果の弱点カテゴリごとにCTA文言・送客先を切り替える。
# URLはカテゴリ別リストへ送客（2026-07-15差し替え済）。generalのみ網羅型リスト⑦。
WEAKNESS_CTA_VARIANTS = {
    "glute_core": {
        "title": "💪 殿筋・体幹を、自宅で強化する",
        "sub": "診断で挙がった殿筋・体幹の補強種目に使える用品をAmazonのおすすめリストにまとめました。ミニバンドや体幹トレーニング用品で、骨盤の安定と股関節伸展の土台をつくれます。",
        "url": AMAZON_LIST_GLUTE_CORE,
    },
    "mobility": {
        "title": "🧘 硬さをほぐして、可動域を広げる",
        "sub": "診断で挙がった股関節・足首の硬さには、フォームローラーやストレッチ用品が役立ちます。可動域を広げるためのグッズをAmazonのおすすめリストにまとめました。",
        "url": AMAZON_LIST_MOBILITY,
    },
    "elasticity": {
        "title": "⚡ 接地のバネを、鍛え直す",
        "sub": "診断で挙がった接地のバネ・弾性の不足には、縄跳びやプライオメトリクス用品が効果的です。地面反力を活かすための用品をAmazonのおすすめリストにまとめました。",
        "url": AMAZON_LIST_ELASTICITY,
    },
    "upper_body": {
        "title": "🏋️ 腕振りと上半身を、整える",
        "sub": "診断で挙がった腕振り・上半身の課題には、トレーニングチューブなどが役立ちます。肩まわりと上下半身の連動性を高める用品をAmazonのおすすめリストにまとめました。",
        "url": AMAZON_LIST_UPPER_BODY,
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

# 診断の再現性向上のためseedを固定する（2026-07-14 フェーズ0測定でスコア完全一致を確認）。
# seedは決定性の「ベストエフォートのヒント」であり完全一致の保証ではない（thinking有効時は特に）
GEMINI_SEED = 42

# 503フォールバック用の代替診断モデル（Gemini 3系・thinking_level対応を確認済み 2026-07-10）。
# プライマリがRETRY_503_MAX_ATTEMPTS回連続503のとき、このモデルでFALLBACK_503_MAX_ATTEMPTS回まで試行する。
# モデルはリクエスト単位で選ばれるため、次の診断は常にプライマリから始まる
GEMINI_ANALYZER_FALLBACK_MODEL = "gemini-3-flash-preview"

# 注: thinkingトークンも max_output_tokens を消費するため、診断本文の必要量に
# 思考分（thinking_level="high"）の余裕を上乗せした床値にする（AMCと同基準）
GEMINI_MAX_OUTPUT_TOKENS = 24576

# 注: temperature / top_p / top_k は全 Gemini 3.x モデルで非推奨となり削除（公式: デフォルト設定が最適化済み）
# Thinking Config（thinking_level: minimal/low/medium/high）
# バイオメカニクスの物理的因果関係の深い推論のため high を指定
GEMINI_THINKING_LEVEL = "high"

# 解析リクエストのタイムアウト（秒）。SDKデフォルトは無期限のためハング対策として明示
ANALYZE_TIMEOUT_SEC = 300
# スクリーニングのタイムアウト（秒）
SCREEN_TIMEOUT_SEC = 60
# 503（モデル高負荷）時の自動リトライ：最大試行回数と待機秒
RETRY_503_MAX_ATTEMPTS = 3
RETRY_503_WAIT_SEC = 10
# プライマリが503で尽きた際のフォールバックモデルの最大試行回数
FALLBACK_503_MAX_ATTEMPTS = 2
# プログレスバーの目安時間（秒）。この時間で95%に達し、完了まで頭打ち
ANALYZE_EXPECTED_SEC = 120

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
