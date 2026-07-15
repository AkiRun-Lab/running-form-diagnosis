"""MediaPipe姿勢推定による測定層（フェーズ2 STEP A・v4）。

Streamlitに依存しない純粋モジュール。動画から実測値（ケイデンス・体幹前傾角・
上下動比・オーバーストライド指標・接地時間比）を計算する。

v4の処理構成:
1. パス1: 全フレームをPoseLandmarker処理（20秒超の動画は2フレームに1回、さらに
   総フレーム数が_PASS1_MAX_FRAMESを超える長尺動画は適応的に間引く決定的間引き。
   長尺動画ではウィンドウ選択の端がstepフレーム単位に粗くなるが、パス2が選択区間を
   全フレームで再処理するため指標への影響は小さい）
2. 解析ウィンドウ自動選択（長さ5〜15秒・検出率×被写体サイズのスコア最大区間）
3. パス2: 間引きが入った動画では、選択ウィンドウ区間だけを全フレーム（間引きなし）で
   新しいPoseLandmarkerインスタンスで再処理し、指標計算はパス2のランドマークで行う
   （VIDEOモードは状態を持つため、パス1のインスタンスは再利用しない）
4. 撮影方向別の部分計測（側面=全5指標／front_or_back=cadence・vertical_osc_ratioのみ）
5. vertical_osc_ratioは移動平均デトレンドでカメラパン・ドリフトを除去し、2〜12%の
   妥当レンジゲートを適用

グレースフルデグラデーションを原則とする：測定処理のいかなる失敗も例外を投げず、
MeasurementResult.ok=False＋reasonで理由を返す。ok=Trueの条件は「解析ウィンドウが
確保でき、計測できた指標が1つ以上あること」。呼び出し側（app.py）はok=Falseの
場合、実測値なしで従来どおりの診断を継続する。

参照：docs/pose-metrics-design.md（フェーズ2設計・承認済み）
"""

from __future__ import annotations

import math
import os
import statistics
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

# --- 定数 ---

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "pose_landmarker_lite.task")
_TARGET_LONG_EDGE_PX = 640
_MIN_DETECTION_RATE = 0.8
_SIDE_VIEW_RATIO_THRESHOLD = 0.5
_MIN_CONTACT_EVENTS = 4
# 接地依存指標（オーバーストライド・接地時間比）の信頼度に必要な接地イベント数。
# 接地サンプルが少ないと動画デコーダの環境差（macOS/Linuxのffmpeg差）だけで値が
# 大きく振れることが実測で確認されたため、計測全体の成立条件（4回）より厳しくする
_CONTACT_MIN_EVENTS_FOR_CONTACT_METRICS = 6
_SMOOTHING_WINDOW = 3
_HEAD_TOP_CORRECTION = 1.08
_CADENCE_MIN_SPM = 120
_CADENCE_MAX_SPM = 220
_DUTY_FACTOR_MIN_FPS = 25

# 解析ウィンドウ自動選択（v3・改良1）
_WINDOW_MIN_SEC = 5.0
_WINDOW_MAX_SEC = 15.0
_WINDOW_START_STEP_SEC = 0.5
_WINDOW_LEN_STEP_SEC = 1.0
_DECIMATE_OVER_SEC = 20.0   # この秒数を超える動画はパス1で最低2フレームに1回処理（決定的間引き）
_PASS1_MAX_FRAMES = 900     # パス1で姿勢推定するフレーム数の上限（長尺動画のCPU時間対策・STEP B）

# 接地検出v2（値レンジ基準）
_CONTACT_BAND_RATIO = 0.10       # y >= y_max - 0.10*(y_max - y_min) を接地帯とする
_CONTACT_MAX_GAP_FRAMES = 1      # 1フレーム以下のギャップは結合
_CONTACT_MIN_SEG_FRAMES = 3      # 3フレーム未満の区間は破棄

# ケイデンスv6（腰バウンス方式）
_STEP_PERIOD_MIN_SEC = 60.0 / 220.0   # ステップ周期の探索下限（220spm相当）
_STEP_PERIOD_MAX_SEC = 60.0 / 60.0    # ステップ周期の探索上限（60spm相当）
_CADENCE_HIP_ANKLE_TOLERANCE = 0.10   # 腰方式とankle方式の乖離許容（10%超で信頼度低）
# 腰中点yは骨盤の左右非対称でストライド周波数成分がステップ成分より強く出るため、
# サブハーモニック（1/2ラグ＝ステップ周期）採用の閾値を足首より緩める
_HIP_SUBHARMONIC_RATIO = 0.3

# duty factor v2 の物理妥当レンジ（%）
_DUTY_FACTOR_MIN_PCT = 15.0
_DUTY_FACTOR_MAX_PCT = 60.0

# vertical_osc_ratio v4 の妥当レンジ（%・デトレンド後）
_VOSC_MIN_PCT = 2.0
_VOSC_MAX_PCT = 12.0

_NOT_SIDE_DETAIL = "側面撮影でないため計測不可"

