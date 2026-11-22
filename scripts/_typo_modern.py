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
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
from _utils import (
    GOLD_RAMP,
    SILVER_RAMP,
    format_attribute_key_text,
    gaussian_blur_f,
    parse_attribute_parts,
    porter_duff_over,
    ramp_lookup,
    rgba_from_float,
    shade_metal_relief,
    smoothstep,
    tight_crop_rgba,
)

# カテゴリ別フォールバックチェーン
FALLBACK_CHAINS: Dict[str, Tuple[str, ...]] = {
    "mincho": ("ShipporiMincho-ExtraBold.ttf", "ShipporiMincho-Bold.ttf", "YujiSyuku-Regular.ttf", "ZenMaruGothic-Bold.ttf"),
    "maru": ("ZenMaruGothic-Black.ttf", "ZenMaruGothic-Bold.ttf", "ShipporiMincho-Bold.ttf"),
    "latin": ("Outfit-VF.ttf", "Cinzel-VF.ttf", "JetBrainsMono-VF.ttf", "ZenMaruGothic-Bold.ttf", "ShipporiMincho-Bold.ttf"),
    "default": ("ZenMaruGothic-Bold.ttf", "ShipporiMincho-Bold.ttf"),
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
            "cardNo":    {"font": "JetBrainsMono-VF.ttf",        "size": 16, "maxW": 220, "maxLines": 1, "style": "clean-sub",        "trackingEm": 0.10, "compressX": 1.0,  "vfWeight": 600, "opacity": 0.85},
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
            "cardNo":    {"font": "JetBrainsMono-VF.ttf",    "size": 16, "maxW": 220, "maxLines": 1, "style": "clean-sub",        "trackingEm": 0.10,  "compressX": 1.0,  "vfWeight": 600, "opacity": 0.94},
        },
    },
}

# Landscape (1480x860 / 内窓 1440x820) 用のスロット調整テーブル
LANDSCAPE_SLOT_OVERRIDES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "royal-foil": {
        "ssr":      {"size": 76, "maxW": 320},
        "subtitle": {"size": 30, "maxW": 1120},
        "title":    {"size": 76, "maxW": 1200},
        "flavor":   {"size": 23, "maxW": 1140},
    },
    "cute-pastel": {
        "ssr":      {"size": 72, "maxW": 280},
        "subtitle": {"size": 31, "maxW": 1060},
        "title":    {"size": 76, "maxW": 1180},
        "flavor":   {"size": 22, "maxW": 1120},
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
    fb_p = resolve_font_path("ZenMaruGothic-Bold.ttf") or resolve_font_path("ShipporiMincho-Bold.ttf")
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


KINSOKU_HEAD: Set[str] = set("、。，．・！？!?）」』】〕〉》｝］ーぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ々ヾヽゝゞ:;,.)]}")
KINSOKU_TAIL: Set[str] = set("（「『【〔〈《｛［([{")


def wrap_lines_kinsoku(
    text: str,
    max_w: float,
    max_lines: int,
    measure_fn: Callable[[str], float],
) -> List[str]:
    """汎用禁則折り返し処理（行頭・行末禁則文字、句読点優先、明示改行対応）"""
    clean = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean:
        return []
    if max_lines <= 1:
        return [re.sub(r"\s*\n\s*", " ", clean)]

    paragraphs = [p.strip() for p in clean.split("\n") if p.strip()]
    if not paragraphs:
        return []

    lines: List[str] = []
    for p_idx, para in enumerate(paragraphs):
        if len(lines) >= max_lines:
            lines[-1] = f"{lines[-1]} {para}".strip()
            continue
        if measure_fn(para) <= max_w:
            lines.append(para)
            continue

        rest = para
        while rest:
            remaining_slots = max_lines - len(lines)
            if remaining_slots <= 1:
                # これ以上の行枠がない場合は残りをすべて最終行へ収める（呼び出し元で縮小される）
                if lines and remaining_slots <= 0:
                    lines[-1] = f"{lines[-1]} {rest}".strip()
                else:
                    lines.append(rest.strip())
                rest = ""
                break
            if measure_fn(rest) <= max_w:
                lines.append(rest.strip())
                rest = ""
                break

            split_idx = len(rest)
            while split_idx > 1 and measure_fn(rest[:split_idx]) > max_w:
                split_idx -= 1
            best = split_idx
            for k in range(split_idx, max(1, split_idx - 8), -1):
                if rest[k - 1] in "、。，．・ ,.　":
                    best = k
                    break

            # 禁則調整（最大2文字まで前送り、ただし best > 1 を維持）
            for _ in range(2):
                if best < len(rest) and rest[best] in KINSOKU_HEAD and best - 1 > 1:
                    best -= 1
                else:
                    break
            for _ in range(2):
                if best > 1 and rest[best - 1] in KINSOKU_TAIL and best - 1 > 1:
                    best -= 1
                else:
                    break

            head_part = rest[:best].rstrip()
            tail_part = rest[best:].lstrip()
            if not head_part:
                head_part = rest[:1]
                tail_part = rest[1:].lstrip()
            lines.append(head_part)
            rest = tail_part

        # 後続段落があるのに既に行枠上限へ達していたら最終行にマージされる
        if p_idx < len(paragraphs) - 1 and len(lines) > max_lines:
            lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]

    return lines[:max_lines] if len(lines) > max_lines else lines


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
    return wrap_lines_kinsoku(
        text=text,
        max_w=max_w,
        max_lines=max_lines,
        measure_fn=lambda s: _measure_width(s, primary, size, tracking_em, vf_weight, norm_factors),
    )


