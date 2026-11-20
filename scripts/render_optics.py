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
    alpha = np.clip(np.max(light_srgb, axis=-1), 0.0, 1.0)
    safe_a = np.maximum(alpha, 1e-4)
    rgb_unpremul = np.clip(light_srgb / safe_a[:, :, None], 0.0, 1.0)

    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[:, :, :3] = (rgb_unpremul * 255.0 + 0.5).astype(np.uint8)
    rgba[:, :, 3] = (alpha * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


# ==============================================================================
# ジオメトリマスク描画（魔法陣3層 / オーブ亀裂 / 星5つ / スパークル）
# ==============================================================================
def draw_dashed_circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, width: int, n_dashes: int = 48) -> None:
    step = 360.0 / n_dashes
    for i in range(n_dashes):
        a0 = i * step
        a1 = a0 + step * 0.56
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(bbox, start=a0, end=a1, fill=215, width=width)


def build_magic_circle_masks(size: int = 900) -> Tuple[Image.Image, Image.Image, Image.Image]:
    """外周・中段・内周の3層魔法陣マスク（2xスーパーサンプリング描画でアンチエイリアス確保）"""
    ss = 2
    S = size * ss
    c = S / 2.0
    sc = S / 800.0

    # 1. Outer Ring
    m_out = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_out)
    for r, w, val in [(372, 6, 255), (312, 4, 210)]:
        rr = r * sc
        d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=val, width=max(2, int(round(w * sc))))
    draw_dashed_circle(d, c, c, 348 * sc, width=max(2, int(round(3 * sc))), n_dashes=56)

    # 2. Mid Polygons
    m_mid = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_mid)

    def poly_pts(n: int, r: float, rot_deg: float) -> List[Tuple[float, float]]:
        pts = []
        for i in range(n):
            a = math.radians(rot_deg + i * (360.0 / n))
            pts.append((c + math.cos(a) * r * sc, c + math.sin(a) * r * sc))
        return pts

    for pts, w, val in [
        (poly_pts(6, 334, -90), 5, 240),
        (poly_pts(8, 334, -90), 3, 185),
        (poly_pts(3, 285, -90), 4.5, 255),
        (poly_pts(3, 285, 90), 4.5, 255),
    ]:
        d.polygon(pts, outline=val, width=max(2, int(round(w * sc))))

    # 3. Inner Ring
    m_in = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m_in)
    rr = 215 * sc
    d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=255, width=max(2, int(round(5.5 * sc))))
    draw_dashed_circle(d, c, c, 192 * sc, width=max(2, int(round(2.5 * sc))), n_dashes=40)

    return (
        m_out.resize((size, size), Image.Resampling.LANCZOS),
        m_mid.resize((size, size), Image.Resampling.LANCZOS),
        m_in.resize((size, size), Image.Resampling.LANCZOS),
    )


def build_orb_cracks_mask(size: int = 440) -> Image.Image:
    ss = 2
    S = size * ss
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    paths = [
        ([(220, 220), (165, 130), (120, 95)], 7, 255),
        ([(220, 220), (295, 145), (355, 110)], 7, 255),
        ([(220, 220), (315, 265), (380, 315)], 7, 255),
        ([(220, 220), (145, 300), (90, 365)], 7, 255),
        ([(220, 220), (232, 98), (248, 45)], 6, 240),
        ([(220, 220), (92, 210), (35, 190)], 6, 240),
        ([(165, 130), (195, 102)], 4.5, 210),
        ([(295, 145), (285, 95)], 4.5, 210),
        ([(315, 265), (350, 232)], 4.5, 210),
        ([(145, 300), (185, 352)], 4.5, 210),
    ]
    for pts, w, val in paths:
        spts = [(x * ss, y * ss) for x, y in pts]
        d.line(spts, fill=val, width=max(2, int(round(w * ss))), joint="curve")
    # 中心コアホットスポット
    d.ellipse([206 * ss, 206 * ss, 234 * ss, 234 * ss], fill=255)
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


def main() -> None:
    cfg = load_card_config()
    opt_cfg = cfg.get("optics", {})
    hal = float(opt_cfg.get("halation", 1.05))
    cg = float(opt_cfg.get("coreGlow", 1.15))
    irr = float(opt_cfg.get("irregularity", 0.85))
    seed = resolve_seed(cfg, section="optics")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 魔法陣 3色 × 3層
    m_outer, m_mid, m_inner = build_magic_circle_masks(900)
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
                ref_scale=28.0,
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

    # 2. オーブ臨界亀裂
    cracks_mask = build_orb_cracks_mask(440)
    cracks_img = render_optical_glow(
        mask_l=cracks_mask,
        spectrum_name="summon_gold",
        ref_scale=24.0,
        exposure=1.28,
        core_glow=cg * 1.15,
        halation=hal * 1.20,
        irregularity=irr,
        prism_mode=True,
        seed=seed + 501,
    )
    cracks_img.save(OUT_DIR / "opt_orb_cracks.png", format="PNG", optimize=True)
    print(f"[OK] opt_orb_cracks.png ({cracks_img.width}x{cracks_img.height})")

    # 3. リザルト星5つ
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

    # 4. 周囲スパークル 4色
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

    # 5. リザルト背景の光学魔法リング
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

    # 6. 玉ボケ光粒（遠景=シャープ / 近景=大ボケ）× 4色
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
