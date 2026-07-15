"""
Running Form Diagnosis - 診断再現性測定CLI

同じ動画を同じパイプラインでN回診断し、5項目スコア（SCORES_JSON）と
弱点カテゴリ（WEAKNESS_TAG）がどれだけ揺れるかを統計化する。
src/ や app.py は一切変更せず、既存の analyzer.py の関数をそのまま再利用する。

使用例（アプリルートから実行すること）:
    cd apps/running-form-diagnosis
    python3 tools/reproducibility_test.py --video sample.mp4 --runs 5
    python3 tools/reproducibility_test.py --video sample.mp4 --runs 5 --variant seed --seed 42
    python3 tools/reproducibility_test.py --video sample.mp4 --runs 5 --measure  # 実測値をプロンプトに注入
    python3 tools/reproducibility_test.py --mock --video dummy.mp4   # API不使用（統計ロジックの検証用）

variant:
    prod: 本番と同一の analyze_form()（自動リトライ・フォールバック含む）をそのまま呼ぶ
    seed: analyze_form() と同一の GenerateContentConfig に seed=<値> だけを追加したローカル実装で呼ぶ
          （フォールバックモデルへの切替は行わない。503時は10秒待ち×3回の簡易リトライのみ）
"""
import argparse
import dataclasses
import json
import statistics
import sys
import time
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path

# スクリプト自身の位置から親（アプリルート）を sys.path に追加し、src/ を再利用する
TOOLS_DIR = Path(__file__).resolve().parent
APP_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(APP_ROOT))

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from src.analyzer import (  # noqa: E402
    upload_video,
    analyze_form,
    extract_weakness_tag,
    extract_scores_json,
    cleanup_video,
)
from src.measurement import measure_running_form  # noqa: E402
from src.config import (  # noqa: E402
    SCORE_ITEMS,
    GEMINI_ANALYZER_MODEL,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_THINKING_LEVEL,
    ANALYZE_TIMEOUT_SEC,
)
from src.prompts import ANALYZER_SYSTEM_INSTRUCTION, build_analyzer_prompt  # noqa: E402

# run間の待機秒（API負荷・レート制限対策）
RUN_INTERVAL_SEC = 5

# --variant seed 時の503リトライ（簡易版：フォールバックモデルへの切替は行わない）
SEED_RETRY_MAX_ATTEMPTS = 3
SEED_RETRY_WAIT_SEC = 10


def load_api_key() -> str:
    """apps/running-form-diagnosis/.streamlit/secrets.toml から GEMINI_API_KEY を読む。

    キーの値は一切printしない（printしてよいのは「読み込めた/読み込めなかった」という事実のみ）。
    """
    secrets_path = APP_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        raise RuntimeError(f"secrets.tomlが見つかりません: {secrets_path}")
    with open(secrets_path, "rb") as f:
        data = tomllib.load(f)
    api_key = data.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("secrets.tomlにGEMINI_API_KEYが設定されていません。")
    return api_key


def analyze_form_seed(
    client: genai.Client, video_file, context: str, seed: int,
    measurements: dict | None = None,
) -> str:
    """analyze_form() と同一の GenerateContentConfig に seed だけを追加したローカル実装。

    再現性検証のための比較用。本番の analyze_form() とは異なり、
    503時のフォールバックモデル切替は行わない（プライマリモデルのみで簡易リトライ）。
    """
    user_prompt = build_analyzer_prompt(context, measurements)
    contents = [video_file, user_prompt]
    config = types.GenerateContentConfig(
        system_instruction=ANALYZER_SYSTEM_INSTRUCTION,
        max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        thinking_config=types.ThinkingConfig(
            thinking_level=GEMINI_THINKING_LEVEL,
        ),
        http_options=types.HttpOptions(timeout=ANALYZE_TIMEOUT_SEC * 1000),
        seed=seed,
    )

    for attempt in range(1, SEED_RETRY_MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_ANALYZER_MODEL,
                contents=contents,
                config=config,
            )
        except Exception as e:
            err = str(e)
            if ("503" in err or "Service Unavailable" in err) and attempt < SEED_RETRY_MAX_ATTEMPTS:
                print(f"    [503] {attempt}回目失敗。{SEED_RETRY_WAIT_SEC}秒待機してリトライします...", flush=True)
                time.sleep(SEED_RETRY_WAIT_SEC)
                continue
            raise RuntimeError(f"診断中にエラーが発生しました: {err}")

        text = response.text
        if not text or not text.strip():
            raise RuntimeError("AIが診断テキストを返しませんでした（空レスポンス）。")
        return text

    raise RuntimeError("503_SERVICE_UNAVAILABLE: 診断が503エラーで完了しませんでした。")


