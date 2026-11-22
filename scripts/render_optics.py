"""
SSRGenerate — 物理光学発光（Optical Burn-in）アセット生成エンジン

`scripts/_optics_core.py` の6段階物理光学モデルと高速ノイズ関数を用い、
SSRガチャ演出の発光体（3層魔法陣×3色、天蓋ゲート、オーブ・臨界亀裂、ゴッドレイ、
光柱、衝撃波、カットイン、星、スパークル、玉ボケ、浮遊クリスタル破片）の
高精細透過PNG群を決定論的に生成する。

使い方:
  python scripts/render_optics.py
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import math
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from _optics_core import (
    OPTICAL_SPECTRA,
    aniso_fbm,
    approx_inner_distance,
    bilinear_warp,
    fbm_noise,
    fft_gaussian_blur,
    prepare_optical_mask,
    render_optical_glow,
    value_noise,
)
from _utils import (
    OUT_DIR,
    linear_to_srgb,
    load_card_config,
    resolve_layout,
    resolve_seed,
    save_png,
    smoothstep,
    srgb_to_unpremul_rgba,
)

# 後方互換エイリアス
_smoothstep = smoothstep
_srgb_to_unpremul_rgba = srgb_to_unpremul_rgba
_aniso_fbm = aniso_fbm


# ==============================================================================
# ジオメトリマスク描画（精密魔法陣3層 / 分岐オーブ亀裂 / 星5つ / スパークル）
# ==============================================================================
def draw_dashed_circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, width: int, n_dashes: int = 48) -> None:
    step = 360.0 / n_dashes
    for i in range(n_dashes):
        a0 = i * step
        a1 = a0 + step * 0.56
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(bbox, start=a0, end=a1, fill=215, width=width)


def build_magic_circle_masks(size: int = 1024, seed: int = 0) -> Tuple[Image.Image, Image.Image, Image.Image]:
    """
    外周・中段・内周の3層精密魔法陣マスク（2xスーパーサンプリング）。
    180本目盛り・決定論擬似ルーン帯・二重六芒星・6頂点副魔法陣ノード・コンパス針で情報階層を持たせる。
    """
    ss = 2
    S = size * ss
    c = S / 2.0
    sc = S / 1024.0
    rng = np.random.default_rng((seed * 747796405 + 2891336453) & 0xFFFFFFFF)

    def circle(d: ImageDraw.ImageDraw, r: float, w: float, val: int = 255) -> None:
        rr = r * sc
        d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=val, width=max(1, int(round(w * sc))))

    def radial(d: ImageDraw.ImageDraw, a_deg: float, r0: float, r1: float, w: float, val: int = 255) -> None:
        a = math.radians(a_deg)
        d.line(
            [(c + math.cos(a) * r0 * sc, c + math.sin(a) * r0 * sc), (c + math.cos(a) * r1 * sc, c + math.sin(a) * r1 * sc)],
            fill=val,
            width=max(1, int(round(w * sc))),
        )

    # 1. Outer Ring: 二重外周円 + 180本目盛り + 決定論擬似ルーン帯 + 12方位菱形ノード
    m_out = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_out)
    circle(d, 434, 4.5, 255)
    circle(d, 418, 2.0, 210)
    for i in range(180):
        long_tick = i % 15 == 0
        radial(d, i * 2.0, 396 if long_tick else 407, 432, 3.0 if long_tick else 1.4, 255 if long_tick else 185)

    a = 0.0
    while a < 360.0:
        kind = int(rng.integers(0, 3))
        span = float(rng.uniform(2.6, 5.2))
        if kind == 0:
            radial(d, a, 373, 393, 2.2, 235)
            radial(d, a + span * 0.52, 380, 393, 1.5, 200)
        elif kind == 1:
            ang = math.radians(a)
            rr = 383 * sc
            px, py = c + math.cos(ang) * rr, c + math.sin(ang) * rr
            dr = 2.8 * sc
            d.ellipse([px - dr, py - dr, px + dr, py + dr], fill=230)
        else:
            rr = (376 + float(rng.uniform(0, 12))) * sc
            d.arc([c - rr, c - rr, c + rr, c + rr], start=a, end=a + span, fill=215, width=max(1, int(round(1.9 * sc))))
        a += span + float(rng.uniform(1.0, 2.4))

    circle(d, 366, 3.2, 245)
    circle(d, 355, 1.5, 175)
    for k in range(12):
        ang = math.radians(k * 30.0)
        ca, sa = math.cos(ang), math.sin(ang)
        rc = 434 * sc
        cx0, cy0 = c + ca * rc, c + sa * rc
        rl, rw = 12.0 * sc, 6.5 * sc
        pts = [
            (cx0 + ca * rl, cy0 + sa * rl),
            (cx0 - sa * rw, cy0 + ca * rw),
            (cx0 - ca * rl, cy0 - sa * rl),
            (cx0 + sa * rw, cy0 - ca * rw),
        ]
        d.polygon(pts, fill=255)

    # 2. Mid Polygons: 二重六芒星 + 外接多角形 + 6頂点副魔法陣ノード
    m_mid = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_mid)

    def poly_pts(n: int, r: float, rot_deg: float) -> List[Tuple[float, float]]:
        return [
            (c + math.cos(math.radians(rot_deg + i * (360.0 / n))) * r * sc,
             c + math.sin(math.radians(rot_deg + i * (360.0 / n))) * r * sc)
            for i in range(n)
        ]

    for pts, w, val in [
        (poly_pts(6, 342, -90), 2.8, 225),
        (poly_pts(8, 336, -90), 1.8, 170),
        (poly_pts(3, 342, -90), 4.2, 255),
        (poly_pts(3, 342, 90),  4.2, 255),
        (poly_pts(3, 324, -90), 1.8, 195),
        (poly_pts(3, 324, 90),  1.8, 195),
    ]:
        d.polygon(pts, outline=val, width=max(1, int(round(w * sc))))

    for k in range(6):
        ang = math.radians(-90.0 + k * 60.0)
        nx0, ny0 = c + math.cos(ang) * 342 * sc, c + math.sin(ang) * 342 * sc
        rn = 20.0 * sc
        d.ellipse([nx0 - rn, ny0 - rn, nx0 + rn, ny0 + rn], outline=240, width=max(1, int(round(2.2 * sc))))
        rd = 4.5 * sc
        d.ellipse([nx0 - rd, ny0 - rd, nx0 + rd, ny0 + rd], fill=255)

    # 3. Inner Ring: 二重細線リング + 60分割破線 + 4方位コンパス針 + 中心核ガイド
    m_in = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_in)
    circle(d, 252, 3.8, 255)
    circle(d, 236, 1.6, 195)
    draw_dashed_circle(d, c, c, 216 * sc, width=max(1, int(round(2.4 * sc))), n_dashes=60)
    circle(d, 148, 2.2, 225)
    circle(d, 132, 1.3, 165)
    for k in range(4):
        ang = math.radians(k * 90.0)
        ca, sa = math.cos(ang), math.sin(ang)
        r0, r1 = 152 * sc, 250 * sc
        rm, w_n = 200 * sc, 6.0 * sc
        pts = [
            (c + ca * r0, c + sa * r0),
            (c + ca * rm - sa * w_n, c + sa * rm + ca * w_n),
            (c + ca * r1, c + sa * r1),
            (c + ca * rm + sa * w_n, c + sa * rm - ca * w_n),
        ]
        d.polygon(pts, outline=240, fill=165)

    return (
        m_out.resize((size, size), Image.Resampling.LANCZOS),
        m_mid.resize((size, size), Image.Resampling.LANCZOS),
        m_in.resize((size, size), Image.Resampling.LANCZOS),
    )


def build_orb_cracks_mask(size: int = 512, seed: int = 0) -> Image.Image:
    """有機的分岐＋距離テーパー付きクリスタル臨界亀裂マスク"""
    ss = 2
    S = size * ss
    c = S / 2.0
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    rng = np.random.default_rng((seed * 2654435761 + 313) & 0xFFFFFFFF)

    def trace_crack(x: float, y: float, ang: float, steps: int, step_len: float, w0: float, val0: int, branch_depth: int) -> None:
        cur_ang = ang
        turn_bias = float(rng.uniform(-0.08, 0.08))
        for st in range(steps):
            t = st / max(1, steps - 1)
            cur_ang += turn_bias + float(rng.uniform(-0.24, 0.24))
            nx = x + math.cos(cur_ang) * step_len
            ny = y + math.sin(cur_ang) * step_len
            w = max(1, int(round(w0 * (1.0 - 0.78 * t) * ss)))
            val = max(110, int(round(val0 * (1.0 - 0.22 * t))))
            d.line([(x, y), (nx, ny)], fill=val, width=w, joint="curve")
            if branch_depth > 0 and 4 <= st <= steps - 5 and rng.random() < 0.34:
                b_ang = cur_ang + float(rng.choice([-1.0, 1.0])) * float(rng.uniform(0.45, 0.92))
                trace_crack(nx, ny, b_ang, max(5, steps - st - 2), step_len * 0.84, w0 * 0.56, int(val * 0.88), branch_depth - 1)
            x, y = nx, ny

    n_main = 7
    base_ang = float(rng.uniform(0.0, math.tau))
    for i in range(n_main):
        ang = base_ang + (i / n_main) * math.tau + float(rng.uniform(-0.22, 0.22))
        steps = int(rng.integers(14, 19))
        step_len = (S * 0.42) / steps
        trace_crack(c, c, ang, steps, step_len, w0=5.2, val0=255, branch_depth=1)

    # 中心の鋭い破砕コアと微細破片ドット
    core_pts = []
    for i in range(14):
        a = (i / 14) * math.tau
        r = (20.0 if i % 2 == 0 else 10.5) * ss * float(rng.uniform(0.85, 1.18))
        core_pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    d.polygon(core_pts, fill=255)
    for _ in range(16):
        da = float(rng.uniform(0.0, math.tau))
        dr = float(rng.uniform(0.18, 0.42)) * S
        px, py = c + math.cos(da) * dr, c + math.sin(da) * dr
        pr = float(rng.uniform(1.2, 2.8)) * ss
        d.ellipse([px - pr, py - pr, px + pr, py + pr], fill=215)

    return m.resize((size, size), Image.Resampling.LANCZOS)


def build_star_mask(size: int = 144) -> Image.Image:
    ss = 2
    S = size * ss
    c = S / 2.0
    r_out = S * 0.28
    r_in = S * 0.118
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        r = r_out if i % 2 == 0 else r_in
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.resize((size, size), Image.Resampling.LANCZOS)


def build_sparkle_mask(size: int = 128) -> Image.Image:
    ss = 2
    S = size * ss
    c = S / 2.0
    r_arm = S * 0.28
    r_waist = S * 0.042
    pts = []
    for i in range(8):
        a = math.radians(-90 + i * 45)
        r = r_arm if i % 2 == 0 else r_waist
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    d.polygon(pts, fill=255)
    rc = S * 0.055
    d.ellipse([c - rc, c - rc, c + rc, c + rc], fill=255)
    return m.resize((size, size), Image.Resampling.LANCZOS)


def build_result_ring_mask(size: int = 1400, seed: int = 0) -> Image.Image:
    """
    リザルト背景の光学魔法リング（設計単位 1700px 直径）。
    二重外周線・目盛り・擬似ルーン帯・六芒星・破線内周で情報階層を持たせ、
    カードの上下左右の余白から円弧が覗く額縁として機能させる。
    """
    ss = 2
    S = size * ss
    c = S / 2.0
    sc = S / 1700.0
    rng = np.random.default_rng((seed * 362437 + 5) & 0xFFFFFFFF)
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)

    def ring(r: float, w: float, val: int = 255) -> None:
        rr = r * sc
        d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=val, width=max(1, int(round(w * sc))))

    def radial(a_deg: float, r0: float, r1: float, w: float, val: int = 255) -> None:
        a = math.radians(a_deg)
        d.line(
            [(c + math.cos(a) * r0 * sc, c + math.sin(a) * r0 * sc), (c + math.cos(a) * r1 * sc, c + math.sin(a) * r1 * sc)],
            fill=val,
            width=max(1, int(round(w * sc))),
        )

    ring(842, 3.5)
    ring(818, 1.6, 200)
    for i in range(180):
        long_tick = i % 15 == 0
        radial(i * 2.0, 806 if long_tick else 822, 840, 2.6 if long_tick else 1.4, 255 if long_tick else 180)

    a = 0.0
    while a < 360.0:
        kind = int(rng.integers(0, 3))
        span = float(rng.uniform(2.2, 4.6))
        if kind == 0:
            radial(a, 774, 798, 2.4, 230)
            radial(a + span * 0.5, 782, 798, 1.6, 200)
        elif kind == 1:
            rr = 786 * sc
            ang = math.radians(a)
            px, py = c + math.cos(ang) * rr, c + math.sin(ang) * rr
            dr = 3.2 * sc
            d.ellipse([px - dr, py - dr, px + dr, py + dr], fill=230)
        else:
            rr = (778 + float(rng.uniform(0, 14))) * sc
            d.arc([c - rr, c - rr, c + rr, c + rr], start=a, end=a + span, fill=210, width=max(1, int(round(2.0 * sc))))
        a += span + float(rng.uniform(0.8, 2.2))

    ring(760, 4.2)
    for rot in (-90.0, 90.0):
        pts = []
        for k in range(3):
            ang = math.radians(rot + k * 120.0)
            pts.append((c + math.cos(ang) * 740 * sc, c + math.sin(ang) * 740 * sc))
        d.polygon(pts, outline=200, width=max(1, int(round(2.2 * sc))))
    draw_dashed_circle(d, c, c, 690 * sc, width=max(1, int(round(2.0 * sc))), n_dashes=90)
    return m.resize((size, size), Image.Resampling.LANCZOS)


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


# ==============================================================================
# Phase 2B 物理光学アセット群（クリスタルオーブ / 不規則ゴッドレイ / 縦ストリーク光柱 / 衝撃波 / カットイン）
# ==============================================================================
def render_crystal_orb_layers(style: str, size: int = 512, seed: int = 0) -> Tuple[Image.Image, Image.Image]:
    """
    ボロノイ多面体ファセット＋薄膜干渉／多方向スペキュラ＋フレネル光輪によるクリスタルオーブの
    shell（多面体外殻）と facet（逆回転用内部渦・結晶屈折）の 2 層透過 PNG を生成する。
    """
    rng = np.random.default_rng((seed * 1664525 + 911) & 0xFFFFFFFF)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) * 0.5
    R = size * 0.34
    nx = (xx - c) / R
    ny = (yy - c) / R
    r2 = nx * nx + ny * ny
    r = np.sqrt(r2)
    nz = np.sqrt(np.maximum(0.0, 1.0 - r2))
    inside_soft = smoothstep(1.015, 0.965, r)

    n_facets = 30
    dirs = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for k in range(n_facets):
        z = 0.96 - (k / max(1, n_facets - 1)) * 0.88
        rad = math.sqrt(max(0.0, 1.0 - z * z))
        ang = k * golden + float(rng.uniform(-0.22, 0.22))
        dx = math.cos(ang) * rad + float(rng.uniform(-0.08, 0.08))
        dy = math.sin(ang) * rad + float(rng.uniform(-0.08, 0.08))
        dz = max(0.08, z + float(rng.uniform(-0.05, 0.05)))
        ln = math.sqrt(dx * dx + dy * dy + dz * dz)
        dirs.append((dx / ln, dy / ln, dz / ln))
    dirs_arr = np.array(dirs, dtype=np.float32)
    f_phases = rng.uniform(0.0, 1.0, size=n_facets).astype(np.float32)

    dots = nx[..., None] * dirs_arr[:, 0] + ny[..., None] * dirs_arr[:, 1] + nz[..., None] * dirs_arr[:, 2]
    f_idx = np.argmax(dots, axis=-1)
    part = np.partition(dots, -2, axis=-1)
    d1 = part[..., -1]
    d2 = part[..., -2]

    fn = dirs_arr[f_idx]
    N_raw = fn * 0.84 + np.stack([nx, ny, nz], axis=-1) * 0.16
    N_len = np.sqrt(np.sum(N_raw * N_raw, axis=-1, keepdims=True))
    N = N_raw / np.maximum(N_len, 1e-5)

    edge = np.exp(-((d1 - d2) / 0.0072) ** 2) * inside_soft
    fresnel = np.power(np.clip(1.0 - nz, 0.0, 1.0), 2.8) * inside_soft

    lights = [
        ((-0.48, -0.58, 0.66), 1.32, 48.0),
        ((0.64, 0.42, 0.28),   0.68, 34.0),
        ((-0.68, 0.26, 0.42),  0.48, 28.0),
    ]
    spec_total = np.zeros((size, size), dtype=np.float32)
    diff_total = np.zeros((size, size), dtype=np.float32)
    for (lx, ly, lz), w_l, shin in lights:
        ll = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / ll, ly / ll, lz / ll
        hx, hy, hz = lx, ly, lz + 1.0
        hl = math.sqrt(hx * hx + hy * hy + hz * hz)
        hx, hy, hz = hx / hl, hy / hl, hz / hl
        diff_total += np.clip(N[..., 0] * lx + N[..., 1] * ly + N[..., 2] * lz, 0.0, 1.0) * w_l * 0.55
        spec_total += np.power(np.clip(N[..., 0] * hx + N[..., 1] * hy + N[..., 2] * hz, 0.0, 1.0), shin) * w_l

    phase_map = f_phases[f_idx]
    facet_tone = np.clip(0.08 + 0.82 * np.power(np.clip(diff_total, 0.0, 1.5), 1.55) + 0.22 * phase_map, 0.05, 1.32)

    if style == "blue":
        ft_b = np.clip(np.power(np.clip(facet_tone, 0.0, 1.4), 1.38), 0.0, 1.45)
        base_col = np.stack([
            0.015 + 0.22 * ft_b,
            0.085 + 0.46 * ft_b,
            0.28 + 0.66 * ft_b,
        ], axis=-1)
        rim_col = np.array([0.62, 0.88, 1.00], dtype=np.float32)
        edge_col = np.array([0.82, 0.96, 1.00], dtype=np.float32)
    elif style == "gold":
        base_col = np.stack([
            0.42 + 0.54 * facet_tone,
            0.24 + 0.48 * facet_tone,
            0.05 + 0.22 * facet_tone,
        ], axis=-1)
        rim_col = np.array([1.00, 0.88, 0.58], dtype=np.float32)
        edge_col = np.array([1.00, 0.96, 0.82], dtype=np.float32)
    else:
        phi = phase_map * math.tau + (1.0 - nz) * 4.2 + (N[..., 0] * 1.4 - N[..., 1] * 1.1) * 2.2
        prism = np.stack([
            0.54 + 0.46 * np.cos(phi),
            0.52 + 0.44 * np.cos(phi - 2.094),
            0.56 + 0.44 * np.cos(phi + 2.094),
        ], axis=-1)
        base_col = prism * (0.48 + 0.52 * facet_tone[..., None])
        rim_col = np.stack([
            0.65 + 0.35 * np.cos(phi + 0.4),
            0.65 + 0.35 * np.cos(phi - 1.7),
            0.65 + 0.35 * np.cos(phi + 2.5),
        ], axis=-1)
        edge_col = np.array([1.00, 0.98, 1.00], dtype=np.float32)

    shell_body = base_col * inside_soft[..., None] * (0.46 + 0.44 * (1.0 - nz * 0.55))[..., None]
    if style == "blue":
        shell_body = shell_body * (1.0 - edge[..., None] * 0.22)
    edge_mask = np.clip(0.14 + 0.95 * fresnel + 0.85 * np.clip(spec_total, 0.0, 1.0), 0.0, 1.0)
    shell_edge = edge_col * (edge * edge_mask)[..., None] * 0.65
    shell_rim = rim_col * (fresnel[..., None] * 1.42)
    spec_mult = 1.32 if style == "blue" else 1.18
    shell_spec = np.array([1.0, 0.99, 0.96], dtype=np.float32)[None, None, :] * (spec_total * inside_soft)[..., None] * spec_mult

    shell_lin = shell_body + shell_edge + shell_rim + shell_spec
    outer_fade = 1.0 - smoothstep(1.16, 1.44, r)
    halo_src = np.stack([
        fft_gaussian_blur(shell_lin[..., k], size * 0.022) * 0.42
        + fft_gaussian_blur(shell_lin[..., k], size * 0.055) * 0.24
        for k in range(3)
    ], axis=-1) * outer_fade[..., None]
    shell_lin = shell_lin * inside_soft[..., None] + halo_src * (1.0 - inside_soft[..., None] * 0.55)
    shell_srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(shell_lin, 0.0) * 1.25))
    shell_img = srgb_to_unpremul_rgba(shell_srgb)

    inner_m = 1.0 - smoothstep(0.52, 0.88, r)
    th = np.arctan2(ny, nx)
    swirl = np.power(0.5 + 0.5 * np.sin(th * 5.0 + r * 7.5 + float(rng.uniform(0.0, math.tau))), 2.6)
    rays = np.power(0.5 + 0.5 * np.sin(th * 9.0 - r * 4.0 + 1.2), 5.0)
    plasma = np.clip(0.5 + 0.35 * fbm_noise(rng, (size, size), size * 0.16, octaves=2), 0.0, 1.0)
    energy = (0.55 * swirl * plasma + 0.50 * rays) * inner_m

    if style == "blue":
        f_col = np.stack([0.22 * energy, 0.58 * energy, 1.05 * energy], axis=-1)
    elif style == "gold":
        f_col = np.stack([1.25 * energy, 0.92 * energy, 0.42 * energy], axis=-1)
    else:
        phi_in = th * 2.0 + r * 6.0
        f_col = np.stack([
            (0.65 + 0.35 * np.cos(phi_in)) * energy * 1.2,
            (0.60 + 0.35 * np.cos(phi_in - 2.094)) * energy * 1.15,
            (0.68 + 0.32 * np.cos(phi_in + 2.094)) * energy * 1.2,
        ], axis=-1)
    facet_srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(f_col, 0.0) * 1.35))
    facet_img = srgb_to_unpremul_rgba(facet_srgb)
    return shell_img, facet_img


def render_orb_core_bleach(size: int = 512) -> Image.Image:
    """多層クリスタルオーブ中心用の白飛びエネルギー核 PNG"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) * 0.5
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (size * 0.34)
    core = np.exp(-((r / 0.21) ** 2)) * 1.85 + np.exp(-((r / 0.42) ** 2)) * 0.45
    core *= 1.0 - smoothstep(0.65, 0.98, r)
    lin = np.stack([core * 1.00, core * 0.98, core * 0.94], axis=-1)
    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.45))
    return srgb_to_unpremul_rgba(srgb)


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