def adjust_short_title_tracking(text: str, base_tracking_em: float, explicit_override: bool = False) -> float:
    """極短タイトル（2〜3文字）のスカスカ感を防ぐため字間を自動拡大（明示上書き時は維持）"""
    if explicit_override:
        return float(base_tracking_em)
    compact_len = len("".join(text.split()))
    if compact_len == 2:
        return float(base_tracking_em) + 0.10
    if compact_len == 3:
        return float(base_tracking_em) + 0.05
    return float(base_tracking_em)


def compute_fitted_font_size(
    text: str,
    primary: str,
    font_size: int,
    max_w: float,
    max_lines: int,
    tracking_em: float,
    vf_weight: int,
    norm_factors: Dict[str, float],
) -> Tuple[int, List[str]]:
    """折り返し後に最大幅へ収まる実効フォントサイズと分割行リストを返す"""
    cur_size = font_size
    lines = _wrap_lines(text, primary, cur_size, max_w, max_lines, tracking_em, vf_weight, norm_factors)
    for _ in range(2):
        if not lines:
            break
        widest = max(_measure_width(ln, primary, cur_size, tracking_em, vf_weight, norm_factors) for ln in lines)
        if widest > max_w and widest > 1.0:
            next_size = max(12, int(cur_size * (max_w / widest)))
            if next_size == cur_size:
                break
            cur_size = next_size
            lines = _wrap_lines(text, primary, cur_size, max_w, max_lines, tracking_em, vf_weight, norm_factors)
        else:
            break
    return cur_size, lines


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
    cur_size, lines = compute_fitted_font_size(
        text, primary, font_size, max_w, max_lines, tracking_em, vf_weight, norm_factors
    )

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


# 左右共通座布団ギミックの統一物理寸法（左 Pattern A × 右 Pattern C）
SHARED_BAND_H = 44
ZABUTON_PAD = 14


def _measure_ink_center_y(im: Image.Image, alpha_thresh: float = 0.80) -> float:
    """ドロップシャドウ等の半透明領域を除外し、文字本体の視覚的な上下中心 Y 座標を返す"""
    arr = np.asarray(im, dtype=np.float32) / 255.0
    a = arr[..., 3]
    ys = np.where(a >= alpha_thresh)[0]
    if len(ys) == 0:
        ys = np.where(a > 0.25)[0]
    if len(ys) == 0:
        return im.height * 0.5
    return (float(ys.min()) + float(ys.max()) + 1.0) * 0.5


