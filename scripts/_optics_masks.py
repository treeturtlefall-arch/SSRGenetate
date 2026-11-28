"""
SSRGenerate — 物理光学ジオメトリマスク ＆ クリスタルオーブ生成モジュール

魔法陣3層、天蓋ゲート2層、オーブ臨界亀裂、多面体クリスタルオーブ、
星・スパークル・リザルト光学魔法リングのマスクおよび描画を担当する。
"""
from __future__ import annotations

import math
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw

from _optics_core import (
    approx_inner_distance,
    bilinear_warp,
    fbm_noise,
    fft_gaussian_blur,
    value_noise,
)
from _utils import (
    linear_to_srgb,
    smoothstep,
    srgb_to_unpremul_rgba,
)

_smoothstep = smoothstep
_srgb_to_unpremul_rgba = srgb_to_unpremul_rgba


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