def build_celestial_gate_masks(size: int = 1024, seed: int = 0) -> Tuple[Image.Image, Image.Image]:
    """
    上空の天蓋・逆さ天球ゲート（Celestial Astrolabe Gate）用の2層マスク (outer, inner)。
    床魔法陣（六芒星＋ルーン）と意匠を差別化し、天球儀・星座弧・子午線目盛り・偏心黄道軌道で構成する。
    """
    ss = 2
    S = size * ss
    c = S / 2.0
    sc = S / 920.0
    rng = np.random.default_rng((seed * 1103515245 + 777) & 0xFFFFFFFF)

    def circle(d: ImageDraw.ImageDraw, r: float, w: float, val: int = 255, ox: float = 0.0, oy: float = 0.0) -> None:
        rr = r * sc
        cx, cy = c + ox * sc, c + oy * sc
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=val, width=max(1, int(round(w * sc))))

    def radial(d: ImageDraw.ImageDraw, a_deg: float, r0: float, r1: float, w: float, val: int = 255) -> None:
        a = math.radians(a_deg)
        d.line(
            [(c + math.cos(a) * r0 * sc, c + math.sin(a) * r0 * sc), (c + math.cos(a) * r1 * sc, c + math.sin(a) * r1 * sc)],
            fill=val,
            width=max(1, int(round(w * sc))),
        )

    # 1. Outer Astrolabe Ring: 二重天球外輪 + 72方位目盛り + 星座連結アーク + 三日月ノード
    m_out = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_out)
    circle(d, 436, 3.8, 250)
    circle(d, 422, 1.8, 195)
    for i in range(72):
        deg = i * 5.0
        is_major = i % 6 == 0
        is_mid = i % 2 == 0
        r_in = 392 if is_major else (404 if is_mid else 412)
        w_t = 2.8 if is_major else (1.8 if is_mid else 1.2)
        v_t = 255 if is_major else (200 if is_mid else 155)
        radial(d, deg, r_in, 434, w_t, v_t)

    circle(d, 390, 2.2, 220)
    for sec in range(8):
        base_deg = sec * 45.0 + 8.0
        rr_arc = (362 + (sec % 2) * 14) * sc
        d.arc([c - rr_arc, c - rr_arc, c + rr_arc, c + rr_arc], start=base_deg, end=base_deg + 28.0, fill=195, width=max(1, int(round(1.8 * sc))))
        star_pts = []
        for st in range(4):
            ad = math.radians(base_deg + st * 9.5 + float(rng.uniform(-2.0, 2.0)))
            rd = (352 + float(rng.uniform(-16.0, 22.0))) * sc
            px, py = c + math.cos(ad) * rd, c + math.sin(ad) * rd
            star_pts.append((px, py))
            nr = (3.4 if st in (0, 3) else 2.4) * sc
            d.ellipse([px - nr, py - nr, px + nr, py + nr], fill=255)
        d.line(star_pts, fill=215, width=max(1, int(round(1.6 * sc))))

    draw_dashed_circle(d, c, c, 336 * sc, width=max(1, int(round(2.0 * sc))), n_dashes=48)

    # 2. Inner Astrolabe Mechanism: 偏心黄道リング2対 + 8方位アストラル指針 + 中央ゲート開口
    m_in = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_in)
    circle(d, 304, 3.0, 245)
    circle(d, 262, 2.2, 220, ox=28.0, oy=-18.0)
    circle(d, 262, 2.0, 200, ox=-28.0, oy=18.0)
    circle(d, 214, 2.4, 235)
    draw_dashed_circle(d, c, c, 196 * sc, width=max(1, int(round(2.0 * sc))), n_dashes=36)
    circle(d, 152, 3.4, 255)
    circle(d, 138, 1.6, 190)

    for k in range(8):
        ang = math.radians(k * 45.0 + 22.5)
        ca, sa = math.cos(ang), math.sin(ang)
        r0, r1 = 140 * sc, 302 * sc
        rm, wn = 220 * sc, (5.2 if k % 2 == 0 else 3.4) * sc
        pts = [
            (c + ca * r0, c + sa * r0),
            (c + ca * rm - sa * wn, c + sa * rm + ca * wn),
            (c + ca * r1, c + sa * r1),
            (c + ca * rm + sa * wn, c + sa * rm - ca * wn),
        ]
        d.polygon(pts, outline=245, fill=175 if k % 2 == 0 else 130)

    return (
        m_out.resize((size, size), Image.Resampling.LANCZOS),
        m_in.resize((size, size), Image.Resampling.LANCZOS),
    )


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Render optical assets")
    parser.add_argument("--cutin-only", action="store_true", help="Render only cutin flare and speedlines (fast resolution sync)")
    args = parser.parse_args()

    cfg = load_card_config()
    layout = resolve_layout(cfg)
    seed = resolve_seed(cfg, section="optics")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.cutin_only and (OUT_DIR / "opt_orb_core_bleach.png").exists():
        flare_img, speed_img = render_cutin_assets(canvas_w=layout.canvas_w, seed=seed + 2901)
        save_png(flare_img, OUT_DIR / "opt_cutin_flare.png")
        save_png(speed_img, OUT_DIR / "opt_cutin_speedlines.png")
        print(f"[OK] [cutin-only] opt_cutin_flare.png ({flare_img.width}x360) & opt_cutin_speedlines.png ({speed_img.width}x420)")
        return

    opt_cfg = cfg.get("optics", {})
    hal = float(opt_cfg.get("halation", 1.05))
    cg = float(opt_cfg.get("coreGlow", 1.15))
    irr = float(opt_cfg.get("irregularity", 0.85))

    # 独立したマスク群を事前構築＆距離変換キャッシュ（並列実行後に3色で共有）
    m_outer, m_mid, m_inner = build_magic_circle_masks(1024, seed=seed + 77)
    g_outer, g_inner = build_celestial_gate_masks(1024, seed=seed + 3101)
    mc_styles = [
        ("blue",    "summon_blue", False, 1.02, hal * 0.95),
        ("gold",    "summon_gold", False, 1.12, hal * 1.10),
        ("rainbow", "summon_gold", True,  1.22, hal * 1.25),
    ]
    cracks_mask = build_orb_cracks_mask(512, seed=seed + 501)
    star_mask = build_star_mask(144)
    sp_mask = build_sparkle_mask(128)
    ring_mask = build_result_ring_mask(1400, seed=seed + 1201)

    with ThreadPoolExecutor(max_workers=8) as ex:
        prep_mc = {
            "outer": ex.submit(prepare_optical_mask, m_outer, 20.0),
            "mid":   ex.submit(prepare_optical_mask, m_mid, 20.0),
            "inner": ex.submit(prepare_optical_mask, m_inner, 20.0),
        }
        prep_gate = {
            "outer": ex.submit(prepare_optical_mask, g_outer, 20.0),
            "inner": ex.submit(prepare_optical_mask, g_inner, 20.0),
        }
        prep_ring_fut = ex.submit(prepare_optical_mask, ring_mask, 14.0)
        rings = [
            ("outer", m_outer, prep_mc["outer"].result()),
            ("mid",   m_mid,   prep_mc["mid"].result()),
            ("inner", m_inner, prep_mc["inner"].result()),
        ]
        gate_rings = [
            ("outer", g_outer, prep_gate["outer"].result()),
            ("inner", g_inner, prep_gate["inner"].result()),
        ]
        prep_ring = prep_ring_fut.result()

        # マルチスレッド並列レンダリング＆保存タスクの構築（NumPy/SciPy/Pillow の GIL 解放を活用）
        tasks = []

        def submit_glow(
            ex_pool: ThreadPoolExecutor,
            fname: str,
            mask: Image.Image,
            spec: str,
            ref_scale: float,
            exp: float,
            core_g: float,
            hal_v: float,
            irr_v: float,
            is_prism: bool,
            s_val: int,
            prepared: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None,
        ) -> None:
            def _job() -> str:
                img = render_optical_glow(
                    mask_l=mask,
                    spectrum_name=spec,
                    ref_scale=ref_scale,
                    exposure=exp,
                    core_glow=core_g,
                    halation=hal_v,
                    irregularity=irr_v,
                    prism_mode=is_prism,
                    seed=s_val,
                    prepared=prepared,
                )
                save_png(img, OUT_DIR / fname)
                return f"[OK] {fname} ({img.width}x{img.height})"

            tasks.append(ex_pool.submit(_job))

        # 1. 魔法陣 3色 × 3層
        for s_idx, (cname, spec, is_prism, exp, h_val) in enumerate(mc_styles):
            for r_idx, (rname, mask, prep) in enumerate(rings):
                submit_glow(
                    ex,
                    f"opt_mc_{cname}_{rname}.png",
                    mask,
                    spec,
                    20.0,
                    exp,
                    cg,
                    h_val,
                    irr,
                    is_prism,
                    seed + s_idx * 100 + r_idx * 17,
                    prepared=prep,
                )

        # 2. オーブ臨界亀裂
        submit_glow(
            ex,
            "opt_orb_cracks.png",
            cracks_mask,
            "summon_gold",
            20.0,
            1.32,
            cg * 1.20,
            hal * 1.20,
            irr,
            True,
            seed + 501,
        )

        # 3. 多面体クリスタルオーブ（3色 × shell/facet + 共通コア）
        for i, cname in enumerate(("blue", "gold", "rainbow")):
            def _orb_job(cn: str = cname, idx: int = i) -> str:
                sh_img, fc_img = render_crystal_orb_layers(cn, size=512, seed=seed + 2101 + idx * 37)
                save_png(sh_img, OUT_DIR / f"opt_orb_{cn}_shell.png")
                save_png(fc_img, OUT_DIR / f"opt_orb_{cn}_facet.png")
                return f"[OK] opt_orb_{cn}_{{shell,facet}}.png (512x512)"

            tasks.append(ex.submit(_orb_job))

        def _core_job() -> str:
            core_img = render_orb_core_bleach(size=512)
            save_png(core_img, OUT_DIR / "opt_orb_core_bleach.png")
            return "[OK] opt_orb_core_bleach.png (512x512)"

        tasks.append(ex.submit(_core_job))

        # 4. 不規則ゴッドレイ 2層（虹昇格用 & リザルト用）
        for mode in ("prism", "gold"):
            for var in ("a", "b"):
                def _gr_job(m: str = mode, v: str = var) -> str:
                    gr_img = render_godrays_layer(mode=m, variant=v, size=1200, seed=seed + 2301)
                    fname = f"opt_godrays_{m}_{v}.png"
                    save_png(gr_img, OUT_DIR / fname)
                    return f"[OK] {fname} ({gr_img.width}x{gr_img.height})"

                tasks.append(ex.submit(_gr_job))

        # 5. 縦ストリーク光柱 2層 & 光学衝撃波リング & カットイン光学素材
        for style in ("gold", "rainbow"):
            def _pl_job(st: str = style) -> str:
                pl_img = render_light_pillar(style=st, w=512, h=1680, seed=seed + 2501)
                save_png(pl_img, OUT_DIR / f"opt_pillar_{st}.png")
                sw_img = render_shockwave_ring(style=st, size=640, seed=seed + 2701)
                save_png(sw_img, OUT_DIR / f"opt_shock_{st}.png")
                return f"[OK] opt_pillar_{st}.png & opt_shock_{st}.png"

            tasks.append(ex.submit(_pl_job))

        def _cutin_job() -> str:
            flare_img, speed_img = render_cutin_assets(canvas_w=layout.canvas_w, seed=seed + 2901)
            save_png(flare_img, OUT_DIR / "opt_cutin_flare.png")
            save_png(speed_img, OUT_DIR / "opt_cutin_speedlines.png")
            return f"[OK] opt_cutin_flare.png ({flare_img.width}x360) & opt_cutin_speedlines.png ({speed_img.width}x420)"

        tasks.append(ex.submit(_cutin_job))

        # 6. リザルト星5つ
        submit_glow(ex, "opt_star_gold.png", star_mask, "star_gold", 18.0, 1.18, cg * 1.10, hal * 0.95, irr * 0.65, False, seed + 701)

        # 7. 周囲スパークル 4色
        for i, (cname, spec) in enumerate([
            ("gold",  "sparkle_gold"),
            ("white", "sparkle_white"),
            ("pink",  "sparkle_pink"),
            ("cyan",  "sparkle_cyan"),
        ]):
            submit_glow(ex, f"opt_sparkle_{cname}.png", sp_mask, spec, 16.0, 1.15, cg * 1.15, hal * 1.05, irr * 0.70, False, seed + 901 + i * 31)

        # 8. リザルト背景の光学魔法リング（3色: rainbow / gold / blue + 後方互換 opt_result_ring.png）
        ring_styles = [
            ("rainbow", "summon_gold", True,  1.08, hal * 1.20),
            ("gold",    "summon_gold", False, 0.95, hal * 1.15),
            ("blue",    "summon_blue", False, 1.00, hal * 1.12),
        ]
        for r_idx, (r_cname, r_spec, r_prism, r_exp, r_hal) in enumerate(ring_styles):
            def _res_ring_job(
                cn: str = r_cname,
                sp: str = r_spec,
                pr: bool = r_prism,
                ex_v: float = r_exp,
                ha_v: float = r_hal,
                s_off: int = r_idx * 41,
            ) -> str:
                img = render_optical_glow(
                    mask_l=ring_mask,
                    spectrum_name=sp,
                    ref_scale=14.0,
                    exposure=ex_v,
                    core_glow=cg,
                    halation=ha_v,
                    irregularity=irr,
                    prism_mode=pr,
                    seed=seed + 1201 + s_off,
                    prepared=prep_ring,
                )
                save_png(img, OUT_DIR / f"opt_result_ring_{cn}.png")
                if cn == "gold":
                    save_png(img, OUT_DIR / "opt_result_ring.png")
                return f"[OK] opt_result_ring_{cn}.png ({img.width}x{img.height})"

            tasks.append(ex.submit(_res_ring_job))

        # 9. 玉ボケ光粒
        def _bokeh_job() -> str:
            bokeh_tints = {
                "gold": (1.00, 0.84, 0.52),
                "rose": (1.00, 0.62, 0.78),
                "aqua": (0.55, 0.88, 1.00),
                "white": (1.00, 0.97, 0.92),
            }
            for i, (cname, tint) in enumerate(bokeh_tints.items()):
                for depth, blur in (("far", 1.6), ("near", 9.0)):
                    bk = render_bokeh_sprite(tint, size_px=160, radius=44.0 if depth == "far" else 40.0, blur=blur, seed=seed + 1301 + i)
                    save_png(bk, OUT_DIR / f"opt_bokeh_{cname}_{depth}.png")
            return "[OK] opt_bokeh_{gold,rose,aqua,white}_{far,near}.png (160x160)"

        tasks.append(ex.submit(_bokeh_job))

        # 10. 上空の天蓋・逆さ天球ゲート（3色 × 2層）
        for s_idx, (cname, spec, is_prism, exp, h_val) in enumerate(mc_styles):
            for r_idx, (rname, mask, prep) in enumerate(gate_rings):
                submit_glow(
                    ex,
                    f"opt_gate_{cname}_{rname}.png",
                    mask,
                    spec,
                    20.0,
                    exp * 0.96,
                    cg,
                    h_val,
                    irr,
                    is_prism,
                    seed + 3100 + s_idx * 97 + r_idx * 19,
                    prepared=prep,
                )

        # 11. 冒頭降臨光の三原色ウィスプ（尾＋星核ヘッド） & 金/虹昇格の天啓光撃
        def _meteor_bolts_job() -> str:
            for c_idx, cname in enumerate(("blue", "red", "green")):
                meteor_img = render_descent_meteor(style=cname, w=256, h=256, seed=seed + 3401 + c_idx * 13)
                save_png(meteor_img, OUT_DIR / f"opt_meteor_{cname}.png")
                head_img = render_wisp_head(style=cname, size=256, seed=seed + 3451 + c_idx * 13)
                save_png(head_img, OUT_DIR / f"opt_wisp_head_{cname}.png")
            bolt_gold_img, bolt_prism_img = render_sky_bolts(seed=seed + 3601)
            save_png(bolt_gold_img, OUT_DIR / "opt_bolt_gold.png")
            save_png(bolt_prism_img, OUT_DIR / "opt_bolt_prism.png")
            return "[OK] opt_meteor_{blue,red,green}.png, opt_wisp_head_{blue,red,green}.png & opt_bolt_{gold,prism}.png"

        tasks.append(ex.submit(_meteor_bolts_job))

        # 12. 2層パララックス浮遊クリスタル破片
        def _shards_job() -> str:
            shards = render_crystal_shards(seed=seed + 3801)
            for fname, s_img in shards.items():
                save_png(s_img, OUT_DIR / fname)
            return "[OK] opt_shard_{far,near}_{0,1,2}.png (6 files)"

        tasks.append(ex.submit(_shards_job))

        for fut in tasks:
            print(fut.result())


if __name__ == "__main__":
    main()
