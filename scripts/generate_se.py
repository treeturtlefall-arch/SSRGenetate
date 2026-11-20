"""
SSRGenerate — プロシージャル効果音（SE・SSRファンファーレ）生成スクリプト

外部素材を使わず、numpy + scipy のみで 15.0秒タイムラインに完全同期した
ステレオ 44.1kHz 16-bit WAV ファイルを `assets/` に決定論的に生成します。

生成ファイル:
  - assets/se_summon.wav   (data-start="0.0",  duration=3.5s) : 召喚陣起動・クリスタル・収束
  - assets/se_upgrade.wav  (data-start="2.5",  duration=4.8s) : 鼓動・金昇格・虹昇格・臨界バースト
  - assets/se_fanfare.wav  (data-start="6.8",  duration=8.0s) : ホワイトアウト爆発・3D回転スウッシュ・SSR確定ファンファーレ＆余韻
"""

from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

from _utils import ASSETS_DIR, load_card_config, resolve_seed

SR = 44100


def make_buffer(duration_sec: float) -> np.ndarray:
    """ステレオ無音バッファ (N, 2) を生成"""
    n = int(round(duration_sec * SR))
    return np.zeros((n, 2), dtype=np.float64)


def add_stereo(buf: np.ndarray, sig_l: np.ndarray, sig_r: np.ndarray, start_sec: float, gain: float = 1.0) -> None:
    """指定開始時刻にステレオ信号を加算合成"""
    i0 = int(round(start_sec * SR))
    if i0 >= len(buf):
        return
    n = min(len(sig_l), len(buf) - i0)
    if n <= 0:
        return
    buf[i0 : i0 + n, 0] += sig_l[:n] * gain
    buf[i0 : i0 + n, 1] += sig_r[:n] * gain


def add_mono_panned(buf: np.ndarray, sig: np.ndarray, start_sec: float, gain: float = 1.0, pan: float = 0.0) -> None:
    """パン位置 (-1.0=L 〜 +1.0=R) を指定してモノラル信号を加算"""
    angle = (pan + 1.0) * (np.pi / 4.0)
    gl = np.cos(angle) * gain
    gr = np.sin(angle) * gain
    add_stereo(buf, sig * gl, sig * gr, start_sec, 1.0)


def lowpass(sig: np.ndarray, cutoff_hz: float, order: int = 4) -> np.ndarray:
    nyq = SR * 0.5
    wn = np.clip(cutoff_hz / nyq, 0.001, 0.99)
    sos = butter(order, wn, btype="low", output="sos")
    return sosfilt(sos, sig)


def highpass(sig: np.ndarray, cutoff_hz: float, order: int = 4) -> np.ndarray:
    nyq = SR * 0.5
    wn = np.clip(cutoff_hz / nyq, 0.001, 0.99)
    sos = butter(order, wn, btype="high", output="sos")
    return sosfilt(sos, sig)


def bandpass(sig: np.ndarray, low_hz: float, high_hz: float, order: int = 3) -> np.ndarray:
    nyq = SR * 0.5
    lo = np.clip(low_hz / nyq, 0.001, 0.98)
    hi = np.clip(high_hz / nyq, lo + 0.005, 0.99)
    sos = butter(order, [lo, hi], btype="band", output="sos")
    return sosfilt(sos, sig)


