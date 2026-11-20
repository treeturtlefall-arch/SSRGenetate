"""
SSRGenerate — 物理光学発光（Optical Burn-in）アセット生成エンジン

FilmDateStamp の 6段階物理光学モデルを抽出し、SSRガチャ演出の発光体
（3層魔法陣×3色、オーブ臨界亀裂、星5つ、4色スパークル）を
芯の白飛び（Core Bleach）・H&D分光飽和・FFT3重異方性PSFハレーション・
3階層有機ゆらぎ（Macro/Meso/Micro）付きの高精細透過PNGとして決定論的に生成する。

使い方:
  python scripts/render_optics.py
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from _utils import OUT_DIR, load_card_config, resolve_seed


# ==============================================================================
# 物理分光スペクトル定義（FilmDateStamp H&D 分光モデル拡張）
# ==============================================================================
OPTICAL_SPECTRA: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "summon_blue": {
        "sens": (0.45, 1.85, 3.40),
        "scatter": (0.04, 0.42, 1.00),
        "tint": (0.88, 0.96, 1.00),
    },
    "summon_gold": {
        "sens": (3.15, 1.55, 0.42),
        "scatter": (1.00, 0.42, 0.04),
        "tint": (1.00, 0.99, 0.88),
    },
    "star_gold": {
        "sens": (3.25, 1.65, 0.45),
        "scatter": (1.00, 0.40, 0.03),
        "tint": (1.00, 0.98, 0.86),
    },
    "sparkle_gold": {
        "sens": (3.10, 1.75, 0.50),
        "scatter": (1.00, 0.48, 0.05),
        "tint": (1.00, 0.99, 0.90),
    },
    "sparkle_pink": {
        "sens": (3.05, 0.78, 2.05),
        "scatter": (1.00, 0.24, 0.58),
        "tint": (1.00, 0.92, 0.96),
    },
    "sparkle_cyan": {
        "sens": (0.62, 2.30, 3.15),
        "scatter": (0.10, 0.60, 1.00),
        "tint": (0.90, 0.98, 1.00),
    },
    "sparkle_white": {
        "sens": (2.95, 2.90, 2.85),
        "scatter": (0.88, 0.86, 0.82),
        "tint": (1.00, 0.99, 0.96),
    },
}


# ==============================================================================
# FilmDateStamp 由来 物理光学コア関数群（純粋 NumPy + Pillow）
# ==============================================================================
def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


def fft_gaussian_blur(
    arr: np.ndarray,
    sigma: float,
    sigma_minor: Optional[float] = None,
    angle_deg: float = 0.0,
    shift_xy: Tuple[float, float] = (0.0, 0.0),
) -> np.ndarray:
    if sigma_minor is None:
        sigma_minor = sigma
    smax = max(sigma, sigma_minor)
    if smax < 0.05 and abs(shift_xy[0]) < 1e-3 and abs(shift_xy[1]) < 1e-3:
        return arr.astype(np.float32, copy=True)

    pad = int(math.ceil(3.2 * smax + abs(shift_xy[0]) + abs(shift_xy[1]))) + 2
    a = np.pad(arr.astype(np.float32), pad, mode="constant")
    h, w = a.shape

    fy = np.fft.fftfreq(h).astype(np.float32)[:, None]
    fx = np.fft.rfftfreq(w).astype(np.float32)[None, :]
    th = math.radians(angle_deg)
    u = fx * math.cos(th) + fy * math.sin(th)
    v = -fx * math.sin(th) + fy * math.cos(th)
    tf = np.exp(-2.0 * math.pi ** 2 * (sigma ** 2 * u ** 2 + sigma_minor ** 2 * v ** 2))
    if shift_xy[0] != 0.0 or shift_xy[1] != 0.0:
        tf = tf * np.exp(-2j * math.pi * (fx * shift_xy[0] + fy * shift_xy[1]))

    out = np.fft.irfft2(np.fft.rfft2(a) * tf, s=a.shape)
    return np.maximum(out[pad:-pad, pad:-pad], 0.0).astype(np.float32)


def approx_inner_distance(binary: np.ndarray, max_iter: int = 48) -> np.ndarray:
    """反復モルフォロジー収縮による八角形メトリック内部距離変換（発光尾根抽出）"""
    dist = np.zeros(binary.shape, dtype=np.float32)
    cur = binary.astype(bool).copy()
    for i in range(max_iter):
        if not cur.any():
            break
        dist += cur
        p = np.pad(cur, 1, constant_values=False)
        er = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        if i % 2 == 1:
            er &= p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:]
        cur = er
    return dist


def value_noise(rng: np.random.Generator, shape: Tuple[int, int], cell: float) -> np.ndarray:
    h, w = shape
    cell = max(1.0, float(cell))
    gh = int(math.ceil(h / cell)) + 4
    gw = int(math.ceil(w / cell)) + 4
    grid = rng.standard_normal((gh, gw)).astype(np.float32)
    up_w, up_h = int(math.ceil(gw * cell)), int(math.ceil(gh * cell))
    up = np.asarray(Image.fromarray(grid).resize((up_w, up_h), Image.BICUBIC), dtype=np.float32)
    oy = int(cell + rng.random() * cell)
    ox = int(cell + rng.random() * cell)
    out = up[oy:oy + h, ox:ox + w]
    std = float(out.std())
    return ((out - out.mean()) / std).astype(np.float32) if std > 1e-6 else np.zeros(shape, np.float32)


def fbm_noise(rng: np.random.Generator, shape: Tuple[int, int], cell: float, octaves: int = 2) -> np.ndarray:
    acc = np.zeros(shape, dtype=np.float32)
    amp, total = 1.0, 0.0
    for i in range(octaves):
        acc += value_noise(rng, shape, cell / (2 ** i)) * amp
        total += amp
        amp *= 0.5
    acc /= total
    std = float(acc.std())
    return (acc / std).astype(np.float32) if std > 1e-6 else acc


def bilinear_warp(field: np.ndarray, dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    h, w = field.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sx = np.clip(xx + dx, 0.0, w - 1.001)
    sy = np.clip(yy + dy, 0.0, h - 1.001)
    x0 = sx.astype(np.int32)
    y0 = sy.astype(np.int32)
    fx = sx - x0
    fy = sy - y0
    a = field[y0, x0]
    b = field[y0, x0 + 1]
    c = field[y0 + 1, x0]
    d = field[y0 + 1, x0 + 1]
    return (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy).astype(np.float32)


def render_optical_glow(
    mask_l: Image.Image,
    spectrum_name: str,
    ref_scale: float,
    exposure: float = 1.05,
    core_glow: float = 1.15,
    halation: float = 1.05,
    irregularity: float = 0.85,
    prism_mode: bool = False,
    seed: int = 0,
) -> Image.Image:
    """
    任意のグレースケール発光マスクに対し、FilmDateStamp の6段階物理光学モデルを適用して
    透過 RGBA 画像を生成する。
    """
    raw = np.asarray(mask_l, dtype=np.float32) / 255.0
    H, W = raw.shape
    fs = float(ref_scale)
    irr = max(0.0, float(irregularity))
    hal = max(0.05, float(halation))

    rng_macro = np.random.default_rng([seed & 0xFFFFFFFF, 11])
    rng_meso = np.random.default_rng([seed & 0xFFFFFFFF, 22])
    rng_micro = np.random.default_rng([seed & 0xFFFFFFFF, 33])

    # Step 1: 距離変換尾根（発光芯）
    inside = raw > 0.28
    dist = approx_inner_distance(inside, max_iter=36)
    dist = fft_gaussian_blur(dist, max(0.4, fs * 0.014)) * inside
    dmax = max(1.0, float(np.percentile(dist[inside], 92))) if inside.any() else 1.0
    ridge = np.power(np.clip(dist / dmax, 0.0, 1.25), 1.10)

    # Step 2: ① Macro ゆらぎ（素子個体差＋微光量勾配）
    if irr > 0:
        n_macro = value_noise(rng_macro, (H, W), max(8.0, fs * 1.4))
        ang = rng_macro.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        lens = math.cos(ang) * (xx - W / 2) / max(1.0, W / 2) + math.sin(ang) * (yy - H / 2) / max(1.0, H / 2)
        gain = np.clip(1.0 + irr * (0.10 * n_macro + 0.06 * lens), 0.65, 1.38)
    else:
        gain = np.ones((H, W), dtype=np.float32)

    slit = fft_gaussian_blur(raw, max(0.35, fs * 0.022))
    hot = ridge * gain
    source = (0.48 * slit * gain + 1.15 * hot * core_glow) * exposure

    # Step 3: 多重異方性 PSF 散乱（FFT 1パス）
    psf_core = fft_gaussian_blur(hot, max(0.45, fs * 0.028))
    psf_narrow = fft_gaussian_blur(source, max(0.8, fs * 0.060))

    if irr > 0:
        aniso = 1.0 + irr * 0.14 * rng_meso.uniform(0.4, 1.0)
        hal_angle = rng_meso.uniform(0.0, 180.0)
        sh_ang = rng_meso.uniform(0, 2 * math.pi)
        sh_mag = irr * fs * 0.028
        shift = (math.cos(sh_ang) * sh_mag, math.sin(sh_ang) * sh_mag)
    else:
        aniso, hal_angle, shift = 1.0, 0.0, (0.0, 0.0)

    sig_mid = max(1.5, fs * 0.14 * math.sqrt(hal))
    sig_wide = max(3.2, fs * 0.34 * hal)
    sig_veil = max(6.5, fs * 0.68 * hal)

    smax_all = max(sig_mid * aniso, sig_wide * aniso, sig_veil * aniso)
    sh_max = abs(shift[0] * 1.6) + abs(shift[1] * 1.6)
    pad = int(math.ceil(3.0 * smax_all + sh_max)) + 2
    padded = np.pad(source, pad, mode="constant")
    ph, pw = padded.shape

    fy = np.fft.fftfreq(ph).astype(np.float32)[:, None]
    fx = np.fft.rfftfreq(pw).astype(np.float32)[None, :]
    th = math.radians(hal_angle)
    u = fx * math.cos(th) + fy * math.sin(th)
    v = -fx * math.sin(th) + fy * math.cos(th)

    def calc_tf(sig: float, sc: float) -> np.ndarray:
        s_maj, s_min = sig * aniso, sig / aniso
        shx, shy = shift[0] * sc, shift[1] * sc
        tf = np.exp(-2.0 * math.pi ** 2 * (s_maj ** 2 * u ** 2 + s_min ** 2 * v ** 2))
        if shx != 0.0 or shy != 0.0:
            tf = tf * np.exp(-2j * math.pi * (fx * shx + fy * shy))
        return tf

    tf_halo = (0.34 * calc_tf(sig_mid, 0.4) + 0.20 * calc_tf(sig_wide, 1.0) + 0.08 * calc_tf(sig_veil, 1.6)) * hal
    out_halo = np.fft.irfft2(np.fft.rfft2(padded) * tf_halo, s=padded.shape)
    halo = np.maximum(out_halo[pad:-pad, pad:-pad], 0.0).astype(np.float32)

    # Step 4: ② Meso ゆらぎ（FBM 雲状変調＋ドメインワープ）
    if irr > 0:
        cloud = fbm_noise(rng_meso, (H, W), max(8.0, fs * 1.4), octaves=2)
        halo = halo * np.clip(1.0 + irr * 0.14 * cloud, 0.55, 1.45)
        wx = fbm_noise(rng_meso, (H, W), max(8.0, fs * 1.2), octaves=2) * (irr * fs * 0.045)
        wy = fbm_noise(rng_meso, (H, W), max(8.0, fs * 1.2), octaves=2) * (irr * fs * 0.045)
        halo = bilinear_warp(halo, wx, wy)

    core_E = (0.88 * hot * raw + 0.55 * psf_core) * core_glow * exposure
    body_E = (0.50 * slit * gain + 0.65 * psf_narrow) * exposure

    # Step 5: ③ Micro ゆらぎ（高露光芯は滑らか、裾野だけ色素雲ちぎれ）
    total = core_E + body_E + halo
    mod = np.ones((H, W), dtype=np.float32)
    fine = rng_micro.standard_normal((H, W)).astype(np.float32)
    clump = value_noise(rng_micro, (H, W), 2.4)
    grain_field = 0.55 * fine + 0.45 * clump
    env = np.clip(total * 2.2, 0.0, 1.0) * np.exp(-core_E * 1.6)
    mod *= 1.0 + 0.18 * grain_field * env
    if irr > 0:
        dye = value_noise(rng_micro, (H, W), 2.0)
        tail = np.exp(-total * 5.5) * np.clip(total * 7.5, 0.0, 1.0)
        mod *= np.clip(1.0 + irr * 0.18 * dye * tail, 0.65, 1.35)

    # Step 6: H&D 分光感光飽和＋芯ブリーチ
    bleach = np.power(np.clip(core_E, 0.0, 2.8), 1.45) * 1.45

    if prism_mode:
        # 角度に応じた連続プリズム分光（虹SSR昇格用）
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        ang_map = np.arctan2(yy - H * 0.5, xx - W * 0.5)
        s_r = 1.85 + 1.45 * np.cos(ang_map)
        s_g = 1.65 + 1.35 * np.cos(ang_map - 2.094)
        s_b = 1.85 + 1.45 * np.cos(ang_map + 2.094)
        E_r = ((core_E + body_E) * s_r + halo * s_r * 0.95 + bleach) * mod
        E_g = ((core_E + body_E) * s_g + halo * s_g * 0.85 + bleach * 0.98) * mod
        E_b = ((core_E + body_E) * s_b + halo * s_b * 0.95 + bleach * 0.96) * mod
        tint = np.array([1.0, 0.99, 1.0], dtype=np.float32)
    else:
        spec = OPTICAL_SPECTRA[spectrum_name]
        s_r, s_g, s_b = spec["sens"]
        k_r, k_g, k_b = spec["scatter"]
        E_r = ((core_E + body_E) * s_r + halo * s_r * k_r * 1.35 + bleach) * mod
        E_g = ((core_E * 1.18 + body_E * 0.88) * s_g + halo * s_g * k_g * 0.85 + bleach * 0.96) * mod
        E_b = ((core_E * 1.45 + body_E * 0.55) * s_b + halo * s_b * k_b * 0.65 + bleach * 0.88) * mod
        tint = np.asarray(spec["tint"], dtype=np.float32)

    E_rgb = np.maximum(np.stack([E_r, E_g, E_b], axis=-1), 0.0)
    light_lin = (1.0 - np.exp(-np.power(E_rgb, 1.15))) * tint[None, None, :]
    light_srgb = linear_to_srgb(light_lin)

    # 透過RGBAへ変換（screen合成でも通常合成でも黒縁が出ない光学アルファ設計）
    return _srgb_to_unpremul_rgba(light_srgb)


def _smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def _srgb_to_unpremul_rgba(light_srgb: np.ndarray) -> Image.Image:
    """sRGB光量配列 (H, W, 3) [0,1] から黒縁の出ない unpremul 透過 RGBA 画像を生成する"""
    alpha = np.clip(np.max(light_srgb, axis=-1), 0.0, 1.0)
    safe_a = np.maximum(alpha, 1e-4)
    rgb_unpremul = np.clip(light_srgb / safe_a[:, :, None], 0.0, 1.0)
    h, w, _ = light_srgb.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, :3] = (rgb_unpremul * 255.0 + 0.5).astype(np.uint8)
    rgba[:, :, 3] = (alpha * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


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
    # 中心芯を少し丸く太らせて白飛びコアを作る
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

    # 擬似ルーン帯（決定論乱数で棒・点・短弧を並べる）
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

    def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
        t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    yy, xx = np.mgrid[0:size_px, 0:size_px].astype(np.float32)
    c = (size_px - 1) * 0.5
    th = np.arctan2(yy - c, xx - c)
    rot = float(rng.uniform(0.0, math.pi))
    dist = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) * (1.0 + 0.035 * np.cos(7.0 * th + rot))

    chans = []
    for k, (ch_tint, r_off) in enumerate(zip(tint, (1.04, 1.0, 0.96))):
        s = radius * r_off
        edge = smoothstep(s + blur * 2.8, s * 0.94, dist) * 0.50
        glow = smoothstep(s + blur * 7.0, s * 0.40, dist) * 0.50
        core = smoothstep(s * 0.50, 0.0, dist) * 0.20
        ring_hi = np.exp(-((dist - s * 0.97) / max(0.8, blur * 0.9)) ** 2) * 0.35
        chans.append((edge + glow + core + ring_hi) * ch_tint)
    light = np.clip(np.stack(chans, axis=-1), 0.0, 1.4)
    light = 1.0 - np.exp(-light * 1.35)
    alpha = np.clip(np.max(light, axis=-1), 0.0, 1.0)
    rgb = np.clip(light / np.maximum(alpha, 1e-4)[..., None], 0.0, 1.0)
    out = np.zeros((size_px, size_px, 4), dtype=np.uint8)
    out[..., :3] = (rgb * 255.0 + 0.5).astype(np.uint8)
    out[..., 3] = (alpha * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


# ==============================================================================
# Phase 2B 物理光学アセット群（クリスタルオーブ / 不規則ゴッドレイ / 縦ストリーク光柱 / 衝撃波 / カットイン）
# ==============================================================================
def _aniso_fbm(
    rng: np.random.Generator,
    h: int,
    w: int,
    cell_y: float,
    cell_x: float,
    octaves: int = 3,
) -> np.ndarray:
    """横高周波・縦低周波の異方性 FBM ノイズ（aurora_claude.hlsl の縦ストリーク用）"""
    acc = np.zeros((h, w), dtype=np.float32)
    amp, total = 1.0, 0.0
    for i in range(octaves):
        cy = max(2.0, cell_y / (2 ** i))
        cx = max(2.0, cell_x / (2 ** i))
        gh = int(math.ceil(h / cy)) + 4
        gw = int(math.ceil(w / cx)) + 4
        grid = rng.standard_normal((gh, gw)).astype(np.float32)
        up_w, up_h = int(math.ceil(gw * cx)), int(math.ceil(gh * cy))
        up = np.asarray(Image.fromarray(grid).resize((up_w, up_h), Image.Resampling.BICUBIC), dtype=np.float32)
        oy = int(cy + rng.random() * cy)
        ox = int(cx + rng.random() * cx)
        acc += up[oy : oy + h, ox : ox + w] * amp
        total += amp
        amp *= 0.5
    acc /= max(1e-6, total)
    std = float(acc.std())
    return (acc / std).astype(np.float32) if std > 1e-6 else np.zeros((h, w), dtype=np.float32)


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
    inside_soft = _smoothstep(1.015, 0.965, r)

    # 手前半球上に 30 個の決定論ファセット中心法線を配置
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

    edge = np.exp(-((d1 - d2) / 0.011) ** 2) * inside_soft
    fresnel = np.power(np.clip(1.0 - nz, 0.0, 1.0), 2.8) * inside_soft

    # 多方向スタジオ反射（単一丸点ハイライトを作らず、ファセット面ごとに鋭く煌めかせる）
    lights = [
        ((-0.48, -0.58, 0.66), 1.05, 28.0),
        ((0.64, 0.42, 0.28),   0.62, 22.0),
        ((-0.68, 0.26, 0.42),  0.46, 20.0),
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
    facet_tone = np.clip(0.14 + 0.72 * np.power(np.clip(diff_total, 0.0, 1.4), 1.35) + 0.26 * phase_map, 0.08, 1.25)

    if style == "blue":
        base_col = np.stack([
            0.05 + 0.26 * facet_tone,
            0.22 + 0.48 * facet_tone,
            0.52 + 0.46 * facet_tone,
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
        # 薄膜干渉：ファセット法線角度＋ファセット固有位相からダイヤモンドのファイア風の多色分散を生成
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
    shell_edge = edge_col * edge[..., None] * 0.95
    shell_rim = rim_col * (fresnel[..., None] * 1.25)
    shell_spec = np.array([1.0, 0.99, 0.96], dtype=np.float32)[None, None, :] * (spec_total * inside_soft)[..., None] * 0.90

    shell_lin = shell_body + shell_edge + shell_rim + shell_spec
    # 球外縁と稜線の物理 FFT ハレーション（黒縁なし、端は 0 へフェード）
    outer_fade = 1.0 - _smoothstep(1.16, 1.44, r)
    halo_src = np.stack([
        fft_gaussian_blur(shell_lin[..., k], size * 0.022) * 0.42
        + fft_gaussian_blur(shell_lin[..., k], size * 0.055) * 0.24
        for k in range(3)
    ], axis=-1) * outer_fade[..., None]
    shell_lin = shell_lin * inside_soft[..., None] + halo_src * (1.0 - inside_soft[..., None] * 0.55)
    shell_srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(shell_lin, 0.0) * 1.25))
    shell_img = _srgb_to_unpremul_rgba(shell_srgb)

    # 2. 内部エネルギー渦＋結晶屈折ライン（facet 層：球内 0.88 以内に収める）
    inner_m = 1.0 - _smoothstep(0.52, 0.88, r)
    th = np.arctan2(ny, nx)
    swirl = np.power(0.5 + 0.5 * np.sin(th * 5.0 + r * 7.5 + float(rng.uniform(0.0, math.tau))), 2.6)
    rays = np.power(0.5 + 0.5 * np.sin(th * 9.0 - r * 4.0 + 1.2), 5.0)
    plasma = np.clip(0.5 + 0.35 * fbm_noise(rng, (size, size), size * 0.16, octaves=2), 0.0, 1.0)
    energy = (0.55 * swirl * plasma + 0.50 * rays) * inner_m

    if style == "blue":
        f_col = np.stack([0.38 * energy, 0.78 * energy, 1.25 * energy], axis=-1)
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
    facet_img = _srgb_to_unpremul_rgba(facet_srgb)
    return shell_img, facet_img


def render_orb_core_bleach(size: int = 512) -> Image.Image:
    """多層クリスタルオーブ中心用の白飛びエネルギー核 PNG"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) * 0.5
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (size * 0.34)
    core = np.exp(-((r / 0.21) ** 2)) * 1.85 + np.exp(-((r / 0.42) ** 2)) * 0.45
    core *= 1.0 - _smoothstep(0.65, 0.98, r)
    lin = np.stack([core * 1.00, core * 0.98, core * 0.94], axis=-1)
    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.45))
    return _srgb_to_unpremul_rgba(srgb)


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
    r_mask = _smoothstep(0.03, 0.16, rad) * (1.0 - _smoothstep(0.50, 0.96, rad))

    nums = (13, 19, 29) if variant == "a" else (11, 17, 23)
    weights = (0.48, 0.36, 0.28) if variant == "a" else (0.42, 0.38, 0.30)
    total_beam = np.zeros((size, size), dtype=np.float32)
    total_needle = np.zeros((size, size), dtype=np.float32)

    if mode == "prism":
        layer_colors = [
            np.array([0.46, 0.84, 0.96], dtype=np.float32),  # cyan
            np.array([0.94, 0.55, 0.72], dtype=np.float32),  # rose
            np.array([0.96, 0.86, 0.58], dtype=np.float32),  # champagne
        ]
    else:
        layer_colors = [
            np.array([0.96, 0.86, 0.62], dtype=np.float32),  # champagne gold
            np.array([0.92, 0.66, 0.76], dtype=np.float32),  # subtle rose tint
            np.array([0.58, 0.84, 0.94], dtype=np.float32),  # subtle aqua tint
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
        total_beam += lzr * w_l
        total_needle += needle * w_l

    cloud_mod = np.clip(0.68 + 0.32 * fbm_noise(rng, (size, size), size * 0.14, octaves=2), 0.35, 1.30)
    col_acc = (col_acc + total_needle[..., None] * np.array([1.0, 0.99, 0.96], dtype=np.float32)) * (cloud_mod * r_mask)[..., None]
    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(col_acc, 0.0) * 1.15))
    return _srgb_to_unpremul_rgba(srgb)


