"""
SSRGenerate — 物理光学発光コアモジュール（FilmDateStamp H&D 分光モデル拡張）

- 物理分光スペクトル定義 (`OPTICAL_SPECTRA`)
- FFT ガウスぼかし (`fft_gaussian_blur`)
- 高速ユークリッド内部距離変換 (`approx_inner_distance`)
- バリューノイズ・等方/異方 FBM ノイズ・ドメインワープ (`value_noise`, `fbm_noise`, `aniso_fbm`, `bilinear_warp`)
- 6段階物理光学発光パイプライン (`render_optical_glow`)
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from _utils import linear_to_srgb, srgb_to_unpremul_rgba

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
# FilmDateStamp 由来 物理光学コア関数群（NumPy + SciPy + Pillow）
# ==============================================================================
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
    """C実装のユークリッド距離変換（scipy.ndimage.distance_transform_edt）による高速発光尾根抽出"""
    if not binary.any():
        return np.zeros(binary.shape, dtype=np.float32)
    dist = distance_transform_edt(binary)
    return np.minimum(dist, float(max_iter)).astype(np.float32)


def value_noise(rng: np.random.Generator, shape: Tuple[int, int], cell: float) -> np.ndarray:
    h, w = shape
    cell = max(1.0, float(cell))
    gh = int(math.ceil(h / cell)) + 4
    gw = int(math.ceil(w / cell)) + 4
    grid = rng.standard_normal((gh, gw)).astype(np.float32)
    up_w, up_h = int(math.ceil(gw * cell)), int(math.ceil(gh * cell))
    up = np.asarray(Image.fromarray(grid).resize((up_w, up_h), Image.Resampling.BICUBIC), dtype=np.float32)
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


def aniso_fbm(
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


def prepare_optical_mask(
    mask_l: Image.Image,
    ref_scale: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Step 1（距離変換尾根 ridge ＆ スリットぼかし slit）を事前計算する。
    同一マスクを複数色（blue/gold/rainbow）で使い回す際の重複計算を回避する。
    """
    raw = np.asarray(mask_l, dtype=np.float32) / 255.0
    fs = float(ref_scale)
    inside = raw > 0.28
    dist = approx_inner_distance(inside, max_iter=36)
    dist = fft_gaussian_blur(dist, max(0.4, fs * 0.014)) * inside
    dmax = max(1.0, float(np.percentile(dist[inside], 92))) if inside.any() else 1.0
    ridge = np.power(np.clip(dist / dmax, 0.0, 1.25), 1.10)
    slit = fft_gaussian_blur(raw, max(0.35, fs * 0.022))
    return raw, ridge, slit


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
    prepared: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None,
) -> Image.Image:
    """
    任意のグレースケール発光マスクに対し、FilmDateStamp の6段階物理光学モデルを適用して
    透過 RGBA 画像を生成する。
    """
    fs = float(ref_scale)
    irr = max(0.0, float(irregularity))
    hal = max(0.05, float(halation))

    rng_macro = np.random.default_rng([seed & 0xFFFFFFFF, 11])
    rng_meso = np.random.default_rng([seed & 0xFFFFFFFF, 22])
    rng_micro = np.random.default_rng([seed & 0xFFFFFFFF, 33])

    # Step 1: 距離変換尾根（発光芯）
    if prepared is not None:
        raw, ridge, slit = prepared
    else:
        raw, ridge, slit = prepare_optical_mask(mask_l, fs)
    H, W = raw.shape

    # Step 2: ① Macro ゆらぎ（素子個体差＋微光量勾配）
    if irr > 0:
        n_macro = value_noise(rng_macro, (H, W), max(8.0, fs * 1.4))
        ang = rng_macro.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        lens = math.cos(ang) * (xx - W / 2) / max(1.0, W / 2) + math.sin(ang) * (yy - H / 2) / max(1.0, H / 2)
        gain = np.clip(1.0 + irr * (0.10 * n_macro + 0.06 * lens), 0.65, 1.38)
    else:
        gain = np.ones((H, W), dtype=np.float32)

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
    return srgb_to_unpremul_rgba(light_srgb)
