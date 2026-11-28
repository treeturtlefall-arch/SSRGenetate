"""
SSRGenerate — 物理光学エフェクト・ビーム・パーティクル生成モジュール

玉ボケ、ゴッドレイ、縦ストリーク光柱、衝撃波リング、カットイン光学素材、
光の三原色ウィスプ（尾・星核ヘッド）、天啓光撃、浮遊クリスタル破片を担当する。
"""
from __future__ import annotations

import math
from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw

from _optics_core import (
    aniso_fbm,
    fbm_noise,
    fft_gaussian_blur,
    render_optical_glow,
)
from _utils import (
    linear_to_srgb,
    smoothstep,
    srgb_to_unpremul_rgba,
)

_smoothstep = smoothstep
_srgb_to_unpremul_rgba = srgb_to_unpremul_rgba
_aniso_fbm = aniso_fbm


def render_bokeh_sprite(
    tint: Tuple[float, float, float],
    size_px: int = 160,
    radius: float = 46.0,
    blur: float = 4.0,
    seed: int = 0,
) -> Image.Image:
    """
    bokeh_flow.hlsl の玉ボケ3層プロファイル（外周リング・ソフトハロー・中心芯）を移植。
    7枚絞り由来のわずかな多角形歪みと、外周リングの軸上色収差（R外側・B内側）を加える。
    """
    rng = np.random.default_rng((seed * 1664525 + 1013904223) & 0xFFFFFFFF)
    yy, xx = np.mgrid[0:size_px, 0:size_px].astype(np.float32)
    c = (size_px - 1) * 0.5
    th = np.arctan2(yy - c, xx - c)
    rot = float(rng.uniform(0.0, math.pi))
    dist = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) * (1.0 + 0.035 * np.cos(7.0 * th + rot))

    chans = []
    for ch_tint, r_off in zip(tint, (1.04, 1.0, 0.96)):
        s = radius * r_off
        edge = smoothstep(s + blur * 2.8, s * 0.94, dist) * 0.50
        glow = smoothstep(s + blur * 7.0, s * 0.40, dist) * 0.50
        core = smoothstep(s * 0.50, 0.0, dist) * 0.20
        ring_hi = np.exp(-((dist - s * 0.97) / max(0.8, blur * 0.9)) ** 2) * 0.35
        chans.append((edge + glow + core + ring_hi) * ch_tint)
    light = np.clip(np.stack(chans, axis=-1), 0.0, 1.4)
    light = (1.0 - np.exp(-light * 1.35)).astype(np.float32)
    return srgb_to_unpremul_rgba(light)

def render_godrays_layer(mode: str, variant: str, size: int = 1200, seed: int = 0) -> Image.Image:
    """
    rave_lasers.hlsl 由来の極座標不規則ゴッドレイ PNG を生成する。
    素数本数 (13/19/29 or 11/17/23) の加算＋針状白芯＋半径フェードで等間隔プロペラ感を払拭する。
    """
    rng = np.random.default_rng((seed * 48271 + (17 if variant == "a" else 53)) & 0xFFFFFFFF)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) * 0.5
    nx = (xx - c) / c
    ny = (yy - c) / c
    rad = np.sqrt(nx * nx + ny * ny)
    r_mask = smoothstep(0.03, 0.16, rad) * (1.0 - smoothstep(0.50, 0.96, rad))

    nums = (13, 19, 29) if variant == "a" else (11, 17, 23)
    weights = (0.48, 0.36, 0.28) if variant == "a" else (0.42, 0.38, 0.30)
    total_needle = np.zeros((size, size), dtype=np.float32)

    if mode == "prism":
        layer_colors = [
            np.array([0.46, 0.84, 0.96], dtype=np.float32),
            np.array([0.94, 0.55, 0.72], dtype=np.float32),
            np.array([0.96, 0.86, 0.58], dtype=np.float32),
        ]
    else:
        layer_colors = [
            np.array([0.96, 0.86, 0.62], dtype=np.float32),
            np.array([0.92, 0.66, 0.76], dtype=np.float32),
            np.array([0.58, 0.84, 0.94], dtype=np.float32),
        ]

    col_acc = np.zeros((size, size, 3), dtype=np.float32)
    for num, w_l, col in zip(nums, weights, layer_colors):
        ox = float(rng.uniform(-0.028, 0.028))
        oy = float(rng.uniform(-0.028, 0.028))
        phase = float(rng.uniform(0.0, math.tau))
        th_i = np.arctan2(ny - oy, nx - ox)
        sn = np.sin(th_i * float(num) + phase)
        lzr = np.power(0.5 + 0.5 * sn, 5.0)
        needle = np.power(np.maximum(sn, 0.0), 64.0) * 0.72
        col_acc += (lzr * w_l)[..., None] * col[None, None, :]
        total_needle += needle * w_l

    cloud_mod = np.clip(0.68 + 0.32 * fbm_noise(rng, (size, size), size * 0.14, octaves=2), 0.35, 1.30)
    col_acc = (col_acc + total_needle[..., None] * np.array([1.0, 0.99, 0.96], dtype=np.float32)) * (cloud_mod * r_mask)[..., None]
    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(col_acc, 0.0) * 1.15))
    return srgb_to_unpremul_rgba(srgb)


