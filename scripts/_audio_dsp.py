"""
SSRGenerate — 物理音響・現代ソシャゲ音像 DSP コアモジュール

Python 標準環境 (numpy / scipy) のみ・完全決定論で動作し、
コンボリューションリバーブ・動的フィルタ・現代シネマティックシンセ・
ITU-R BS.1770-4 準拠 LUFS 計測を提供する。
"""
from __future__ import annotations

import functools
import math
from typing import Sequence

import numpy as np
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

SR = 44100


# =========================================================================
# バッファ・パン・基本フィルタ・エンベロープ
# =========================================================================

def make_buffer(duration_sec: float, sr: int = SR) -> np.ndarray:
    """ステレオ無音バッファ (N, 2) を生成"""
    n = max(1, int(round(duration_sec * sr)))
    return np.zeros((n, 2), dtype=np.float64)


def add_stereo(
    buf: np.ndarray,
    sig_l: np.ndarray,
    sig_r: np.ndarray,
    start_sec: float,
    gain: float = 1.0,
    sr: int = SR,
) -> None:
    """指定開始時刻にステレオ信号を加算合成（負オフセットは先頭クリップ）"""
    i0 = int(round(start_sec * sr))
    src_start = 0
    if i0 < 0:
        src_start = -i0
        i0 = 0
    if i0 >= len(buf) or src_start >= len(sig_l):
        return
    n = min(len(sig_l) - src_start, len(sig_r) - src_start, len(buf) - i0)
    if n <= 0:
        return
    buf[i0 : i0 + n, 0] += sig_l[src_start : src_start + n] * gain
    buf[i0 : i0 + n, 1] += sig_r[src_start : src_start + n] * gain


def add_mono_panned(
    buf: np.ndarray,
    sig: np.ndarray,
    start_sec: float,
    gain: float = 1.0,
    pan: float = 0.0,
    sr: int = SR,
) -> None:
    """定電力パン (-1.0=L 〜 +1.0=R) を指定してモノラル信号を加算"""
    p = float(np.clip(pan, -1.0, 1.0))
    angle = (p + 1.0) * (np.pi / 4.0)
    gl = math.cos(angle) * gain
    gr = math.sin(angle) * gain
    add_stereo(buf, sig * gl, sig * gr, start_sec, gain=1.0, sr=sr)


def lowpass(sig: np.ndarray, cutoff_hz: float, order: int = 4, sr: int = SR) -> np.ndarray:
    nyq = sr * 0.5
    wn = float(np.clip(cutoff_hz / nyq, 0.0005, 0.99))
    sos = butter(order, wn, btype="low", output="sos")
    return sosfilt(sos, sig)


def highpass(sig: np.ndarray, cutoff_hz: float, order: int = 4, sr: int = SR) -> np.ndarray:
    nyq = sr * 0.5
    wn = float(np.clip(cutoff_hz / nyq, 0.0005, 0.99))
    sos = butter(order, wn, btype="high", output="sos")
    return sosfilt(sos, sig)


def bandpass(sig: np.ndarray, low_hz: float, high_hz: float, order: int = 3, sr: int = SR) -> np.ndarray:
    nyq = sr * 0.5
    lo = float(np.clip(low_hz / nyq, 0.0005, 0.97))
    hi = float(np.clip(high_hz / nyq, lo + 0.005, 0.99))
    sos = butter(order, [lo, hi], btype="band", output="sos")
    return sosfilt(sos, sig)


def adsr(
    n: int,
    attack: float,
    decay: float,
    sustain: float,
    release: float,
    sr: int = SR,
) -> np.ndarray:
    """秒指定の滑らかな ADSR エンベロープ"""
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    na = min(max(0, int(round(attack * sr))), n)
    nd = min(max(0, int(round(decay * sr))), max(0, n - na))
    nr = min(max(0, int(round(release * sr))), max(0, n - na - nd))
    ns = max(0, n - na - nd - nr)
    parts = []
    if na > 0:
        parts.append(0.5 - 0.5 * np.cos(np.pi * np.linspace(0.0, 1.0, na, endpoint=False)))
    if nd > 0:
        parts.append(1.0 - (1.0 - sustain) * (np.linspace(0.0, 1.0, nd, endpoint=False) ** 0.85))
    if ns > 0:
        parts.append(np.full(ns, sustain, dtype=np.float64))
    if nr > 0:
        parts.append(sustain * (0.5 + 0.5 * np.cos(np.pi * np.linspace(0.0, 1.0, nr))))
    env = np.concatenate(parts) if parts else np.zeros(n, dtype=np.float64)
    return env[:n]


def cosine_fade_in(sig: np.ndarray, fade_sec: float, sr: int = SR) -> np.ndarray:
    nf = min(len(sig), max(0, int(round(fade_sec * sr))))
    if nf <= 0:
        return sig
    out = sig.copy()
    curve = 0.5 - 0.5 * np.cos(np.pi * np.linspace(0.0, 1.0, nf, endpoint=False))
    if out.ndim == 1:
        out[:nf] *= curve
    else:
        out[:nf, :] *= curve[:, None]
    return out