def build_mock_text(run_idx0: int) -> str:
    """--mock モード用のダミー診断テキストを生成する（API不使用）。

    run毎にスコアを1項目だけ小さく揺らし、WEAKNESS_TAGも一部変化させることで、
    統計ロジック（min/max/range/stdev・最頻タグ一致率）の動作を確認できるようにする。
    """
    base_scores = {"foot_strike": 7, "pelvis_core": 6, "arm_swing": 8, "hip_extension": 5, "vertical_osc": 6}
    deltas = [0, 1, -1, 0, 1]
    keys = list(SCORE_ITEMS.keys())

    scores = dict(base_scores)
    target_key = keys[run_idx0 % len(keys)]
    delta = deltas[run_idx0 % len(deltas)]
    scores[target_key] = max(1, min(10, scores[target_key] + delta))

    tags = ["glute_core", "glute_core", "mobility", "glute_core", "elasticity"]
    tag = tags[run_idx0 % len(tags)]

    scores_json = json.dumps(scores, ensure_ascii=False)
    return (
        "## 1. 全体評価（良い点）\n"
        "（--mockモードのダミーテキストです）\n\n"
        "## 2. 改善すべき点\n"
        "（--mockモードのダミーテキストです）\n\n"
        "## 3. 具体的なトレーニング提案\n"
        "（--mockモードのダミーテキストです）\n\n"
        f"SCORES_JSON: {scores_json}\n"
        f"WEAKNESS_TAG: {tag}\n"
    )


def run_one(
    client, video_file, context: str, variant: str, seed: int, run_idx: int,
    video_name: str, outdir: Path, mock: bool,
    measurements: dict | None = None,
    measurements_ok: bool = False,
    injected_metrics: list | None = None,
) -> dict:
    """1回分の診断を実行し、レコード（dict）を返す。失敗してもraiseせずerrorフィールドに記録する。

    measurements/measurements_ok/injected_metrics は --measure 時に動画ごとに1回だけ
    計測した結果（呼び出し側で使い回す）。measurements_ok・injected_metrics は
    --measure なし、または --mock 時は常に False / [] になる。
    """
    print(f"  [run {run_idx}] 開始...", flush=True)
    start = time.time()
    record = {
        "video": video_name,
        "variant": variant,
        "seed": seed if variant == "seed" else None,
        "run": run_idx,
        "scores": None,
        "weakness_tag": None,
        "elapsed_sec": None,
        "error": None,
        "fallback_used": False,
        "measurements_ok": measurements_ok,
        "injected_metrics": injected_metrics if injected_metrics is not None else [],
    }

    try:
        if mock:
            text = build_mock_text(run_idx - 1)
        elif variant == "seed":
            text = analyze_form_seed(client, video_file, context, seed, measurements)
        else:
            # フォールバックモデルに切り替わったrunは別モデルの結果であり、
            # 再現性の測定対象から区別できるよう記録する
            progress_state = {}
            text = analyze_form(
                client, video_file, context, progress_state=progress_state, measurements=measurements
            )
            record["fallback_used"] = bool(progress_state.get("fallback", False))

        # 本番パイプライン（app.py）と同一の順序：SCORES_JSON抽出 → WEAKNESS_TAG抽出
        body, scores = extract_scores_json(text)
        body, tag = extract_weakness_tag(body)

        elapsed = time.time() - start
        record["scores"] = scores
        record["weakness_tag"] = tag
        record["elapsed_sec"] = round(elapsed, 1)

        md_path = outdir / f"{video_name}_run{run_idx}.md"
        md_path.write_text(text, encoding="utf-8")

        fallback_note = "（フォールバックモデル使用）" if record["fallback_used"] else ""
        print(f"  [run {run_idx}] 完了（{elapsed:.1f}秒） scores={scores} tag={tag}{fallback_note}", flush=True)

    except Exception as e:
        elapsed = time.time() - start
        record["elapsed_sec"] = round(elapsed, 1)
        record["error"] = str(e)
        print(f"  [run {run_idx}] 失敗（{elapsed:.1f}秒）: {e}", flush=True)

    return record