# MediaPipe Pose 33ランドマークのインデックス（公式定義）
_LM_NOSE = 0
_LM_LEFT_SHOULDER = 11
_LM_RIGHT_SHOULDER = 12
_LM_LEFT_HIP = 23
_LM_RIGHT_HIP = 24
_LM_LEFT_ANKLE = 27
_LM_RIGHT_ANKLE = 28


@dataclass
class MeasurementResult:
    ok: bool
    reason: str = ""
    fps: float = 0.0
    n_frames_analyzed: int = 0
    detection_rate: float = 0.0
    view: str = "unknown"
    metrics: dict = field(default_factory=dict)
    window_start_sec: float = 0.0   # 選択された解析ウィンドウの開始秒（v3）
    window_end_sec: float = 0.0     # 選択された解析ウィンドウの終了秒（v3）


def _metric(value: Optional[float], unit: str, reliable: bool, detail: str) -> dict:
    return {
        "value": None if value is None else round(float(value), 2),
        "unit": unit,
        "reliable": bool(reliable) if value is not None else False,
        "detail": detail,
    }


def _resize_long_edge(frame: np.ndarray, target: int) -> np.ndarray:
    h, w = frame.shape[:2]
    long_edge = max(h, w)
    if long_edge <= target:
        return frame
    scale = target / long_edge
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _smooth(series: list, window: int) -> list:
    """単純移動平均。Noneは除外して利用可能な範囲で平均する。"""
    n = len(series)
    if n == 0:
        return []
    out = []
    half = window // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        vals = [series[j] for j in range(lo, hi) if series[j] is not None]
        out.append(sum(vals) / len(vals) if vals else None)
    return out


def _percentile(values: list, pct: float) -> float:
    return float(np.percentile(np.array(values, dtype=float), pct))


def _detect_contact_frames(ankle_y: list, valid_mask: list) -> list:
    """足首y系列から接地区間 [(start_idx, end_idx), ...] を返す（接地検出v2）。

    v2仕様（分布パーセンタイルではなく値レンジ基準）:
    1. その足のy値レンジに対し y >= y_max - 0.10*(y_max - y_min) を接地帯とする
       （画像座標はy下向き正のため、y最大＝最下点＝接地）
    2. 1フレーム以下のギャップは結合、3フレーム未満の区間は破棄（ノイズ除去）
    3. 各区間の開始フレーム＝初期接地
    """
    valid_y = [y for y, v in zip(ankle_y, valid_mask) if v and y is not None]
    if len(valid_y) < 5:
        return []
    y_max = max(valid_y)
    y_min = min(valid_y)
    y_range = y_max - y_min
    if y_range <= 1e-6:
        return []
    threshold = y_max - _CONTACT_BAND_RATIO * y_range

    # 接地帯フラグから素の区間を抽出
    segments = []
    in_contact = False
    start = None
    for i, (y, v) in enumerate(zip(ankle_y, valid_mask)):
        is_contact = bool(v and y is not None and y >= threshold)
        if is_contact and not in_contact:
            start = i
            in_contact = True
        elif not is_contact and in_contact:
            segments.append((start, i - 1))
            in_contact = False
    if in_contact and start is not None:
        segments.append((start, len(ankle_y) - 1))

    # 1フレーム以下のギャップは結合
    merged = []
    for seg in segments:
        if merged and seg[0] - merged[-1][1] - 1 <= _CONTACT_MAX_GAP_FRAMES:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)

    # 3フレーム未満の区間は破棄
    cleaned = [seg for seg in merged if seg[1] - seg[0] + 1 >= _CONTACT_MIN_SEG_FRAMES]
    return cleaned


