"""
Running Form Diagnosis - 測定モジュール検証CLI（フェーズ2 STEP A）

src/measurement.py の measure_running_form() を動画に対してN回実行し、
(1) 全指標値のテーブル表示、(2) repeat間の決定性判定、(3) 結果をJSONで保存する。
src/ の既存モジュール・app.py は一切変更せず、measurement.py を新規に呼ぶだけ。

使用例（アプリルートから実行すること）:
    .venv/bin/python tools/measure_video.py --video test.MOV test1.MOV --repeat 2
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
APP_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(APP_ROOT))

from src.measurement import measure_running_form  # noqa: E402

RESULT_DIR = TOOLS_DIR / "repro_results"
RESULT_PATH = RESULT_DIR / "measurement_check.json"


def result_to_dict(result) -> dict:
    return {
        "ok": result.ok,
        "reason": result.reason,
        "fps": result.fps,
        "n_frames_analyzed": result.n_frames_analyzed,
        "detection_rate": result.detection_rate,
        "view": result.view,
        "metrics": result.metrics,
        "window_start_sec": result.window_start_sec,
        "window_end_sec": result.window_end_sec,
    }


def print_table(video_name: str, runs: list) -> None:
    print(f"\n=== {video_name} ===")
    for i, r in enumerate(runs, start=1):
        print(f"\n--- run {i} ({r['elapsed_sec']:.1f}秒) ---")
        d = r["result"]
        print(f"  ok={d['ok']}  reason={d['reason'] or '-'}")
        print(f"  fps={d['fps']:.2f}  n_frames_analyzed={d['n_frames_analyzed']}  "
              f"detection_rate={d['detection_rate']:.3f}  view={d['view']}  "
              f"window={d['window_start_sec']:.1f}〜{d['window_end_sec']:.1f}s")
        if d["metrics"]:
            print(f"  {'指標':<20}{'値':>12}{'単位':>6}{'信頼':>8}  詳細")
            for name, m in d["metrics"].items():
                val = "N/A" if m["value"] is None else m["value"]
                print(f"  {name:<20}{val!s:>12}{m['unit']:>6}{str(m['reliable']):>8}  {m['detail']}")


def check_determinism(runs: list) -> bool:
    if len(runs) < 2:
        return True
    base = json.dumps(runs[0]["result"], sort_keys=True, ensure_ascii=False)
    for r in runs[1:]:
        if json.dumps(r["result"], sort_keys=True, ensure_ascii=False) != base:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="測定モジュール検証CLI")
    parser.add_argument("--video", nargs="+", required=True, help="検証する動画パス（複数可）")
    parser.add_argument("--repeat", type=int, default=2, help="各動画の測定回数（デフォルト2）")
    args = parser.parse_args()

    all_results = {}

    for video_path in args.video:
        video_name = Path(video_path).name
        runs = []
        for i in range(args.repeat):
            start = time.time()
            result = measure_running_form(video_path)
            elapsed = time.time() - start
            runs.append({"elapsed_sec": elapsed, "result": result_to_dict(result)})
            print(f"[{video_name}] run {i + 1}/{args.repeat} 完了（{elapsed:.1f}秒）")

        print_table(video_name, runs)

        deterministic = check_determinism(runs)
        print(f"\n  決定性（{args.repeat}回で完全一致）: {'YES' if deterministic else 'NO'}")

        all_results[video_name] = {
            "video_path": str(video_path),
            "runs": runs,
            "deterministic": deterministic,
        }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "generated_at": datetime.now().isoformat(),
        "repeat": args.repeat,
        "results": all_results,
    }
    RESULT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n結果をJSONで保存しました: {RESULT_PATH}")


if __name__ == "__main__":
    main()
