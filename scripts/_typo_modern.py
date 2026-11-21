"""
SSRGenerate — Phase 3.5 モダン・カードタイポグラフィ生成エンジン (`_typo_modern.py`)

4軸直交スキーマ (font × style × palette × layout) と AA EDT / 2x SSAA 描画エンジンにより、
以下の確定 2 大標準プリセット（および個別軸オーバーライド）を高精細 PNG として生成する:
  1. royal-foil  : A-1 (royal-fantasy) × ShipporiMincho / Cinzel × 純金ベベル (royal-gold-clean)
  2. cute-pastel : B-2 水平 (pop-horizontal) × ZenMaruGothic / Outfit × 案D (2x SSAA + ローズプラム外縁)
"""
from __future__ import annotations

import functools
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_fill_holes, distance_transform_edt, gaussian_filter

from _font_slots import (
    FONT_NORM_FACTORS as MODERN_NORM_FACTORS,
    build_norm_factors,
    get_cmap_chars,
    load_custom_fonts_manifest,
    resolve_font_path,
    resolve_slot_font,
)
from _utils import GOLD_RAMP, SILVER_RAMP, porter_duff_over, ramp_lookup, smoothstep, tight_crop_rgba

# カテゴリ別フォールバックチェーン
FALLBACK_CHAINS: Dict[str, Tuple[str, ...]] = {
    "mincho": ("ShipporiMincho-ExtraBold.ttf", "ShipporiMincho-Bold.ttf", "YujiSyuku-Regular.ttf", "KleeOne-Regular.ttf", "SetoFont.ttf", "TekitouPoem.ttf"),
    "maru": ("ZenMaruGothic-Black.ttf", "ZenMaruGothic-Bold.ttf", "SetoFont.ttf", "KleeOne-Regular.ttf", "TekitouPoem.ttf"),
    "latin": ("Outfit-VF.ttf", "Cinzel-VF.ttf", "JetBrainsMono-VF.ttf", "ZenMaruGothic-Bold.ttf", "ShipporiMincho-Bold.ttf", "SetoFont.ttf"),
    "default": ("SetoFont.ttf", "KleeOne-Regular.ttf", "TekitouPoem.ttf"),
}

# 脱 Tailwind 禁止色パレット（役割トークン）
PALETTES: Dict[str, Dict[str, str]] = {
    "royal-gold": {
        "fillTop": "#FFFDF2",
        "fillBottom": "#D4A24C",
        "inline": "#F2DFB3",
        "outline": "#1C120B",
        "shadow": "#090B14",
        "glow": "#F5D68E",
        "ribbonA": "#161B30",
        "ribbonB": "#C9953B",
        "accent": "#E8F0FA",
        "plateBg": "#0F1426",
        "plateText": "#F2DFB3",
    },
    "royal-silver": {
        "fillTop": "#FFFFFF",
        "fillBottom": "#9AA8BE",
        "inline": "#E8EFFA",
        "outline": "#121826",
        "shadow": "#080C16",
        "glow": "#B8D4F5",
        "ribbonA": "#141C2E",
        "ribbonB": "#8496B4",
        "accent": "#F2DFB3",
        "plateBg": "#101728",
        "plateText": "#EEF4FC",
    },
    "cute-pastel": {
        "fillTop": "#FFD6E6",
        "fillBottom": "#FF7AA8",
        "inline": "#FFFDF9",
        "outline": "#6D3F73",  # 案D: 優しいローズプラム外縁
        "shadow": "#3D234A",
        "glow": "#FF85B8",
        "ribbonA": "#4DBFB8",
        "ribbonB": "#FFC2D9",
        "accent": "#FFE48F",
        "plateBg": "#382046",
        "plateText": "#FFEBF3",
    },
    "idol-pop": {
        "fillTop": "#FFE38C",
        "fillBottom": "#FF4B6E",
        "inline": "#FFF9F2",
        "outline": "#1C1030",
        "shadow": "#2E144D",
        "glow": "#FFB870",
        "ribbonA": "#E0315E",
        "ribbonB": "#FF9642",
        "accent": "#2CE6D0",
        "plateBg": "#1E1338",
        "plateText": "#FFF4E0",
    },
}