def _estimate_period_sec(
    series: list,
    valid_mask: list,
    fps: float,
    min_period_sec: float = 0.3,
    max_period_sec: Optional[float] = None,
    subharmonic_ratio: float = 0.5,
) -> tuple[Optional[float], bool]:
    """座標y系列の自己相関から周期（秒）を推定する。

    足首y系列に対してはストライド周期（v5まで）、デトレンド済み腰中点y系列に
    対してはステップ周期（v6）の推定に使う。有効フレームの範囲を切り出し、
    欠損を線形補間した後、平均を引いた系列の自己相関を計算。探索ラグ範囲
    [min_period_sec, max_period_sec]（上限省略時は系列長の半分）で自己相関が
    最大となるラグを周期とみなす。推定不能なら(None, False)を返す。

    戻り値: (周期秒 または None, best_lagが探索範囲の下限・上限に張り付いたか)。
    境界張り付きは「生理帯域にピークが見つからず探索範囲の端で打ち切られた」
    ことを示すため、呼び出し側でその方式の推定失敗とみなす判断に使える
    （STEP B・腰バウンス方式のフォールバック判定で使用）。
    """
    arr = np.array([y if (v and y is not None) else np.nan
                    for y, v in zip(series, valid_mask)], dtype=float)
    valid_idx = np.where(~np.isnan(arr))[0]
    if len(valid_idx) < int(fps):  # 有効データ1秒未満では推定しない
        return None, False
    seg = arr[valid_idx.min(): valid_idx.max() + 1]
    nan_mask = np.isnan(seg)
    if nan_mask.any():
        idx = np.arange(len(seg))
        seg[nan_mask] = np.interp(idx[nan_mask], idx[~nan_mask], seg[~nan_mask])

    seg = seg - seg.mean()
    n = len(seg)
    min_lag = max(2, int(round(min_period_sec * fps)))
    max_lag = n // 2
    if max_period_sec is not None:
        max_lag = min(max_lag, int(round(max_period_sec * fps)))
    if max_lag <= min_lag:
        return None, False

    denom = float(np.dot(seg, seg))
    if denom <= 1e-9:
        return None, False
    autocorr = np.correlate(seg, seg, mode="full")[n - 1:] / denom
    lag_range = autocorr[min_lag: max_lag + 1]
    best_lag = min_lag + int(np.argmax(lag_range))
    if autocorr[best_lag] <= 0:  # 周期性が見えない
        return None, False

    # 倍音対策: best_lagの1/2・1/3のラグ近傍にも強いピークがあれば短い方を採用
    # （自己相関は真の周期の整数倍にもピークを持つため）。
    # 採用条件は「そのラグが自己相関の局所極大であること」を必須とする
    # （短ラグは系列の滑らかさだけで値が高くなるため、値の比較だけでは誤検出する）
    for k in (3, 2):
        sub_lag = best_lag // k
        if sub_lag < min_lag:
            continue
        lo = max(min_lag, sub_lag - 2)
        hi = min(max_lag, sub_lag + 2)
        local = autocorr[lo: hi + 1]
        sub_best = lo + int(np.argmax(local))
        is_local_peak = (
            sub_best - 1 >= 0
            and sub_best + 1 < len(autocorr)
            and autocorr[sub_best] > autocorr[sub_best - 1]
            and autocorr[sub_best] >= autocorr[sub_best + 1]
        )
        if (is_local_peak
                and autocorr[sub_best] >= subharmonic_ratio * autocorr[best_lag]
                and autocorr[sub_best] > 0):
            best_lag = sub_best
            break

    # 境界張り付き判定（STEP B）: 倍音対策で内部の局所ピークに置き換わらず、
    # 最終的なbest_lagが探索範囲の下限・上限のままなら「生理帯域にピークが
    # 見つからず探索範囲の端で打ち切られた」ことを意味する。この場合、周期の
    # 値自体は返すが、boundary_hit=Trueとして呼び出し側に推定失敗の可能性を伝える。
    boundary_hit = (best_lag == min_lag or best_lag == max_lag)

    # サブフレーム補間（v5）: 整数ラグの量子化誤差（30fps・周期18フレームで約±5%）を
    # 低減するため、確定ラグの近傍3点 (k-1, k, k+1) に放物線をフィットして頂点を採用する
    refined_lag = float(best_lag)
    if 1 <= best_lag < len(autocorr) - 1:
        y1 = float(autocorr[best_lag - 1])
        y2 = float(autocorr[best_lag])
        y3 = float(autocorr[best_lag + 1])
        denom_parab = y1 - 2.0 * y2 + y3
        if abs(denom_parab) > 1e-12:
            delta = 0.5 * (y1 - y3) / denom_parab
            if delta > 0.5:
                delta = 0.5
            elif delta < -0.5:
                delta = -0.5
        else:
            delta = 0.0
        refined_lag = best_lag + delta

    return refined_lag / fps, boundary_hit


def _select_window(valid_mask: list, sizes: list, eff_fps: float) -> Optional[tuple]:
    """解析ウィンドウ自動選択（v3・改良1）。

    長さ5〜15秒の連続ウィンドウのうち、スコア＝（ウィンドウ内検出率）×
    （被写体サイズ中央値の正規化値）が最大の区間を返す。検出率0.8以上の
    ウィンドウが存在しなければNoneを返す。すべて決定的な処理
    （候補はソート順に評価し、同点は先に見つかった方を採用）。

    戻り値: (start_idx, end_idx)（処理済みフレーム系列のインデックス・両端含む）
    """
    n = len(valid_mask)
    if n == 0:
        return None

    min_len = max(1, int(round(_WINDOW_MIN_SEC * eff_fps)))
    max_len = max(min_len, int(round(_WINDOW_MAX_SEC * eff_fps)))
    start_step = max(1, int(round(_WINDOW_START_STEP_SEC * eff_fps)))
    len_step = max(1, int(round(_WINDOW_LEN_STEP_SEC * eff_fps)))

    candidates = set()
    if n <= min_len:
        candidates.add((0, n - 1))  # 動画が5秒以下なら全体を唯一の候補にする
    else:
        for length in range(min_len, min(max_len, n) + 1, len_step):
            for start in range(0, n - length + 1, start_step):
                candidates.add((start, start + length - 1))
            candidates.add((n - length, n - 1))  # 末尾整列ウィンドウも必ず候補に含める
        if n <= max_len:
            candidates.add((0, n - 1))  # 動画全体も候補にする

    valid_arr = np.array(valid_mask, dtype=int)
    prefix = np.concatenate([[0], np.cumsum(valid_arr)])

    qualified = []  # (start, end, det_rate, median_size)
    for start, end in sorted(candidates):
        length = end - start + 1
        det_rate = float(prefix[end + 1] - prefix[start]) / length
        if det_rate < _MIN_DETECTION_RATE:
            continue
        window_sizes = [sizes[i] for i in range(start, end + 1)
                        if valid_mask[i] and sizes[i] is not None]
        if not window_sizes:
            continue
        qualified.append((start, end, det_rate, statistics.median(window_sizes)))

    if not qualified:
        return None

    max_median = max(q[3] for q in qualified)
    if max_median <= 1e-9:
        return None

    best = None
    best_score = -1.0
    for start, end, det_rate, median_size in qualified:  # ソート済み→同点は先頭優先で決定的
        score = det_rate * (median_size / max_median)
        if score > best_score:
            best_score = score
            best = (start, end)
    return best


