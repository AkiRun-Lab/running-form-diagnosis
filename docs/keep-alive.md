# RFD 自動起動（Keep Alive）マニュアル

## 概要

ランニングフォーム診断ツール（RFD）は Streamlit Community Cloud の無料プランで動いています。
無料プランでは一定期間アクセスがないとアプリが**スリープ状態**になり、次に誰かが訪問したとき起動待ち（最大 2 分）が発生します。

これを防ぐため、GitHub Actions で **6時間ごとに自動でアプリを起動** しています。
スリープ中であれば Wake up ボタンを自動クリックしてアプリを再起動します。

---

## 自動実行スケジュール

| UTC | JST | 動作 |
|---|---|---|
| 0:00 | 9:00 | 自動チェック・起動 |
| 6:00 | 15:00 | 自動チェック・起動 |
| 12:00 | 21:00 | 自動チェック・起動 |
| 18:00 | 3:00 | 自動チェック・起動 |

---

## 動作履歴（ログ）の確認方法

### ステップ 1：GitHub リポジトリを開く

[https://github.com/AkiRun-Lab/running-form-diagnosis](https://github.com/AkiRun-Lab/running-form-diagnosis) にアクセス。

### ステップ 2：Actions タブを開く

ページ上部の「**Actions**」タブをクリック。

### ステップ 3：ワークフローを選択

左側のサイドバーに「**Keep Alive - RFD (Running Form Diagnosis)**」が表示されます。クリックしてください。

### ステップ 4：実行履歴を確認

直近の実行一覧が表示されます。

| アイコン | 意味 |
|---|---|
| ✅ 緑のチェック | 正常完了 |
| ❌ 赤の × | エラーで失敗 |
| 🟡 黄色の円 | 実行中 |

### ステップ 5：ログの詳細を読む

実行行をクリック → 「**wake-up**」ジョブ → 「**Wake up RFD App**」ステップを開くと詳細ログが見えます。

**ログの読み方：**

```
STATUS: RUNNING - No action needed.
```
→ アプリは起動中でした。問題なし。

```
STATUS: SLEEPING - Clicking wake-up button...
Wake-up request sent. App should be starting.
```
→ スリープを検知して起動しました。

```
ERROR: ○○○
```
→ 何らかのエラーが発生しました（ネットワーク遅延など一時的な問題が多い）。

---

## 今すぐ手動で起動する方法

ユーザーが来る前にアプリを確実に起動しておきたい場合などに使います。

1. [Actions タブ](https://github.com/AkiRun-Lab/running-form-diagnosis/actions/workflows/keep-alive.yml) を開く
2. 右側の「**Run workflow**」ボタンをクリック
3. 「Run workflow」を押す
4. 数秒後にジョブが開始されます（完了まで 3〜5 分）

---

## よくある質問

**Q: 毎回「RUNNING」と表示されていればOK？**
A: はい。「RUNNING」はアプリが起動済みだったことを意味します。

**Q: ワークフローが表示されなくなった**
A: GitHub Actions の cron は 60 日間リポジトリへの push がないと自動停止します。「Run workflow」で手動実行するか、何かコードを push してください。

**Q: ログに「ERROR」が出ている**
A: 1〜2 回のエラーは一時的なネットワーク問題が多く、次の実行では自動回復します。毎回エラーになる場合は Streamlit 側の仕様変更の可能性があります。
