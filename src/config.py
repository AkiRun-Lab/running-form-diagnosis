"""
Running Form Diagnosis - Configuration
アプリケーション全体の設定値を管理
"""

# =============================================
# アプリ情報
# =============================================
APP_NAME = "ランニングフォーム診断アプリ"
APP_VERSION = "1.5.0"

# Amazonおすすめリスト⑦（ランナーの補強・筋トレ）の送客先URL。
# 公開情報（シークレットではない）。リスト未確定時はストアトップにフォールバック。
AMAZON_FITNESS_LIST_URL = "https://amzn.to/4o3iHCx"

# =============================================
# Gemini API Configuration
# =============================================
# スクリーニング用：高速・低コスト
GEMINI_SCREENER_MODEL = "gemini-3.1-flash-lite"
GEMINI_SCREENER_TEMPERATURE = 0.2

# メイン診断用：深いバイオメカニクス推論
GEMINI_ANALYZER_MODEL = "gemini-3.5-flash"

GEMINI_MAX_OUTPUT_TOKENS = 16384

# Thinking Config（thinking_budget: 0=無効, -1=自動, N=最大Nトークン）
# バイオメカニクスの物理的因果関係の深い推論のため高めに設定
GEMINI_THINKING_BUDGET = 16384

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