def measure_running_form(video_path: str) -> MeasurementResult:
    try:
        return _measure_running_form_impl(video_path)
    except Exception as exc:  # グレースフルデグラデーション：例外は投げない
        return MeasurementResult(ok=False, reason=f"計測処理中にエラーが発生しました（{exc}）")


def _measure_running_form_impl(video_path: str) -> MeasurementResult:
    if not os.path.exists(_MODEL_PATH):
        return MeasurementResult(ok=False, reason="計測モデルファイルが見つかりませんでした")

    probe = cv2.VideoCapture(video_path)
    if not probe.isOpened():
        return MeasurementResult(ok=False, reason="動画を開けませんでした")
    fps = probe.get(cv2.CAP_PROP_FPS)
    total_frames = int(probe.get(cv2.CAP_PROP_FRAME_COUNT))
    probe.release()

    if not fps or fps <= 0:
        return MeasurementResult(ok=False, reason="動画のフレームレートを取得できませんでした")

    duration = total_frames / fps if total_frames > 0 else 0.0

    # 20秒超の動画はパス1を2フレームに1回処理（決定的間引き）。さらに長尺動画は
    # _PASS1_MAX_FRAMES を上限とする適応間引きでCPU時間を抑える（5分動画で step=10 ≒ 実効3fps）。
    # ウィンドウ端がstep単位に丸まる粗さはパス2の全フレーム再処理で吸収される
    base_step = 2 if duration > _DECIMATE_OVER_SEC else 1
    cap_step = math.ceil(total_frames / _PASS1_MAX_FRAMES) if total_frames > 0 else 1
    frame_step = max(base_step, cap_step)
    pass1_fps = fps / frame_step

    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            PoseLandmarker,
            PoseLandmarkerOptions,
            RunningMode,
        )
    except Exception as exc:
        return MeasurementResult(ok=False, reason=f"MediaPipeの読み込みに失敗しました（{exc}）")

    def collect(step: int, start_frame: int = 0, end_frame: Optional[int] = None) -> Optional[dict]:
        """動画を先頭から読み、[start_frame, end_frame]（両端含む）のフレームを
        step間隔でPoseLandmarker処理してランドマーク座標を蓄積する（v4・パス共通）。

        パスごとに新しいPoseLandmarkerインスタンスを生成する（VIDEOモードは
        状態を持つため、インスタンスを跨いで再利用すると決定性を壊す恐れがある）。
        フレーム画像は溜めない。シーク（CAP_PROP_POS_FRAMES）はコーデックに
        よって不正確になりうるため使わず、先頭から順に読み飛ばす。
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
        )

        data = {
            "orig_idx": [],   # 元動画のフレーム番号
            "secs": [],       # 動画内秒位置
            "nose_y": [],
            "l_shoulder": [],
            "r_shoulder": [],
            "l_hip": [],
            "r_hip": [],
            "l_ankle": [],
            "r_ankle": [],
            "valid": [],
            "sizes": [],      # 被写体サイズ（検出時の鼻y〜足首y平均のピクセル距離）
        }

        frame_idx = 0
        frame_w = frame_h = None

        with PoseLandmarker.create_from_options(options) as landmarker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if end_frame is not None and frame_idx > end_frame:
                    break
                if frame_idx < start_frame or (frame_idx - start_frame) % step != 0:
                    frame_idx += 1
                    continue

                frame = _resize_long_edge(frame, _TARGET_LONG_EDGE_PX)
                if frame_w is None:
                    frame_h, frame_w = frame.shape[:2]

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int(round((frame_idx - start_frame) * (1000.0 / fps)))

                result = landmarker.detect_for_video(mp_image, timestamp_ms)
                data["orig_idx"].append(frame_idx)
                data["secs"].append(frame_idx / fps)

                if result.pose_landmarks:
                    lms = result.pose_landmarks[0]

                    def px(lm):
                        return (lm.x * frame_w, lm.y * frame_h)

                    nx, ny = px(lms[_LM_NOSE])
                    ls_pt = px(lms[_LM_LEFT_SHOULDER])
                    rs_pt = px(lms[_LM_RIGHT_SHOULDER])
                    lh_pt = px(lms[_LM_LEFT_HIP])
                    rh_pt = px(lms[_LM_RIGHT_HIP])
                    la_pt = px(lms[_LM_LEFT_ANKLE])
                    ra_pt = px(lms[_LM_RIGHT_ANKLE])

                    data["nose_y"].append(ny)
                    data["l_shoulder"].append(ls_pt)
                    data["r_shoulder"].append(rs_pt)
                    data["l_hip"].append(lh_pt)
                    data["r_hip"].append(rh_pt)
                    data["l_ankle"].append(la_pt)
                    data["r_ankle"].append(ra_pt)
                    data["valid"].append(True)
                    ankle_mean_y = (la_pt[1] + ra_pt[1]) / 2.0
                    data["sizes"].append(abs(ankle_mean_y - ny))
                else:
                    for key in ("nose_y", "l_shoulder", "r_shoulder", "l_hip",
                                "r_hip", "l_ankle", "r_ankle", "sizes"):
                        data[key].append(None)
                    data["valid"].append(False)

                frame_idx += 1

        cap.release()
        return data

    # --- パス1: 間引きありで全体を処理し、ウィンドウを決める ---
    pass1 = collect(frame_step)
    if pass1 is None:
        return MeasurementResult(ok=False, reason="動画を開けませんでした")

    n_processed = len(pass1["valid"])
    if n_processed == 0:
        return MeasurementResult(ok=False, reason="動画からフレームを取得できませんでした", fps=fps)

    overall_detection_rate = sum(pass1["valid"]) / n_processed

    # --- 解析ウィンドウ自動選択（改良1） ---
    window = _select_window(pass1["valid"], pass1["sizes"], pass1_fps)
    if window is None:
        return MeasurementResult(
            ok=False,
            reason="ランナーの姿勢を安定して検出できませんでした",
            fps=fps,
            n_frames_analyzed=n_processed,
            detection_rate=overall_detection_rate,
        )

    w_start, w_end = window
    window_start_sec = pass1["secs"][w_start]
    window_end_sec = pass1["secs"][w_end]
    window_note = f"解析区間{window_start_sec:.1f}〜{window_end_sec:.1f}秒"

    # --- パス2（v4・修正1）: 間引きが入った動画は、選択ウィンドウだけを全フレームで再処理 ---
    # 指標計算はパス2のランドマークで行う（接地系指標が実フレームレートで機能する）
    if frame_step > 1:
        orig_start = pass1["orig_idx"][w_start]
        orig_end = pass1["orig_idx"][w_end]
        pass2 = collect(1, orig_start, orig_end)
        if pass2 is not None and len(pass2["valid"]) > 0:
            analysis = pass2
            metric_fps = fps
        else:
            # パス2失敗時はパス1のウィンドウ切り出しで続行（実効fpsは間引き後のまま）
            analysis = {key: val[w_start: w_end + 1] for key, val in pass1.items()}
            metric_fps = pass1_fps
    else:
        analysis = {key: val[w_start: w_end + 1] for key, val in pass1.items()}
        metric_fps = fps

    nose_y = analysis["nose_y"]
    l_shoulder = analysis["l_shoulder"]
    r_shoulder = analysis["r_shoulder"]
    l_hip = analysis["l_hip"]
    r_hip = analysis["r_hip"]
    l_ankle = analysis["l_ankle"]
    r_ankle = analysis["r_ankle"]
    valid_mask = analysis["valid"]

    analyzed = len(valid_mask)
    detection_rate = sum(valid_mask) / analyzed

    # --- 撮影方向判定（改良2: 側面でなくてもスキップせず部分計測に切替） ---
    shoulder_widths = []
    trunk_lengths = []
    hip_mid_x_series = []
    for i in range(analyzed):
        if not valid_mask[i]:
            continue
        lsx, lsy = l_shoulder[i]
        rsx, rsy = r_shoulder[i]
        lhx, lhy = l_hip[i]
        rhx, rhy = r_hip[i]
        shoulder_mid = ((lsx + rsx) / 2.0, (lsy + rsy) / 2.0)
        hip_mid = ((lhx + rhx) / 2.0, (lhy + rhy) / 2.0)
        shoulder_width = abs(lsx - rsx)
        trunk_length = ((shoulder_mid[0] - hip_mid[0]) ** 2 + (shoulder_mid[1] - hip_mid[1]) ** 2) ** 0.5
        if trunk_length > 1e-6:
            shoulder_widths.append(shoulder_width)
            trunk_lengths.append(trunk_length)
        hip_mid_x_series.append(hip_mid[0])

    view = "front_or_back"
    if trunk_lengths:
        ratios = [sw / tl for sw, tl in zip(shoulder_widths, trunk_lengths)]
        side_ratio = statistics.median(ratios)
        if side_ratio < _SIDE_VIEW_RATIO_THRESHOLD and len(hip_mid_x_series) >= 2:
            # 進行方向判定：腰中点xの時間変化の符号
            net_delta = hip_mid_x_series[-1] - hip_mid_x_series[0]
            view = "side_right" if net_delta > 0 else "side_left"

    is_side = view in ("side_left", "side_right")

    # --- 接地イベント検出（v2） ---
    l_ankle_y_raw = [v[1] if v is not None else None for v in l_ankle]
    r_ankle_y_raw = [v[1] if v is not None else None for v in r_ankle]
    l_ankle_y = _smooth(l_ankle_y_raw, _SMOOTHING_WINDOW)
    r_ankle_y = _smooth(r_ankle_y_raw, _SMOOTHING_WINDOW)

    l_segments = _detect_contact_frames(l_ankle_y, valid_mask)
    r_segments = _detect_contact_frames(r_ankle_y, valid_mask)
    total_contacts = len(l_segments) + len(r_segments)

    analyzed_seconds = analyzed / metric_fps
    metrics = {}

    # --- ケイデンスv6（腰バウンス方式を主計算に・両方向で計測可） ---
    slow_note = "スロー動画では実際より低く算出される"

    # ankle方式（v5ロジック・整合性チェックと他指標のストライド周期用に保持）:
    # 左右それぞれ自己相関でストライド周期を推定→平均→cadence = 2×(60/周期秒)
    periods = []
    for series in (l_ankle_y, r_ankle_y):
        period, _ = _estimate_period_sec(series, valid_mask, metric_fps)
        if period is not None:
            periods.append(period)
    mean_period = None
    cadence_ankle = None
    if periods:
        mean_period = sum(periods) / len(periods)
        if mean_period > 1e-6:
            cadence_ankle = 2.0 * (60.0 / mean_period)

    # 腰中点yのデトレンド（v4・vertical_osc_ratioと共用）
    hip_mid_y_full = []
    for i in range(analyzed):
        if valid_mask[i]:
            lhx, lhy = l_hip[i]
            rhx, rhy = r_hip[i]
            hip_mid_y_full.append((lhy + rhy) / 2.0)
        else:
            hip_mid_y_full.append(None)

    # デトレンド窓長: ストライド周期（ankle自己相関）が取れればそのフレーム数、取れなければ1秒相当
    if mean_period is not None:
        detrend_win = max(3, int(round(mean_period * metric_fps)))
        detrend_note = f"デトレンド窓{detrend_win}フレーム（ストライド周期）"
    else:
        detrend_win = max(3, int(round(metric_fps)))
        detrend_note = f"デトレンド窓{detrend_win}フレーム（1秒相当・ストライド周期が取れないため）"

    trend = _smooth(hip_mid_y_full, detrend_win)
    detrended_full = [
        (hip_mid_y_full[i] - trend[i])
        if (hip_mid_y_full[i] is not None and trend[i] is not None) else None
        for i in range(analyzed)
    ]

    # 主計算（v6）: デトレンド済み腰中点y系列の自己相関からステップ周期を推定。
    # 腰はステップ周波数（ストライドの2倍）で上下するため、5秒窓に約17周期入り、
    # 足首方式（約8周期）より分解能・安定性が高い。倍音対策とサブフレーム補間は
    # _estimate_period_sec内でv5と同じ方式が適用される
    step_period, hip_boundary_hit = _estimate_period_sec(
        detrended_full, valid_mask, metric_fps,
        min_period_sec=_STEP_PERIOD_MIN_SEC,
        max_period_sec=_STEP_PERIOD_MAX_SEC,
        subharmonic_ratio=_HIP_SUBHARMONIC_RATIO,
    )
    cadence_hip = None
    # 残課題対応（STEP B）: best_lagが探索範囲の境界に張り付いた場合は、生理帯域に
    # ピークを見つけられなかった＝腰方式の推定失敗とみなし、cadence_hipをNoneのまま
    # にしてankle方式へフォールバックさせる（下のif/elifチェーンが自動的に処理する）
    cadence_hip_failure_note = None
    if step_period is not None and step_period > 1e-6:
        if hip_boundary_hit:
            cadence_hip_failure_note = "腰バウンス方式のピークが探索範囲の境界に張り付き推定失敗"
        else:
            cadence_hip = 60.0 / step_period

    # 副計算: 接地回数ベース（v6: detailに記録するのみ・信頼度判定には使わない。
    # 接地検出率が低い動画で正しい値まで弾いてしまうため）
    cadence_secondary = None
    if analyzed_seconds > 0 and total_contacts > 0:
        cadence_secondary = total_contacts / (analyzed_seconds / 60.0)
    if cadence_secondary is not None:
        secondary_note = (
            f"接地回数ベース{cadence_secondary:.1f}spm"
            f"（接地{total_contacts}回/{analyzed_seconds:.1f}秒・参考値）"
        )
    else:
        secondary_note = "接地回数ベース算出不能"

    if cadence_hip is not None and cadence_ankle is not None:
        diff_ratio = abs(cadence_hip - cadence_ankle) / cadence_hip
        agree = diff_ratio <= _CADENCE_HIP_ANKLE_TOLERANCE
        cadence_value = cadence_hip
        cadence_reliable = agree
        cadence_detail = (
            f"主計算（腰バウンス）{cadence_hip:.1f}spm・ankle方式{cadence_ankle:.1f}spm・"
            f"乖離{diff_ratio * 100:.1f}%"
        )
        if not agree:
            cadence_detail += "（10%超のため信頼度低）"
        cadence_detail += f"・{secondary_note}・{window_note}。{slow_note}"
    elif cadence_hip is not None:
        cadence_value = cadence_hip
        cadence_reliable = False
        cadence_detail = (
            f"主計算（腰バウンス）{cadence_hip:.1f}spm・ankle方式算出不能（整合性未確認）・"
            f"{secondary_note}・{window_note}。{slow_note}"
        )
    elif cadence_ankle is not None:
        cadence_value = cadence_ankle
        cadence_reliable = False
        hip_reason = cadence_hip_failure_note or "腰バウンス方式が算出不能"
        cadence_detail = (
            f"{hip_reason}のためankle方式{cadence_ankle:.1f}spmを使用・"
            f"{secondary_note}・{window_note}。{slow_note}"
        )
    elif cadence_secondary is not None:
        cadence_value = cadence_secondary
        cadence_reliable = False
        cadence_detail = (
            f"自己相関で周期を推定できず接地回数ベース"
            f"（接地{total_contacts}回/{analyzed_seconds:.1f}秒）を使用・{window_note}。{slow_note}"
        )
    else:
        cadence_value = None
        cadence_reliable = False
        cadence_detail = f"周期も接地も検出できませんでした・{window_note}"

    # 範囲ゲート（維持）: 120〜220spmの範囲外は信頼度低
    if cadence_value is not None and not (_CADENCE_MIN_SPM <= cadence_value <= _CADENCE_MAX_SPM):
        cadence_reliable = False

    metrics["cadence"] = _metric(cadence_value, "spm", cadence_reliable, cadence_detail)

    # --- 体幹前傾角（側面のみ） ---
    if is_side:
        trunk_angles = []
        for i in range(analyzed):
            if not valid_mask[i]:
                continue
            lsx, lsy = l_shoulder[i]
            rsx, rsy = r_shoulder[i]
            lhx, lhy = l_hip[i]
            rhx, rhy = r_hip[i]
            shoulder_mid = ((lsx + rsx) / 2.0, (lsy + rsy) / 2.0)
            hip_mid = ((lhx + rhx) / 2.0, (lhy + rhy) / 2.0)
            vx = shoulder_mid[0] - hip_mid[0]
            vy = shoulder_mid[1] - hip_mid[1]  # y下向き正
            # 鉛直（真上方向）とのなす角
            angle = np.degrees(np.arctan2(abs(vx), abs(vy)))
            trunk_angles.append(angle)

        trunk_lean_value = statistics.median(trunk_angles) if trunk_angles else None
        metrics["trunk_lean"] = _metric(
            trunk_lean_value,
            "°",
            trunk_lean_value is not None,
            f"前傾角（検出{len(trunk_angles)}フレームの中央値）",
        )
    else:
        metrics["trunk_lean"] = _metric(None, "°", False, _NOT_SIDE_DETAIL)

    # --- 身長ピクセル（各接地フレームでの鼻y〜接地足首y距離の中央値×1.08） ---
    def contact_frame_indices(segments):
        return [seg[0] for seg in segments]

    height_px_samples = []
    for start_idx in contact_frame_indices(l_segments):
        if valid_mask[start_idx] and nose_y[start_idx] is not None and l_ankle[start_idx] is not None:
            height_px_samples.append(abs(l_ankle[start_idx][1] - nose_y[start_idx]))
    for start_idx in contact_frame_indices(r_segments):
        if valid_mask[start_idx] and nose_y[start_idx] is not None and r_ankle[start_idx] is not None:
            height_px_samples.append(abs(r_ankle[start_idx][1] - nose_y[start_idx]))

    height_px = (statistics.median(height_px_samples) * _HEAD_TOP_CORRECTION) if height_px_samples else None

    # --- 上下動比（両方向で計測可・v4修正2: 移動平均デトレンドでパン/ドリフト除去） ---
    # デトレンド済み腰中点y系列はケイデンスv6のセクションで計算済み（共用）
    detrended = [v for v in detrended_full if v is not None]

    if detrended and height_px and height_px > 1e-6:
        p95 = _percentile(detrended, 95)
        p5 = _percentile(detrended, 5)
        vosc_value = (p95 - p5) / height_px * 100.0
        vosc_reliable = _VOSC_MIN_PCT <= vosc_value <= _VOSC_MAX_PCT
        vosc_detail = (
            f"デトレンド後の腰中点yのP95-P5・身長換算{height_px:.0f}px基準・"
            f"{detrend_note}・{window_note}"
        )
        if not vosc_reliable:
            vosc_detail += f"・値が{_VOSC_MIN_PCT:.0f}〜{_VOSC_MAX_PCT:.0f}%の範囲外のため信頼度低"
    else:
        vosc_value = None
        vosc_reliable = False
        vosc_detail = "身長ピクセルを推定できませんでした"
    metrics["vertical_osc_ratio"] = _metric(vosc_value, "%", vosc_reliable, vosc_detail)

    # --- オーバーストライド指標（側面のみ） ---
    if is_side:
        # 進行方向：view="side_right"なら前方はx正方向、"side_left"ならx負方向
        forward_sign = 1.0 if view == "side_right" else -1.0

        overstride_samples = []
        for start_idx in contact_frame_indices(l_segments):
            if not valid_mask[start_idx] or l_ankle[start_idx] is None:
                continue
            lhx, lhy = l_hip[start_idx]
            rhx, rhy = r_hip[start_idx]
            hip_mid_x = (lhx + rhx) / 2.0
            diff = (l_ankle[start_idx][0] - hip_mid_x) * forward_sign
            overstride_samples.append(diff)
        for start_idx in contact_frame_indices(r_segments):
            if not valid_mask[start_idx] or r_ankle[start_idx] is None:
                continue
            lhx, lhy = l_hip[start_idx]
            rhx, rhy = r_hip[start_idx]
            hip_mid_x = (lhx + rhx) / 2.0
            diff = (r_ankle[start_idx][0] - hip_mid_x) * forward_sign
            overstride_samples.append(diff)

        if overstride_samples and height_px and height_px > 1e-6:
            overstride_value = statistics.median(overstride_samples) / height_px * 100.0
            # 接地サンプルが少ないと動画デコーダの環境差だけで値が大きく振れる
            # （実測: 接地4回でmacOS 2.5% vs Cloud 9.6%）ため、6回未満は非表示
            overstride_reliable = len(overstride_samples) >= _CONTACT_MIN_EVENTS_FOR_CONTACT_METRICS
            overstride_detail = f"初期接地{len(overstride_samples)}回の中央値・身長換算{height_px:.0f}px基準"
            if not overstride_reliable:
                overstride_detail += f"（接地{_CONTACT_MIN_EVENTS_FOR_CONTACT_METRICS}回未満のため信頼度低）"
        else:
            overstride_value = None
            overstride_reliable = False
            overstride_detail = "身長ピクセルまたは接地サンプルが不足しています"
        metrics["overstride"] = _metric(overstride_value, "%", overstride_reliable, overstride_detail)
    else:
        metrics["overstride"] = _metric(None, "%", False, _NOT_SIDE_DETAIL)

    # --- 接地時間比（duty factor・側面のみ） ---
    if is_side:
        def duty_factor_for_side(segments):
            """同じ足の連続する初期接地の間隔＝ストライド周期。接地フレーム数/周期の比を返す。"""
            if len(segments) < 2:
                return []
            ratios = []
            for i in range(len(segments) - 1):
                contact_frames = segments[i][1] - segments[i][0] + 1
                stride_period = segments[i + 1][0] - segments[i][0]
                if stride_period > 0:
                    ratios.append(contact_frames / stride_period)
            return ratios

        duty_ratios = duty_factor_for_side(l_segments) + duty_factor_for_side(r_segments)
        if duty_ratios:
            duty_value = statistics.median(duty_ratios) * 100.0
            # 信頼度条件（v2）: 実効fps>=25・クリーニング後接地が左右合計4回以上・値が物理妥当レンジ内
            reasons = []
            if metric_fps < _DUTY_FACTOR_MIN_FPS:
                reasons.append(f"実効fps={metric_fps:.1f}が{_DUTY_FACTOR_MIN_FPS}未満")
            if total_contacts < _CONTACT_MIN_EVENTS_FOR_CONTACT_METRICS:
                reasons.append(f"接地{total_contacts}回が{_CONTACT_MIN_EVENTS_FOR_CONTACT_METRICS}回未満")
            if not (_DUTY_FACTOR_MIN_PCT <= duty_value <= _DUTY_FACTOR_MAX_PCT):
                reasons.append(
                    f"値が{_DUTY_FACTOR_MIN_PCT:.0f}〜{_DUTY_FACTOR_MAX_PCT:.0f}%の範囲外（物理的に不自然）"
                )
            duty_reliable = not reasons
            detail = f"ストライド{len(duty_ratios)}周期の中央値・実効fps={metric_fps:.1f}"
            if reasons:
                detail += "・信頼度低（" + "、".join(reasons) + "）"
            metrics["duty_factor"] = _metric(duty_value, "%", duty_reliable, detail)
        else:
            metrics["duty_factor"] = _metric(None, "%", False, "ストライド周期を算出できませんでした")
    else:
        metrics["duty_factor"] = _metric(None, "%", False, _NOT_SIDE_DETAIL)

    # --- ok判定（改良2: 計測できた指標が1つ以上あればok） ---
    measured_any = any(m["value"] is not None for m in metrics.values())
    return MeasurementResult(
        ok=measured_any,
        reason="" if measured_any else "有効な指標を計測できませんでした",
        fps=fps,
        n_frames_analyzed=analyzed,
        detection_rate=detection_rate,
        view=view,
        metrics=metrics,
        window_start_sec=window_start_sec,
        window_end_sec=window_end_sec,
    )
