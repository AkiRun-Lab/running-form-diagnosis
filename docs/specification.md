# 仕様書 — ランニングフォーム診断

## システム概要

| 項目 | 内容 |
|------|------|
| アプリ名 | ランニングフォーム診断 |
| バージョン | 1.12.0 |
| フレームワーク | Streamlit |
| ホスティング | Streamlit Community Cloud |
| 本番URL | https://running-form-diagnosis.streamlit.app/ |
| AIバックエンド | Google Gemini API（google-genai SDK） |
| リポジトリ | https://github.com/AkiRun-Lab/running-form-diagnosis |

---

## アーキテクチャ

```
ユーザー（ブラウザ）
  ↓ 動画アップロード
Streamlit app.py
  ↓
[0] ローカル姿勢推定（測定層・src/measurement.py・MEASUREMENT_ENABLED時のみ）
    ・一時ファイル化した動画をMediaPipe PoseLandmarkerで解析（Gemini非依存・ローカル実行）
    ・ケイデンス・体幹前傾角・上下動比・オーバーストライド指標・接地時間比を計測
    ・失敗（側面撮影でない・検出不能等）時は例外を投げず ok=False を返し、以降は測定なしで続行
  ↓
[1] Gemini Files API
    動画をアップロード → ACTIVE 状態になるまでポーリング
  ↓
[2] 動画長さチェック（Python側・Files APIメタデータ）
    ・video_metadata.video_duration で 5秒以上5分以下か確認
    → 範囲外の場合はファイルを削除してエラーを返す
  ↓
[3] gemini-3.5-flash-lite（スクリーニング）
    ・全身が映っているか
    ・ランナー（人物）が映っているか
    → {"ok": bool, "reason": str} を返す
  ↓ ok=True の場合のみ
[4] gemini-3.6-flash（フォーム診断）
    ・thinking_level=high で深層推論
    ・接地・骨盤・腕振り・上下動・疲労による代償動作を分析
    ・[0]の実測値が得られていればプロンプトに注入し、診断根拠として使用
    → マークダウン形式の診断レポートを返す
  ↓
[5] Gemini Files API からファイルを削除（cleanup）
  ↓
Streamlit 診断結果表示（実測値カード（β）含む）+ Markdown ダウンロードボタン
```

---

## Gemini API パラメータ

### スクリーニング（gemini-3.5-flash-lite）

| パラメータ | 値 | 理由 |
|-----------|-----|------|
| max_output_tokens | 256 | JSON のみを返すため小さく設定 |

※ `temperature` / `top_p` / `top_k` は全 Gemini 3.x モデルで非推奨のため指定しない。

### 診断（gemini-3.6-flash）

| パラメータ | 値 | 理由 |
|-----------|-----|------|
| max_output_tokens | 24576 | 詳細な診断レポートに対応（thinkingトークンも消費するため、本文の必要量にthinking_level=highの余裕を上乗せ） |
| thinking_level | high | 接地・骨盤・腕振りの物理的因果関係の深い推論のために最大段階を指定 |
| seed | 42 | 診断再現性向上のための固定シード（ベストエフォート。詳細は`docs/reproducibility-phase0.md`） |

※ `temperature` / `top_p` / `top_k` は Gemini 3.6 Flash のデフォルト設定に最適化済みのため非推奨（指定しない）

---

## ファイル構成

```
running-form-diagnosis/
├── app.py                      # メインUIエントリポイント
├── requirements.txt            # 依存パッケージ
├── packages.txt                # Streamlit Cloud aptパッケージ（opencv-contrib実行時依存）
├── .gitignore
├── .streamlit/
│   ├── config.toml             # テーマ設定（ダークテーマ・シアン系）
│   ├── secrets.toml            # APIキー（gitignore済み・本番はStreamlit Secrets）
│   └── secrets.toml.example   # テンプレート
├── models/
│   └── pose_landmarker_lite.task  # MediaPipe Poseモデル（測定層・リポジトリ同梱）
├── src/
│   ├── config.py               # モデル名・APIパラメータ定数
│   ├── screener.py             # gemini-3.5-flash-lite によるスクリーニング
│   ├── analyzer.py             # アップロード・診断（gemini-3.6-flash）・クリーンアップ
│   ├── measurement.py          # MediaPipe姿勢推定による測定層（フェーズ2・Gemini非依存）
│   ├── prompts.py              # システムインストラクション・プロンプトテンプレート（実測値注入含む）
│   └── ui/
│       └── components.py       # render_header / render_result / render_measurements / render_footer
├── tools/
│   ├── reproducibility_test.py # 診断再現性測定CLI（--measureで測定層を統合検証可）
│   └── measure_video.py        # 測定層単体の検証スクリプト
└── docs/
    ├── user-manual.md          # ユーザーマニュアル
    ├── specification.md        # 本ファイル
    ├── pose-metrics-design.md  # フェーズ2（測定層）設計文書
    └── reproducibility-phase0.md  # 診断再現性フェーズ0測定レポート
```

---

## 依存パッケージ

```
streamlit>=1.30.0
google-genai>=2.7.0
streamlit-cookies-controller>=0.0.4
plotly>=5.24.0
mediapipe>=0.10.35
```

MediaPipeの依存でopencv-contrib-pythonが導入され、cv2はこれで提供される
（`opencv-python-headless` は二重インストール回避のため追加しない）。
Streamlit Cloud（Linux）ではopencv-contribの実行時依存として `packages.txt`
（`libgl1`・`libglib2.0-0`）が必要。

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
| プライマリカラー | #22D3EE（シアン） |
| 背景色 | #0F172A |
| サブ背景色 | #1E293B |
| テキスト色 | #FFFFFF |
