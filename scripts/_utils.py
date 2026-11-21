"""
SSRGenerate — アセット生成スクリプト共通ユーティリティ

- card-config.js の読み込み (`load_card_config`)
- 決定論的シード解決 (`resolve_seed`)
- スカラー補間・色変換・合成ヘルパー (`smoothstep`, `linear_to_srgb`, `srgb_to_unpremul_rgba`, `porter_duff_over`, `tight_crop_rgba`)
- 斜め多段ストップ・リニアグラデーション生成 (`make_linear_gradient`)
- 多周波微細シボ高さマップ生成 (`generate_micro_emboss_height`)
- 標準偏差正規化 (`norm_std`)
- カード物理寸法・金属パレット定数 (`CARD_*`, `GOLD_RAMP`, `SILVER_RAMP`)
- 金属レリーフ陰影（法線勾配ランバート＋ブリン・フォン）(`shade_metal_relief`)
- 高速PNG保存ヘルパー (`save_png`)
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OUT_DIR = ASSETS_DIR / "generated"
CONFIG_PATH = PROJECT_ROOT / "card-config.js"
DEFAULT_SEED = 20261120

# リザルトカードの物理寸法（compositions/shared-base.css の --card-w / --card-h / --card-border と一致させること）
CARD_W = 900
CARD_H = 1590
CARD_BORDER = 20
CARD_OUTER_R = 40
CARD_INNER_R = 24
CARD_INNER_W = CARD_W - CARD_BORDER * 2
CARD_INNER_H = CARD_H - CARD_BORDER * 2

# 金属パレット（白 → シャンパン → 琥珀 → 暗褐の明暗階調）
GOLD_RAMP: List[Tuple[int, int, int]] = [
    (58, 34, 14),     # 暗褐
    (140, 88, 30),    # 琥珀影
    (212, 162, 76),   # 琥珀
    (242, 223, 179),  # シャンパン
    (255, 253, 245),  # 白金
]
SILVER_RAMP: List[Tuple[int, int, int]] = [
    (36, 40, 52),
    (104, 112, 132),
    (178, 186, 204),
    (226, 232, 242),
    (255, 255, 255),
]


def load_card_config() -> Dict[str, Any]:
    """card-config.js から window.SSR_CARD_CONFIG を読み込む"""
    if CONFIG_PATH.exists():
        try:
            res = subprocess.run(
                [
                    "node",
                    "-e",
                    (
                        "const fs=require('fs');"
                        "const window={};"
                        "eval(fs.readFileSync(process.argv[1],'utf8'));"
                        "process.stdout.write(JSON.stringify(window.SSR_CARD_CONFIG||{}));"
                    ),
                    str(CONFIG_PATH),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            return json.loads(res.stdout)
        except Exception:
            pass
    return {}


def resolve_seed(cfg: Dict[str, Any], section: str | None = None, override: int | None = None) -> int:
    """セクション固有シード → ルートシード → デフォルトシードの順で決定論シードを解決する"""
    if override is not None:
        return int(override)
    if section and isinstance(cfg.get(section), dict):
        sec_seed = cfg[section].get("seed")
        if sec_seed is not None:
            return int(sec_seed)
    return int(cfg.get("seed", DEFAULT_SEED))


def save_png(img: Image.Image, path: Path, compress_level: int = 6) -> None:
    """総当たりフィルタ探索(optimize=True)を避け、バランスの良い圧縮レベルで高速にPNG保存する"""
    img.save(path, format="PNG", compress_level=compress_level)


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    """エルミート3次補間 smoothstep"""
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """リニアRGB [0, 1] から sRGB [0, 1] へのガンマ変換"""
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


def srgb_to_unpremul_rgba(light_srgb: np.ndarray) -> Image.Image:
    """sRGB発光配列 (H, W, 3) [0,1] から黒縁の出ない unpremul 透過 RGBA 画像を生成する"""
    alpha = np.clip(np.max(light_srgb, axis=-1), 0.0, 1.0)
    safe_a = np.maximum(alpha, 1e-4)
    rgb_unpremul = np.clip(light_srgb / safe_a[:, :, None], 0.0, 1.0)
    return rgba_from_float(rgb_unpremul, alpha)


def porter_duff_over(
    fg_rgb: np.ndarray,
    fg_a: np.ndarray,
    bg_rgb: np.ndarray,
    bg_a: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Porter-Duff Over 合成: 前景 (fg_rgb, fg_a) を 背景 (bg_rgb, bg_a) の上に重ねる"""
    a = fg_a + bg_a * (1.0 - fg_a)
    rgb = (fg_rgb * fg_a[..., None] + bg_rgb * (bg_a * (1.0 - fg_a))[..., None]) / np.maximum(a, 1e-5)[..., None]
    return np.clip(rgb, 0.0, 1.0), np.clip(a, 0.0, 1.0)