def build_summary(records: list) -> dict:
    """動画ごとにスコア項目のmin/max/range/stdevとWEAKNESS_TAGの分布・最頻一致率を集計する。"""
    stats = {}
    videos = sorted({r["video"] for r in records})

    for video in videos:
        video_records = [r for r in records if r["video"] == video]
        success = [r for r in video_records if r["error"] is None and r["scores"] is not None]
        n_total = len(video_records)
        n_success = len(success)

        score_stats = {}
        for key in SCORE_ITEMS:
            values = [r["scores"][key] for r in success if r["scores"] and key in r["scores"]]
            if values:
                score_stats[key] = {
                    "min": min(values),
                    "max": max(values),
                    "range": max(values) - min(values),
                    "stdev": round(statistics.stdev(values), 3) if len(values) >= 2 else 0.0,
                    "n": len(values),
                }
            else:
                score_stats[key] = {"min": None, "max": None, "range": None, "stdev": None, "n": 0}

        tags = [r["weakness_tag"] for r in success if r["weakness_tag"]]
        tag_counts = Counter(tags)
        most_common_tag, most_common_count = tag_counts.most_common(1)[0] if tag_counts else (None, 0)
        match_rate = round(most_common_count / n_success, 3) if n_success > 0 else None

        stats[video] = {
            "n_total_runs": n_total,
            "n_success_runs": n_success,
            "n_error_runs": n_total - n_success,
            "score_stats": score_stats,
            "weakness_tag_counts": dict(tag_counts),
            "most_common_tag": most_common_tag,
            "most_common_tag_match_rate": match_rate,
        }

    return stats


def print_markdown_summary(stats: dict) -> None:
    """スコア統計とWEAKNESS_TAG分布をMarkdown表でstdoutに出力する。"""
    print("\n" + "=" * 60)
    print("診断再現性サマリ")
    print("=" * 60)

    for video, s in stats.items():
        print(f"\n### {video}")
        print(f"成功: {s['n_success_runs']}/{s['n_total_runs']} run（失敗: {s['n_error_runs']}）")
        print()
        print("| 項目 | min | max | range | stdev |")
        print("|---|---|---|---|---|")
        for key, label in SCORE_ITEMS.items():
            ss = s["score_stats"][key]
            if ss["n"] == 0:
                print(f"| {label} | - | - | - | - |")
            else:
                print(f"| {label} | {ss['min']} | {ss['max']} | {ss['range']} | {ss['stdev']} |")

        print()
        print("WEAKNESS_TAG出現:")
        if s["weakness_tag_counts"]:
            for tag, count in sorted(s["weakness_tag_counts"].items(), key=lambda kv: -kv[1]):
                print(f"  - {tag}: {count}回")
            if s["most_common_tag_match_rate"] is not None:
                pct = s["most_common_tag_match_rate"] * 100
                print(f"最頻タグ一致率: {s['most_common_tag']}（{pct:.1f}%）")
        else:
            print("  （成功runなし）")