def render_light_pillar(style: str, w: int = 512, h: int = 1680, seed: int = 0) -> Image.Image:
    """
    aurora_claude.hlsl の縦ストリーク数式を移植した光柱 2 層光学 PNG を生成する。
    細白芯＋縦ノイズ筋＋上下完全フェードで灰色縦帯感を完全に排除する。
    """
    rng = np.random.default_rng((seed * 65537 + (7 if style == "gold" else 29)) & 0xFFFFFFFF)
    u = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    v = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]

    rays_a = smoothstep(0.32, 0.90, 0.5 + 0.25 * aniso_fbm(rng, h, w, cell_y=150.0, cell_x=11.0, octaves=3))
    rays_b = smoothstep(0.46, 0.94, 0.5 + 0.25 * aniso_fbm(rng, h, w, cell_y=92.0, cell_x=5.5, octaves=2))
    ray_mix = rays_a * 0.72 + rays_b * 0.45

    v_env = smoothstep(0.01, 0.24, v) * (1.0 - smoothstep(0.74, 0.99, v))
    v_core = smoothstep(0.06, 0.30, v) * (1.0 - smoothstep(0.68, 0.94, v))
    h_fade = 1.0 - smoothstep(0.66, 0.96, np.abs(u))

    h_core = np.exp(-((u / 0.045) ** 2))
    h_mid = np.exp(-((u / 0.22) ** 2))
    h_wide = np.exp(-((u / 0.44) ** 2))

    core_int = v_core * h_core * (1.25 + 0.35 * rays_b) * h_fade
    streak_int = v_env * (h_mid * (0.22 + ray_mix * 0.95) + h_wide * 0.24) * h_fade

    if style == "gold":
        streak_col = np.array([0.96, 0.76, 0.38], dtype=np.float32)[None, None, :]
        outer_col = np.array([0.85, 0.54, 0.16], dtype=np.float32)[None, None, :]
        lin = (
            core_int[..., None] * np.array([1.00, 0.98, 0.92], dtype=np.float32)
            + streak_int[..., None] * (0.7 * streak_col + 0.3 * outer_col)
        )
    else:
        hue_t = u * 2.2 + (rays_a - 0.5) * 1.4
        aurora_col = np.stack([
            0.62 + 0.38 * np.cos(hue_t + 0.5),
            0.54 + 0.36 * np.cos(hue_t - 1.6),
            0.68 + 0.32 * np.cos(hue_t + 2.4),
        ], axis=-1)
        lin = core_int[..., None] * np.array([1.0, 0.99, 1.0], dtype=np.float32) + streak_int[..., None] * aurora_col

    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.25))
    return srgb_to_unpremul_rgba(srgb)