def cosine_fade_out(sig: np.ndarray, fade_sec: float, sr: int = SR) -> np.ndarray:
    nf = min(len(sig), max(0, int(round(fade_sec * sr))))
    if nf <= 0:
        return sig
    out = sig.copy()
    curve = 0.5 + 0.5 * np.cos(np.pi * np.linspace(0.0, 1.0, nf))
    if out.ndim == 1:
        out[-nf:] *= curve
    else:
        out[-nf:, :] *= curve[:, None]
    return out


def dynamic_lowpass(
    sig: np.ndarray,
    cutoff_curve_hz: np.ndarray,
    n_bands: int = 12,
    order: int = 3,
    sr: int = SR,
) -> np.ndarray:
    """
    時間変化するカットオフ周波数カーブを対数間隔マルチバンド補間で近似する
    高速ベクトル化可変ローパスフィルタ。
    """
    n = len(sig)
    if n == 0:
        return sig.copy()
    curve = np.clip(np.asarray(cutoff_curve_hz, dtype=np.float64), 60.0, sr * 0.45)
    lo_hz = float(np.min(curve))
    hi_hz = float(np.max(curve))
    if hi_hz / max(lo_hz, 1.0) < 1.05:
        return lowpass(sig, 0.5 * (lo_hz + hi_hz), order=order, sr=sr)

    centers_hz = np.geomspace(lo_hz, hi_hz, n_bands)
    centers_log = np.log2(centers_hz)
    curve_log = np.log2(curve)
    step_log = max((centers_log[-1] - centers_log[0]) / max(1, n_bands - 1), 1e-4)

    out = np.zeros(n, dtype=np.float64)
    weight_sum = np.zeros(n, dtype=np.float64)
    for c_hz, c_log in zip(centers_hz, centers_log):
        w = np.exp(-0.5 * ((curve_log - c_log) / (step_log * 0.95)) ** 2)
        if np.max(w) < 1e-4:
            continue
        filtered = lowpass(sig, float(c_hz), order=order, sr=sr)
        out += filtered * w
        weight_sum += w

    return out / np.maximum(weight_sum, 1e-8)


def stereo_widen(
    sig_l: np.ndarray,
    sig_r: np.ndarray,
    haas_ms: float = 8.0,
    width: float = 1.18,
    sr: int = SR,
) -> tuple[np.ndarray, np.ndarray]:
    """M/S 処理と極小 Haas 遅延ブレンドによるステレオ広がり拡張"""
    mid = 0.5 * (sig_l + sig_r)
    side = 0.5 * (sig_l - sig_r) * width
    d = max(1, int(round(haas_ms * 0.001 * sr)))
    if d < len(side):
        delayed_mid = np.zeros_like(mid)
        delayed_mid[d:] = mid[:-d]
        side = side + 0.14 * (delayed_mid - mid)
    return mid + side, mid - side


# =========================================================================
# 高密度コンボリューションリバーブ（Phase 3-2）
# =========================================================================

def make_hall_ir(
    duration_sec: float,
    rt60: float,
    rng: np.random.Generator,
    shimmer: float = 0.0,
    sr: int = SR,
) -> np.ndarray:
    """
    初期反射（左右非対称素数タップ）＋空気吸収減衰ステレオガウスノイズによる
    決定論的コンサートホール・インパルス応答 (N, 2) を生成する。
    """
    n = max(64, int(round(duration_sec * sr)))
    t = np.arange(n, dtype=np.float64) / sr

    # 空気吸収モデル: 低中域 (<2.5kHz) は rt60、高域は rt60 * 0.52 で減衰
    tau_low = max(0.08, rt60 / 6.907755)
    tau_hi = max(0.05, (rt60 * 0.52) / 6.907755)
    env_low = np.exp(-t / tau_low)
    env_hi = np.exp(-t / tau_hi)

    noise_l = rng.standard_normal(n)
    noise_r = rng.standard_normal(n)

    low_l = lowpass(noise_l, 2500.0, order=2, sr=sr) * env_low
    low_r = lowpass(noise_r, 2500.0, order=2, sr=sr) * env_low
    hi_l = (noise_l - lowpass(noise_l, 2500.0, order=2, sr=sr)) * env_hi
    hi_r = (noise_r - lowpass(noise_r, 2500.0, order=2, sr=sr)) * env_hi

    ir_l = low_l + hi_l * 0.72
    ir_r = low_r + hi_r * 0.72

    # 煌めきシマー残響（高域 2.2k〜7.5kHz の長い減衰成分）
    if shimmer > 0.0:
        tau_shim = max(0.12, (rt60 * 0.92) / 6.907755)
        env_shim = np.exp(-t / tau_shim)
        shim_l = bandpass(rng.standard_normal(n), 2200.0, 7600.0, order=2, sr=sr) * env_shim
        shim_r = bandpass(rng.standard_normal(n), 2200.0, 7600.0, order=2, sr=sr) * env_shim
        ir_l += shim_l * (shimmer * 0.85)
        ir_r += shim_r * (shimmer * 0.85)

    # 冒頭 14ms の滑らかな立ち上がりで直接音との衝突を回避
    fade_in_n = min(n, int(round(0.014 * sr)))
    if fade_in_n > 0:
        ramp = 0.5 - 0.5 * np.cos(np.pi * np.linspace(0.0, 1.0, fade_in_n, endpoint=False))
        ir_l[:fade_in_n] *= ramp
        ir_r[:fade_in_n] *= ramp

    # 左右非対称の初期反射タップ (12ms〜79ms)
    er_taps = [
        (0.0127, 0.42, 0.20),
        (0.0193, 0.22, 0.40),
        (0.0269, 0.36, 0.25),
        (0.0347, 0.18, 0.34),
        (0.0431, 0.28, 0.19),
        (0.0523, 0.15, 0.26),
        (0.0641, 0.21, 0.14),
        (0.0769, 0.12, 0.18),
    ]
    for sec, al, ar in er_taps:
        idx = int(round(sec * sr))
        if idx < n:
            ir_l[idx] += al
            ir_r[idx] += ar

    ir = np.stack([ir_l, ir_r], axis=1)
    # チャンネル平均総エネルギーで正規化し、リバーブ長による音量差を無くす
    energy = float(np.sqrt(0.5 * (np.sum(ir[:, 0] ** 2) + np.sum(ir[:, 1] ** 2))))
    if energy > 1e-8:
        ir /= energy
    return ir


