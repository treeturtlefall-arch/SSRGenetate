"""
SSRGenerate — ローカル専用カスタム SE スロットローダー

`assets/se_custom/`（.gitignore 対象）に配置されたユーザー所有のワンショット WAV を
自動検出・44.1kHz ステレオ変換・ピッチシフト・トリムして読み込む。
未配置時は空スロットとして動作し、100% プロシージャル合成へ自動フォールバックする。
"""
from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from _audio_dsp import SR, cosine_fade_in, cosine_fade_out
from _utils import ASSETS_DIR

CUSTOM_SE_DIR = ASSETS_DIR / "se_custom"

# 全11スロットのデフォルト設定
SLOT_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "ignition":        {"mode": "layer", "gain": 0.90, "proc_duck": 0.45, "offset_sec": 0.0, "trim_sec": None},
    "heartbeat":       {"mode": "layer", "gain": 0.90, "proc_duck": 0.45, "offset_sec": 0.0, "trim_sec": None},
    "gold_hit":        {"mode": "layer", "gain": 0.95, "proc_duck": 0.45, "offset_sec": 0.0, "trim_sec": None},
    "orb_crack":       {"mode": "layer", "gain": 0.95, "proc_duck": 0.40, "offset_sec": 0.0, "trim_sec": None},
    "rainbow_shatter": {"mode": "layer", "gain": 1.00, "proc_duck": 0.45, "offset_sec": 0.0, "trim_sec": None},
    "cutin_whoosh":    {"mode": "layer", "gain": 0.95, "proc_duck": 0.40, "offset_sec": 0.0, "trim_sec": None},
    "riser":           {"mode": "layer", "gain": 0.90, "proc_duck": 0.45, "offset_sec": 0.0, "trim_sec": 1.70},
    "whiteout_impact": {"mode": "layer", "gain": 1.00, "proc_duck": 0.45, "offset_sec": 0.0, "trim_sec": None},
    "card_whoosh":     {"mode": "layer", "gain": 0.95, "proc_duck": 0.38, "offset_sec": 0.0, "trim_sec": None},
    "card_land":       {"mode": "layer", "gain": 1.00, "proc_duck": 0.45, "offset_sec": 0.0, "trim_sec": None},
    "star_chime":      {"mode": "layer", "gain": 0.85, "proc_duck": 0.40, "offset_sec": 0.0, "trim_sec": None},
}


def _to_stereo_float(arr: np.ndarray) -> np.ndarray:
    """任意の (N,) / (N, C) float64 配列を (N, 2) ステレオへ正規化する"""
    if arr.ndim == 1:
        return np.stack([arr, arr], axis=1)
    if arr.shape[1] == 1:
        return np.repeat(arr, 2, axis=1)
    return arr[:, :2].copy()