def render_light_pillar(style: str, w: int = 512, h: int = 1680, seed: int = 0) -> Image.Image:
    """
    aurora_claude.hlsl の縦ストリーク数式を移植した光柱 2 層光学 PNG を生成する。
    細白芯＋縦ノイズ筋＋上下完全フェードで灰色縦帯感を完全に排除する。
    """
    rng = np.random.default_rng((seed * 65537 + (7 if style == "gold" else 29)) & 0xFFFFFFFF)
    u = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    v = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]

    rays_a = _smoothstep(0.32, 0.90, 0.5 + 0.25 * _aniso_fbm(rng, h, w, cell_y=150.0, cell_x=11.0, octaves=3))
    rays_b = _smoothstep(0.46, 0.94, 0.5 + 0.25 * _aniso_fbm(rng, h, w, cell_y=92.0, cell_x=5.5, octaves=2))
    ray_mix = rays_a * 0.72 + rays_b * 0.45

    v_env = _smoothstep(0.01, 0.24, v) * (1.0 - _smoothstep(0.74, 0.99, v))
    v_core = _smoothstep(0.06, 0.30, v) * (1.0 - _smoothstep(0.68, 0.94, v))
    h_fade = 1.0 - _smoothstep(0.66, 0.96, np.abs(u))

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
        # 横位置とストリークノイズに応じたオーロラ分光
        hue_t = u * 2.2 + (rays_a - 0.5) * 1.4
        aurora_col = np.stack([
            0.62 + 0.38 * np.cos(hue_t + 0.5),
            0.54 + 0.36 * np.cos(hue_t - 1.6),
            0.68 + 0.32 * np.cos(hue_t + 2.4),
        ], axis=-1)
        lin = core_int[..., None] * np.array([1.0, 0.99, 1.0], dtype=np.float32) + streak_int[..., None] * aurora_col

    srgb = linear_to_srgb(1.0 - np.exp(-np.maximum(lin, 0.0) * 1.25))
    return _srgb_to_unpremul_rgba(srgb)


