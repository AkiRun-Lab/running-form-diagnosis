# ランニングフォーム診断

ランニング動画をアップロードすると、Google Gemini AIがバイオメカニクスの観点からフォームを診断するStreamlitアプリです。

**[アプリを使う → https://running-form-diagnosis.streamlit.app/](https://running-form-diagnosis.streamlit.app/)**

**[AkiRun](https://akirun.net/)** が開発・運営しています。

---

## 機能

- 動画アップロード（MP4 / MOV / AVI / WEBM、最大200MB）
- gemini-3.1-flash-lite による動画スクリーニング（画角・人物の確認）
- gemini-3.5-flash + Thinking Mode による深層フォーム診断
- 練習内容・気になる点のコンテキスト入力
- 診断結果のMarkdownファイルダウンロード

## 診断内容

1. **全体評価（良い点）**：動きの連動性・効率的なポイント
2. **改善すべき点**：力学的根拠とともにエネルギーロスの要因を解説
3. **ドリル・トレーニング提案**：優先度順に3〜5個の具体的な改善案

## ローカルでの起動

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# APIキーの設定
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# secrets.toml を編集して GEMINI_API_KEY を設定

# アプリ起動
python3 -m streamlit run app.py
```

## デプロイ

Streamlit Cloud を使用します。詳細は [仕様書](docs/specification.md) を参照してください。

## ドキュメント

- [ユーザーマニュアル](docs/user-manual.md)
- [仕様書](docs/specification.md)
- [更新履歴](CHANGELOG.md)

## 関連ツール

- [マラソンペース計算ツール（MPC）](https://akirun.net/lp/marathon-simulator/)
- [マラソントレーニング・プランナー（MTP）](https://akirun.net/lp/ai-marathon-coach/)

## ライセンス

© 2026 AkiRun. All rights reserved.
