# 仕様書 — ランニングフォーム診断

## システム概要

| 項目 | 内容 |
|------|------|
| アプリ名 | ランニングフォーム診断 |
| バージョン | 1.0.0 |
| フレームワーク | Streamlit |
| ホスティング | Streamlit Community Cloud |
| AIバックエンド | Google Gemini API（google-genai SDK） |
| リポジトリ | https://github.com/AkiRun-Lab/running-form-diagnosis |

---

## アーキテクチャ

```
ユーザー（ブラウザ）
  ↓ 動画アップロード
Streamlit app.py
  ↓
[1] Gemini Files API
    動画をアップロード → ACTIVE 状態になるまでポーリング
  ↓
[2] gemini-3.1-flash-lite（スクリーニング）
    ・全身が映っているか
    ・ランナー（人物）が映っているか
    ・5秒以上5分以下か
    → {"ok": bool, "reason": str} を返す
  ↓ ok=True の場合のみ
[3] gemini-3.1-pro-preview（フォーム診断）
    ・Thinking Budget 8192 tokens で深層推論
    ・接地・骨盤・腕振り・上下動・疲労による代償動作を分析
    → マークダウン形式の診断レポートを返す
  ↓
[4] Gemini Files API からファイルを削除（cleanup）
  ↓
Streamlit 診断結果表示 + Markdown ダウンロードボタン
```

---

## Gemini API パラメータ

### スクリーニング（gemini-3.1-flash-lite）

| パラメータ | 値 | 理由 |
|-----------|-----|------|
| temperature | 0.2 | ハルシネーション抑制 |
| max_output_tokens | 256 | JSON のみを返すため小さく設定 |

### 診断（gemini-3.1-pro-preview）

| パラメータ | 値 | 理由 |
|-----------|-----|------|
| temperature | 0.2 | 物理法則に基づく一貫したフィードバックのため低く設定 |
| top_p | 0.8 | 確率の低い突飛な表現を排除 |
| top_k | 32 | 専門用語の安定した出力 |
| max_output_tokens | 16384 | 詳細な診断レポートに対応 |
| thinking_budget | 8192 | 接地・骨盤・腕振りの物理的因果関係の深い推論のために確保 |

---

## ファイル構成

```
running-form-diagnosis/
├── app.py                      # メインUIエントリポイント
├── requirements.txt            # 依存パッケージ
├── .gitignore
├── .streamlit/
│   ├── config.toml             # テーマ設定（ダークテーマ・赤系）
│   ├── secrets.toml            # APIキー（gitignore済み・本番はStreamlit Secrets）
│   └── secrets.toml.example   # テンプレート
├── src/
│   ├── config.py               # モデル名・APIパラメータ定数
│   ├── screener.py             # gemini-3.1-flash-lite によるスクリーニング
│   ├── analyzer.py             # アップロード・診断・クリーンアップ
│   ├── prompts.py              # システムインストラクション・プロンプトテンプレート
│   └── ui/
│       └── components.py       # render_header / render_result / render_footer
└── docs/
    ├── user-manual.md          # ユーザーマニュアル
    └── specification.md        # 本ファイル
```

---

## 依存パッケージ

```
streamlit>=1.30.0
google-genai>=1.0.0
```

---

## システムインストラクション（診断用）

```
バイオメカニクスと運動生理学に精通した世界的レベルのランニングコーチ兼データアナリスト。
接地・骨盤・腕振り・上下動・疲労による代償動作を力学的に分析し、マージナル・ゲインを特定する。
精神論は排除し、物理法則に基づいた客観的フィードバックのみ提供。日本語で出力。
```

---

## 動画アップロード仕様

| 項目 | 仕様 |
|------|------|
| 対応形式 | MP4 / MOV / AVI / WEBM |
| 最大サイズ | 200MB |
| 推奨時間 | 20〜60秒 |
| 最短 / 最長 | 5秒 / 5分 |
| アップロード先 | Gemini Files API（診断後に自動削除） |
| ポーリング間隔 | 2秒 |
| タイムアウト | 120秒 |

---

## Streamlit Cloud へのデプロイ手順

1. [Streamlit Cloud](https://streamlit.io/cloud) にログイン
2. 「New app」→ リポジトリ `AkiRun-Lab/running-form-diagnosis` を選択
3. Main file: `app.py`
4. 「Advanced settings」→「Secrets」に以下を入力：
   ```toml
   GEMINI_API_KEY = "your-api-key"
   ```
5. 「Deploy」をクリック

---

## エラーハンドリング

| エラーコード | 原因 | ユーザーへの表示 |
|-------------|------|----------------|
| 404 NOT_FOUND | モデル名が無効 | エラーメッセージ（詳細） |
| 429 RATE_LIMITED | APIレート制限 | 「しばらく待ってから再試行してください」 |
| 503 SERVICE_UNAVAILABLE | APIサーバー障害 | 「APIが一時的に利用できません」 |
| FAILED（ファイル状態） | 動画処理エラー | 「別の動画ファイルをお試しください」 |
| タイムアウト（120秒超） | 動画が大きすぎる | 「短い動画か圧縮された動画をお試しください」 |
| スクリーニングNG | 全身が映っていない等 | スクリーニング結果の理由を表示 |

---

## テーマ設定

| 項目 | 値 |
|------|-----|
| ベーステーマ | dark |
| プライマリカラー | #FF4B4B（AkiRun赤） |
| 背景色 | #0F172A |
| サブ背景色 | #1E293B |
| テキスト色 | #FFFFFF |