def convolution_reverb(
    buf: np.ndarray,
    ir: np.ndarray,
    mix: float = 0.30,
    predelay_sec: float = 0.014,
    wet_hpf_hz: float = 180.0,
    sr: int = SR,
) -> np.ndarray:
    """
    fftconvolve を用いた高密度ステレオ・コンボリューションリバーブ。
    Wet 経路にハイパスを挟むことで低域（サブベース）の濁りを防止する。
    """
    n = len(buf)
    wet_in_l = highpass(buf[:, 0], wet_hpf_hz, order=2, sr=sr)
    wet_in_r = highpass(buf[:, 1], wet_hpf_hz, order=2, sr=sr)

    conv_l = fftconvolve(wet_in_l, ir[:, 0], mode="full")
    conv_r = fftconvolve(wet_in_r, ir[:, 1], mode="full")

    pd = max(0, int(round(predelay_sec * sr)))
    wet = np.zeros((n, 2), dtype=np.float64)
    if pd < n:
        take = min(n - pd, len(conv_l))
        wet[pd : pd + take, 0] = conv_l[:take]
        wet[pd : pd + take, 1] = conv_r[:take]

    dry_gain = 1.0 - mix * 0.28
    return buf * dry_gain + wet * mix


# =========================================================================
# 現代ソシャゲ音像シンセサイザー群（Phase 3-1）
# =========================================================================

def synth_sub_drop(
    duration: float = 1.5,
    f_start: float = 115.0,
    f_end: float = 34.0,
    decay: float = 2.9,
    punch: float = 0.38,
    sr: int = SR,
) -> np.ndarray:
    """重厚なサブベース・ドロップ（ピッチ降下＋極短アタック倍音サチュレーション）"""
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    freq = f_end + (f_start - f_end) * np.exp(-t * 16.0)
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    sub = np.sin(phase)
    # スマホ環境でも輪郭が聴こえるよう、冒頭だけ 2次/3次倍音を加味
    punch_env = np.exp(-t * 22.0)
    overtones = punch * punch_env * (0.65 * np.sin(2.0 * phase) + 0.35 * np.sin(3.0 * phase))
    amp = (1.0 - np.exp(-t * 280.0)) * np.exp(-t * decay)
    sig = (sub + overtones) * amp
    return cosine_fade_out(sig, min(0.15, duration * 0.25), sr=sr)


def synth_timpani_hit(
    freq: float = 96.0,
    duration: float = 1.15,
    rng: np.random.Generator | None = None,
    sr: int = SR,
) -> np.ndarray:
    """オーケストラ・ティンパニ打撃（ピッチベンドダウン＋非整数膜振動モード＋フェルトマレット音）"""
    if rng is None:
        rng = np.random.default_rng(1)
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr

    f_curve = freq * (1.0 + 0.20 * np.exp(-t * 28.0))
    ph = 2.0 * np.pi * np.cumsum(f_curve) / sr
    modes = [
        (1.00, 1.00, 3.8),
        (1.50, 0.42, 6.2),
        (1.98, 0.24, 9.0),
        (2.44, 0.12, 13.0),
    ]
    body = np.zeros(n, dtype=np.float64)
    for mult, amp, dec in modes:
        body += amp * np.sin(ph * mult) * np.exp(-t * dec)
    body *= 1.0 - np.exp(-t * 240.0)

    # フェルトマレットの短い打撃トランジェント
    mallet_noise = bandpass(rng.standard_normal(n), 180.0, 950.0, order=2, sr=sr)
    mallet = mallet_noise * np.exp(-t * 48.0) * 0.45

    sig = lowpass(body + mallet, 2200.0, order=2, sr=sr)
    return cosine_fade_out(sig, min(0.12, duration * 0.2), sr=sr)