def render_shockwave_ring(style: str, size: int = 640, seed: int = 0) -> Image.Image:
    """内縁シャープ・外縁へ滲む非対称光学衝撃波リング＋微細飛散光粒 PNG"""
    rng = np.random.default_rng((seed * 31337 + (11 if style == "gold" else 43)) & 0xFFFFFFFF)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) * 0.5
    r_base = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    th = np.arctan2(yy - c, xx - c)

    wobble = 0.014 * np.sin(th * 5.0 + 0.4) + 0.009 * np.cos(th * 9.0 - 1.1)
    r = r_base + wobble
    edge_fade = 1.0 - _smoothstep(0.76, 0.96, r_base)

    # 非対称リングプロファイル（内縁 0.54 で急に立ち上がり、外縁へなだらかに滲む）
    R0 = 0.54
    chans = []
    offsets = (1.016, 1.000, 0.984)
    if style == "gold":
        tints = (1.00, 0.84, 0.46)
    else:
        tints = None

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
    # 外縁に飛散する微細光粒ドット
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
    return _srgb_to_unpremul_rgba(srgb)


def render_cutin_assets(seed: int = 0) -> Tuple[Image.Image, Image.Image]:
    """脱ベタ帯カットイン用の水平アナモルフィックフレア(1080x360)とスピードライン(1080x420)を生成"""
    rng = np.random.default_rng((seed * 99991 + 17) & 0xFFFFFFFF)

    # 1. opt_cutin_flare.png (1080x360)
    fw, fh = 1080, 360
    yy, xx = np.mgrid[0:fh, 0:fw].astype(np.float32)
    nx = (xx - (fw - 1) * 0.5) / ((fw - 1) * 0.5)
    ny = (yy - (fh - 1) * 0.5) / ((fh - 1) * 0.5)
    edge_fade = (1.0 - _smoothstep(0.76, 0.98, np.abs(nx))) * (1.0 - _smoothstep(0.60, 0.96, np.abs(ny)))

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
    flare_img = _srgb_to_unpremul_rgba(linear_to_srgb(1.0 - np.exp(-np.maximum(lin_flare, 0.0) * 1.3)))

    # 2. opt_cutin_speedlines.png (1080x420)
    sw, sh = 1080, 420
    sl = np.zeros((sh, sw, 3), dtype=np.float32)
    y_grid, x_grid = np.mgrid[0:sh, 0:sw].astype(np.float32)
    v_fade = _smoothstep(0.04, 0.28, y_grid / sh) * (1.0 - _smoothstep(0.72, 0.96, y_grid / sh))
    h_fade = 1.0 - _smoothstep(0.80, 0.98, np.abs((x_grid - sw * 0.5) / (sw * 0.5)))

    palette = [
        np.array([1.00, 0.96, 0.84], dtype=np.float32),
        np.array([0.52, 0.88, 1.00], dtype=np.float32),
        np.array([0.96, 0.58, 0.78], dtype=np.float32),
    ]
    for i in range(44):
        yc = float(rng.uniform(28, sh - 28))
        xc = float(rng.uniform(140, sw - 140))
        half_len = float(rng.uniform(90, 420))
        thick = float(rng.uniform(0.8, 2.2))
        amp = float(rng.uniform(0.30, 0.95))
        line_y = np.exp(-((y_grid - yc) / thick) ** 2)
        line_x = np.maximum(0.0, 1.0 - np.abs(x_grid - xc) / half_len) ** 1.6
        col = palette[i % len(palette)]
        sl += (line_y * line_x * amp)[..., None] * col[None, None, :]

    sl *= (v_fade * h_fade)[..., None]
    speed_img = _srgb_to_unpremul_rgba(linear_to_srgb(1.0 - np.exp(-np.maximum(sl, 0.0) * 1.2)))
    return flare_img, speed_img