# 2大標準モダンプリセット定義（実寸 900x1590 カード基準）
MODERN_PRESETS: Dict[str, Dict[str, Any]] = {
    "royal-foil": {
        "layout": "royal-fantasy",
        "palette": "royal-gold",
        "slots": {
            "ssr":       {"font": "Cinzel-VF.ttf",               "size": 86, "maxW": 340, "maxLines": 1, "style": "royal-gold-clean", "trackingEm": 0.04, "compressX": 1.0,  "vfWeight": 700, "opacity": 1.0},
            "attribute": {"font": "ShipporiMincho-Bold.ttf",     "size": 25, "maxW": 270, "maxLines": 1, "style": "plate-royal",      "trackingEm": 0.06, "compressX": 1.0,  "vfWeight": 700, "opacity": 1.0},
            "subtitle":  {"font": "ShipporiMincho-Bold.ttf",     "size": 35, "maxW": 740, "maxLines": 1, "style": "clean-sub",        "trackingEm": 0.16, "compressX": 1.0,  "vfWeight": 700, "opacity": 1.0},
            "title":     {"font": "ShipporiMincho-ExtraBold.ttf","size": 90, "maxW": 780, "maxLines": 1, "style": "royal-gold-clean", "trackingEm": 0.05, "compressX": 1.0,  "vfWeight": 800, "opacity": 1.0},
            "flavor":    {"font": "ShipporiMincho-Bold.ttf",     "size": 26, "maxW": 720, "maxLines": 2, "style": "clean-sub",        "trackingEm": 0.04, "compressX": 1.0,  "vfWeight": 700, "opacity": 0.94},
            "cardNo":    {"font": "JetBrainsMono-VF.ttf",        "size": 16, "maxW": 220, "maxLines": 1, "style": "clean-sub",        "trackingEm": 0.10, "compressX": 1.0,  "vfWeight": 600, "opacity": 0.72},
        },
    },
    "cute-pastel": {
        "layout": "pop-horizontal",
        "palette": "cute-pastel",
        "slots": {
            "ssr":       {"font": "Outfit-VF.ttf",           "size": 80, "maxW": 300, "maxLines": 1, "style": "pop-sticker-rose", "trackingEm": -0.04, "compressX": 0.84, "vfWeight": 800, "opacity": 1.0},
            "attribute": {"font": "ZenMaruGothic-Bold.ttf",  "size": 24, "maxW": 260, "maxLines": 1, "style": "plate-pop",        "trackingEm": 0.04,  "compressX": 1.0,  "vfWeight": 700, "opacity": 1.0},
            "subtitle":  {"font": "ZenMaruGothic-Bold.ttf",  "size": 36, "maxW": 620, "maxLines": 1, "style": "pop-sticker-rose", "trackingEm": 0.06,  "compressX": 1.0,  "vfWeight": 700, "opacity": 1.0},
            "title":     {"font": "ZenMaruGothic-Black.ttf", "size": 90, "maxW": 770, "maxLines": 1, "style": "pop-sticker-rose", "trackingEm": 0.02,  "compressX": 1.0,  "vfWeight": 900, "opacity": 1.0},
            "flavor":    {"font": "ZenMaruGothic-Bold.ttf",  "size": 25, "maxW": 680, "maxLines": 2, "style": "pop-sticker-rose", "trackingEm": 0.03,  "compressX": 1.0,  "vfWeight": 700, "opacity": 0.96},
            "cardNo":    {"font": "JetBrainsMono-VF.ttf",    "size": 16, "maxW": 220, "maxLines": 1, "style": "clean-sub",        "trackingEm": 0.10,  "compressX": 1.0,  "vfWeight": 600, "opacity": 0.72},
        },
    },
}