def main():
    parser = argparse.ArgumentParser(
        description="RFD（ランニングフォーム診断アプリ）の診断再現性を測定するCLI。"
                     "同じ動画を同じパイプラインでN回診断し、5項目スコアとWEAKNESS_TAGの揺れを統計化する。"
    )
    parser.add_argument("--video", nargs="+", required=True, help="診断する動画ファイルパス（複数指定可）")
    parser.add_argument("--runs", type=int, default=5, help="動画1本あたりの診断回数（デフォルト5）")
    parser.add_argument(
        "--variant", choices=["prod", "seed"], default="prod",
        help="prod: 本番同一のanalyze_form()を使用 / seed: 同一設定+seed固定のローカル実装を使用",
    )
    parser.add_argument("--seed", type=int, default=42, help="--variant seed 時に使うseed値（デフォルト42）")
    parser.add_argument("--outdir", default=None, help="出力先ディレクトリ（省略時は自動生成）")
    parser.add_argument("--context", default="", help="診断時に渡すコンテキスト文字列（省略可）")
    parser.add_argument("--mock", action="store_true", help="APIを呼ばずダミーテキストで統計ロジックのみ検証する")
    parser.add_argument(
        "--measure", action="store_true",
        help="診断前に src.measurement.measure_running_form() を動画ごとに1回実行し、"
             "結果をプロンプトに注入する（フェーズ2測定層）。--mock時は測定自体を行わない",
    )
    args = parser.parse_args()

    if args.outdir:
        outdir = Path(args.outdir)
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        outdir = TOOLS_DIR / "repro_results" / f"{ts}_{args.variant}"
    outdir.mkdir(parents=True, exist_ok=True)

    if not args.mock:
        missing = [v for v in args.video if not Path(v).exists()]
        if missing:
            print(f"エラー: 動画ファイルが見つかりません: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)

    client = None
    if not args.mock:
        try:
            api_key = load_api_key()
        except RuntimeError as e:
            print(f"エラー: {e}", file=sys.stderr)
            sys.exit(1)
        client = genai.Client(api_key=api_key)

    print(f"variant={args.variant} runs={args.runs} outdir={outdir}" + (" (mock)" if args.mock else ""))

    all_records = []

    for video_path_str in args.video:
        video_name = Path(video_path_str).stem
        print(f"\n=== 動画: {video_name} ===", flush=True)

        # 測定は動画ごとに1回だけ実行し、全runで同じ辞書を使い回す（決定的な処理のため
        # runごとに再実行しても結果は変わらず、時間の無駄になる）。--mock時は測定自体を
        # 行わず measurements_ok=False・injected_metrics=[] のまま扱う
        measurement_dict = None
        measurements_ok = False
        injected_metrics: list = []
        if args.measure and not args.mock:
            print("  フォーム計測中...", flush=True)
            t_m0 = time.time()
            measurement_result = measure_running_form(video_path_str)
            measurements_ok = measurement_result.ok
            measurement_dict = dataclasses.asdict(measurement_result)
            if measurement_result.ok:
                injected_metrics = [
                    key for key, m in measurement_result.metrics.items()
                    if m.get("reliable") and m.get("value") is not None
                ]
            print(
                f"  フォーム計測完了（{time.time() - t_m0:.1f}秒） "
                f"ok={measurements_ok} injected={injected_metrics}"
                + ("" if measurements_ok else f" reason={measurement_result.reason}"),
                flush=True,
            )

        video_file = None
        try:
            if not args.mock:
                video_bytes = Path(video_path_str).read_bytes()
                print("  アップロード中...", flush=True)
                t0 = time.time()
                video_file = upload_video(client, video_bytes, Path(video_path_str).name)
                print(f"  アップロード完了（{time.time() - t0:.1f}秒）", flush=True)

            for run_idx in range(1, args.runs + 1):
                record = run_one(
                    client, video_file, args.context, args.variant, args.seed,
                    run_idx, video_name, outdir, args.mock,
                    measurements=measurement_dict,
                    measurements_ok=measurements_ok,
                    injected_metrics=injected_metrics,
                )
                all_records.append(record)
                if run_idx < args.runs:
                    time.sleep(RUN_INTERVAL_SEC)

        finally:
            if video_file is not None:
                print("  クリーンアップ中...", flush=True)
                cleanup_video(client, video_file)

    summary = build_summary(all_records)

    summary_path = outdir / "summary.json"
    summary_payload = {
        "generated_at": datetime.now().isoformat(),
        "variant": args.variant,
        "seed": args.seed if args.variant == "seed" else None,
        "runs": args.runs,
        "mock": args.mock,
        "measure": args.measure,
        "records": all_records,
        "stats": summary,
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print_markdown_summary(summary)
    print(f"\n結果を保存しました: {outdir}")


if __name__ == "__main__":
    main()