def synth_crash_cymbal(
    duration: float = 2.6,
    rng: np.random.Generator | None = None,
    bright: float = 1.0,
    sr: int = SR,
) -> tuple[np.ndarray, np.ndarray]:
    """現代ソシャゲ必須のステレオ金属クラッシュシンバル残響"""
    if rng is None:
        rng = np.random.default_rng(2)
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr

    # 非調和金属パーシャル群（L/R で僅かに位相・周波数をずらしステレオ化）
    partials = [312.0, 447.0, 589.0, 743.0, 892.0, 1127.0, 1483.0]
    metal_l = np.zeros(n, dtype=np.float64)
    metal_r = np.zeros(n, dtype=np.float64)
    for idx, pf in enumerate(partials):
        ph_l = rng.uniform(0.0, 2.0 * np.pi)
        ph_r = rng.uniform(0.0, 2.0 * np.pi)
        dec = 4.2 + idx * 0.65
        metal_l += np.sin(2.0 * np.pi * pf * t + ph_l) * np.exp(-t * dec)
        metal_r += np.sin(2.0 * np.pi * (pf * 1.003) * t + ph_r) * np.exp(-t * dec)

    # 3k〜12.5kHz の複合ノイズシマー
    raw_l = rng.standard_normal(n)
    raw_r = rng.standard_normal(n)
    hi_l = bandpass(raw_l, 3200.0, 12500.0 * np.clip(bright, 0.7, 1.15), order=3, sr=sr)
    hi_r = bandpass(raw_r, 3200.0, 12500.0 * np.clip(bright, 0.7, 1.15), order=3, sr=sr)
    air_l = bandpass(raw_l, 1500.0, 4200.0, order=2, sr=sr)
    air_r = bandpass(raw_r, 1500.0, 4200.0, order=2, sr=sr)

    atk = 1.0 - np.exp(-t * 320.0)
    env_hi = atk * (0.65 * np.exp(-t * 2.1) + 0.35 * np.exp(-t * 5.8))
    env_air = atk * np.exp(-t * 3.4)

    out_l = (metal_l * 0.08 + hi_l * 0.75 * env_hi + air_l * 0.38 * env_air)
    out_r = (metal_r * 0.08 + hi_r * 0.75 * env_hi + air_r * 0.38 * env_air)
    return cosine_fade_out(out_l, 0.25, sr=sr), cosine_fade_out(out_r, 0.25, sr=sr)


def synth_crystal_celesta(
    freq: float,
    duration: float = 1.5,
    brightness: float = 1.0,
    sr: int = SR,
) -> np.ndarray:
    """透明感のあるガラス・チェレスタ音（ソフト FM ＋高次ベルパーシャル）"""
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr

    mod_env = np.exp(-t * 9.0) * (1.25 * brightness)
    mod = np.sin(2.0 * np.pi * (freq * 2.0) * t) * mod_env
    carrier = np.sin(2.0 * np.pi * freq * t + mod)
    p2 = 0.34 * np.sin(2.0 * np.pi * (freq * 2.002) * t) * np.exp(-t * 4.8)
    p3 = 0.16 * brightness * np.sin(2.0 * np.pi * (freq * 3.98) * t) * np.exp(-t * 10.5)
    p4 = 0.045 * brightness * np.sin(2.0 * np.pi * (freq * 5.42) * t) * np.exp(-t * 18.0)

    amp = (1.0 - np.exp(-t * 380.0)) * np.exp(-t * 2.7)
    sig = lowpass((carrier + p2 + p3 + p4) * amp, 6800.0, order=2, sr=sr)
    return cosine_fade_out(sig, min(0.15, duration * 0.2), sr=sr)


def synth_harp_pluck(
    freq: float,
    duration: float = 1.75,
    rng: np.random.Generator | None = None,
    sr: int = SR,
) -> np.ndarray:
    """倍音減衰加算＋指弾きノイズ＋動的LPFによる温かみのあるコンサートハープ撥弦"""
    if rng is None:
        rng = np.random.default_rng(3)
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr

    sig = np.zeros(n, dtype=np.float64)
    nyq_limit = sr * 0.42
    for k in range(1, 10):
        fk = freq * k * (1.0 + 0.00018 * (k ** 2))  # わずかな弦の硬さ非調和性
        if fk >= nyq_limit:
            break
        amp_k = (1.0 / (k ** 1.58)) * np.exp(-t * (2.1 + 1.45 * k))
        sig += amp_k * np.sin(2.0 * np.pi * fk * t)

    # 指先のアタックノイズ（高域の刺さりを抑えた柔らかな撥弦感）
    pluck_n = bandpass(rng.standard_normal(n), max(200.0, freq * 0.8), min(4200.0, freq * 4.2), order=2, sr=sr)
    sig += pluck_n * np.exp(-t * 120.0) * 0.12
    sig *= 1.0 - np.exp(-t * 450.0)

    # 動的ローパス仕上げ: アタック後に自然に閉じてキンキン感を除去
    h_open = min(5000.0, max(2600.0, freq * 3.6))
    h_tail = min(2900.0, max(1600.0, freq * 2.2))
    h_curve = h_tail + (h_open - h_tail) * np.exp(-t * 14.0)
    sig = dynamic_lowpass(sig, h_curve, n_bands=6, order=2, sr=sr)
    return cosine_fade_out(sig, min(0.18, duration * 0.2), sr=sr)