def hex_to_rgb01(h: str) -> np.ndarray:
    s = h.lstrip("#")
    return np.array([int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0], dtype=np.float32)


def hex_to_rgb255(h: str) -> Tuple[int, int, int]:
    s = h.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


@functools.lru_cache(maxsize=128)
def _load_vf_font(font_path_str: str, size: int, vf_weight: int = 700) -> ImageFont.FreeTypeFont:
    """可変フォント (VF) の Weight 軸をキャッシュキーに含めて安全にロード"""
    f = ImageFont.truetype(font_path_str, max(8, int(size)))
    try:
        axes = f.get_variation_axes()
        if axes:
            vals = []
            for ax in axes:
                name = ax.get("name", b"")
                tag = ax.get("tag", b"")
                if name in (b"Weight", "Weight") or tag in (b"wght", "wght"):
                    vals.append(min(ax["maximum"], max(ax["minimum"], vf_weight)))
                else:
                    vals.append(ax["default"])
            f.set_variation_by_axes(vals)
    except Exception:
        pass
    return f


def _fallback_chain_for(font_name: str) -> Tuple[str, ...]:
    low = font_name.lower()
    if "mincho" in low or "yuji" in low:
        return FALLBACK_CHAINS["mincho"]
    if "maru" in low or "mochiy" in low or "seto" in low:
        return FALLBACK_CHAINS["maru"]
    if any(k in low for k in ("cinzel", "outfit", "jetbrains", "montserrat", "chakra", "bebas")):
        return FALLBACK_CHAINS["latin"]
    return FALLBACK_CHAINS["default"]


def _pick_char_font(
    ch: str,
    primary_name: str,
    size: int,
    vf_weight: int,
    norm_factors: Dict[str, float],
) -> ImageFont.FreeTypeFont:
    code = ord(ch)
    chain = (primary_name,) + tuple(fb for fb in _fallback_chain_for(primary_name) if fb != primary_name)
    for fname in chain:
        p = resolve_font_path(fname)
        if p is None:
            continue
        cset = get_cmap_chars(str(p))
        if (not cset) or (code in cset) or fname == chain[-1]:
            f_norm = norm_factors.get(fname, 1.0)
            eff = max(8, int(round(size * f_norm)))
            return _load_vf_font(str(p), eff, vf_weight)
    fb_p = resolve_font_path("TekitouPoem.ttf")
    assert fb_p is not None
    return _load_vf_font(str(fb_p), size, vf_weight)


def _measure_width(text: str, primary: str, size: int, tracking_em: float, vf_weight: int, norm_factors: Dict[str, float]) -> float:
    total = 0.0
    trk = tracking_em * size
    for i, ch in enumerate(text):
        f = _pick_char_font(ch, primary, size, vf_weight, norm_factors)
        try:
            adv = float(f.getlength(ch))
        except Exception:
            bb = f.getbbox(ch)
            adv = float(bb[2] - bb[0]) if bb else size * 0.5
        total += adv + (trk if i < len(text) - 1 else 0.0)
    return total


def _wrap_lines(
    text: str,
    primary: str,
    size: int,
    max_w: float,
    max_lines: int,
    tracking_em: float,
    vf_weight: int,
    norm_factors: Dict[str, float],
) -> List[str]:
    clean = text.strip()
    if not clean:
        return []
    if max_lines <= 1 or _measure_width(clean, primary, size, tracking_em, vf_weight, norm_factors) <= max_w:
        return [clean]
    lines: List[str] = []
    rest = clean
    for _ in range(max_lines - 1):
        if _measure_width(rest, primary, size, tracking_em, vf_weight, norm_factors) <= max_w:
            break
        split_idx = len(rest)
        while split_idx > 1 and _measure_width(rest[:split_idx], primary, size, tracking_em, vf_weight, norm_factors) > max_w:
            split_idx -= 1
        best = split_idx
        for k in range(split_idx, max(1, split_idx - 8), -1):
            if rest[k - 1] in "、。，．・ ,.　":
                best = k
                break
        lines.append(rest[:best].rstrip())
        rest = rest[best:].lstrip()
    if rest:
        lines.append(rest)
    return lines