def render_shockwave_ring(style: str, size: int = 640, seed: int = 0) -> Image.Image:
    """内縁シャープ・外縁へ滲む非対称光学衝撃波リング＋微細飛散光粒 PNG"""
    rng = np.random.default_rng((seed * 31337 + (11 if style == "gold" else 43)) & 0xFFFFFFFF)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) * 0.5
    r_base = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    th = np.arctan2(yy - c, xx - c)

    wobble = 0.014 * np.sin(th * 5.0 + 0.4) + 0.009 * np.cos(th * 9.0 - 1.1)
    r = r_base + wobble
    edge_fade = 1.0 - smoothstep(0.76, 0.96, r_base)

    R0 = 0.54
    chans = []
    offsets = (1.016, 1.000, 0.984)
    tints = (1.00, 0.84, 0.46) if style == "gold" else None

    for ch_idx, r_mul in enumerate(offsets):
        d = r - R0 * r_mul
        sharp_in = np.where(d < 0, np.exp(-((d / 0.016) ** 2)), np.exp(-((d / 0.068) ** 2)))
        core_ridge = np.exp(-((d / 0.012) ** 2)) * 1.15
        band = (sharp_in * 0.72 + core_ridge) * edge_fade
        if tints is not None:
            chans.append(band * tints[ch_idx])
        else:
            ang_shift = (0.0, -2.094, 2.094)[ch_idx]
            prism_w = 0.68 + 0.32 * np.cos(th * 2.0 + ang_shift)
            chans.append(band * prism_w + core_ridge * edge_fade * 0.35)

    lin = np.stack(chans, axis=-1)
    # 外縁に飛散する微細光粒ドット（一括生成して加算）
    sp_mask = np.zeros((size, size), dtype=np.float32)
    for _ in range(90):
        ang = float(rng.uniform(0.0, math.tau))
        rr = float(rng.uniform(0.55, 0.80)) * c
        px, py = int(round(c + math.cos(ang) * rr)), int(round(c + math.sin(ang) * rr))
        if 4 <= px < size - 4 and 4 <= py < size - 4:
            sp_mask[py - 1 : py + 2, px - 1 : px + 2] += float(rng.uniform(0.4, 1.0))
    sp_glow = fft_gaussian_blur(sp_mask, 2.4) * edge_fade
    lin += sp_glow[..., None] * np.array([1.0, 0.95, 0.88], dtype=np.float32)
    lin = np.stack([fft_gaussian_blur(lin[..., k], 1.6) * 0.35 + lin[..., k] * 0.85 for k in range(3)], axis=-1)
    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.25))
    return srgb_to_unpremul_rgba(srgb)