def _decode_via_wave(path: Path) -> tuple[int, np.ndarray]:
    """Python標準 wave で 8/16/24/32-bit PCM を float64 [-1.0, 1.0] へデコード"""
    with wave.open(str(path), "rb") as wf:
        n_ch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif sampwidth == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif sampwidth == 3:
        # 24-bit リトルエンディアン符号付き整数を 32-bit 符号拡張で高速デコード
        raw_u8 = np.frombuffer(raw, dtype=np.uint8)
        n_samples = len(raw_u8) // 3
        b = raw_u8[: n_samples * 3].reshape(n_samples, 3)
        padded = np.zeros((n_samples, 4), dtype=np.uint8)
        padded[:, 1:4] = b
        signed32 = padded.view("<i4").reshape(-1) >> 8
        data = signed32.astype(np.float64) / 8388608.0
    elif sampwidth == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    if n_ch > 1:
        total = (len(data) // n_ch) * n_ch
        data = data[:total].reshape(-1, n_ch)
    return int(sr), _to_stereo_float(data)


def _decode_via_scipy(path: Path) -> tuple[int, np.ndarray]:
    """scipy.io.wavfile.read で IEEE float32/64 等をデコード"""
    sr, arr = wavfile.read(str(path))
    if arr.dtype == np.uint8:
        f = (arr.astype(np.float64) - 128.0) / 128.0
    elif arr.dtype == np.int16:
        f = arr.astype(np.float64) / 32768.0
    elif arr.dtype == np.int32:
        f = arr.astype(np.float64) / 2147483648.0
    elif np.issubdtype(arr.dtype, np.floating):
        f = arr.astype(np.float64)
    else:
        raise ValueError(f"Unsupported wav dtype: {arr.dtype}")
    return int(sr), _to_stereo_float(f)


def _decode_via_ffmpeg(path: Path, target_sr: int = SR) -> tuple[int, np.ndarray]:
    """最終フォールバック: ffmpeg で 44.1kHz ステレオ float32le へデコード"""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-ac",
        "2",
        "-ar",
        str(target_sr),
        "-f",
        "f32le",
        "-",
    ]
    raw = subprocess.check_output(cmd)
    data = np.frombuffer(raw, dtype="<f4").astype(np.float64)
    total = (len(data) // 2) * 2
    return target_sr, data[:total].reshape(-1, 2)


def load_wav_stereo_44k(path: Path, target_sr: int = SR) -> np.ndarray:
    """
    任意の WAV ファイルを堅牢にデコードし、44.1kHz ステレオ float64 (N, 2) で返す。
    クリップ端クリック防止のため先頭・末尾に 2ms マイクロフェードを適用する。
    """
    src_sr: int
    stereo: np.ndarray
    try:
        src_sr, stereo = _decode_via_wave(path)
    except Exception:
        try:
            src_sr, stereo = _decode_via_scipy(path)
        except Exception:
            src_sr, stereo = _decode_via_ffmpeg(path, target_sr=target_sr)

    if len(stereo) == 0:
        return np.zeros((0, 2), dtype=np.float64)

    if src_sr != target_sr and src_sr > 0:
        g = math.gcd(target_sr, src_sr)
        up = target_sr // g
        down = src_sr // g
        l_rs = resample_poly(stereo[:, 0], up, down)
        r_rs = resample_poly(stereo[:, 1], up, down)
        stereo = np.stack([l_rs, r_rs], axis=1)

    stereo = cosine_fade_in(stereo, 0.002, sr=target_sr)
    stereo = cosine_fade_out(stereo, 0.002, sr=target_sr)
    return stereo


def pitch_shift_oneshot(stereo: np.ndarray, semitones: float) -> np.ndarray:
    """再生速度比 2**(semitones/12) でワンショット素材を簡易ピッチシフトする"""
    if abs(semitones) < 1e-4 or len(stereo) < 2:
        return stereo.copy()
    rate = 2.0 ** (semitones / 12.0)
    new_len = max(2, int(round(len(stereo) / rate)))
    x_old = np.arange(len(stereo), dtype=np.float64)
    x_new = np.linspace(0.0, len(stereo) - 1, new_len, dtype=np.float64)
    out_l = np.interp(x_new, x_old, stereo[:, 0])
    out_r = np.interp(x_new, x_old, stereo[:, 1])
    return np.stack([out_l, out_r], axis=1)


def fit_duration(
    stereo: np.ndarray,
    max_sec: float | None,
    fade_out_sec: float = 0.08,
    sr: int = SR,
) -> np.ndarray:
    """max_sec を超えるサンプルを切り詰め、末尾を滑らかにフェードアウト整形する"""
    if max_sec is None or max_sec <= 0.0:
        return stereo
    max_n = int(round(max_sec * sr))
    if len(stereo) <= max_n:
        return stereo
    trimmed = stereo[:max_n].copy()
    return cosine_fade_out(trimmed, min(fade_out_sec, max_sec * 0.4), sr=sr)


class CustomSlotBank:
    """`assets/se_custom/` からカスタム SE スロットを管理・供給するバンク"""

    def __init__(self, custom_dir: Path = CUSTOM_SE_DIR, target_sr: int = SR) -> None:
        self.custom_dir = custom_dir
        self.target_sr = target_sr
        self._configs: Dict[str, Dict[str, Any]] = {
            k: dict(v) for k, v in SLOT_DEFAULTS.items()
        }
        self._samples: Dict[str, np.ndarray] = {}

        if not self.custom_dir.exists():
            return

        cfg_path = self.custom_dir / "slots.json"
        if cfg_path.exists():
            try:
                user_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(user_cfg, dict):
                    for slot, overrides in user_cfg.items():
                        if slot in self._configs and isinstance(overrides, dict):
                            self._configs[slot].update(overrides)
            except Exception as err:
                print(f"[WARN] Failed to parse {cfg_path.name}: {err}")

        for slot in self._configs:
            wav_path = self.custom_dir / f"{slot}.wav"
            if wav_path.exists():
                try:
                    sig = load_wav_stereo_44k(wav_path, target_sr=self.target_sr)
                    if len(sig) > 0:
                        self._samples[slot] = sig
                except Exception as err:
                    print(f"[WARN] Failed to load custom slot '{wav_path.name}': {err}")

    def has(self, slot_name: str) -> bool:
        return slot_name in self._samples

    def mode(self, slot_name: str) -> str:
        if not self.has(slot_name):
            return "none"
        m = str(self._configs.get(slot_name, {}).get("mode", "layer")).lower()
        return "replace" if m == "replace" else "layer"

    def proc_scale(self, slot_name: str) -> float:
        """プロシージャル側にかける音量係数（未配置=1.0, replace=0.0, layer=proc_duck）"""
        m = self.mode(slot_name)
        if m == "none":
            return 1.0
        if m == "replace":
            return 0.0
        return float(self._configs.get(slot_name, {}).get("proc_duck", 0.45))

    def offset(self, slot_name: str) -> float:
        return float(self._configs.get(slot_name, {}).get("offset_sec", 0.0))

    def get(
        self,
        slot_name: str,
        semitones: float = 0.0,
        max_sec: float | None = None,
    ) -> Optional[np.ndarray]:
        """設定ゲイン・ピッチシフト・最大尺を適用したステレオサンプルを返す"""
        base = self._samples.get(slot_name)
        if base is None:
            return None
        cfg = self._configs.get(slot_name, {})
        gain = float(cfg.get("gain", 1.0))
        cfg_trim = cfg.get("trim_sec")
        eff_max = cfg_trim if cfg_trim is not None else max_sec

        sig = pitch_shift_oneshot(base, semitones) if abs(semitones) >= 1e-4 else base.copy()
        sig = fit_duration(sig, eff_max, sr=self.target_sr)
        return sig * gain

    def used_summary(self) -> str:
        if not self._samples:
            return "Custom SE slots: none (100% procedural)"
        parts = [f"{k}({self.mode(k)})" for k in sorted(self._samples.keys())]
        return f"Custom SE slots ({len(parts)} active): " + ", ".join(parts)