def _measure_ink_center_x(im: Image.Image, alpha_thresh: float = 0.80) -> float:
    """ドロップシャドウ等の半透明領域を除外し、文字本体の視覚的な左右中心 X 座標を返す"""
    arr = np.asarray(im, dtype=np.float32) / 255.0
    a = arr[..., 3]
    xs = np.where(a >= alpha_thresh)[1]
    if len(xs) == 0:
        xs = np.where(a > 0.25)[1]
    if len(xs) == 0:
        return im.width * 0.5
    return (float(xs.min()) + float(xs.max()) + 1.0) * 0.5


def render_shared_zabuton(
    w: int,
    h: int,
    theme: str,
    palette: Dict[str, str],
    skew_px: float = 15.0,
    fishtail_right: bool = False,
) -> Image.Image:
    """左右共通座布団ベース生成（Royal: 3D金属レリーフ枠 / Pop: 白ステッカー＋外縁＋ストライプ）"""
    ss = 3
    pad = ZABUTON_PAD
    W, H = (w + pad * 2) * ss, (h + pad * 2) * ss
    ox, oy = pad * ss, pad * ss
    bw, bh = w * ss, h * ss
    sk = skew_px * ss

    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)

    if theme == "royal":
        p_tl = (ox + sk, oy)
        p_tr = (ox + bw, oy)
        p_br = (ox + bw - sk, oy + bh)
        p_bl = (ox, oy + bh)
        if fishtail_right:
            notch = ox + bw - sk * 0.85
            pts = [p_tl, p_tr, (notch, oy + bh * 0.5), p_br, p_bl]
        else:
            pts = [p_tl, p_tr, p_br, p_bl]
        d.polygon(pts, fill=255)
    else:
        r = int(bh * 0.48)
        d.rounded_rectangle([ox, oy, ox + bw, oy + bh], radius=r, fill=255)
        if fishtail_right:
            cut = [
                (ox + bw + 4 * ss, oy - 2 * ss),
                (ox + bw - int(bh * 0.34), oy + bh // 2),
                (ox + bw + 4 * ss, oy + bh + 2 * ss),
            ]
            d.polygon(cut, fill=0)

    mask = np.asarray(im.resize((w + pad * 2, h + pad * 2), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    mh, mw = mask.shape
    yy, xx = np.mgrid[0:mh, 0:mw].astype(np.float32)
    inside = mask >= 0.5
    d_in = distance_transform_edt(inside).astype(np.float32)
    d_out = distance_transform_edt(~inside).astype(np.float32)

    if theme == "royal":
        is_silver = palette.get("fillBottom", "").upper() == "#9AA8BE"
        ramp = SILVER_RAMP if is_silver else GOLD_RAMP
        shimmer_tint = np.array([0.82, 0.90, 1.00], dtype=np.float32) if is_silver else np.array([0.95, 0.82, 0.50], dtype=np.float32)

        ty = np.clip((yy - pad) / max(1.0, float(h)), 0.0, 1.0)
        c_top = np.array([0.09, 0.12, 0.28], dtype=np.float32)
        c_bot = np.array([0.02, 0.03, 0.09], dtype=np.float32)
        body_rgb = c_top[None, None, :] * (1.0 - ty[..., None]) + c_bot[None, None, :] * ty[..., None]
        shimmer = np.exp(-(((xx - mw * 0.42) * 0.65 + (yy - mh * 0.5)) / 14.0) ** 2) * 0.22
        shimmer2 = np.exp(-(((xx - mw * 0.58) * 0.65 + (yy - mh * 0.5)) / 5.0) ** 2) * 0.18
        body_rgb = np.clip(body_rgb + (shimmer + shimmer2)[..., None] * shimmer_tint, 0.0, 1.0)
        body_a = mask * 0.88

        outer_rim = mask * smoothstep(4.2, 2.5, d_in)
        inner_pin = np.exp(-((d_in - 6.0) / 0.85) ** 2) * 0.55 * inside
        metal_mask = np.clip(outer_rim + inner_pin, 0.0, 1.0)
        metal_rgb = shade_metal_relief(metal_mask, ramp, bevel_px=1.2, depth=5.2, tone=0.68, shininess=34.0)

        shadow = np.roll(np.roll(gaussian_blur_f(mask, 4.5), 3, axis=0), 2, axis=1) * 0.68
        rgb, a = np.zeros((mh, mw, 3), dtype=np.float32), shadow
        rgb, a = porter_duff_over(body_rgb, body_a, rgb, a)
        rgb, a = porter_duff_over(metal_rgb, metal_mask, rgb, a)
    else:
        c_out = hex_to_rgb01(palette["outline"])
        c_in = hex_to_rgb01(palette["inline"])
        c_p1 = np.array([1.00, 0.91, 0.95], dtype=np.float32)
        c_p2 = np.array([0.95, 0.82, 0.90], dtype=np.float32)

        stripe = 0.5 + 0.5 * np.tanh(np.sin((xx * 0.75 + yy * 0.75) * (2.0 * math.pi / 18.0)) * 3.0)
        body_rgb = c_p1[None, None, :] * stripe[..., None] + c_p2[None, None, :] * (1.0 - stripe[..., None])
        gloss = smoothstep(mh * 0.52, pad + 3.0, yy) * smoothstep(1.5, 4.0, d_in) * 0.45
        body_rgb = np.clip(body_rgb + gloss[..., None], 0.0, 1.0)

        m_white = np.maximum(mask, smoothstep(4.6, 3.3, d_out))
        m_plum = np.maximum(m_white, smoothstep(7.4, 6.0, d_out))
        stitch = np.exp(-((d_in - 3.6) / 0.8) ** 2) * 0.65 * inside
        body_rgb = np.clip(body_rgb * (1.0 - stitch[..., None]) + c_in[None, None, :] * stitch[..., None], 0.0, 1.0)

        shadow = np.roll(gaussian_filter(m_plum, sigma=3.2), 2, axis=0) * 0.26
        rgb, a = np.broadcast_to(c_out[None, None, :], (mh, mw, 3)), shadow
        rgb, a = porter_duff_over(np.broadcast_to(c_out[None, None, :], (mh, mw, 3)), m_plum, rgb, a)
        rgb, a = porter_duff_over(np.broadcast_to(c_in[None, None, :], (mh, mw, 3)), m_white, rgb, a)
        rgb, a = porter_duff_over(body_rgb, mask, rgb, a)

    return rgba_from_float(rgb, a)


def _render_pastel_medallion_char(
    ch: str,
    size: int,
    palette: Dict[str, str],
    norm_factors: Optional[Dict[str, float]] = None,
) -> Image.Image:
    """Pastel ハートメダリオン専用のスリム縁取り 1 文字（白抜き＋プラム細縁）"""
    nf = norm_factors or MODERN_NORM_FACTORS
    ss = 2
    fs = int(round(size * ss))
    alpha, _ = _render_mask_ls(
        text=ch,
        primary="ZenMaruGothic-Black.ttf",
        font_size=fs,
        max_w=fs * 1.4,
        max_lines=1,
        tracking_em=0.0,
        vf_weight=900,
        norm_factors=nf,
        align="center",
        pad=24 * ss,
    )
    h, w = alpha.shape
    _, d_out = _compute_sdf(alpha, need_in=False, need_out=True)
    assert d_out is not None

    c_fill = hex_to_rgb01(palette["inline"])
    c_out = hex_to_rgb01(palette["outline"])
    c_sh = hex_to_rgb01(palette["shadow"])

    m_out = _stroke_mask(d_out, alpha, 2.2 * ss, fill_holes=True)
    sh = _shift_subpixel(gaussian_filter(m_out, sigma=1.8 * ss, mode="constant"), 0.0, 1.4 * ss) * 0.34

    rgb, a = np.broadcast_to(c_sh[None, None, :], (h, w, 3)), sh
    rgb, a = porter_duff_over(np.broadcast_to(c_out[None, None, :], (h, w, 3)), m_out, rgb, a)
    rgb, a = porter_duff_over(np.broadcast_to(c_fill[None, None, :], (h, w, 3)), alpha, rgb, a)

    im = tight_crop_rgba(rgb, a, alpha_threshold=0.008, pad=2 * ss)
    return im.resize((max(1, im.width // ss), max(1, im.height // ss)), Image.Resampling.LANCZOS)


def _render_attribute_medallion(
    theme: str,
    palette: Dict[str, str],
    badge_char: str = "",
    norm_factors: Optional[Dict[str, float]] = None,
) -> Tuple[Image.Image, float]:
    """拡大属性メダリオン（Royal: 78px ダイヤ / Pastel: 4x SSAA 3次ベジェハート）と視覚基準 Y を返す"""
    if theme == "royal":
        is_silver = palette.get("fillBottom", "").upper() == "#9AA8BE"
        ramp = SILVER_RAMP if is_silver else GOLD_RAMP
        size = 78
        ss = 3
        S = size * ss
        c = S * 0.5
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        cy, cx = size * 0.5, size * 0.5

        im_base = Image.new("L", (S, S), 0)
        r_out = S * 0.46
        ImageDraw.Draw(im_base).polygon([(c, c - r_out), (c + r_out, c), (c, c + r_out), (c - r_out, c)], fill=255)
        m_base = np.asarray(im_base.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

        im_in = Image.new("L", (S, S), 0)
        r_in = S * 0.37
        ImageDraw.Draw(im_in).polygon([(c, c - r_in), (c + r_in, c), (c, c + r_in), (c - r_in, c)], fill=255)
        m_gem = np.asarray(im_in.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
        m_bezel = np.clip(m_base - m_gem, 0.0, 1.0)

        im_star = Image.new("L", (S, S), 0)
        pts = []
        for i in range(16):
            a_rad = math.radians(-90 + i * 22.5)
            r = (S * 0.30 if i % 4 == 0 else S * 0.21) if i % 2 == 0 else S * 0.08
            pts.append((c + math.cos(a_rad) * r, c + math.sin(a_rad) * r))
        ImageDraw.Draw(im_star).polygon(pts, fill=255)
        m_star = np.asarray(im_star.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

        bezel_rgb = shade_metal_relief(m_bezel, ramp, bevel_px=1.3, depth=5.8, tone=0.70, shininess=36.0)
        star_rgb = shade_metal_relief(m_star, ramp, bevel_px=1.0, depth=4.5, tone=0.82, shininess=40.0)

        ang = np.arctan2(yy - cy, xx - cx)
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size * 0.37)
        facet = 0.5 + 0.5 * np.tanh(4.0 * np.sin(4.0 * ang + 0.4))
        if badge_char:
            c_dark = np.array([0.07, 0.24, 0.52], dtype=np.float32)
            c_lite = np.array([0.18, 0.52, 0.78], dtype=np.float32)
            glow_str = 0.28
        else:
            c_dark = np.array([0.16, 0.56, 0.86], dtype=np.float32)
            c_lite = np.array([0.45, 0.88, 0.98], dtype=np.float32)
            glow_str = 0.85

        gem_rgb = c_dark[None, None, :] * (1.0 - facet[..., None]) + c_lite[None, None, :] * facet[..., None]
        core_glow = np.exp(-((dist / 0.48) ** 2)) * glow_str
        gem_rgb = np.clip(gem_rgb + core_glow[..., None] * np.array([0.95, 0.96, 1.0]), 0.0, 1.0)

        shadow = np.roll(gaussian_blur_f(m_base, 3.2), 2, axis=0) * 0.72
        rgb, a = np.zeros((size, size, 3), dtype=np.float32), shadow
        rgb, a = porter_duff_over(gem_rgb, m_gem, rgb, a)
        rgb, a = porter_duff_over(bezel_rgb, m_bezel, rgb, a)
        if not badge_char:
            rgb, a = porter_duff_over(star_rgb, m_star, rgb, a)
        out_im = rgba_from_float(rgb, a)

        if badge_char:
            ch = badge_char.strip()[:1]
            k_im = render_modern_text(
                ch,
                font_name="ShipporiMincho-ExtraBold.ttf",
                font_size=33,
                max_w=46,
                max_lines=1,
                style_id="royal-gold-clean",
                palette=palette,
                vf_weight=800,
                norm_factors=norm_factors,
            )
            kx = int(round(cx - _measure_ink_center_x(k_im)))
            ky = int(round(cy - _measure_ink_center_y(k_im)))
            out_im.alpha_composite(k_im, (kx, ky))
        return out_im, cy

    else:
        size = 86
        ss = 4
        S = size * ss
        cx_s, cy_s = S * 0.5, S * 0.5

        def cubic_bezier(p0, p1, p2, p3, n=90):
            u = np.linspace(0.0, 1.0, n, endpoint=False)[:, None]
            return (
                ((1 - u) ** 3) * np.array(p0)
                + 3 * ((1 - u) ** 2) * u * np.array(p1)
                + 3 * (1 - u) * (u ** 2) * np.array(p2)
                + (u ** 3) * np.array(p3)
            )

        r_top = cubic_bezier((0.0, -0.42), (0.26, -1.00), (1.08, -0.84), (1.00, -0.06), 90)
        r_bot = cubic_bezier((1.00, -0.06), (0.92, 0.44), (0.38, 0.74), (0.0, 0.96), 90)
        l_bot = np.column_stack([-r_bot[::-1, 0], r_bot[::-1, 1]])
        l_top = np.column_stack([-r_top[::-1, 0], r_top[::-1, 1]])
        curve = np.vstack([r_top, r_bot, l_bot, l_top])
        hx, hy = curve[:, 0], curve[:, 1]
        hx = hx - (hx.min() + hx.max()) * 0.5
        hy = hy - (hy.min() + hy.max()) * 0.5
        scale_h = (S * 0.72) / max(hx.max() - hx.min(), hy.max() - hy.min())
        pts = [(float(cx_s + x * scale_h), float(cy_s + y * scale_h)) for x, y in zip(hx, hy)]

        im_h = Image.new("L", (S, S), 0)
        ImageDraw.Draw(im_h).polygon(pts, fill=255)
        m_heart = np.asarray(im_h, dtype=np.float32) / 255.0
        inside = m_heart >= 0.5
        d_out = distance_transform_edt(~inside).astype(np.float32)

        ys_in = np.where(inside)[0]
        heart_centroid_y = float(np.mean(ys_in)) / ss
        heart_box_cy = (float(ys_in.min()) + float(ys_in.max())) * 0.5 / ss

        yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
        c_out = hex_to_rgb01(palette["outline"])
        c_in = hex_to_rgb01(palette["inline"])

        y_min_h, y_max_h = float(ys_in.min()), float(ys_in.max())
        ty = np.clip((yy - y_min_h) / max(1.0, y_max_h - y_min_h), 0.0, 1.0)
        c_top = np.array([1.00, 0.58, 0.78], dtype=np.float32)
        c_bot = np.array([0.92, 0.22, 0.52], dtype=np.float32)
        h_rgb = c_top[None, None, :] * (1.0 - ty[..., None]) + c_bot[None, None, :] * ty[..., None]

        spec = np.exp(-(((xx - S * 0.34) / (S * 0.072)) ** 2 + ((yy - S * 0.32) / (S * 0.048)) ** 2)) * 0.82 * inside
        h_rgb = np.clip(h_rgb + spec[..., None], 0.0, 1.0)

        w_white = 3.8 * ss
        w_plum = (3.8 + 2.6) * ss
        m_white = np.maximum(m_heart, smoothstep(w_white + 0.8 * ss, w_white - 0.8 * ss, d_out))
        m_plum = np.maximum(m_white, smoothstep(w_plum + 0.8 * ss, w_plum - 0.8 * ss, d_out))
        shadow = np.roll(gaussian_filter(m_plum, sigma=2.4 * ss), 2 * ss, axis=0) * 0.28

        rgb, a = np.broadcast_to(c_out[None, None, :], (S, S, 3)), shadow
        rgb, a = porter_duff_over(np.broadcast_to(c_out[None, None, :], (S, S, 3)), m_plum, rgb, a)
        rgb, a = porter_duff_over(np.broadcast_to(c_in[None, None, :], (S, S, 3)), m_white, rgb, a)
        rgb, a = porter_duff_over(h_rgb, m_heart, rgb, a)

        out_im = rgba_from_float(rgb, a).resize((size, size), Image.Resampling.LANCZOS)

        if badge_char:
            ch = badge_char.strip()[:1]
            k_im = _render_pastel_medallion_char(ch, size=30, palette=palette, norm_factors=norm_factors)
            kx = int(round(size * 0.5 - _measure_ink_center_x(k_im)))
            ky = int(round(heart_centroid_y - _measure_ink_center_y(k_im)))
            out_im.alpha_composite(k_im, (kx, ky))

        return out_im, heart_box_cy


def render_modern_ssr_emblem(
    text: str,
    *,
    font_name: str,
    font_size: int,
    max_w: float,
    style_id: str,
    palette: Dict[str, str],
    tracking_em: float = 0.0,
    compress_x: float = 1.0,
    vf_weight: int = 700,
    opacity: float = 1.0,
    norm_factors: Optional[Dict[str, float]] = None,
) -> Image.Image:
    """左上 SSR エンブレム（Pattern A: 共通ハーフ座布団＋フィッシュテール＋文字オーバーハング）"""
    theme = "royal" if style_id == "royal-gold-clean" else "pastel"
    ssr_txt = render_modern_text(
        text,
        font_name=font_name,
        font_size=font_size,
        max_w=max_w,
        max_lines=1,
        style_id=style_id,
        palette=palette,
        tracking_em=tracking_em,
        compress_x=compress_x,
        vf_weight=vf_weight,
        opacity=opacity,
        norm_factors=norm_factors,
    )
    tw, th = ssr_txt.size
    z_w = tw + 56
    zab = render_shared_zabuton(z_w, SHARED_BAND_H, theme, palette, skew_px=15, fishtail_right=True)

    cw = max(zab.width, tw + 64)
    ch = max(zab.height, th + 20)
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    zx = (cw - zab.width) // 2
    zy = (ch - zab.height) // 2
    canvas.alpha_composite(zab, (zx, zy))

    band_cy = zy + ZABUTON_PAD + SHARED_BAND_H * 0.5
    tx = zx + (zab.width - tw) // 2 - 5
    ty = int(round(band_cy - _measure_ink_center_y(ssr_txt)))
    canvas.alpha_composite(ssr_txt, (max(0, tx), max(0, ty)))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    return tight_crop_rgba(arr[..., :3], arr[..., 3], pad=2)


def render_modern_attribute_badge(
    badge_char: str,
    label_text: str,
    *,
    style_id: str,
    palette: Dict[str, str],
    norm_factors: Optional[Dict[str, float]] = None,
) -> Image.Image:
    """右上 属性バッジ（Pattern C: 拡大メダリオン 1文字 ＋ 共通座布団ラベル帯）"""
    theme = "royal" if style_id == "plate-royal" else "pastel"
    med, med_cy = _render_attribute_medallion(theme, palette, badge_char=badge_char, norm_factors=norm_factors)

    clean_label = label_text.strip()
    if not clean_label:
        # ラベル空・バッジのみの場合はメダリオン単体を返す
        arr = np.asarray(med, dtype=np.float32) / 255.0
        return tight_crop_rgba(arr[..., :3], arr[..., 3], pad=2)

    is_ascii = all(ord(c) < 128 for c in clean_label)
    if theme == "royal":
        font_name = "Cinzel-VF.ttf" if is_ascii else "ShipporiMincho-ExtraBold.ttf"
        txt_style = "royal-gold-clean"
        tracking = 0.11 if is_ascii else 0.06
        fsize = 27 if is_ascii else 26
    else:
        font_name = "Outfit-VF.ttf" if is_ascii else "ZenMaruGothic-Black.ttf"
        txt_style = "pop-sticker-rose"
        tracking = 0.06 if is_ascii else 0.04
        fsize = 26 if is_ascii else 25

    t_lbl = render_modern_text(
        clean_label,
        font_name=font_name,
        font_size=fsize,
        max_w=196.0,
        max_lines=1,
        style_id=txt_style,
        palette=palette,
        tracking_em=tracking,
        vf_weight=800,
        norm_factors=norm_factors,
    )

    med_overlap = int(med.width * 0.42)
    z_w = max(176, t_lbl.width + med_overlap + 42)
    zab = render_shared_zabuton(z_w, SHARED_BAND_H, theme, palette, skew_px=15, fishtail_right=False)

    zab_x = int(med.width * 0.34)
    cw = zab_x + zab.width + 4
    ch = max(med.height, zab.height, t_lbl.height) + 12
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

    zab_y = (ch - zab.height) // 2
    band_cy = zab_y + ZABUTON_PAD + SHARED_BAND_H * 0.5
    canvas.alpha_composite(zab, (zab_x, zab_y))

    med_y = int(round(band_cy - med_cy))
    canvas.alpha_composite(med, (0, max(0, med_y)))

    area_left = med.width - 4
    area_right = zab_x + ZABUTON_PAD + z_w - (12 if theme == "royal" else 8)
    area_cx = (area_left + area_right) * 0.5
    tx = int(round(area_cx - _measure_ink_center_x(t_lbl)))
    ty = int(round(band_cy - _measure_ink_center_y(t_lbl)))
    canvas.alpha_composite(t_lbl, (max(0, tx), max(0, ty)))

    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    return tight_crop_rgba(arr[..., :3], arr[..., 3], pad=2)


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


def resolve_modern_plan(
    preset_name: str,
    typo_cfg: Dict[str, Any],
    orientation: str = "portrait",
) -> Dict[str, Any]:
    """4軸直交スキーマ (preset + font/style/palette/layout 個別上書き + fonts_custom + orientation) を解決する"""
    base = MODERN_PRESETS[preset_name]
    custom_mf = load_custom_fonts_manifest()
    land_ov_map = LANDSCAPE_SLOT_OVERRIDES.get(preset_name, {}) if orientation == "landscape" else {}

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
        if skey in land_ov_map:
            cur.update(land_ov_map[skey])
        cur["trackingExplicit"] = False
        # fonts_custom/fonts.json 上書き
        cur["font"] = resolve_slot_font(skey, cur["font"], custom_mf)
        # card-config.js 個別スロット上書き
        ov = font_slots_ov.get(skey)
        if isinstance(ov, dict):
            if isinstance(ov.get("family"), str) and ov["family"].strip():
                cur["font"] = ov["family"].strip()
            if isinstance(ov.get("trackingEm"), (int, float)):
                cur["trackingEm"] = float(ov["trackingEm"])
                cur["trackingExplicit"] = True
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