def _render_mask_ls(
    text: str,
    primary: str,
    font_size: int,
    max_w: float,
    max_lines: int,
    tracking_em: float,
    vf_weight: int,
    norm_factors: Dict[str, float],
    align: str = "center",
    pad: int = 36,
) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    cur_size = font_size
    lines = _wrap_lines(text, primary, cur_size, max_w, max_lines, tracking_em, vf_weight, norm_factors)
    if lines:
        widest = max(_measure_width(ln, primary, cur_size, tracking_em, vf_weight, norm_factors) for ln in lines)
        if widest > max_w and widest > 1.0:
            cur_size = max(12, int(cur_size * (max_w / widest)))
            lines = _wrap_lines(text, primary, cur_size, max_w, max_lines, tracking_em, vf_weight, norm_factors)

    if not lines:
        return np.zeros((16, 16), dtype=np.float32), (0, 16, 0, 16)

    trk = tracking_em * cur_size
    line_items = []
    line_widths = []
    for ln in lines:
        items = []
        cx = 0.0
        for i, ch in enumerate(ln):
            f = _pick_char_font(ch, primary, cur_size, vf_weight, norm_factors)
            try:
                adv = float(f.getlength(ch))
            except Exception:
                bb = f.getbbox(ch)
                adv = float(bb[2] - bb[0]) if bb else cur_size * 0.5
            items.append((ch, f, cx))
            cx += adv + (trk if i < len(ln) - 1 else 0.0)
        line_items.append(items)
        line_widths.append(cx)

    max_lw = max(1.0, max(line_widths))
    line_h = int(math.ceil(cur_size * 1.38))
    W = int(math.ceil(max_lw)) + pad * 2 + 28
    H = line_h * len(lines) + pad * 2 + 20
    canvas = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(canvas)

    for li, (items, lw) in enumerate(zip(line_items, line_widths)):
        if align == "left":
            ox = float(pad + 10)
        elif align == "right":
            ox = float(pad + 10) + (max_lw - lw)
        else:
            ox = float(pad + 10) + (max_lw - lw) * 0.5
        base_y = float(pad) + cur_size * 1.02 + li * line_h
        for ch, f, cx in items:
            draw.text((ox + cx, base_y), ch, fill=255, font=f, anchor="ls")

    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    ys, xs = np.where(arr > 0.04)
    if len(ys) == 0:
        return arr, (0, H, 0, W)
    return arr, (int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1)


def _compute_sdf(alpha: np.ndarray, need_in: bool = True, need_out: bool = True) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    inside = alpha >= 0.5
    d_in = None
    d_out = None
    if need_in:
        raw_in = distance_transform_edt(inside).astype(np.float32)
        d_in = np.where(inside, raw_in - 1.0 + alpha, alpha).astype(np.float32)
    if need_out:
        raw_out = distance_transform_edt(~inside).astype(np.float32)
        d_out = np.where(~inside, raw_out - alpha, 0.0).astype(np.float32)
    return d_in, d_out


def _stroke_mask(d_out: np.ndarray, alpha: np.ndarray, width_px: float, fill_holes: bool = False) -> np.ndarray:
    m = np.maximum(alpha, smoothstep(width_px + 0.65, width_px - 0.65, d_out))
    if fill_holes:
        filled = binary_fill_holes(m >= 0.5)
        m = np.where(filled & (m < 0.5), 1.0, m).astype(np.float32)
    return m