def synth_shimmer_pad(
    freqs: Sequence[float],
    duration: float,
    attack: float = 0.35,
    release: float = 1.35,
    rng: np.random.Generator | None = None,
    bright_hz: float = 3400.0,
    sr: int = SR,
) -> tuple[np.ndarray, np.ndarray]:
    """
    現代ソシャゲ音響の主役：リッチなステレオ・シマーストリングスパッド。
    デチューン3ボイス＋穏やかなLFOビブラート＋オクターブ上エアリー倍音＋動的ローパス。
    """
    if rng is None:
        rng = np.random.default_rng(4)
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    acc_l = np.zeros(n, dtype=np.float64)
    acc_r = np.zeros(n, dtype=np.float64)

    detune_ratios = [2.0 ** (-7.5 / 1200.0), 1.0, 2.0 ** (7.5 / 1200.0)]
    for idx, f0 in enumerate(freqs):
        lfo_rate = 4.2 + (idx % 3) * 0.45
        lfo_phase = rng.uniform(0.0, 2.0 * np.pi)
        vib = 1.0 + 0.0022 * np.sin(2.0 * np.pi * lfo_rate * t + lfo_phase) * np.clip(t / 0.5, 0.0, 1.0)
        pan = -0.55 + (idx / max(1, len(freqs) - 1)) * 1.1 if len(freqs) > 1 else 0.0
        gl = math.cos((pan + 1.0) * np.pi / 4.0)
        gr = math.sin((pan + 1.0) * np.pi / 4.0)

        voice_l = np.zeros(n, dtype=np.float64)
        voice_r = np.zeros(n, dtype=np.float64)
        for v_idx, dr in enumerate(detune_ratios):
            ph0 = rng.uniform(0.0, 2.0 * np.pi)
            ph1 = rng.uniform(0.0, 2.0 * np.pi)
            f_inst = f0 * dr * vib
            phase = 2.0 * np.pi * np.cumsum(f_inst) / sr
            # 鋸波寄りの偶数＋奇数倍音（上位6倍音のみ・丸く豊か）
            s_l = (
                0.70 * np.sin(phase + ph0)
                + 0.34 * np.sin(2.0 * phase + ph0)
                + 0.19 * np.sin(3.0 * phase + ph0)
                + 0.11 * np.sin(4.0 * phase + ph0)
                + 0.06 * np.sin(5.0 * phase + ph0)
            )
            s_r = (
                0.70 * np.sin(phase + ph1)
                + 0.34 * np.sin(2.0 * phase + ph1)
                + 0.19 * np.sin(3.0 * phase + ph1)
                + 0.11 * np.sin(4.0 * phase + ph1)
                + 0.06 * np.sin(5.0 * phase + ph1)
            )
            if v_idx == 0:
                voice_l += s_l * 0.85
                voice_r += s_r * 0.45
            elif v_idx == 2:
                voice_l += s_l * 0.45
                voice_r += s_r * 0.85
            else:
                voice_l += s_l * 0.65
                voice_r += s_r * 0.65

        # ほんのりオクターブ上の天使の倍音シマー
        shimmer_tone = 0.12 * np.sin(2.0 * np.pi * (f0 * 2.0) * t + rng.uniform(0, 6.28))
        acc_l += (voice_l * gl + shimmer_tone * gl)
        acc_r += (voice_r * gr + shimmer_tone * gr)

    norm = 1.0 / max(1.0, math.sqrt(len(freqs)) * 1.45)
    acc_l *= norm
    acc_r *= norm

    # 動的ローパスで開いてからゆったり落ち着く
    t_norm = t / max(duration, 1e-4)
    cutoff_curve = 950.0 + (bright_hz - 950.0) * (np.sin(np.pi * np.clip(t_norm * 1.15, 0.0, 1.0)) ** 0.75)
    acc_l = dynamic_lowpass(acc_l, cutoff_curve, n_bands=10, order=2, sr=sr)
    acc_r = dynamic_lowpass(acc_r, cutoff_curve, n_bands=10, order=2, sr=sr)

    env = adsr(n, attack=attack, decay=min(0.45, duration * 0.25), sustain=0.78, release=release, sr=sr)
    return stereo_widen(acc_l * env, acc_r * env, haas_ms=7.0, width=1.22, sr=sr)


