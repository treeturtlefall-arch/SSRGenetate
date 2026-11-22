"""
SSRGenerate — 現代ソシャゲ音像プロシージャル＆カスタムスロット SE 生成スクリプト

外部素材ゼロ（numpy + scipy のみ）で 16.0 秒構成（前後 0.5 秒無音余白＋本編 15.0 秒）に
完全同期したステレオ 44.1kHz 16-bit WAV ファイルを `assets/` に決定論的に生成します。
`assets/se_custom/` にユーザー所有 WAV を配置した場合は自動で検出し、
コンボリューションリバーブ・真空ダッキング・統合 -14.0 LUFS マスタリングを一体適用します。

生成ファイル:
  - assets/se_summon.wav   (data-start="0.5",  duration=3.5s)
  - assets/se_upgrade.wav  (data-start="3.0",  duration=4.8s)
  - assets/se_fanfare.wav  (data-start="7.3",  duration=8.0s)
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import numpy as np
from scipy.io import wavfile

from _audio_dsp import (
    SR,
    add_mono_panned,
    add_stereo,
    adsr,
    bandpass,
    convolution_reverb,
    cosine_fade_in,
    cosine_fade_out,
    lowpass,
    make_buffer,
    make_hall_ir,
    measure_lufs,
    measure_true_peak_db,
    soft_limit,
    stereo_widen,
    synth_air_whoosh,
    synth_crash_cymbal,
    synth_crystal_celesta,
    synth_glass_crackle,
    synth_harp_pluck,
    synth_modern_horn,
    synth_riser,
    synth_shimmer_pad,
    synth_sub_drop,
    synth_timpani_hit,
)
from _audio_slots import CustomSlotBank
from _utils import ASSETS_DIR, load_card_config, resolve_seed

DEFAULT_TARGET_LUFS = -14.0


def _mix_slot(
    buf: np.ndarray,
    slots: CustomSlotBank,
    slot_name: str,
    start_sec: float,
    semitones: float = 0.0,
    pan: float = 0.0,
    max_sec: float | None = None,
    extra_gain: float = 1.0,
) -> float:
    """
    カスタムスロットが配置されていれば加算し、
    プロシージャル側へ掛けるべき減衰係数 (1.0 / proc_duck / 0.0) を返す。
    """
    if not slots.has(slot_name):
        return 1.0
    sample = slots.get(slot_name, semitones=semitones, max_sec=max_sec)
    if sample is not None and len(sample) > 0:
        t_pos = start_sec + slots.offset(slot_name)
        if abs(pan) > 1e-3:
            ang = (np.clip(pan, -1.0, 1.0) + 1.0) * (np.pi / 4.0)
            gl = np.cos(ang) * 1.15
            gr = np.sin(ang) * 1.15
            add_stereo(buf, sample[:, 0] * gl, sample[:, 1] * gr, t_pos, gain=extra_gain)
        else:
            add_stereo(buf, sample[:, 0], sample[:, 1], t_pos, gain=extra_gain)
    return slots.proc_scale(slot_name)


def build_se_summon(rng: np.random.Generator, slots: CustomSlotBank) -> np.ndarray:
    """Track 1 (0.0s 〜 3.5s): 冒頭点火・RGB螺旋ウィスプ・前面点火・オーブ形成"""
    dur = 3.5
    buf = make_buffer(dur)
    n = len(buf)
    t = np.arange(n, dtype=np.float64) / SR

    # 1. 深淵サブドローン（55Hz/110Hz ステレオうねり）
    drone_env = adsr(n, attack=0.35, decay=0.6, sustain=0.72, release=0.95)
    lfo = 1.0 + 0.10 * np.sin(2.0 * np.pi * 1.3 * t)
    drone_l = (0.68 * np.sin(2.0 * np.pi * 55.0 * t) + 0.30 * np.sin(2.0 * np.pi * 110.25 * t)) * drone_env * lfo
    drone_r = (0.68 * np.sin(2.0 * np.pi * 55.18 * t) + 0.30 * np.sin(2.0 * np.pi * 109.75 * t)) * drone_env * lfo
    add_stereo(buf, drone_l, drone_r, 0.0, gain=0.22)

    # 2. 0.15s〜1.30s: 3条 RGB 螺旋ウィスプ降下スウッシュ & 星屑チェレスタ分散アルペジオ
    notes = [523.25, 659.25, 783.99, 987.77, 1174.66, 1318.51]  # Cmaj9
    pans = [-0.62, 0.55, -0.35, 0.42, -0.18, 0.12]
    for idx, (freq, pan) in enumerate(zip(notes, pans)):
        bell = synth_crystal_celesta(freq, duration=1.35, brightness=1.05)
        add_mono_panned(buf, bell, 0.16 + idx * 0.19, gain=0.17, pan=pan)

    for w_idx, (t_w, p0, p1) in enumerate([(0.12, -0.75, 0.25), (0.38, 0.75, -0.25), (0.68, -0.45, 0.0)]):
        wl, wr = synth_air_whoosh(0.65, 380.0 + w_idx * 120.0, 2900.0 + w_idx * 450.0, rng=rng, pan_start=p0, pan_end=p1, curve=1.5)
        add_stereo(buf, wl, wr, t_w, gain=0.20)

    # 3. 1.34s 前面点火フラッシュ同期（引き締めサブ＋輝き）
    p_scale_1 = _mix_slot(buf, slots, "ignition", 1.34, semitones=5.0, extra_gain=0.95)
    if p_scale_1 > 0.0:
        ig1 = synth_crystal_celesta(1567.98, duration=1.25, brightness=1.2)
        add_mono_panned(buf, ig1, 1.34, gain=0.26 * p_scale_1, pan=0.0)
        sub1 = synth_sub_drop(0.65, f_start=95.0, f_end=42.0, decay=4.5, punch=0.28)
        add_mono_panned(buf, sub1, 1.34, gain=0.26 * p_scale_1, pan=0.0)

    # 4. 1.45s〜2.55s: クリスタルオーブ形成シマーパッド & 収束エアスイープ
    pad_l, pad_r = synth_shimmer_pad([261.63, 392.00, 587.33, 783.99], duration=1.75, attack=0.45, release=0.85, rng=rng, bright_hz=2600.0)
    add_stereo(buf, pad_l, pad_r, 1.45, gain=0.24)
    conv_l, conv_r = synth_air_whoosh(1.05, 240.0, 2600.0, rng=rng, curve=1.85)
    add_stereo(buf, conv_l, conv_r, 1.40, gain=0.24)

    # コンボリューションリバーブ適用＆末尾フェード
    ir = make_hall_ir(1.9, rt60=1.7, rng=rng, shimmer=0.25)
    buf = convolution_reverb(buf, ir, mix=0.30, predelay_sec=0.012, wet_hpf_hz=180.0)
    return cosine_fade_out(buf, 0.70)


def build_se_upgrade(rng: np.random.Generator, slots: CustomSlotBank) -> np.ndarray:
    """Track 2 (2.5s 〜 7.3s / clip 0.0s 〜 4.8s): 鼓動 → 金昇格 → 亀裂 → 真空 → 虹昇格 → 臨界ライザー"""
    dur = 4.8
    buf = make_buffer(dur)

    def _add_heartbeat(clip_t: float, amp: float, semi: float = 0.0) -> None:
        ps = _mix_slot(buf, slots, "heartbeat", clip_t, semitones=semi, extra_gain=amp * 1.1)
        if ps > 0.0:
            hb1 = synth_sub_drop(0.32, f_start=92.0, f_end=36.0, decay=7.5, punch=0.42)
            hb2 = synth_sub_drop(0.28, f_start=74.0, f_end=32.0, decay=9.0, punch=0.32)
            add_mono_panned(buf, hb1, clip_t, gain=amp * 0.68 * ps, pan=0.0)
            add_mono_panned(buf, hb2, clip_t + 0.15, gain=amp * 0.48 * ps, pan=0.0)

    # --- 青フェイク脈動 (2.68s, 3.35s -> clip 0.18s, 0.85s) ---
    _add_heartbeat(0.18, 0.62)
    _add_heartbeat(0.85, 0.66)

    # --- 収縮吸い込み & 黄金天頂雷撃 (3.48s〜3.78s -> clip 0.98s〜1.28s) ---
    suck_l, suck_r = synth_air_whoosh(0.28, 300.0, 3800.0, rng=rng, curve=2.2)
    add_stereo(buf, suck_l, suck_r, 0.98, gain=0.28)
    bolt_l, bolt_r = synth_air_whoosh(0.16, 4800.0, 720.0, rng=rng, curve=0.7)
    add_stereo(buf, bolt_l, bolt_r, 1.16, gain=0.30)

    # --- 金昇格インパクト (3.78s -> clip 1.28s) ---
    ps_gold = _mix_slot(buf, slots, "gold_hit", 1.28, extra_gain=0.95)
    if ps_gold > 0.0:
        timp_g = synth_timpani_hit(98.0, duration=0.95, rng=rng)
        sub_g = synth_sub_drop(0.90, f_start=110.0, f_end=38.0, decay=3.8, punch=0.40)
        add_mono_panned(buf, timp_g, 1.28, gain=0.44 * ps_gold, pan=0.0)
        add_mono_panned(buf, sub_g, 1.28, gain=0.40 * ps_gold, pan=0.0)
        sw_gl, sw_gr = synth_air_whoosh(0.70, 480.0, 5600.0, rng=rng, curve=1.5)
        add_stereo(buf, sw_gl, sw_gr, 1.26, gain=0.32 * ps_gold)

    # 金昇格 D major 9 輝き和音
    for i, f in enumerate([587.33, 880.00, 1174.66, 1318.51, 1760.00]):
        ch = synth_crystal_celesta(f, duration=1.2, brightness=1.1)
        add_mono_panned(buf, ch, 1.28 + i * 0.025, gain=0.16, pan=-0.42 + i * 0.21)
    g_pad_l, g_pad_r = synth_shimmer_pad([293.66, 440.00, 587.33, 739.99], duration=1.20, attack=0.12, release=0.55, rng=rng, bright_hz=3200.0)
    add_stereo(buf, g_pad_l, g_pad_r, 1.28, gain=0.22)

    # --- 加速鼓動 (4.50s -> clip 2.00s) & オーブ亀裂 (4.84s -> clip 2.34s) ---
    _add_heartbeat(2.00, 0.72, semi=2.0)

    ps_crack = _mix_slot(buf, slots, "orb_crack", 2.34, extra_gain=0.95)
    if ps_crack > 0.0:
        cr_l, cr_r = synth_glass_crackle(0.55, rng=rng, density=13)
        add_stereo(buf, cr_l, cr_r, 2.34, gain=0.45 * ps_crack)

    # 臨界吸い込みサクション (4.90s〜5.06s -> clip 2.40s〜2.56s)
    vac_l, vac_r = synth_air_whoosh(0.16, 420.0, 6200.0, rng=rng, curve=2.4)
    add_stereo(buf, vac_l, vac_r, 2.40, gain=0.34)

    # --- プリズム雷撃 (5.185s -> clip 2.685s) & 虹昇格大爆発 (5.20s -> clip 2.70s) ---
    pl_l, pl_r = synth_air_whoosh(0.14, 7200.0, 900.0, rng=rng, curve=0.65)
    add_stereo(buf, pl_l, pl_r, 2.685, gain=0.32)

    ps_rb = _mix_slot(buf, slots, "rainbow_shatter", 2.70, extra_gain=1.0)
    if ps_rb > 0.0:
        shat_l, shat_r = synth_glass_crackle(1.35, rng=rng, density=22)
        add_stereo(buf, shat_l, shat_r, 2.70, gain=0.52 * ps_rb)
        sub_rb = synth_sub_drop(1.25, f_start=128.0, f_end=34.0, decay=3.2, punch=0.45)
        add_mono_panned(buf, sub_rb, 2.70, gain=0.55 * ps_rb, pan=0.0)
        timp_rb = synth_timpani_hit(87.31, duration=1.1, rng=rng)
        add_mono_panned(buf, timp_rb, 2.70, gain=0.46 * ps_rb, pan=0.0)
        cym_l, cym_r = synth_crash_cymbal(2.1, rng=rng, bright=1.08)
        add_stereo(buf, cym_l, cym_r, 2.70, gain=0.36 * ps_rb)

    # 虹昇格の壮大な G9sus4 シマーパッド & ハープグリッサンド
    rb_pad_l, rb_pad_r = synth_shimmer_pad([196.00, 293.66, 392.00, 440.00, 587.33, 783.99], duration=1.85, attack=0.14, release=0.75, rng=rng, bright_hz=4200.0)
    add_stereo(buf, rb_pad_l, rb_pad_r, 2.72, gain=0.34)
    harp_rb = [783.99, 987.77, 1174.66, 1318.51, 1567.98, 1975.53, 2349.32]
    for i, f in enumerate(harp_rb):
        hp = synth_harp_pluck(f, duration=1.3, rng=rng)
        add_mono_panned(buf, hp, 2.72 + i * 0.032, gain=0.10, pan=-0.65 + (i / (len(harp_rb) - 1)) * 1.3)

    # --- 虹カットイン突入 (5.62s -> clip 3.12s) ---
    ps_cut = _mix_slot(buf, slots, "cutin_whoosh", 3.12, extra_gain=0.95)
    if ps_cut > 0.0:
        cut_l, cut_r = synth_air_whoosh(0.48, 520.0, 6800.0, rng=rng, pan_start=-0.85, pan_end=0.85, curve=1.35)
        add_stereo(buf, cut_l, cut_r, 3.12, gain=0.44 * ps_cut)
        cut_ch = synth_crystal_celesta(2093.00, duration=0.85, brightness=1.2)
        add_mono_panned(buf, cut_ch, 3.14, gain=0.16 * ps_cut, pan=0.18)

    # --- 臨界バースト上昇ライザー (5.25s〜6.94s -> clip 2.75s〜4.44s) ---
    ps_riser = _mix_slot(buf, slots, "riser", 2.75, max_sec=1.69, extra_gain=0.90)
    if ps_riser > 0.0:
        rl, rr = synth_riser(1.69, rng=rng)
        add_stereo(buf, rl, rr, 2.75, gain=0.42 * ps_riser)

    # 高密度ホール・コンボリューションリバーブ適用
    ir = make_hall_ir(2.2, rt60=2.0, rng=rng, shimmer=0.35)
    buf = convolution_reverb(buf, ir, mix=0.32, predelay_sec=0.014, wet_hpf_hz=180.0)

    # 真空の間（映像 5.06s〜5.18s = clip 2.56s〜2.68s）の完全同期ダッキング
    # リバーブ適用後に絞ることで、残響までスッと吸い込まれる劇的なコントラストを作る
    env_vac = np.ones(len(buf), dtype=np.float64)
    i_start = int(round(2.56 * SR))
    i_end = int(round(2.68 * SR))
    n_fo = int(round(0.012 * SR))
    n_fi = int(round(0.004 * SR))
    floor_lvl = 0.006
    if i_end + n_fi < len(buf):
        env_vac[i_start : i_start + n_fo] = np.linspace(1.0, floor_lvl, n_fo)
        env_vac[i_start + n_fo : i_end] = floor_lvl
        env_vac[i_end : i_end + n_fi] = np.linspace(floor_lvl, 1.0, n_fi)
    buf *= env_vac[:, None]

    # Track 3 ホワイトアウト爆発 (6.96s = clip 4.46s) へ向けて滑らかに末尾を整える
    return cosine_fade_out(buf, 0.32)


def build_se_fanfare(rng: np.random.Generator, slots: CustomSlotBank, star_count: int = 0) -> np.ndarray:
    """Track 3 (6.8s 〜 14.8s / clip 0.0s 〜 8.0s): ホワイトアウト爆発・3D回転・SSR確定ファンファーレ・14.8s余韻"""
    dur = 8.0
    buf = make_buffer(dur)

    # 1. ホワイトアウト大爆発インパクト (映像 6.96s -> clip 0.16s)
    ps_wo = _mix_slot(buf, slots, "whiteout_impact", 0.16, extra_gain=1.0)
    if ps_wo > 0.0:
        sub_wo = synth_sub_drop(1.65, f_start=132.0, f_end=33.0, decay=2.8, punch=0.45)
        add_mono_panned(buf, sub_wo, 0.16, gain=0.66 * ps_wo, pan=0.0)
        timp_wo = synth_timpani_hit(82.41, duration=1.35, rng=rng)
        add_mono_panned(buf, timp_wo, 0.16, gain=0.50 * ps_wo, pan=0.0)
        cym_wo_l, cym_wo_r = synth_crash_cymbal(2.5, rng=rng, bright=1.05)
        add_stereo(buf, cym_wo_l, cym_wo_r, 0.16, gain=0.42 * ps_wo)
        burst_n = int(1.25 * SR)
        t_b = np.arange(burst_n, dtype=np.float64) / SR
        air_b_l = lowpass(rng.standard_normal(burst_n), 4800.0, order=2) * np.exp(-t_b * 4.4)
        air_b_r = lowpass(rng.standard_normal(burst_n), 4800.0, order=2) * np.exp(-t_b * 4.4)
        add_stereo(buf, air_b_l, air_b_r, 0.16, gain=0.22 * ps_wo)

    # 2. 3Dカード飛び出し & 反転スウッシュ (7.38s -> clip 0.58s, 8.28s -> clip 1.48s)
    ps_wh1 = _mix_slot(buf, slots, "card_whoosh", 0.58, semitones=0.0, pan=-0.25, extra_gain=0.92)
    if ps_wh1 > 0.0:
        w1_l, w1_r = synth_air_whoosh(0.52, 280.0, 3400.0, rng=rng, pan_start=-0.75, pan_end=0.65, curve=1.45)
        add_stereo(buf, w1_l, w1_r, 0.58, gain=0.42 * ps_wh1)

    ps_wh2 = _mix_slot(buf, slots, "card_whoosh", 1.48, semitones=2.5, pan=0.20, extra_gain=0.98)
    if ps_wh2 > 0.0:
        w2_l, w2_r = synth_air_whoosh(0.46, 420.0, 4800.0, rng=rng, pan_start=0.70, pan_end=0.0, curve=1.55)
        add_stereo(buf, w2_l, w2_r, 1.48, gain=0.48 * ps_wh2)

    # 3. カード正面ビタ止め着地インパクト (8.68s -> clip 1.88s)
    ps_land = _mix_slot(buf, slots, "card_land", 1.88, extra_gain=1.0)
    if ps_land > 0.0:
        sub_ld = synth_sub_drop(1.15, f_start=118.0, f_end=36.0, decay=3.6, punch=0.48)
        add_mono_panned(buf, sub_ld, 1.88, gain=0.62 * ps_land, pan=0.0)
        timp_ld = synth_timpani_hit(98.0, duration=1.1, rng=rng)
        add_mono_panned(buf, timp_ld, 1.88, gain=0.52 * ps_land, pan=0.0)
        cym_ld_l, cym_ld_r = synth_crash_cymbal(2.3, rng=rng, bright=1.02)
        add_stereo(buf, cym_ld_l, cym_ld_r, 1.88, gain=0.34 * ps_land)
        # SSR確定の輪郭を際立たせる極短クリスタル倍音アタック (E7 + G7, Nyquist安全帯域)
        atk_c1 = synth_crystal_celesta(2637.02, duration=0.38, brightness=1.05)
        atk_c2 = synth_crystal_celesta(3135.96, duration=0.32, brightness=1.00)
        add_mono_panned(buf, atk_c1, 1.88, gain=0.065 * ps_land, pan=-0.22)
        add_mono_panned(buf, atk_c2, 1.885, gain=0.055 * ps_land, pan=0.22)

    # 4. 現代ソシャゲ SSR 確定ファンファーレ (clip 1.88s 〜 5.80s = 映像 8.68s 〜 12.60s)
    # 主役は広大なステレオ・シマーパッド＋ティンパニ打点、モダンホーンは厚み補助
    prog = [
        # (start, dur, pad_freqs, horn_freqs, timp_hz, pad_gain, horn_gain)
        (1.88, 0.34, [261.63, 329.63, 392.00, 493.88], [261.63, 523.25], 130.81, 0.25, 0.14),  # Cmaj7
        (2.12, 0.34, [246.94, 293.66, 392.00, 587.33], [293.66, 587.33], 146.83, 0.25, 0.14),  # G/B
        (2.36, 0.38, [261.63, 349.23, 440.00, 523.25, 659.25], [349.23, 698.46], 174.61, 0.27, 0.15),  # Fmaj9
        (2.64, 3.35, [261.63, 392.00, 493.88, 587.33, 659.25, 783.99], [261.63, 523.25, 783.99], 130.81, 0.36, 0.16),  # Cmaj9 栄光フィナーレ
    ]
    for idx, (st, d, p_freqs, h_freqs, t_hz, pg, hg) in enumerate(prog):
        atk = 0.045 if idx < 3 else 0.10
        rel = 0.12 if idx < 3 else 1.45
        pl, pr = synth_shimmer_pad(p_freqs, duration=d, attack=atk, release=rel, rng=rng, bright_hz=3600.0)
        add_stereo(buf, pl, pr, st, gain=pg)
        for hf in h_freqs:
            hl, hr = synth_modern_horn(hf, d, brightness=0.92)
            add_stereo(buf, hl, hr, st, gain=hg)
        if idx in (1, 2, 3):
            tp = synth_timpani_hit(t_hz, duration=0.75, rng=rng)
            add_mono_panned(buf, tp, st, gain=0.28 if idx < 3 else 0.42, pan=0.0)

    # フィナーレ頭 (clip 2.64s = 映像 9.44s) の荘厳なクラッシュシンバル
    fin_cym_l, fin_cym_r = synth_crash_cymbal(2.8, rng=rng, bright=1.10)
    add_stereo(buf, fin_cym_l, fin_cym_r, 2.64, gain=0.38)
    # Cmaj9 フィナーレ頭の高域ウィンドチャイム風4音煌めき (C7-D7-E7-G7)
    for w_i, wf in enumerate([2093.00, 2349.32, 2637.02, 3135.96]):
        wc = synth_crystal_celesta(wf, duration=0.45, brightness=1.02)
        add_mono_panned(buf, wc, 2.64 + w_i * 0.022, gain=0.042, pan=-0.55 + w_i * 0.36)

    # 5. 星点灯に合わせたキラメキチャイム連打 (clip 2.20s 〜 2.76s = 映像 9.00s 〜 9.56s)
    # stars == 0 のときはテキスト出現 (clip 2.58s = 9.38s サブタイトル / clip 2.80s = 9.60s タイトル) に寄り添う2音の控えめな煌めき
    if star_count > 0:
        star_notes = [1046.50, 1174.66, 1318.51, 1567.98, 2093.00, 2349.32]
        star_semis = [0.0, 2.0, 4.0, 7.0, 12.0, 14.0]
        n_play = min(star_count, len(star_notes))
        for i in range(n_play):
            f = star_notes[i]
            semi = star_semis[i]
            pan = -0.52 + (i / max(1, n_play - 1)) * 1.04 if n_play > 1 else 0.0
            st_time = 2.20 + i * 0.14
            ps_star = _mix_slot(buf, slots, "star_chime", st_time, semitones=semi, pan=pan, extra_gain=0.78)
            if ps_star > 0.0:
                cel = synth_crystal_celesta(f, duration=1.35, brightness=1.15)
                add_mono_panned(buf, cel, st_time, gain=0.14 * ps_star, pan=pan)
    else:
        # stars: 0 時はテキスト出現（9.38s サブタイトル / 9.60s タイトル）に合わせた控えめな2音
        sub_ch = synth_crystal_celesta(1567.98, duration=1.2, brightness=0.95)
        add_mono_panned(buf, sub_ch, 2.58, gain=0.08, pan=-0.22)
        tit_ch = synth_crystal_celesta(2093.00, duration=1.2, brightness=1.0)
        add_mono_panned(buf, tit_ch, 2.80, gain=0.09, pan=0.22)

    # 6. タイトル光走査ワイプ (clip 2.80s = 映像 9.60s)
    wipe_l, wipe_r = synth_air_whoosh(0.42, 1800.0, 7800.0, rng=rng, pan_start=-0.65, pan_end=0.65, curve=1.2)
    add_stereo(buf, wipe_l, wipe_r, 2.80, gain=0.15)

    # 7. コンサートハープ上昇大グリッサンド (clip 2.85s 〜 3.80s = 映像 9.65s 〜 10.60s)
    # ホーン・シマーパッドの後ろで上品に彩るバランスへ抑制
    harp_notes = [523.25, 587.33, 659.25, 783.99, 987.77, 1046.50, 1174.66, 1318.51, 1567.98, 1975.53, 2093.00]
    for i, f in enumerate(harp_notes):
        hp = synth_harp_pluck(f, duration=1.75, rng=rng)
        u = i / max(1, len(harp_notes) - 1)
        pan = -0.65 + u * 1.30
        vel = 0.78 + 0.22 * float(np.sin(np.pi * u))
        add_mono_panned(buf, hp, 2.85 + i * 0.082, gain=0.068 * vel, pan=pan)

    # 8. 終盤 12.0s〜14.8s 「光の呼吸」余韻 (clip 4.60s 〜 7.98s)
    # レイアウト固定後のシマー・スパークル呼吸に寄り添う柔らかな Cmaj9 エアリー余韻
    tail_pad_l, tail_pad_r = synth_shimmer_pad(
        [261.63, 392.00, 523.25, 659.25, 783.99, 1174.66],
        duration=3.35,
        attack=0.75,
        release=1.65,
        rng=rng,
        bright_hz=2350.0,
    )
    add_stereo(buf, tail_pad_l, tail_pad_r, 4.60, gain=0.22)

    # 12.95s (clip 6.15s) 外枠リムグレア (#frame-rim-glare) に寄り添う一筋のクリスタル余韻
    glare_cel = synth_crystal_celesta(1567.98, duration=1.45, brightness=0.85)
    add_mono_panned(buf, glare_cel, 6.15, gain=0.075, pan=0.15)
    glare_cel2 = synth_crystal_celesta(2093.00, duration=1.25, brightness=0.80)
    add_mono_panned(buf, glare_cel2, 6.32, gain=0.055, pan=-0.18)

    # 高密度ホール・シマー・コンボリューションリバーブ適用
    ir = make_hall_ir(2.6, rt60=2.3, rng=rng, shimmer=0.55)
    buf = convolution_reverb(buf, ir, mix=0.38, predelay_sec=0.016, wet_hpf_hz=180.0)

    # ラスト 1.05s（映像 13.75s〜14.80s）を余弦カーブで滑らかにフェードアウト
    # 14.0-14.5s 区間にも上品な残響が残り、14.80s で無音へ着地する
    return cosine_fade_out(buf, 1.05)


def _save_pcm16_wav(path: Path, buf: np.ndarray) -> None:
    pcm = np.clip(buf * 32767.0, -32768, 32767).astype(np.int16)
    wavfile.write(str(path), SR, pcm)
    print(f"Generated: {path.name} ({len(buf)/SR:.2f}s)")


def main() -> None:
    t0 = time.perf_counter()
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_card_config()
    seed = resolve_seed(cfg)
    rng = np.random.default_rng(seed)

    target_lufs = DEFAULT_TARGET_LUFS
    if isinstance(cfg.get("audio"), dict) and cfg["audio"].get("targetLufs") is not None:
        target_lufs = float(cfg["audio"]["targetLufs"])

    slots = CustomSlotBank()
    print(slots.used_summary())

    # 各トラックを独立シードで並列生成（1トラックの変更が他トラックの位相へ波及しない）
    star_count = max(0, min(6, int(cfg.get("stars", 0))))
    with ThreadPoolExecutor(max_workers=3) as ex:
        fut_summon = ex.submit(build_se_summon, np.random.default_rng(seed + 101), slots)
        fut_upgrade = ex.submit(build_se_upgrade, np.random.default_rng(seed + 202), slots)
        fut_fanfare = ex.submit(build_se_fanfare, np.random.default_rng(seed + 303), slots, star_count)
        b_summon = fut_summon.result()
        b_upgrade = fut_upgrade.result()
        b_fanfare = fut_fanfare.result()

    # index.html と同一オフセット（0.5s プリロール含む）＆トラック音量で 16.0s 仮想マスターを組み立てて統合 LUFS を計測
    tracks = [
        ("se_summon.wav",  b_summon,  0.5, 0.85),
        ("se_upgrade.wav", b_upgrade, 3.0, 0.92),
        ("se_fanfare.wav", b_fanfare, 7.3, 0.95),
    ]
    master = make_buffer(16.0)
    for _, b, st, vol in tracks:
        add_stereo(master, b[:, 0], b[:, 1], st, gain=vol)

    raw_lufs = measure_lufs(master, sr=SR)
    # -3.1 dBFS TruePeak 天井（HyperFrames delivery 自動レベル低下回避）を見込み 2 パスで目標 LUFS へ収束
    ceiling_db = -3.1
    gain_db = target_lufs - raw_lufs
    for _ in range(2):
        gain_lin = 10.0 ** (gain_db / 20.0)
        tmp_master = make_buffer(16.0)
        for _, b, st, vol in tracks:
            bt = soft_limit(b * gain_lin, ceiling_db=ceiling_db)
            add_stereo(tmp_master, bt[:, 0], bt[:, 1], st, gain=vol)
        est_lufs = measure_lufs(tmp_master, sr=SR)
        gain_db += target_lufs - est_lufs

    gain_lin = 10.0 ** (gain_db / 20.0)
    master_final = make_buffer(16.0)
    mastered_tracks = []
    for fname, b, st, vol in tracks:
        b_mastered = soft_limit(b * gain_lin, ceiling_db=ceiling_db)
        mastered_tracks.append((fname, b_mastered, st, vol))
        add_stereo(master_final, b_mastered[:, 0], b_mastered[:, 1], st, gain=vol)

    # 4x オーバーサンプリング TruePeak が -2.8 dBFS を超える場合は追加リミットして配信安全余裕を確保
    tp_db = measure_true_peak_db(master_final, oversample=4)
    if tp_db > -2.85:
        extra_trim_db = -2.85 - tp_db
        ceiling_db += extra_trim_db
        master_final = make_buffer(16.0)
        new_list = []
        for fname, bm, st, vol in mastered_tracks:
            bm2 = soft_limit(bm, ceiling_db=ceiling_db)
            new_list.append((fname, bm2, st, vol))
            add_stereo(master_final, bm2[:, 0], bm2[:, 1], st, gain=vol)
        mastered_tracks = new_list
        tp_db = measure_true_peak_db(master_final, oversample=4)

    for fname, bm, _, _ in mastered_tracks:
        _save_pcm16_wav(ASSETS_DIR / fname, bm)

    final_lufs = measure_lufs(master_final, sr=SR)
    peak_lin = float(np.max(np.abs(master_final)))
    peak_db = 20.0 * np.log10(max(peak_lin, 1e-9))

    def _win_rms_db(s0: float, s1: float) -> float:
        seg = master_final[int(round(s0 * SR)) : int(round(s1 * SR))]
        if len(seg) == 0:
            return -120.0
        return 20.0 * np.log10(max(float(np.sqrt(np.mean(seg * seg))), 1e-6))

    rms_head = _win_rms_db(0.0, 0.5)
    rms_145 = _win_rms_db(14.5, 15.0)
    rms_tail = _win_rms_db(15.5, 16.0)

    elapsed = time.perf_counter() - t0
    print(
        f"Master preview (16.0s): raw={raw_lufs:.2f} LUFS -> gain={gain_db:+.2f} dB -> "
        f"est={final_lufs:.2f} LUFS, Peak={peak_db:.2f} dBFS, TruePeak={tp_db:.2f} dBTP | "
        f"RMS head(0-0.5s)={rms_head:.1f}dB, tail(14.5-15s)={rms_145:.1f}dB, pad(15.5-16s)={rms_tail:.1f}dB ({elapsed:.2f}s)"
    )


if __name__ == "__main__":
    main()
