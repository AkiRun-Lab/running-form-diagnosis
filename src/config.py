"""
Running Form Diagnosis - Configuration
アプリケーション全体の設定値を管理
"""

# =============================================
# アプリ情報
# =============================================
APP_NAME = "ランニングフォーム診断アプリ"
APP_VERSION = "1.2.1"

# =============================================
# Gemini API Configuration
# =============================================
# スクリーニング用：高速・低コスト
GEMINI_SCREENER_MODEL = "gemini-3.1-flash-lite"

# メイン診断用：深いバイオメカニクス推論
GEMINI_ANALYZER_MODEL = "gemini-3.1-pro-preview"

# 診断パラメータ（Gemini壁打ち推奨値）
# ハルシネーション抑制・物理法則ベースの一貫した出力のため低めに設定
GEMINI_TEMPERATURE = 0.2
GEMINI_TOP_P = 0.8
GEMINI_TOP_K = 32
GEMINI_MAX_OUTPUT_TOKENS = 16384

# Thinking Config
# 接地・骨盤・腕振りの連動性など物理的因果関係の深い推論のために確保
GEMINI_THINKING_BUDGET = 8192

# =============================================
# 動画アップロード設定
# =============================================
SUPPORTED_VIDEO_TYPES = ["mp4", "mov", "avi", "webm"]
MAX_VIDEO_SIZE_MB = 200
MAX_DIAGNOSES_PER_DAY = 1

# Files API ポーリング設定
UPLOAD_POLL_INTERVAL_SEC = 2
UPLOAD_TIMEOUT_SEC = 120