def synth_modern_horn(
    freq: float,
    duration: float,
    brightness: float = 1.0,
    sr: int = SR,
) -> tuple[np.ndarray, np.ndarray]:
    """
    ファンファーレ補助用のモダン・シネマティックホーン。
    固定 LPF 鋸波を廃し、アタックのピッチ滑り込み (-14cents->0) ・サステインビブラート・動的フィルタ開閉を行う。
    """
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    vib_depth = 4.5 * np.clip((t - 0.18) / 0.25, 0.0, 1.0)
    vib_cents = vib_depth * np.sin(2.0 * np.pi * 4.8 * t)
    slide = 2.0 ** ((-14.0 * np.exp(-t * 36.0) + vib_cents) / 1200.0)
    detune = 2.0 ** (6.0 / 1200.0)

    def _horn_voice(f_base: float) -> np.ndarray:
        f_inst = f_base * slide
        ph = 2.0 * np.pi * np.cumsum(f_inst) / sr
        s = np.zeros(n, dtype=np.float64)
        for k in range(1, 9):
            if f_base * k < sr * 0.40:
                # 奇数次を少し強めて金管の芯を出す
                w = (1.0 / (k ** 1.12)) * (1.15 if k % 2 == 1 else 0.88)
                s += w * np.sin(ph * k)
        return s * 0.45

    l_raw = _horn_voice(freq * detune) + 0.45 * _horn_voice(freq * 0.5)
    r_raw = _horn_voice(freq / detune) + 0.45 * _horn_voice(freq * 0.5)

    # アタック瞬間だけ明るく開き、すぐ温かく落ち着く動的フィルタ
    open_hz = min(freq * 6.5 + 1150.0, 4400.0) * brightness
    sustain_hz = min(freq * 3.2 + 650.0, 1950.0) * brightness
    cutoff_curve = sustain_hz + (open_hz - sustain_hz) * np.exp(-t * 9.5)
    l_flt = dynamic_lowpass(l_raw, cutoff_curve, n_bands=8, order=3, sr=sr)
    r_flt = dynamic_lowpass(r_raw, cutoff_curve, n_bands=8, order=3, sr=sr)

    # 7msズラしたセカンドボイスを薄くブレンドし、金管セクションの厚みを出す
    d7 = int(round(0.007 * sr))
    if d7 < n:
        l_sec = np.zeros(n, dtype=np.float64)
        r_sec = np.zeros(n, dtype=np.float64)
        l_sec[d7:] = r_flt[:-d7]
        r_sec[d7:] = l_flt[:-d7]
        l_flt = l_flt * 0.88 + l_sec * 0.24
        r_flt = r_flt * 0.88 + r_sec * 0.24

    env = adsr(n, attack=0.032, decay=0.16, sustain=0.66, release=min(0.45, duration * 0.35), sr=sr)
    return l_flt * env, r_flt * env


def synth_glass_crackle(
    duration: float = 0.65,
    rng: np.random.Generator | None = None,
    density: int = 14,
    sr: int = SR,
) -> tuple[np.ndarray, np.ndarray]:
    """水晶クラック・破砕音（不規則高域インパルス列＋高Qガラス共振モード・クリアな余韻）"""
    if rng is None:
        rng = np.random.default_rng(5)
    n = int(round(duration * sr))
    out_l = np.zeros(n, dtype=np.float64)
    out_r = np.zeros(n, dtype=np.float64)

    for i in range(density):
        # 破片タイミングを広げつつ後半にも細かな破片を残す
        t0 = float((rng.random() ** 1.7) * max(0.05, duration * 0.62))
        idx0 = int(round(t0 * sr))
        rem = n - idx0
        if rem < 32:
            continue
        t_sub = np.arange(rem, dtype=np.float64) / sr
        f_res = rng.uniform(2200.0, 8800.0)
        dec = rng.uniform(5.8, 16.5)
        shard = (
            np.sin(2.0 * np.pi * f_res * t_sub)
            + 0.55 * np.sin(2.0 * np.pi * (f_res * 1.41) * t_sub)
            + 0.26 * np.sin(2.0 * np.pi * (f_res * 2.13) * t_sub)
        ) * np.exp(-t_sub * dec) * (1.0 - np.exp(-t_sub * 900.0))
        # 微小クリック
        click_n = min(rem, int(0.004 * sr))
        shard[:click_n] += rng.standard_normal(click_n) * 0.32 * np.exp(-t_sub[:click_n] * 600.0)

        pan = float(rng.uniform(-0.82, 0.82))
        amp = float(rng.uniform(0.35, 1.0) * (1.0 - 0.42 * (i / max(1, density))))
        angle = (pan + 1.0) * (np.pi / 4.0)
        out_l[idx0:] += shard * math.cos(angle) * amp
        out_r[idx0:] += shard * math.sin(angle) * amp

    out_l = highpass(out_l, 950.0, order=2, sr=sr)
    out_r = highpass(out_r, 950.0, order=2, sr=sr)
    return cosine_fade_out(out_l, min(0.22, duration * 0.28), sr=sr), cosine_fade_out(out_r, min(0.22, duration * 0.28), sr=sr)