def render_cutin_assets(canvas_w: int = 1080, seed: int = 0) -> Tuple[Image.Image, Image.Image]:
    """脱ベタ帯カットイン用の水平アナモルフィックフレア(canvas_w x 360)とスピードライン(canvas_w x 420)を生成"""
    rng = np.random.default_rng((seed * 99991 + 17) & 0xFFFFFFFF)

    # 1. opt_cutin_flare.png (canvas_w x 360)
    fw, fh = int(canvas_w), 360
    yy, xx = np.mgrid[0:fh, 0:fw].astype(np.float32)
    nx = (xx - (fw - 1) * 0.5) / ((fw - 1) * 0.5)
    ny = (yy - (fh - 1) * 0.5) / ((fh - 1) * 0.5)
    edge_fade = (1.0 - smoothstep(0.76, 0.98, np.abs(nx))) * (1.0 - smoothstep(0.60, 0.96, np.abs(ny)))

    core_line = np.exp(-((ny / 0.022) ** 2)) * np.exp(-((nx / 0.72) ** 2)) * 1.6
    mid_band = np.exp(-((ny / 0.11) ** 2)) * np.exp(-((nx / 0.82) ** 2)) * 0.65
    diamond = np.exp(-(np.abs(nx) / 0.22 + np.abs(ny) / 0.16)) * 1.25
    halo_band = np.exp(-((ny / 0.34) ** 2)) * np.exp(-((nx / 0.90) ** 2)) * 0.28

    lr_mix = (0.5 + 0.5 * np.tanh(nx * 2.2))[..., None]
    col_left = np.array([0.28, 0.78, 1.00], dtype=np.float32)[None, None, :]
    col_right = np.array([1.00, 0.38, 0.68], dtype=np.float32)[None, None, :]
    col_band = col_left * (1.0 - lr_mix) + col_right * lr_mix
    lin_flare = (
        (core_line + diamond)[..., None] * np.array([1.0, 0.99, 0.96], dtype=np.float32)
        + (mid_band + halo_band)[..., None] * col_band
    ) * edge_fade[..., None]
    flare_img = srgb_to_unpremul_rgba(linear_to_srgb(1.0 - np.exp(-np.maximum(lin_flare, 0.0) * 1.3)))

    # 2. opt_cutin_speedlines.png (canvas_w x 420) — 1D分離ベクトル計算で高速化
    sw, sh = int(canvas_w), 420
    sl = np.zeros((sh, sw, 3), dtype=np.float32)
    y_1d = np.arange(sh, dtype=np.float32)[:, None]
    x_1d = np.arange(sw, dtype=np.float32)[None, :]
    v_fade = smoothstep(0.04, 0.28, y_1d / sh) * (1.0 - smoothstep(0.72, 0.96, y_1d / sh))
    h_fade = 1.0 - smoothstep(0.80, 0.98, np.abs((x_1d - sw * 0.5) / (sw * 0.5)))

    palette = [
        np.array([1.00, 0.96, 0.84], dtype=np.float32),
        np.array([0.52, 0.88, 1.00], dtype=np.float32),
        np.array([0.96, 0.58, 0.78], dtype=np.float32),
    ]
    n_lines = int(round(44 * (sw / 1080.0)))
    w_scale = sw / 1080.0
    for i in range(n_lines):
        yc = float(rng.uniform(28, sh - 28))
        xc = float(rng.uniform(140 * w_scale, sw - 140 * w_scale))
        half_len = float(rng.uniform(90 * w_scale, 420 * w_scale))
        thick = float(rng.uniform(0.8, 2.2))
        amp = float(rng.uniform(0.30, 0.95))
        # (sh, 1) と (1, sw) の1次元配列で計算してから外積をとることで 420x1080 全要素の exp を回避
        line_y = np.exp(-((y_1d - yc) / thick) ** 2)
        line_x = (np.maximum(0.0, 1.0 - np.abs(x_1d - xc) / half_len) ** 1.6) * amp
        col = palette[i % len(palette)]
        sl += (line_y @ line_x)[..., None] * col[None, None, :]

    sl *= (v_fade @ h_fade)[..., None]
    speed_img = srgb_to_unpremul_rgba(linear_to_srgb(1.0 - np.exp(-np.maximum(sl, 0.0) * 1.2)))
    return flare_img, speed_img


WISP_PALETTES = {
    "blue": (
        np.array([0.96, 0.99, 1.00], dtype=np.float32),
        np.array([0.32, 0.84, 1.00], dtype=np.float32),
        np.array([0.10, 0.42, 0.98], dtype=np.float32),
    ),
    "red": (
        np.array([1.00, 0.95, 0.97], dtype=np.float32),
        np.array([1.00, 0.34, 0.50], dtype=np.float32),
        np.array([0.90, 0.12, 0.34], dtype=np.float32),
    ),
    "green": (
        np.array([0.94, 1.00, 0.97], dtype=np.float32),
        np.array([0.24, 0.96, 0.68], dtype=np.float32),
        np.array([0.08, 0.72, 0.48], dtype=np.float32),
    ),
}


