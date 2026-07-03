"""
Running Form Diagnosis - Configuration
アプリケーション全体の設定値を管理
"""

# =============================================
# アプリ情報
# =============================================
APP_NAME = "ランニングフォーム診断アプリ"
APP_VERSION = "1.5.2"

# Amazonおすすめリスト⑦（ランナーの補強・筋トレ）の送客先URL。
# 公開情報（シークレットではない）。リスト未確定時はストアトップにフォールバック。
AMAZON_FITNESS_LIST_URL = "https://amzn.to/4o3iHCx"

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