def synth_air_whoosh(
    duration: float,
    f_start: float,
    f_end: float,
    rng: np.random.Generator | None = None,
    pan_start: float = 0.0,
    pan_end: float = 0.0,
    curve: float = 1.6,
    sr: int = SR,
) -> tuple[np.ndarray, np.ndarray]:
    """パン移動を伴う有機的ステレオエアスウッシュ"""
    if rng is None:
        rng = np.random.default_rng(6)
    n = int(round(duration * sr))
    t_norm = np.linspace(0.0, 1.0, n, dtype=np.float64)
    raw_l = rng.standard_normal(n)
    raw_r = rng.standard_normal(n)

    out_l = np.zeros(n, dtype=np.float64)
    out_r = np.zeros(n, dtype=np.float64)
    steps = 12
    for i in range(steps):
        c = i / (steps - 1)
        w = np.exp(-0.5 * ((t_norm - c) / (1.0 / steps * 1.15)) ** 2)
        freq = f_start + (f_end - f_start) * (c ** curve)
        lo = max(70.0, freq * 0.62)
        hi = min(14500.0, freq * 1.52)
        out_l += bandpass(raw_l, lo, hi, order=2, sr=sr) * w
        out_r += bandpass(raw_r, lo, hi, order=2, sr=sr) * w

    bell_env = np.sin(np.pi * t_norm) ** 1.15
    pan_curve = pan_start + (pan_end - pan_start) * t_norm
    angle = (np.clip(pan_curve, -1.0, 1.0) + 1.0) * (np.pi / 4.0)
    return out_l * bell_env * np.cos(angle) * 0.55, out_r * bell_env * np.sin(angle) * 0.55


def synth_riser(
    duration: float,
    rng: np.random.Generator | None = None,
    sr: int = SR,
) -> tuple[np.ndarray, np.ndarray]:
    """臨界バースト用の多層シネマティックライザー（シェパード上昇音＋エアスイープ）"""
    if rng is None:
        rng = np.random.default_rng(7)
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    u = t / max(duration, 1e-4)

    # オクターブ重ねの上昇トーン
    f_rise = 196.0 * (2.0 ** (u * 2.25))
    ph = 2.0 * np.pi * np.cumsum(f_rise) / sr
    tone = (
        0.58 * np.sin(ph)
        + 0.34 * np.sin(ph * 1.5)
        + 0.22 * np.sin(ph * 2.0)
        + 0.12 * np.sin(ph * 3.0)
    )
    tone_l = dynamic_lowpass(tone, 600.0 + 5200.0 * (u ** 1.5), n_bands=10, order=2, sr=sr)
    tone_r = dynamic_lowpass(tone * np.cos(0.05 * u), 600.0 + 5200.0 * (u ** 1.5), n_bands=10, order=2, sr=sr)

    # 加速トレモロ感（緊張感を高める）
    pulse = 0.84 + 0.16 * np.sin(2.0 * np.pi * np.cumsum(4.0 + 18.0 * (u ** 2)) / sr)
    env = (u ** 1.4) * (1.0 - np.exp(-t * 24.0))
    # 終端 50ms でスパッと抜けて爆発へバトンタッチ
    fade_end = np.clip((duration - t) / 0.050, 0.0, 1.0)

    sw_l, sw_r = synth_air_whoosh(duration, 280.0, 9600.0, rng=rng, curve=2.1, sr=sr)
    out_l = (tone_l * 0.42 * pulse + sw_l * 0.78) * env * fade_end
    out_r = (tone_r * 0.42 * pulse + sw_r * 0.78) * env * fade_end
    return stereo_widen(out_l, out_r, haas_ms=6.5, width=1.18, sr=sr)


# =========================================================================
# ITU-R BS.1770-4 準拠ラウドネス計測＆透明ソフトリミッター
# =========================================================================