def render_descent_meteor(style: str = "blue", w: int = 256, h: int = 256, seed: int = 0) -> Image.Image:
    """
    冒頭 0.04s〜1.50s に天蓋から曲線軌道で降臨する光の三原色ウィスプの尾用ノード (256x256)。
    針状白芯＋高彩度内側光層＋広大で透き通った宝石色オーラを分離し、綿棒感を排除する。
    """
    rng = np.random.default_rng((seed * 65537 + 41) & 0xFFFFFFFF)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - (w - 1) * 0.5) / ((w - 1) * 0.5)
    ny = (yy - (h - 1) * 0.5) / ((h - 1) * 0.5)

    r = np.sqrt(nx * nx + ny * ny + 1e-6)
    noise = aniso_fbm(rng, h, w, cell_y=32.0, cell_x=32.0)
    r_wobble = np.maximum(0.0, r + 0.035 * noise * smoothstep(0.08, 0.55, r))

    core = np.exp(-((r / 0.068) ** 2.1)) * 2.15
    inner_band = np.exp(-((r_wobble / 0.165) ** 1.9)) * 0.78
    outer_aura = np.exp(-((r_wobble / 0.48) ** 1.55)) * (0.82 + 0.18 * noise) * 0.30

    col_core, col_inner, col_aura = WISP_PALETTES.get(style, WISP_PALETTES["blue"])

    lin = (
        core[..., None] * col_core
        + inner_band[..., None] * col_inner
        + outer_aura[..., None] * col_aura
    )

    lin = np.stack([fft_gaussian_blur(lin[..., k], 0.9) * 0.22 + lin[..., k] * 0.90 for k in range(3)], axis=-1)
    post_fade = (1.0 - smoothstep(0.50, 0.92, r)) ** 2
    lin *= post_fade[..., None]

    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.18))
    return srgb_to_unpremul_rgba(srgb)


def render_wisp_head(style: str = "blue", size: int = 256, seed: int = 0) -> Image.Image:
    """
    光の三原色ウィスプ各条の先頭を飾る専用星核ヘッド (256x256)。
    超高輝度星核＋水平アナモルフィック閃光＋四芒星スパイク＋薄い宝石色ハロー。
    """
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    nx = (xx - (size - 1) * 0.5) / ((size - 1) * 0.5)
    ny = (yy - (size - 1) * 0.5) / ((size - 1) * 0.5)
    r = np.sqrt(nx * nx + ny * ny + 1e-6)

    star_core = np.exp(-((r / 0.068) ** 2.0)) * 2.4
    anamorphic = np.exp(-((ny / 0.020) ** 2)) * np.exp(-((nx / 0.68) ** 2)) * 1.45
    spike_v = np.exp(-((nx / 0.018) ** 2)) * np.exp(-((ny / 0.46) ** 2)) * 1.15

    u45 = (nx + ny) * 0.7071
    v45 = (nx - ny) * 0.7071
    spike_diag = (
        np.exp(-((u45 / 0.015) ** 2)) * np.exp(-((v45 / 0.26) ** 2))
        + np.exp(-((v45 / 0.015) ** 2)) * np.exp(-((u45 / 0.26) ** 2))
    ) * 0.55

    halo = np.exp(-((r / 0.34) ** 1.7)) * 0.46
    col_core, col_inner, col_aura = WISP_PALETTES.get(style, WISP_PALETTES["blue"])

    lin = (
        (star_core + anamorphic * 0.75 + spike_v * 0.75 + spike_diag * 0.6)[..., None] * col_core
        + (anamorphic * 0.55 + spike_v * 0.45 + halo)[..., None] * col_inner
        + (halo * 0.55)[..., None] * col_aura
    )
    lin *= ((1.0 - smoothstep(0.62, 0.96, r)) ** 2)[..., None]
    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.25))
    return srgb_to_unpremul_rgba(srgb)