def tight_crop_rgba(rgb: np.ndarray, a: np.ndarray, alpha_threshold: float = 0.012) -> Image.Image:
    """アルファ値閾値を超える実インク領域の外接矩形でタイトクロップした RGBA Image を返す"""
    ys, xs = np.where(a > alpha_threshold)
    if len(ys) > 0:
        y0, y1 = max(0, int(ys.min()) - 1), min(a.shape[0], int(ys.max()) + 2)
        x0, x1 = max(0, int(xs.min()) - 1), min(a.shape[1], int(xs.max()) + 2)
        rgb, a = rgb[y0:y1, x0:x1], a[y0:y1, x0:x1]
    return rgba_from_float(rgb, a)


def norm_std(arr: np.ndarray) -> np.ndarray:
    """配列を平均0・標準偏差1に正規化する"""
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    if std < 1e-6:
        return arr - mean
    return (arr - mean) / std


def make_linear_gradient(
    h: int,
    w: int,
    stops: List[Tuple[int, int, int]],
    angle_deg: float = 135.0,
) -> np.ndarray:
    """多段ストップの斜めリニアグラデーション画像 (H, W, 3) float32 [0, 1] を生成する"""
    n_stops = len(stops)
    if n_stops == 1:
        arr = np.zeros((h, w, 3), dtype=np.float32)
        arr[:, :] = np.array(stops[0], dtype=np.float32) / 255.0
        return arr

    th = math.radians(angle_deg)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = xx / max(1.0, float(w - 1)) - 0.5
    ny = yy / max(1.0, float(h - 1)) - 0.5
    proj = nx * math.cos(th) + ny * math.sin(th)
    pmin, pmax = float(proj.min()), float(proj.max())
    t = (proj - pmin) / max(1e-6, pmax - pmin)

    scaled = np.clip(t * (n_stops - 1), 0.0, float(n_stops - 1) - 1e-6)
    idx = scaled.astype(np.int32)
    frac = (scaled - idx)[:, :, None]
    stops_arr = np.array(stops, dtype=np.float32) / 255.0
    c0 = stops_arr[idx]
    c1 = stops_arr[np.minimum(idx + 1, n_stops - 1)]
    return c0 * (1.0 - frac) + c1 * frac