@functools.lru_cache(maxsize=8)
def _k_weighting_sos(sr: int = SR) -> np.ndarray:
    """ITU-R BS.1770-4 K-weighting 2段フィルタ (High-Shelf + RLB High-Pass) の SOS 係数"""
    # Stage 1: +4 dB High-Shelf @ 1681.97 Hz
    f0_s = 1681.974450955533
    G_db = 3.999843853973347
    Q_s = 0.7071752369554196
    K = math.tan(math.pi * f0_s / sr)
    Vh = 10.0 ** (G_db / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0_s = 1.0 + K / Q_s + K * K
    b0_s = (Vh + Vb * K / Q_s + K * K) / a0_s
    b1_s = 2.0 * (K * K - Vh) / a0_s
    b2_s = (Vh - Vb * K / Q_s + K * K) / a0_s
    a1_s = 2.0 * (K * K - 1.0) / a0_s
    a2_s = (1.0 - K / Q_s + K * K) / a0_s

    # Stage 2: RLB High-Pass @ 38.135 Hz
    f0_h = 38.13547087602444
    Q_h = 0.5003270373238773
    Kh = math.tan(math.pi * f0_h / sr)
    a0_h = 1.0 + Kh / Q_h + Kh * Kh
    b0_h = 1.0 / a0_h
    b1_h = -2.0 / a0_h
    b2_h = 1.0 / a0_h
    a1_h = 2.0 * (Kh * Kh - 1.0) / a0_h
    a2_h = (1.0 - Kh / Q_h + Kh * Kh) / a0_h

    return np.array(
        [
            [b0_s, b1_s, b2_s, 1.0, a1_s, a2_s],
            [b0_h, b1_h, b2_h, 1.0, a1_h, a2_h],
        ],
        dtype=np.float64,
    )


def measure_lufs(stereo: np.ndarray, sr: int = SR) -> float:
    """ITU-R BS.1770-4 準拠の統合ラウドネス (LUFS) を算出する"""
    if len(stereo) == 0:
        return -70.0
    sos = _k_weighting_sos(sr)
    yl = sosfilt(sos, stereo[:, 0])
    yr = sosfilt(sos, stereo[:, 1])
    power = yl * yl + yr * yr

    win_n = int(round(0.4 * sr))
    step_n = int(round(0.1 * sr))
    if len(power) < win_n:
        mean_p = float(np.mean(power))
        return -0.691 + 10.0 * math.log10(max(mean_p, 1e-12))

    # 累積和で高速に 400ms 移動平均パワーを算出
    csum = np.concatenate([[0.0], np.cumsum(power)])
    starts = np.arange(0, len(power) - win_n + 1, step_n)
    block_powers = (csum[starts + win_n] - csum[starts]) / float(win_n)
    block_lufs = -0.691 + 10.0 * np.log10(np.maximum(block_powers, 1e-12))

    # 第1ゲート: -70 LUFS
    g1 = block_powers[block_lufs > -70.0]
    if len(g1) == 0:
        return -70.0
    gamma_a = -0.691 + 10.0 * math.log10(float(np.mean(g1)))
    # 第2ゲート: 相対 -10 LU
    g2 = block_powers[block_lufs > (gamma_a - 10.0)]
    if len(g2) == 0:
        return gamma_a
    return -0.691 + 10.0 * math.log10(float(np.mean(g2)))


def measure_true_peak_db(buf: np.ndarray, oversample: int = 4) -> float:
    """オーバーサンプリングによる True Peak (dBFS) を算出する（ピーク近傍ウィンドウ抽出による高速・厳密計測）"""
    if len(buf) == 0:
        return -120.0
    abs_buf = np.abs(buf)
    raw_pk = float(np.max(abs_buf))
    if oversample <= 1 or raw_pk < 1e-9:
        return 20.0 * math.log10(max(raw_pk, 1e-9))

    # 全長70万サンプルの一括リサンプリングを避け、ピーク近傍（>= 0.55 * raw_pk）の前後64サンプル窓のみ評価
    ch_max = np.max(abs_buf, axis=1)
    hot = np.where(ch_max >= raw_pk * 0.55)[0]
    if len(hot) == 0 or len(buf) <= 4096:
        up_l = resample_poly(buf[:, 0], oversample, 1)
        up_r = resample_poly(buf[:, 1], oversample, 1)
        pk = max(float(np.max(np.abs(up_l))), float(np.max(np.abs(up_r))))
        return 20.0 * math.log10(max(pk, 1e-9))

    pad = 64
    n = len(buf)
    pk = raw_pk
    # 近接するホットインデックスを連続区間にマージ
    seg_start = max(0, int(hot[0]) - pad)
    seg_end = min(n, int(hot[0]) + pad + 1)
    windows = []
    for idx in hot[1:]:
        s = max(0, int(idx) - pad)
        e = min(n, int(idx) + pad + 1)
        if s <= seg_end:
            seg_end = max(seg_end, e)
        else:
            windows.append((seg_start, seg_end))
            seg_start, seg_end = s, e
    windows.append((seg_start, seg_end))

    for s, e in windows:
        up_l = resample_poly(buf[s:e, 0], oversample, 1)
        up_r = resample_poly(buf[s:e, 1], oversample, 1)
        pk = max(pk, float(np.max(np.abs(up_l))), float(np.max(np.abs(up_r))))
    return 20.0 * math.log10(max(pk, 1e-9))


def soft_limit(buf: np.ndarray, ceiling_db: float = -1.2) -> np.ndarray:
    """閾値以下のダイナミクスを一切歪ませない透明ソフトリミッター"""
    ceiling = 10.0 ** (ceiling_db / 20.0)
    thresh = ceiling * 0.82
    headroom = ceiling - thresh
    abs_x = np.abs(buf)
    over = abs_x > thresh
    if not np.any(over):
        return buf.copy()
    out = buf.copy()
    excess = (abs_x[over] - thresh) / headroom
    out[over] = np.sign(buf[over]) * (thresh + headroom * np.tanh(excess))
    return out
