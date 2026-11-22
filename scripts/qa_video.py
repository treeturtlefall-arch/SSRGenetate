"""
SSRGenerate — 出力MP4の自動定量QAスクリプト

ffmpeg + ffprobe + numpy を用いて以下を定量計測・判定する（`PREROLL_SEC = 0.5` を加算した全体時刻基準）:
  1. ストリーム仕様（解像度 / FPS / 総尺 <= 16.05s）＆前後 0.5s 黒フェード余白（先頭・末尾 mean < 5.0）
  2. グレー曇り膜フレーム検出（mean > 150 & p95-p5 < 70 & mean < 245 <= 2 frames）
  3. 真空の間 (全体 5.60s〜5.68s / 本編 5.10s〜5.18s) の輝度低下率（全体 5.25s〜5.35s 比 < 50.0%）
  4. 着地直前 (全体 8.83s〜9.18s / 本編 8.33s〜8.68s) の低動き連続ダレ（diff < 2.5 <= 0.20s）
  5. 終盤 (全体 12.7s〜15.3s / 本編 12.2s〜14.8s) のレイアウト固定（max diff < 2.5）＆微動確認
  6. 音響（ebur128 Integrated LUFS / True Peak / 0.0-0.5s 無音余白 / 12.5s〜16.0s 0.5s毎 RMS dBFS）

使い方:
  python scripts/qa_video.py [renders/ssr_gacha.mp4] [--check-audio] [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

PREROLL_SEC = 0.5
TOTAL_LIMIT_SEC = 16.05


def parse_fps(rate_str: str) -> float:
    if "/" in rate_str:
        num_s, den_s = rate_str.split("/", 1)
        den = float(den_s)
        return float(num_s) / den if den > 0 else 30.0
    return float(rate_str)


def probe_streams(video_path: Path) -> Dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height,r_frame_rate,nb_frames,duration:format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v_stream is None:
        raise RuntimeError("No video stream found in target file.")

    fps = parse_fps(str(v_stream.get("r_frame_rate", "30/1")))
    dur_raw = v_stream.get("duration") or data.get("format", {}).get("duration")
    if dur_raw is not None:
        duration = float(dur_raw)
    elif v_stream.get("nb_frames"):
        duration = float(v_stream["nb_frames"]) / fps
    else:
        duration = 0.0

    return {
        "width": int(v_stream.get("width", 0)),
        "height": int(v_stream.get("height", 0)),
        "fps": fps,
        "duration": duration,
        "has_audio": a_stream is not None,
    }


def decode_gray_frames(video_path: Path, w: int = 270, h: int = 480) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"scale={w}:{h},format=gray",
        "-f",
        "rawvideo",
        "-",
    ]
    raw = subprocess.check_output(cmd)
    frame_bytes = w * h
    n_frames = len(raw) // frame_bytes
    if n_frames == 0:
        raise RuntimeError("Decoded 0 video frames.")
    return np.frombuffer(raw[: n_frames * frame_bytes], dtype=np.uint8).reshape(n_frames, h, w)


def measure_audio(video_path: Path, duration: float) -> Dict[str, Any]:
    ebur_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(video_path),
        "-af",
        "ebur128=peak=true",
        "-f",
        "null",
        "-",
    ]
    ebur_res = subprocess.run(ebur_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    stderr = ebur_res.stderr or ""
    summary_idx = stderr.rfind("Summary:")
    tail_txt = stderr[summary_idx:] if summary_idx != -1 else stderr

    lufs_m = re.search(r"I:\s*([-+]?\d+(?:\.\d+)?)\s*LUFS", tail_txt)
    peak_m = re.search(r"Peak:\s*([-+]?\d+(?:\.\d+)?)\s*dBFS", tail_txt)
    lufs = float(lufs_m.group(1)) if lufs_m else None
    true_peak = float(peak_m.group(1)) if peak_m else None

    sr = 44100
    pcm_cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-ac",
        "2",
        "-ar",
        str(sr),
        "-f",
        "s16le",
        "-",
    ]
    raw_pcm = subprocess.check_output(pcm_cmd)
    samples = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float64) / 32768.0
    if len(samples) % 2 == 1:
        samples = samples[:-1]
    stereo = samples.reshape(-1, 2)

    def _seg_rms(s0: float, s1: float) -> float:
        i0 = int(round(s0 * sr))
        i1 = int(round(s1 * sr))
        if i0 >= len(stereo) or i1 <= i0:
            return -120.0
        seg = stereo[i0:i1]
        rms = float(np.sqrt(np.mean(seg * seg)))
        return round(20.0 * math.log10(max(rms, 1e-6)), 1)

    head_rms = {"window": "0.0-0.5s", "rms_dbfs": _seg_rms(0.0, 0.5)}
    tail_rms: List[Dict[str, Any]] = []
    for start_s in (12.5, 13.0, 13.5, 14.0, 14.5, 15.0, 15.5):
        end_s = min(start_s + 0.5, duration if duration > 0 else 16.0)
        tail_rms.append({"window": f"{start_s:.1f}-{end_s:.1f}s", "rms_dbfs": _seg_rms(start_s, end_s)})

    return {
        "integrated_lufs": round(lufs, 2) if lufs is not None else None,
        "true_peak_dbfs": round(true_peak, 2) if true_peak is not None else None,
        "head_rms": head_rms,
        "tail_rms": tail_rms,
    }


def analyze_video(video_path: Path, check_audio: bool = False) -> Dict[str, Any]:
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    info = probe_streams(video_path)
    fps = info["fps"]
    frames = decode_gray_frames(video_path)
    n_frames = len(frames)
    times = np.arange(n_frames, dtype=np.float64) / fps

    means = frames.mean(axis=(1, 2))
    p5 = np.percentile(frames, 5, axis=(1, 2))
    p95 = np.percentile(frames, 95, axis=(1, 2))
    spread = p95 - p5

    # 1. ストリーム仕様
    stream_pass = (
        info["width"] > 0
        and info["height"] > 0
        and info["fps"] > 0
        and info["duration"] <= TOTAL_LIMIT_SEC
    )

    # 1.5 前後 0.5s フェード余白チェック（先頭・最終フレームが純黒近傍）
    head_mean = float(means[0])
    tail_mean = float(means[-1])
    edge_pass = (head_mean < 5.0) and (tail_mean < 5.0)

    # 2. グレー曇り膜検出
    veil_mask = (means > 150.0) & (spread < 70.0) & (means < 245.0)
    veil_indices = np.where(veil_mask)[0]
    veil_frames = [
        {
            "frame": int(i),
            "sec": round(float(times[i]), 2),
            "mean": round(float(means[i]), 1),
            "p5": round(float(p5[i]), 1),
            "spread": round(float(spread[i]), 1),
        }
        for i in veil_indices
    ]
    veil_pass = len(veil_frames) <= 2

    gold_mask = (times >= 3.70 + PREROLL_SEC) & (times <= 4.20 + PREROLL_SEC)
    gold_max_p5 = round(float(p5[gold_mask].max()), 1) if gold_mask.any() else None

    wo_clear_mask = (times >= 7.05 + PREROLL_SEC) & (times <= 7.50 + PREROLL_SEC) & (p5 < 30.0)
    wo_clear_idx = np.where(wo_clear_mask)[0]
    wo_clear_sec = round(float(times[wo_clear_idx[0]]), 2) if len(wo_clear_idx) > 0 else None

    # 3. 真空の間 (5.10s〜5.18s + PREROLL_SEC) の輝度低下
    base_mask = (times >= 4.75 + PREROLL_SEC) & (times <= 4.85 + PREROLL_SEC)
    vac_mask = (times >= 5.10 + PREROLL_SEC) & (times <= 5.18 + PREROLL_SEC)
    baseline_mean = float(means[base_mask].mean()) if base_mask.any() else 1.0
    vacuum_min_mean = float(means[vac_mask].min()) if vac_mask.any() else baseline_mean
    vacuum_ratio_pct = (vacuum_min_mean / max(1e-6, baseline_mean)) * 100.0
    vacuum_pass = vacuum_ratio_pct < 50.0

    # 4. 着地直前ダレ区間 (8.33s〜8.68s + PREROLL_SEC)
    diffs = np.abs(frames[1:].astype(np.float32) - frames[:-1].astype(np.float32)).mean(axis=(1, 2))
    diff_times = times[1:]
    pre_land_mask = (diff_times >= 8.33 + PREROLL_SEC) & (diff_times <= 8.68 + PREROLL_SEC)
    pre_land_diffs = diffs[pre_land_mask]
    max_run = 0
    cur_run = 0
    for d in pre_land_diffs:
        if d < 2.5:
            cur_run += 1
            if cur_run > max_run:
                max_run = cur_run
        else:
            cur_run = 0
    max_stall_sec = max_run / fps
    stall_pass = max_stall_sec <= 0.20

    motion_summary: List[Dict[str, Any]] = []
    for sec in np.arange(7.5 + PREROLL_SEC, 9.31 + PREROLL_SEC, 0.1):
        idx = int(round(sec * fps)) - 1
        if 0 <= idx < len(diffs):
            motion_summary.append({"sec": round(float(diff_times[idx]), 2), "diff": round(float(diffs[idx]), 2)})

    # 5. 終盤 (12.2s〜14.8s + PREROLL_SEC = 12.7s〜15.3s) レイアウト固定＆微動確認
    tail_mask = (diff_times >= 12.20 + PREROLL_SEC) & (diff_times <= 14.80 + PREROLL_SEC)
    tail_max_diff = float(diffs[tail_mask].max()) if tail_mask.any() else 0.0
    tail_layout_pass = tail_max_diff < 2.5

    idx_13 = min(n_frames - 1, max(0, int(round((13.0 + PREROLL_SEC) * fps))))
    idx_14 = min(n_frames - 1, max(0, int(round((14.0 + PREROLL_SEC) * fps))))
    changed_pixels = np.abs(frames[idx_14].astype(np.int16) - frames[idx_13].astype(np.int16)) >= 2
    shimmer_pct = float(changed_pixels.mean() * 100.0)
    shimmer_ok = shimmer_pct > 0.1

    # 6. 音響計測
    audio_info: Optional[Dict[str, Any]] = None
    audio_pass = True
    if info["has_audio"]:
        audio_info = measure_audio(video_path, info["duration"])
        if check_audio:
            lufs = audio_info["integrated_lufs"]
            rms_head = audio_info["head_rms"]["rms_dbfs"]
            rms_145 = next((x["rms_dbfs"] for x in audio_info["tail_rms"] if x["window"].startswith("14.5")), -120.0)
            rms_155 = next((x["rms_dbfs"] for x in audio_info["tail_rms"] if x["window"].startswith("15.5")), -120.0)
            audio_pass = (
                (lufs is not None and -15.5 <= lufs <= -12.5)
                and (rms_head < -60.0)
                and (rms_145 > -65.0)
                and (rms_155 < -60.0)
            )
    elif check_audio:
        audio_pass = False

    overall_pass = stream_pass and edge_pass and veil_pass and vacuum_pass and stall_pass and tail_layout_pass and audio_pass

    return {
        "video_path": str(video_path),
        "overall_pass": overall_pass,
        "stream": {
            "pass": stream_pass,
            "width": info["width"],
            "height": info["height"],
            "fps": round(fps, 3),
            "duration": round(info["duration"], 3),
            "frames": n_frames,
            "has_audio": info["has_audio"],
        },
        "edge_padding": {
            "pass": edge_pass,
            "head_mean": round(head_mean, 2),
            "tail_mean": round(tail_mean, 2),
            "limit_mean": 5.0,
        },
        "gray_veil": {
            "pass": veil_pass,
            "count": len(veil_frames),
            "limit": 2,
            "frames": veil_frames,
            "gold_max_p5": gold_max_p5,
            "whiteout_clear_sec": wo_clear_sec,
        },
        "vacuum_pause": {
            "pass": vacuum_pass,
            "baseline_mean_475_485": round(baseline_mean, 2),
            "min_mean_510_518": round(vacuum_min_mean, 2),
            "ratio_pct": round(vacuum_ratio_pct, 1),
            "limit_pct": 50.0,
        },
        "landing_stall": {
            "pass": stall_pass,
            "max_stall_sec_833_868": round(max_stall_sec, 3),
            "limit_sec": 0.20,
            "motion_75_93": motion_summary,
        },
        "tail_result": {
            "layout_fixed_pass": tail_layout_pass,
            "max_diff_122_148": round(tail_max_diff, 3),
            "shimmer_status": "PASS" if shimmer_ok else "WARN",
            "changed_pixel_pct_13_vs_14": round(shimmer_pct, 2),
        },
        "audio": {
            "checked": check_audio,
            "pass": audio_pass,
            "details": audio_info,
        },
    }


def print_report(res: Dict[str, Any]) -> None:
    st = res["stream"]
    ep = res["edge_padding"]
    gv = res["gray_veil"]
    vp = res["vacuum_pause"]
    ls = res["landing_stall"]
    tr = res["tail_result"]
    au = res["audio"]

    def tag(ok: bool) -> str:
        return "[PASS]" if ok else "[FAIL]"

    print(f"=== SSRGenerate Video QA Report: {res['video_path']} ===")
    print(f"{tag(st['pass'])} Stream: {st['width']}x{st['height']} @ {st['fps']}fps, duration={st['duration']}s ({st['frames']} frames)")
    print(f"{tag(ep['pass'])} Edge Padding (0s / end): head_mean={ep['head_mean']}, tail_mean={ep['tail_mean']} (< {ep['limit_mean']})")
    print(
        f"{tag(gv['pass'])} Gray Veil Frames: {gv['count']} <= {gv['limit']} "
        f"(gold 4.2-4.7s max p5={gv['gold_max_p5']}, whiteout clear p5<30 at {gv['whiteout_clear_sec']}s)"
    )
    if gv["frames"]:
        print(f"       Details: {gv['frames']}")
    print(
        f"{tag(vp['pass'])} Vacuum Pause (5.60-5.68s): min={vp['min_mean_510_518']} vs base(5.25-5.35s)={vp['baseline_mean_475_485']} "
        f"({vp['ratio_pct']}% < {vp['limit_pct']}%)"
    )
    print(
        f"{tag(ls['pass'])} Pre-Landing Stall (8.83-9.18s): max stall={ls['max_stall_sec_833_868']}s <= {ls['limit_sec']}s"
    )
    motion_line = ", ".join(f"{m['sec']:.1f}s:{m['diff']:.1f}" for m in ls["motion_75_93"])
    print(f"       Motion (8.0-9.8s): {motion_line}")
    print(
        f"{tag(tr['layout_fixed_pass'])} Tail Fixed (12.7-15.3s): max_diff={tr['max_diff_122_148']} < 2.5 | "
        f"[{tr['shimmer_status']}] Shimmer (13.5s vs 14.5s): {tr['changed_pixel_pct_13_vs_14']}% > 0.1%"
    )
    if au["details"] is not None:
        det = au["details"]
        au_tag = tag(au["pass"]) if au["checked"] else "[INFO]"
        hr = det["head_rms"]
        tail_str = ", ".join(f"{w['window']}:{w['rms_dbfs']}dB" for w in det["tail_rms"])
        print(
            f"{au_tag} Audio: LUFS={det['integrated_lufs']}, TruePeak={det['true_peak_dbfs']}dBFS | "
            f"Head({hr['window']}):{hr['rms_dbfs']}dB | Tail RMS: {tail_str}"
        )
    else:
        au_tag = "[FAIL]" if au["checked"] else "[INFO]"
        print(f"{au_tag} Audio: No audio stream")
    print(f"OVERALL: {'PASS' if res['overall_pass'] else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SSRGenerate automated video QA")
    parser.add_argument("video_path", nargs="?", default=None, help="Target MP4 path (defaults to newest in renders/)")
    parser.add_argument("--check-audio", action="store_true", help="Enforce Phase 3 audio LUFS/tail criteria")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    target_path = args.video_path
    if not target_path:
        renders_dir = Path("renders")
        mp4_files = list(renders_dir.glob("*.mp4")) if renders_dir.is_dir() else []
        if mp4_files:
            mp4_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            target_path = str(mp4_files[0])
        else:
            target_path = "renders/ssr_gacha.mp4"

    res = analyze_video(Path(target_path), check_audio=args.check_audio)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print_report(res)
    return 0 if res["overall_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