def _shift_subpixel(arr: np.ndarray, dx: float, dy: float) -> np.ndarray:
    h, w = arr.shape
    ix, iy = int(math.floor(dx)), int(math.floor(dy))
    fx, fy = dx - ix, dy - iy

    def shift_int(a: np.ndarray, sx: int, sy: int) -> np.ndarray:
        out = np.zeros_like(a)
        x0_s, x1_s = max(0, -sx), min(w, w - sx)
        y0_s, y1_s = max(0, -sy), min(h, h - sy)
        if x1_s > x0_s and y1_s > y0_s:
            out[y0_s + sy : y1_s + sy, x0_s + sx : x1_s + sx] = a[y0_s:y1_s, x0_s:x1_s]
        return out

    return (
        shift_int(arr, ix, iy) * ((1.0 - fx) * (1.0 - fy))
        + shift_int(arr, ix + 1, iy) * (fx * (1.0 - fy))
        + shift_int(arr, ix, iy + 1) * ((1.0 - fx) * fy)
        + shift_int(arr, ix + 1, iy + 1) * (fx * fy)
    ).astype(np.float32)


def render_modern_text(
    text: str,
    *,
    font_name: str,
    font_size: int,
    max_w: float,
    max_lines: int,
    style_id: str,
    palette: Dict[str, str],
    tracking_em: float = 0.0,
    compress_x: float = 1.0,
    vf_weight: int = 700,
    opacity: float = 1.0,
    align: str = "center",
    norm_factors: Optional[Dict[str, float]] = None,
) -> Image.Image:
    """確定デザイン仕様（royal-gold-clean / pop-sticker-rose 案D / clean-sub）で透過PNG生成"""
    nf = norm_factors or MODERN_NORM_FACTORS
    c_top = hex_to_rgb01(palette["fillTop"])
    c_bot = hex_to_rgb01(palette["fillBottom"])
    c_in = hex_to_rgb01(palette["inline"])
    c_out = hex_to_rgb01(palette["outline"])
    c_sh = hex_to_rgb01(palette["shadow"])

    # 案D (pop-sticker-rose) は 2x SSAA でジャギーを物理解消
    ss = 2 if style_id == "pop-sticker-rose" else 1
    fs = int(round(font_size * ss))
    pad = max(32 * ss, int(fs * 0.55))

    alpha, (y0, y1, _, _) = _render_mask_ls(
        text=text,
        primary=font_name,
        font_size=fs,
        max_w=max_w * ss,
        max_lines=max_lines,
        tracking_em=tracking_em,
        vf_weight=vf_weight,
        norm_factors=nf,
        align=align,
        pad=pad,
    )
    h, w = alpha.shape
    d_in, d_out = _compute_sdf(alpha, need_in=(style_id == "royal-gold-clean"), need_out=True)
    assert d_out is not None

    yn = np.clip((np.arange(h, dtype=np.float32)[:, None] - y0) / max(1.0, float(y1 - y0)), 0.0, 1.0)
    fill_rgb = c_top[None, None, :] * (1.0 - yn[..., None]) + c_bot[None, None, :] * yn[..., None]
    sc = fs / 84.0

    if style_id == "royal-gold-clean":
        assert d_in is not None
        bevel_w = max(2.2, 5.2 * sc)
        prof = np.clip(d_in / bevel_w, 0.0, 1.0)
        prof = prof * prof * (3.0 - 2.0 * prof)
        prof = gaussian_filter(prof, sigma=0.45) * 4.2
        gy, gx = np.gradient(prof)
        nx, ny, nz = -gx, -gy, np.ones_like(gx)
        nlen = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-8
        nx, ny, nz = nx / nlen, ny / nlen, nz / nlen
        rad = math.radians(-122.0)
        lx, ly, lz = math.cos(rad) * 0.65, math.sin(rad) * 0.65, 0.76
        hx, hy, hz = lx, ly, lz + 1.0
        hlen = math.sqrt(hx * hx + hy * hy + hz * hz)
        hx, hy, hz = hx / hlen, hy / hlen, hz / hlen
        diff = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
        spec = np.power(np.clip(nx * hx + ny * hy + nz * hz, 0.0, 1.0), 28.0)
        delta = diff - lz

        is_silver = palette.get("fillBottom", "").upper() == "#9AA8BE"
        ramp = SILVER_RAMP if is_silver else GOLD_RAMP
        base_t = np.clip(0.84 - yn * 0.34 + delta * 0.95, 0.0, 1.0)
        fill_rgb = np.clip(ramp_lookup(base_t, ramp) + spec[..., None] * 0.48, 0.0, 1.0)

        w_i = max(1.2, 1.6 * sc)
        base_sil = _stroke_mask(d_out, alpha, w_i)
        depth_px = max(3.2, 5.5 * sc)
        n_steps = max(4, int(math.ceil(depth_px / 0.8)))
        ext_a = np.zeros((h, w), dtype=np.float32)
        ext_t = np.zeros((h, w), dtype=np.float32)
        ux, uy = math.cos(math.radians(55.0)), math.sin(math.radians(55.0))
        for i in range(1, n_steps + 1):
            t = i / float(n_steps)
            sh = _shift_subpixel(base_sil, ux * depth_px * t, uy * depth_px * t)
            c_step = sh * (1.0 - ext_a)
            ext_a += c_step
            ext_t += t * c_step
        ext_a = np.clip(ext_a, 0.0, 1.0)
        t_n = ext_t / np.maximum(ext_a, 1e-5)
        if is_silver:
            c_near = np.array([0.42, 0.46, 0.56], dtype=np.float32)
            c_far = np.array([0.12, 0.14, 0.22], dtype=np.float32)
        else:
            c_near = np.array([0.52, 0.34, 0.12], dtype=np.float32)
            c_far = np.array([0.16, 0.09, 0.04], dtype=np.float32)
        ext_rgb = c_near[None, None, :] * (1.0 - t_n[..., None]) + c_far[None, None, :] * t_n[..., None]

        union_sil = np.maximum(base_sil, ext_a)
        _, d_u = _compute_sdf(union_sil, need_in=False, need_out=True)
        assert d_u is not None
        m_rim = _stroke_mask(d_u, union_sil, max(1.2, 1.8 * sc))
        amb = _shift_subpixel(gaussian_filter(m_rim, sigma=3.0, mode="constant"), 0.0, 2.5) * 0.38
        rgb, a = porter_duff_over(np.broadcast_to(c_out[None, None, :], (h, w, 3)), m_rim, np.zeros((h, w, 3), dtype=np.float32), amb)
        rgb, a = porter_duff_over(ext_rgb, ext_a, rgb, a)
        rgb, a = porter_duff_over(np.broadcast_to(c_in[None, None, :], (h, w, 3)), base_sil, rgb, a)
        rgb, a = porter_duff_over(fill_rgb, alpha, rgb, a)

    elif style_id == "pop-sticker-rose":
        # 案D: 2x SSAA + 白太ステッカー縁 (fill_holes=True) + 優しいローズプラム外縁 (3.0px相当) + 極薄ソフト影
        w_s = max(5.0 * ss, 10.5 * sc)
        w_o = max(1.8 * ss, 3.0 * sc)
        m_s = _stroke_mask(d_out, alpha, w_s, fill_holes=True)
        m_o = _stroke_mask(d_out, alpha, w_s + w_o, fill_holes=True)
        sh = _shift_subpixel(gaussian_filter(m_o, sigma=4.0 * sc, mode="constant"), 0.0, 2.5 * sc) * 0.28
        rgb, a = np.broadcast_to(c_sh[None, None, :], (h, w, 3)), sh
        rgb, a = porter_duff_over(np.broadcast_to(c_out[None, None, :], (h, w, 3)), m_o, rgb, a)
        rgb, a = porter_duff_over(np.broadcast_to(c_in[None, None, :], (h, w, 3)), m_s, rgb, a)
        rgb, a = porter_duff_over(fill_rgb, alpha, rgb, a)

    else:  # clean-sub
        m_o = _stroke_mask(d_out, alpha, max(1.1, 1.8 * sc))
        sh = _shift_subpixel(gaussian_filter(m_o, sigma=2.2, mode="constant"), 0.0, 1.8) * 0.38
        rgb, a = porter_duff_over(
            np.broadcast_to(c_out[None, None, :], (h, w, 3)),
            m_o * 0.85,
            np.zeros((h, w, 3), dtype=np.float32),
            sh,
        )
        rgb, a = porter_duff_over(fill_rgb, alpha, rgb, a)

    if opacity < 0.999:
        a = a * float(opacity)

    im = tight_crop_rgba(rgb, a, alpha_threshold=0.006, pad=3 * ss)

    if ss > 1:
        im = im.resize((max(1, im.width // ss), max(1, im.height // ss)), Image.Resampling.LANCZOS)
    if abs(compress_x - 1.0) > 0.01:
        nw = max(1, int(round(im.width * compress_x)))
        im = im.resize((nw, im.height), Image.Resampling.LANCZOS)
    return im


def render_modern_attribute_plate(
    text: str,
    *,
    font_name: str,
    font_size: int,
    style_id: str,
    palette: Dict[str, str],
    tracking_em: float = 0.05,
    vf_weight: int = 700,
    norm_factors: Optional[Dict[str, float]] = None,
) -> Image.Image:
    """3x SSAA による Royal 鋭角プレート / Pop 丸ピルタグ生成"""
    txt_im = render_modern_text(
        text,
        font_name=font_name,
        font_size=font_size,
        max_w=270.0,
        max_lines=1,
        style_id="clean-sub",
        palette=palette,
        tracking_em=tracking_em,
        vf_weight=vf_weight,
        norm_factors=norm_factors,
    )
    tw, th = txt_im.size
    pad_x = 34 if style_id == "plate-royal" else 30
    pad_y = 14
    bw = max(180, tw + pad_x * 2)
    bh = max(54, th + pad_y * 2)

    ss = 3
    pbg = hex_to_rgb255(palette["plateBg"])
    border_col = hex_to_rgb255(palette["ribbonB"] if style_id == "plate-royal" else palette["accent"])
    plate = Image.new("RGBA", (bw * ss, bh * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(plate)
    if style_id == "plate-royal":
        skew = 16 * ss
        d.polygon(
            [(skew, 2 * ss), ((bw - 2) * ss, 2 * ss), ((bw - 2) * ss - skew, (bh - 2) * ss), (2 * ss, (bh - 2) * ss)],
            fill=(*pbg, 222),
            outline=(*border_col, 232),
            width=int(2 * ss),
        )
    else:
        r = (bh // 2 - 2) * ss
        d.rounded_rectangle(
            [2 * ss, 2 * ss, (bw - 2) * ss, (bh - 2) * ss],
            radius=r,
            fill=(*pbg, 218),
            outline=(*border_col, 235),
            width=int(2.5 * ss),
        )
    plate = plate.resize((bw, bh), Image.Resampling.LANCZOS)
    plate.alpha_composite(txt_im, ((bw - tw) // 2, (bh - th) // 2))
    return plate


def render_royal_diamond_rule(width: int = 760, palette: Optional[Dict[str, str]] = None, ss: int = 3) -> Image.Image:
    """Royal-1 下部アクセント用の 3x SSAA 細二重罫線＋中央◇＋両端◆"""
    pal = palette or PALETTES["royal-gold"]
    ptx = hex_to_rgb255(pal["plateText"])
    col = (*ptx, 224)
    sub_col = (*ptx, 145)
    h = 34
    Sw, Sh = width * ss, h * ss
    im = Image.new("RGBA", (Sw, Sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cy = Sh * 0.5

    # 両端の菱形 ◆
    dr = 7.0 * ss
    for ex in (16 * ss, Sw - 16 * ss):
        d.polygon([(ex, cy - dr), (ex + dr, cy), (ex, cy + dr), (ex - dr, cy)], fill=col)

    # 中央のダイヤ ◇
    mx = Sw * 0.5
    mr = 10.5 * ss
    d.polygon([(mx, cy - mr), (mx + mr, cy), (mx, cy + mr), (mx - mr, cy)], outline=col, width=max(1, int(round(2.0 * ss))))

    # 左右の二重罫線
    mw = max(1, int(round(2.0 * ss)))
    sw = max(1, int(round(1.4 * ss)))
    d.line([(32 * ss, cy - 3.2 * ss), (mx - 18 * ss, cy - 3.2 * ss)], fill=col, width=mw)
    d.line([(32 * ss, cy + 3.2 * ss), (mx - 18 * ss, cy + 3.2 * ss)], fill=sub_col, width=sw)
    d.line([(mx + 18 * ss, cy - 3.2 * ss), (Sw - 32 * ss, cy - 3.2 * ss)], fill=col, width=mw)
    d.line([(mx + 18 * ss, cy + 3.2 * ss), (Sw - 32 * ss, cy + 3.2 * ss)], fill=sub_col, width=sw)
    return im.resize((width, h), Image.Resampling.LANCZOS)


def resolve_modern_plan(preset_name: str, typo_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """4軸直交スキーマ (preset + font/style/palette/layout 個別上書き + fonts_custom) を解決する"""
    base = MODERN_PRESETS[preset_name]
    custom_mf = load_custom_fonts_manifest()

    # 1. layout 軸
    lay_cfg = typo_cfg.get("layout", {})
    if isinstance(lay_cfg, str):
        layout_id = lay_cfg
        mirror = False
    elif isinstance(lay_cfg, dict):
        layout_id = str(lay_cfg.get("id", base["layout"]))
        mirror = bool(lay_cfg.get("mirror", False))
    else:
        layout_id = base["layout"]
        mirror = False

    # 2. palette 軸
    pal_cfg = typo_cfg.get("palette", {})
    pal_bundle = pal_cfg if isinstance(pal_cfg, str) else str(pal_cfg.get("bundle", base["palette"])) if isinstance(pal_cfg, dict) else base["palette"]
    palette = dict(PALETTES.get(pal_bundle, PALETTES[base["palette"]]))
    if isinstance(pal_cfg, dict) and isinstance(pal_cfg.get("tokens"), dict):
        for k, v in pal_cfg["tokens"].items():
            if isinstance(v, str) and v.startswith("#"):
                palette[k] = v

    # 3. norm_factors + custom_mf
    norm_factors = build_norm_factors(custom_mf)

    # 4. font / style スロット解決
    font_cfg = typo_cfg.get("font", {}) if isinstance(typo_cfg.get("font"), dict) else {}
    font_slots_ov = font_cfg.get("slots", {}) if isinstance(font_cfg.get("slots"), dict) else {}
    style_cfg = typo_cfg.get("style", {}) if isinstance(typo_cfg.get("style"), dict) else {}
    style_bundle_ov = style_cfg.get("bundle") if isinstance(style_cfg.get("bundle"), str) else None

    slots: Dict[str, Dict[str, Any]] = {}
    for skey, sdef in base["slots"].items():
        cur = dict(sdef)
        # fonts_custom/fonts.json 上書き
        cur["font"] = resolve_slot_font(skey, cur["font"], custom_mf)
        # card-config.js 個別スロット上書き
        ov = font_slots_ov.get(skey)
        if isinstance(ov, dict):
            if isinstance(ov.get("family"), str) and ov["family"].strip():
                cur["font"] = ov["family"].strip()
            if isinstance(ov.get("trackingEm"), (int, float)):
                cur["trackingEm"] = float(ov["trackingEm"])
            if isinstance(ov.get("size"), (int, float)):
                cur["size"] = int(ov["size"])
            if isinstance(ov.get("compressX"), (int, float)):
                cur["compressX"] = float(ov["compressX"])
        if style_bundle_ov and skey in ("title", "ssr"):
            cur["style"] = style_bundle_ov
        slots[skey] = cur

    return {
        "preset": preset_name,
        "layout": layout_id,
        "mirror": mirror,
        "palette_id": pal_bundle,
        "palette": palette,
        "norm_factors": norm_factors,
        "slots": slots,
    }