def adsr(n: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    """秒指定の簡易 ADSR エンベロープ"""
    na = min(int(attack * SR), n)
    nd = min(int(decay * SR), max(0, n - na))
    nr = min(int(release * SR), max(0, n - na - nd))
    ns = max(0, n - na - nd - nr)
    parts = []
    if na > 0:
        parts.append(np.linspace(0.0, 1.0, na, endpoint=False))
    if nd > 0:
        parts.append(np.linspace(1.0, sustain, nd, endpoint=False))
    if ns > 0:
        parts.append(np.full(ns, sustain))
    if nr > 0:
        parts.append(np.linspace(sustain, 0.0, nr))
    env = np.concatenate(parts) if parts else np.zeros(n)
    return env[:n]


def synth_fm_bell(freq: float, duration: float, mod_ratio: float = 2.0, mod_index: float = 2.2) -> np.ndarray:
    """クリスタル・ベル音（FM合成）"""
    n = int(duration * SR)
    t = np.arange(n) / SR
    mod_env = np.exp(-t * 4.5) * mod_index
    mod = np.sin(2 * np.pi * (freq * mod_ratio) * t) * mod_env
    carrier = np.sin(2 * np.pi * freq * t + mod)
    # ほのかな倍音きらめき
    shimmer = 0.25 * np.sin(2 * np.pi * (freq * 3.0) * t) * np.exp(-t * 7.0)
    amp = (1.0 - np.exp(-t * 220.0)) * np.exp(-t * 2.6)
    return (carrier + shimmer) * amp


def synth_brass_note(freq: float, duration: float, detune_cents: float = 8.0) -> tuple[np.ndarray, np.ndarray]:
    """リッチなシンセブラス音（ステレオ・デチューン鋸波＋ローパス）"""
    n = int(duration * SR)
    t = np.arange(n) / SR
    ratio = 2.0 ** (detune_cents / 1200.0)

    def saw(f: float) -> np.ndarray:
        # 帯域制限の近似（上位10倍音までの加算合成でエイリアシング回避）
        s = np.zeros(n, dtype=np.float64)
        for k in range(1, 11):
            if f * k < SR * 0.42:
                s += (1.0 / k) * np.sin(2 * np.pi * f * k * t)
        return s * 0.55

    l_sig = saw(freq * ratio) + 0.65 * saw(freq * 0.5)
    r_sig = saw(freq / ratio) + 0.65 * saw(freq * 0.5)

    # 明るめブラスフィルタ
    l_sig = lowpass(l_sig, min(freq * 7.0 + 900.0, 7500.0), order=3)
    r_sig = lowpass(r_sig, min(freq * 7.0 + 900.0, 7500.0), order=3)

    env = adsr(n, attack=0.035, decay=0.14, sustain=0.72, release=min(0.45, duration * 0.35))
    return l_sig * env, r_sig * env


def synth_heartbeat(duration: float = 0.55) -> np.ndarray:
    """鼓動の低音ドンッ（ドクン）"""
    n = int(duration * SR)
    t = np.arange(n) / SR
    # 1発目（ド）
    f1 = 92.0 * np.exp(-t * 7.0) + 36.0
    ph1 = 2 * np.pi * np.cumsum(f1) / SR
    hit1 = np.sin(ph1) * np.exp(-t * 9.5) * (1.0 - np.exp(-t * 160.0))
    # 2発目（クン：0.16秒後）
    t2 = np.maximum(0.0, t - 0.16)
    mask2 = (t >= 0.16).astype(np.float64)
    f2 = 74.0 * np.exp(-t2 * 8.0) + 32.0
    ph2 = 2 * np.pi * np.cumsum(f2 * mask2) / SR
    hit2 = mask2 * np.sin(ph2) * np.exp(-t2 * 11.0) * (1.0 - np.exp(-t2 * 150.0)) * 0.72
    return hit1 + hit2


def synth_noise_sweep(
    duration: float,
    f_start: float,
    f_end: float,
    rng: np.random.Generator,
    curve: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    """周波数が時間変化するステレオノイズスイープ（吸い込み・スウッシュ用）"""
    n = int(duration * SR)
    t_norm = np.linspace(0.0, 1.0, n)
    raw_l = rng.standard_normal(n)
    raw_r = rng.standard_normal(n)

    # 12バンドのクロスフェードで滑らかな可変フィルタを近似
    out_l = np.zeros(n)
    out_r = np.zeros(n)
    steps = 12
    for i in range(steps):
        center = i / (steps - 1)
        w = np.exp(-0.5 * ((t_norm - center) / (1.0 / steps * 1.15)) ** 2)
        freq = f_start + (f_end - f_start) * (center ** curve)
        lo = max(80.0, freq * 0.65)
        hi = min(14000.0, freq * 1.45)
        out_l += bandpass(raw_l, lo, hi, order=2) * w
        out_r += bandpass(raw_r, lo, hi, order=2) * w

    return out_l * 0.45, out_r * 0.45


def simple_stereo_reverb(buf: np.ndarray, mix: float = 0.28) -> np.ndarray:
    """軽量・決定論的マルチタップディレイ残響"""
    out = buf.copy()
    taps = [
        (0.037, 0.34, True),
        (0.061, 0.26, False),
        (0.097, 0.20, True),
        (0.149, 0.15, False),
        (0.223, 0.11, True),
        (0.311, 0.08, False),
    ]
    wet = np.zeros_like(buf)
    for delay_sec, amp, swap in taps:
        d = int(delay_sec * SR)
        if d < len(buf):
            if swap:
                wet[d:, 0] += buf[:-d, 1] * amp
                wet[d:, 1] += buf[:-d, 0] * amp
            else:
                wet[d:, 0] += buf[:-d, 0] * amp
                wet[d:, 1] += buf[:-d, 1] * amp
    wet[:, 0] = lowpass(wet[:, 0], 5500.0, order=2)
    wet[:, 1] = lowpass(wet[:, 1], 5500.0, order=2)
    return out * (1.0 - mix * 0.4) + wet * mix


def save_wav(path: Path, buf: np.ndarray, peak_db: float = -1.5) -> None:
    """ソフトクリッピング＆ピークノーマライズして 16-bit WAV 保存"""
    # 緩やかなソフトサチュレーションで迫力と安全性を両立
    buf = np.tanh(buf * 0.92) / np.tanh(0.92)
    peak = np.max(np.abs(buf))
    target = 10.0 ** (peak_db / 20.0)
    if peak > 1e-6:
        buf = buf * (target / peak)
    pcm = np.clip(buf * 32767.0, -32768, 32767).astype(np.int16)
    wavfile.write(str(path), SR, pcm)
    print(f"Generated: {path.name} ({len(buf)/SR:.2f}s)")


def build_se_summon(rng: np.random.Generator) -> np.ndarray:
    """0.0s 〜 3.5s: 深淵ドローン・魔法陣展開クリスタル・オーブ収束"""
    dur = 3.5
    buf = make_buffer(dur)
    n = len(buf)
    t = np.arange(n) / SR

    # 1. 深淵サブドローン（宇宙の静寂＋うねり）
    drone_env = adsr(n, 0.4, 0.6, 0.75, 0.8)
    lfo = 1.0 + 0.12 * np.sin(2 * np.pi * 1.4 * t)
    drone_l = (0.65 * np.sin(2 * np.pi * 55.0 * t) + 0.35 * np.sin(2 * np.pi * 110.3 * t)) * drone_env * lfo
    drone_r = (0.65 * np.sin(2 * np.pi * 55.2 * t) + 0.35 * np.sin(2 * np.pi * 109.7 * t)) * drone_env * lfo
    add_stereo(buf, drone_l, drone_r, 0.0, gain=0.35)

    # 2. 魔法陣起動のクリスタル・アルペジオ (0.2s 〜 1.8s)
    notes = [523.25, 659.25, 783.99, 987.77, 1046.50, 1318.51]  # C5 E5 G5 B5 C6 E6
    for idx, freq in enumerate(notes):
        bell = synth_fm_bell(freq, 1.4, mod_ratio=2.0, mod_index=1.8)
        pan = -0.55 + (idx / (len(notes) - 1)) * 1.1
        add_mono_panned(buf, bell, 0.22 + idx * 0.21, gain=0.22, pan=pan)

    # 3. 粒子収束スイープ (0.9s 〜 2.5s)
    sw_l, sw_r = synth_noise_sweep(1.65, 220.0, 2600.0, rng, curve=1.8)
    sw_env = np.linspace(0.0, 1.0, len(sw_l)) ** 1.5 * np.exp(-np.maximum(0, np.linspace(0, 1, len(sw_l)) - 0.85) * 14.0)
    add_stereo(buf, sw_l * sw_env, sw_r * sw_env, 0.9, gain=0.35)

    # 4. オーブ形成の柔らかいチャイム (2.4s)
    orb_bell = synth_fm_bell(587.33, 1.1, mod_ratio=1.5, mod_index=2.5)
    add_mono_panned(buf, orb_bell, 2.4, gain=0.28, pan=0.0)

    return simple_stereo_reverb(buf, mix=0.32)


def build_se_upgrade(rng: np.random.Generator) -> np.ndarray:
    """2.5s 〜 7.3s (クリップ内 0.0s 〜 4.8s): 鼓動 → 金昇格 → 虹昇格 → 臨界"""
    dur = 4.8
    buf = make_buffer(dur)

    # --- 青フェイク：鼓動2回 (映像 2.7s, 3.4s -> クリップ 0.2s, 0.9s) ---
    for beat_t in [0.20, 0.90]:
        hb = synth_heartbeat(0.55)
        add_mono_panned(buf, hb, beat_t, gain=0.58, pan=0.0)

    # --- 金昇格 (映像 3.8s -> クリップ 1.3s) ---
    # 鋭い金属チャイム＋和音
    for i, f in enumerate([587.33, 880.0, 1174.66, 1760.0]):  # D major 輝き
        b = synth_fm_bell(f, 1.3, mod_ratio=2.5, mod_index=3.0)
        add_mono_panned(buf, b, 1.30 + i * 0.035, gain=0.26, pan=-0.35 + i * 0.23)
    # 金昇格スウッシュ
    gl, gr = synth_noise_sweep(0.8, 400.0, 5200.0, rng, curve=1.6)
    genv = adsr(len(gl), 0.05, 0.2, 0.6, 0.35)
    add_stereo(buf, gl * genv, gr * genv, 1.25, gain=0.42)
    # 加速鼓動 (映像 4.5s, 4.95s -> クリップ 2.0s, 2.45s)
    add_mono_panned(buf, synth_heartbeat(0.45), 2.00, gain=0.62, pan=0.0)
    add_mono_panned(buf, synth_heartbeat(0.40), 2.45, gain=0.68, pan=0.0)

    # --- 虹色昇格！！ (映像 5.2s -> クリップ 2.7s) ---
    # 1. クリスタル亀裂パリーン！（高域スパークル連打）
    sparkle_freqs = [1567.98, 2093.0, 2637.02, 3135.96, 3520.0, 4186.01]
    for i, f in enumerate(sparkle_freqs):
        sp = synth_fm_bell(f, 0.95, mod_ratio=3.14, mod_index=4.0)
        pan = rng.uniform(-0.75, 0.75)
        add_mono_panned(buf, sp, 2.70 + i * 0.025, gain=0.22, pan=pan)

    # 2. 虹昇格の強烈な上昇ライザー (2.7s 〜 4.35s = 映像 5.2s 〜 6.85s)
    n_rise = int(1.65 * SR)
    t_r = np.arange(n_rise) / SR
    f_rise = 220.0 * (2.0 ** (t_r * 2.15))  # 約2オクターブ超上昇
    ph_r = 2 * np.pi * np.cumsum(f_rise) / SR
    riser_tone = (np.sin(ph_r) + 0.45 * np.sin(ph_r * 1.5) + 0.25 * np.sin(ph_r * 2.0))
    riser_env = (t_r / 1.65) ** 1.35 * (1.0 - np.exp(-t_r * 25.0))
    # 終端でスッと抜けてインパクトへ繋ぐ
    fade_end = np.clip((1.65 - t_r) / 0.06, 0.0, 1.0)
    add_stereo(buf, riser_tone * riser_env * fade_end, riser_tone * riser_env * fade_end, 2.70, gain=0.34)

    rl, rr = synth_noise_sweep(1.65, 350.0, 9500.0, rng, curve=2.2)
    add_stereo(buf, rl * riser_env * fade_end, rr * riser_env * fade_end, 2.70, gain=0.55)

    # 3. 虹昇格確定コード（華麗なG7sus4→G7高揚感）
    for f, p in [(392.0, -0.4), (523.25, -0.15), (587.33, 0.15), (783.99, 0.4)]:
        bl, br = synth_brass_note(f, 1.55, detune_cents=10.0)
        add_stereo(buf, bl, br, 2.78, gain=0.19)

    return simple_stereo_reverb(buf, mix=0.30)


def build_se_fanfare(rng: np.random.Generator) -> np.ndarray:
    """6.8s 〜 14.8s (クリップ内 0.0s 〜 8.0s): ホワイトアウト爆発・3D回転・SSR確定ファンファーレ"""
    dur = 8.0
    buf = make_buffer(dur)

    # 1. ホワイトアウト大爆発インパクト (映像 6.8s -> クリップ 0.0s)
    n_imp = int(1.6 * SR)
    t_i = np.arange(n_imp) / SR
    sub_f = 135.0 * np.exp(-t_i * 6.5) + 34.0
    sub_ph = 2 * np.pi * np.cumsum(sub_f) / SR
    sub_boom = np.sin(sub_ph) * np.exp(-t_i * 3.0) * (1.0 - np.exp(-t_i * 260.0))
    add_stereo(buf, sub_boom, sub_boom, 0.02, gain=0.72)

    burst_l = lowpass(rng.standard_normal(n_imp), 6800.0, order=2) * np.exp(-t_i * 3.8)
    burst_r = lowpass(rng.standard_normal(n_imp), 6800.0, order=2) * np.exp(-t_i * 3.8)
    add_stereo(buf, burst_l, burst_r, 0.02, gain=0.44)

    # 2. 3Dカード回転スウッシュ (映像 7.5s, 8.2s, 8.8s -> クリップ 0.7s, 1.4s, 2.0s)
    for idx, sw_t in enumerate([0.70, 1.40, 2.00]):
        sw_l, sw_r = synth_noise_sweep(0.55, 300.0 + idx * 150, 3200.0 + idx * 600, rng, curve=1.4)
        senv = np.sin(np.linspace(0, np.pi, len(sw_l))) ** 1.3
        add_stereo(buf, sw_l * senv, sw_r * senv, sw_t, gain=0.26 + idx * 0.05)

    # 3. カード正面着地ドンッ！ (映像 9.3s -> クリップ 2.5s)
    n_land = int(0.8 * SR)
    t_l = np.arange(n_land) / SR
    lf = 110.0 * np.exp(-t_l * 9.0) + 40.0
    land_boom = np.sin(2 * np.pi * np.cumsum(lf) / SR) * np.exp(-t_l * 5.2)
    add_stereo(buf, land_boom, land_boom, 2.50, gain=0.62)

    # 4. 王道ソシャゲ SSR 確定ファンファーレ (クリップ 2.50s 〜 5.8s = 映像 9.3s 〜 12.6s)
    # メロディ: タ・タ・タ・ターーン！！ (C5 -> G5 -> A5 -> C6) + 豪華ブラス和音
    fanfare_chords = [
        # (start, dur, freqs, gain)
        (2.50, 0.24, [261.63, 329.63, 392.00, 523.25], 0.24),           # C major (短)
        (2.74, 0.24, [293.66, 392.00, 493.88, 587.33], 0.24),           # G/D (短)
        (2.98, 0.28, [349.23, 440.00, 523.25, 698.46], 0.26),           # F major (短)
        (3.26, 2.55, [261.63, 392.00, 523.25, 659.25, 783.99, 1046.50], 0.23),  # C major9 栄光のフィナーレ！
    ]
    for st, d, freqs, g in fanfare_chords:
        for f in freqs:
            bl, br = synth_brass_note(f, d, detune_cents=9.0)
            add_stereo(buf, bl, br, st, gain=g)

    # 5. 5つ星点灯に合わせたキラキラベル連打 (クリップ 2.85s 〜 3.85s = 映像 9.65s 〜 10.65s)
    star_notes = [1046.50, 1318.51, 1567.98, 2093.00, 2637.02]
    for i, f in enumerate(star_notes):
        bell = synth_fm_bell(f, 1.35, mod_ratio=2.0, mod_index=2.2)
        pan = -0.5 + i * 0.25
        add_mono_panned(buf, bell, 2.85 + i * 0.19, gain=0.22, pan=pan)

    # 6. ハープ・グリッサンド（栄光の余韻 クリップ 3.55s 〜 4.8s = 映像 10.35s 〜 11.6s）
    harp_notes = [523.25, 587.33, 659.25, 783.99, 987.77, 1046.50, 1318.51, 1567.98, 2093.00]
    for i, f in enumerate(harp_notes):
        hp = synth_fm_bell(f, 1.8, mod_ratio=1.0, mod_index=1.1)
        pan = -0.65 + (i / (len(harp_notes) - 1)) * 1.3
        add_mono_panned(buf, hp, 3.55 + i * 0.085, gain=0.14, pan=pan)

    # リバーブ付与＆ラスト 1.5 秒（映像 13.3s 〜 14.8s）を滑らかに無音フェードアウト
    buf = simple_stereo_reverb(buf, mix=0.36)
    fade_samples = int(1.6 * SR)
    fade_curve = np.linspace(1.0, 0.0, fade_samples) ** 1.8
    buf[-fade_samples:, 0] *= fade_curve
    buf[-fade_samples:, 1] *= fade_curve
    return buf


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_card_config()
    seed = resolve_seed(cfg)
    rng = np.random.default_rng(seed)

    save_wav(ASSETS_DIR / "se_summon.wav", build_se_summon(rng), peak_db=-3.0)
    save_wav(ASSETS_DIR / "se_upgrade.wav", build_se_upgrade(rng), peak_db=-2.0)
    save_wav(ASSETS_DIR / "se_fanfare.wav", build_se_fanfare(rng), peak_db=-1.5)
    print("All procedural SE files generated successfully.")


if __name__ == "__main__":
    main()