def main() -> None:
    cfg = load_card_config()
    opt_cfg = cfg.get("optics", {})
    hal = float(opt_cfg.get("halation", 1.05))
    cg = float(opt_cfg.get("coreGlow", 1.15))
    irr = float(opt_cfg.get("irregularity", 0.85))
    seed = resolve_seed(cfg, section="optics")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 魔法陣 3色 × 3層（1024px 精密階層化）
    m_outer, m_mid, m_inner = build_magic_circle_masks(1024, seed=seed + 77)
    rings = [("outer", m_outer), ("mid", m_mid), ("inner", m_inner)]
    mc_styles = [
        ("blue",    "summon_blue", False, 1.02, hal * 0.95),
        ("gold",    "summon_gold", False, 1.12, hal * 1.10),
        ("rainbow", "summon_gold", True,  1.22, hal * 1.25),
    ]
    for s_idx, (cname, spec, is_prism, exp, h_val) in enumerate(mc_styles):
        for r_idx, (rname, mask) in enumerate(rings):
            img = render_optical_glow(
                mask_l=mask,
                spectrum_name=spec,
                ref_scale=20.0,
                exposure=exp,
                core_glow=cg,
                halation=h_val,
                irregularity=irr,
                prism_mode=is_prism,
                seed=seed + s_idx * 100 + r_idx * 17,
            )
            fname = f"opt_mc_{cname}_{rname}.png"
            img.save(OUT_DIR / fname, format="PNG", optimize=True)
            print(f"[OK] {fname} ({img.width}x{img.height})")

    # 2. オーブ臨界亀裂（有機分岐・テーパー付き 512px）
    cracks_mask = build_orb_cracks_mask(512, seed=seed + 501)
    cracks_img = render_optical_glow(
        mask_l=cracks_mask,
        spectrum_name="summon_gold",
        ref_scale=20.0,
        exposure=1.32,
        core_glow=cg * 1.20,
        halation=hal * 1.20,
        irregularity=irr,
        prism_mode=True,
        seed=seed + 501,
    )
    cracks_img.save(OUT_DIR / "opt_orb_cracks.png", format="PNG", optimize=True)
    print(f"[OK] opt_orb_cracks.png ({cracks_img.width}x{cracks_img.height})")

    # 3. 多面体クリスタルオーブ（3色 × shell/facet + 共通コア）
    for i, cname in enumerate(("blue", "gold", "rainbow")):
        sh_img, fc_img = render_crystal_orb_layers(cname, size=512, seed=seed + 2101 + i * 37)
        sh_img.save(OUT_DIR / f"opt_orb_{cname}_shell.png", format="PNG", optimize=True)
        fc_img.save(OUT_DIR / f"opt_orb_{cname}_facet.png", format="PNG", optimize=True)
        print(f"[OK] opt_orb_{cname}_{{shell,facet}}.png (512x512)")
    core_img = render_orb_core_bleach(size=512)
    core_img.save(OUT_DIR / "opt_orb_core_bleach.png", format="PNG", optimize=True)
    print("[OK] opt_orb_core_bleach.png (512x512)")

    # 4. 不規則ゴッドレイ 2層（虹昇格用 & リザルト用）
    for mode in ("prism", "gold"):
        for var in ("a", "b"):
            gr_img = render_godrays_layer(mode=mode, variant=var, size=1200, seed=seed + 2301)
            fname = f"opt_godrays_{mode}_{var}.png"
            gr_img.save(OUT_DIR / fname, format="PNG", optimize=True)
            print(f"[OK] {fname} ({gr_img.width}x{gr_img.height})")

    # 5. 縦ストリーク光柱 2層 & 光学衝撃波リング & カットイン光学素材
    for style in ("gold", "rainbow"):
        pl_img = render_light_pillar(style=style, w=512, h=1680, seed=seed + 2501)
        pl_img.save(OUT_DIR / f"opt_pillar_{style}.png", format="PNG", optimize=True)
        print(f"[OK] opt_pillar_{style}.png ({pl_img.width}x{pl_img.height})")
        sw_img = render_shockwave_ring(style=style, size=640, seed=seed + 2701)
        sw_img.save(OUT_DIR / f"opt_shock_{style}.png", format="PNG", optimize=True)
        print(f"[OK] opt_shock_{style}.png ({sw_img.width}x{sw_img.height})")

    flare_img, speed_img = render_cutin_assets(seed=seed + 2901)
    flare_img.save(OUT_DIR / "opt_cutin_flare.png", format="PNG", optimize=True)
    speed_img.save(OUT_DIR / "opt_cutin_speedlines.png", format="PNG", optimize=True)
    print("[OK] opt_cutin_flare.png (1080x360) & opt_cutin_speedlines.png (1080x420)")

    # 6. リザルト星5つ
    star_mask = build_star_mask(144)
    star_img = render_optical_glow(
        mask_l=star_mask,
        spectrum_name="star_gold",
        ref_scale=18.0,
        exposure=1.18,
        core_glow=cg * 1.10,
        halation=hal * 0.95,
        irregularity=irr * 0.65,
        prism_mode=False,
        seed=seed + 701,
    )
    star_img.save(OUT_DIR / "opt_star_gold.png", format="PNG", optimize=True)
    print(f"[OK] opt_star_gold.png ({star_img.width}x{star_img.height})")

    # 7. 周囲スパークル 4色
    sp_mask = build_sparkle_mask(128)
    for i, (cname, spec) in enumerate([
        ("gold",  "sparkle_gold"),
        ("white", "sparkle_white"),
        ("pink",  "sparkle_pink"),
        ("cyan",  "sparkle_cyan"),
    ]):
        sp_img = render_optical_glow(
            mask_l=sp_mask,
            spectrum_name=spec,
            ref_scale=16.0,
            exposure=1.15,
            core_glow=cg * 1.15,
            halation=hal * 1.05,
            irregularity=irr * 0.70,
            prism_mode=False,
            seed=seed + 901 + i * 31,
        )
        fname = f"opt_sparkle_{cname}.png"
        sp_img.save(OUT_DIR / fname, format="PNG", optimize=True)
        print(f"[OK] {fname} ({sp_img.width}x{sp_img.height})")

    # 8. リザルト背景の光学魔法リング
    ring_mask = build_result_ring_mask(1400, seed=seed + 1201)
    ring_img = render_optical_glow(
        mask_l=ring_mask,
        spectrum_name="summon_gold",
        ref_scale=14.0,
        exposure=0.95,
        core_glow=cg,
        halation=hal * 1.15,
        irregularity=irr,
        prism_mode=False,
        seed=seed + 1201,
    )
    ring_img.save(OUT_DIR / "opt_result_ring.png", format="PNG", optimize=True)
    print(f"[OK] opt_result_ring.png ({ring_img.width}x{ring_img.height})")

    # 9. 玉ボケ光粒（遠景=シャープ / 近景=大ボケ）× 4色
    bokeh_tints = {
        "gold": (1.00, 0.84, 0.52),
        "rose": (1.00, 0.62, 0.78),
        "aqua": (0.55, 0.88, 1.00),
        "white": (1.00, 0.97, 0.92),
    }
    for i, (cname, tint) in enumerate(bokeh_tints.items()):
        for depth, blur in (("far", 1.6), ("near", 9.0)):
            bk = render_bokeh_sprite(tint, size_px=160, radius=44.0 if depth == "far" else 40.0, blur=blur, seed=seed + 1301 + i)
            fname = f"opt_bokeh_{cname}_{depth}.png"
            bk.save(OUT_DIR / fname, format="PNG", optimize=True)
    print("[OK] opt_bokeh_{gold,rose,aqua,white}_{far,near}.png (160x160)")


if __name__ == "__main__":
    main()