def generate_micro_emboss_height(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    """軽量多周波微細シボ高さマップ（平均0・標準偏差1）を生成する"""
    hs1, ws1 = max(8, int(h * 0.65)), max(8, int(w * 0.65))
    n1 = rng.standard_normal((hs1, ws1)).astype(np.float32)
    a1 = np.array(
        Image.fromarray(np.clip((n1 / 5.5 + 0.5) * 255.0, 0, 255).astype(np.uint8), "L").resize(
            (w, h), Image.Resampling.BILINEAR
        ),
        dtype=np.float32,
    )
    hs2, ws2 = max(6, int(h * 0.35)), max(6, int(w * 0.35))
    n2 = rng.standard_normal((hs2, ws2)).astype(np.float32)
    a2 = np.array(
        Image.fromarray(np.clip((n2 / 5.5 + 0.5) * 255.0, 0, 255).astype(np.uint8), "L").resize(
            (w, h), Image.Resampling.BICUBIC
        ),
        dtype=np.float32,
    )
    return norm_std(a1 * 0.6 + a2 * 0.4)


def gaussian_blur_f(arr: np.ndarray, sigma: float) -> np.ndarray:
    """float32 配列へのガウスぼかし（scipy.ndimage）"""
    if sigma <= 0.05:
        return arr.astype(np.float32, copy=True)
    return gaussian_filter(arr.astype(np.float32), sigma=sigma, mode="constant").astype(np.float32)


def ramp_lookup(t: np.ndarray, ramp: List[Tuple[int, int, int]]) -> np.ndarray:
    """0..1 のスカラー場を多段カラーランプで RGB (H, W, 3) float32 へ写像する"""
    stops = np.array(ramp, dtype=np.float32) / 255.0
    n = len(stops)
    scaled = np.clip(t, 0.0, 1.0) * (n - 1)
    idx = np.clip(scaled.astype(np.int32), 0, n - 2)
    frac = (scaled - idx)[..., None]
    return stops[idx] * (1.0 - frac) + stops[idx + 1] * frac


def polygon_mask(w: int, h: int, pts: List[Tuple[float, float]], ss: int = 3) -> np.ndarray:
    """スーパーサンプリング付きの多角形マスク [0, 1] (H, W) float32"""
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


def shade_metal_relief(
    mask: np.ndarray,
    ramp: List[Tuple[int, int, int]] = GOLD_RAMP,
    bevel_px: float = 2.2,
    depth: float = 6.0,
    light_deg: float = -130.0,
    shininess: float = 28.0,
    tone: float = 0.62,
    tone_map: np.ndarray | None = None,
) -> np.ndarray:
    """
    マスクを高さ場とみなし、法線勾配からランバート拡散＋ブリン・フォン鏡面を計算して
    金属レリーフ（面取り・押し出し感）の RGB (H, W, 3) float32 を返す。
    tone: 平坦部の明度位置（ランプ上の 0..1）。tone_map を渡すと画素ごとに上書きする。
    """
    hgt = gaussian_blur_f(np.clip(mask, 0.0, 1.0), bevel_px)
    gy, gx = np.gradient(hgt * depth)
    nz = np.ones_like(hgt)
    norm = np.sqrt(gx * gx + gy * gy + nz)
    nx, ny, nz = -gx / norm, -gy / norm, nz / norm

    la = math.radians(light_deg)
    lx, ly, lz = math.cos(la) * 0.62, math.sin(la) * 0.62, 0.78
    ll = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ll, ly / ll, lz / ll
    hx, hy, hz = lx, ly, lz + 1.0
    hl = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / hl, hy / hl, hz / hl

    diffuse = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
    spec = np.power(np.clip(nx * hx + ny * hy + nz * hz, 0.0, 1.0), shininess)
    flat_d = lz
    base_t = tone_map if tone_map is not None else np.full_like(hgt, tone)
    t = np.clip(base_t + (diffuse - flat_d) * 1.35, 0.0, 1.0)
    rgb = ramp_lookup(t, ramp)
    return np.clip(rgb + spec[..., None] * 0.85, 0.0, 1.0).astype(np.float32)


def rgba_from_float(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    """float RGB [0,1] と alpha [0,1] から RGBA Image を生成する"""
    h, w = alpha.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    out[..., 3] = (np.clip(alpha, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def generate_film_grain_overlay(
    w: int = 540,
    h: int = 960,
    sigma: float = 14.0,
    seed: int = DEFAULT_SEED,
) -> Image.Image:
    """
    暗部バンディング解消用の決定論的フィルムグレイン（中性グレー128中心のグレースケール画像）を生成する。
    高周波の微細粒子とわずかな中周波シボをブレンドし、overlay/soft-light 合成で自然な階調補間を行う。
    540x960（1/4画素数）で生成し、ファイルサイズと生成時間を 1/4 に抑えつつ視覚品質を維持する。
    """
    rng = np.random.default_rng((int(seed) * 2654435761 + 97) & 0xFFFFFFFF)
    fine = rng.standard_normal((h, w)).astype(np.float32)
    mid = generate_micro_emboss_height(h, w, rng)
    combined = norm_std(fine * 0.78 + mid * 0.22)
    arr = np.clip(128.0 + combined * sigma, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(arr, mode="L")