def render_sky_bolts(seed: int = 0) -> Tuple[Image.Image, Image.Image]:
    """
    昇格直前に天蓋から中央オーブへ突き刺さる天啓光撃2種:
      1. opt_bolt_gold.png (384x1024): 金昇格(3.68-3.78s)用の黄金の螺旋天啓光槍
      2. opt_bolt_prism.png (512x1024): 虹昇格(5.19-5.20s)用の有機分岐プリズム落雷
    """
    gw, gh = 384, 1024
    yy, xx = np.mgrid[0:gh, 0:gw].astype(np.float32)
    nx = (xx - (gw - 1) * 0.5) / ((gw - 1) * 0.5)
    ny = yy / float(gh - 1)

    v_env = smoothstep(0.02, 0.10, ny) * (1.0 - smoothstep(0.88, 0.98, ny))
    h_env = 1.0 - smoothstep(0.74, 0.96, np.abs(nx))
    env = v_env * h_env

    lance_taper = 0.016 + 0.022 * np.sin(np.clip(ny / 0.88, 0.0, 1.0) * math.pi)
    core_shaft = np.exp(-((nx / lance_taper) ** 2)) * 1.65
    outer_shaft = np.exp(-((nx / (lance_taper * 4.2)) ** 2)) * 0.75

    h1_x = 0.085 * np.sin(ny * 19.0) * (1.0 - 0.55 * ny)
    h2_x = -0.085 * np.sin(ny * 19.0 + 0.8) * (1.0 - 0.55 * ny)
    helix = (np.exp(-(((nx - h1_x) / 0.024) ** 2)) + np.exp(-(((nx - h2_x) / 0.024) ** 2))) * 0.85

    tip_y = 0.84
    tip_flare = np.exp(-(((ny - tip_y) / 0.045) ** 2) - ((nx / 0.16) ** 2)) * 1.75
    tip_cross = np.exp(-(((ny - tip_y) / 0.011) ** 2)) * np.exp(-((nx / 0.65) ** 2)) * 1.35

    col_w = np.array([1.00, 0.99, 0.94], dtype=np.float32)
    col_g = np.array([1.00, 0.78, 0.28], dtype=np.float32)
    lin_gold = (
        (core_shaft + tip_flare + tip_cross)[..., None] * col_w
        + (outer_shaft + helix + tip_flare * 0.6)[..., None] * col_g
    ) * env[..., None]
    bolt_gold_img = srgb_to_unpremul_rgba(linear_to_srgb(1.0 - np.exp(-np.maximum(lin_gold, 0.0) * 1.30)))

    pw, ph = 512, 1024
    ss = 2
    W, H = pw * ss, ph * ss
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    rng = np.random.default_rng((seed * 2654435761 + 919) & 0xFFFFFFFF)

    def trace_lightning(x0: float, y0: float, x1: float, y1: float, steps: int, w_start: float, w_end: float, val: int, depth: int) -> None:
        pts = [(x0, y0)]
        cx, cy = x0, y0
        for st in range(1, steps):
            t = st / float(steps)
            tx = x0 + (x1 - x0) * t
            ty = y0 + (y1 - y0) * t
            jitter = (1.0 - abs(2.0 * t - 1.0)) * (38.0 if depth > 0 else 22.0) * ss
            cx = tx + float(rng.normal(0.0, jitter * 0.45))
            cy = ty + float(rng.normal(0.0, 6.0 * ss))
            pts.append((cx, cy))
        pts.append((x1, y1))

        for i in range(len(pts) - 1):
            t = i / max(1, len(pts) - 2)
            w_cur = max(1, int(round((w_start * (1.0 - t) + w_end * t) * ss)))
            d.line([pts[i], pts[i + 1]], fill=val, width=w_cur, joint="curve")
            if depth > 0 and 2 <= i <= len(pts) - 4 and (i % 3 == 1):
                side = -1.0 if (i % 2 == 0) else 1.0
                bx = pts[i][0] + side * float(rng.uniform(75.0, 165.0)) * ss
                by = min(H * 0.90, pts[i][1] + float(rng.uniform(110.0, 230.0)) * ss)
                trace_lightning(pts[i][0], pts[i][1], bx, by, max(5, steps // 2), w_start * 0.55, 1.0, int(val * 0.86), depth - 1)

    trace_lightning(W * 0.5, H * 0.05, W * 0.5, H * 0.85, steps=16, w_start=7.0, w_end=4.8, val=255, depth=2)
    imp_x, imp_y = W * 0.5, H * 0.85
    d.ellipse([imp_x - 18 * ss, imp_y - 18 * ss, imp_x + 18 * ss, imp_y + 18 * ss], fill=255)
    d.line([(imp_x - 95 * ss, imp_y), (imp_x + 95 * ss, imp_y)], fill=245, width=4 * ss)

    mask_prism = m.resize((pw, ph), Image.Resampling.LANCZOS)
    bolt_prism_img = render_optical_glow(
        mask_l=mask_prism,
        spectrum_name="summon_gold",
        ref_scale=18.0,
        exposure=1.42,
        core_glow=1.35,
        halation=1.22,
        irregularity=0.80,
        prism_mode=True,
        seed=seed + 919,
    )
    return bolt_gold_img, bolt_prism_img


def render_crystal_shards(seed: int = 0) -> Dict[str, Image.Image]:
    """
    上空を2層パララックスで浮遊する多面体クリスタル破片:
      - opt_shard_far_{0,1,2}.png (96x96, シャープな多面体結晶)
      - opt_shard_near_{0,1,2}.png (160x160, 大口径前ボケ＋微細プリズム色収差)
    """
    out: Dict[str, Image.Image] = {}
    palettes = [
        (np.array([0.48, 0.88, 1.00], dtype=np.float32), np.array([0.85, 0.97, 1.00], dtype=np.float32)),
        (np.array([1.00, 0.78, 0.34], dtype=np.float32), np.array([1.00, 0.96, 0.86], dtype=np.float32)),
        (np.array([0.96, 0.54, 0.82], dtype=np.float32), np.array([0.56, 0.92, 1.00], dtype=np.float32)),
    ]
    shapes = [
        [(0.0, -0.72), (0.38, -0.18), (0.24, 0.68), (-0.28, 0.54), (-0.42, -0.22)],
        [(-0.14, -0.68), (0.48, -0.32), (0.34, 0.46), (-0.18, 0.70), (-0.52, 0.08)],
        [(0.06, -0.74), (0.52, -0.08), (0.16, 0.68), (-0.46, 0.32), (-0.36, -0.44)],
    ]

    for idx in range(3):
        col_a, col_b = palettes[idx]
        poly_norm = shapes[idx]

        for depth, size in (("far", 96), ("near", 160)):
            ss = 2
            S = size * ss
            c = S / 2.0
            rad = S * (0.33 if depth == "far" else 0.27)

            m_body = Image.new("L", (S, S), 0)
            m_ridge = Image.new("L", (S, S), 0)
            db = ImageDraw.Draw(m_body)
            dr = ImageDraw.Draw(m_ridge)

            pts = [(c + px * rad, c + py * rad) for (px, py) in poly_norm]
            db.polygon(pts, fill=175, outline=255)
            apex = (c + 0.08 * rad, c - 0.05 * rad)
            for i in range(len(pts)):
                p0 = pts[i]
                p1 = pts[(i + 1) % len(pts)]
                dr.line([p0, p1], fill=255, width=max(1, int(round(2.4 * ss))))
                dr.line([apex, p0], fill=220 if i % 2 == 0 else 150, width=max(1, int(round(1.8 * ss))))

            body = np.asarray(m_body.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
            ridge = np.asarray(m_ridge.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

            yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
            grad = np.clip((xx - yy) / float(size) + 0.5, 0.0, 1.0)[..., None]
            facet_col = col_a[None, None, :] * (1.0 - grad) + col_b[None, None, :] * grad

            lin = (
                body[..., None] * facet_col * 0.72
                + ridge[..., None] * np.array([1.0, 0.99, 0.96], dtype=np.float32) * 1.35
                + fft_gaussian_blur(ridge, 2.2)[..., None] * col_a[None, None, :] * 0.85
            )

            if depth == "near":
                r_ch = fft_gaussian_blur(lin[..., 0], 5.6, shift_xy=(1.4, -0.6))
                g_ch = fft_gaussian_blur(lin[..., 1], 5.4, shift_xy=(0.0, 0.0))
                b_ch = fft_gaussian_blur(lin[..., 2], 5.8, shift_xy=(-1.4, 0.6))
                lin = np.stack([r_ch, g_ch, b_ch], axis=-1) * 1.18
            else:
                lin = np.stack([fft_gaussian_blur(lin[..., k], 1.1) * 0.45 + lin[..., k] * 0.85 for k in range(3)], axis=-1)

            srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.28))
            out[f"opt_shard_{depth}_{idx}.png"] = srgb_to_unpremul_rgba(srgb)

    return out

