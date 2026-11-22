"""
SSRGenerate — 文字ヒューマナイズ＆箔物理タイポグラフィ生成エンジン

InstantFilmFrame の書字キネマティクス（AR(1)慣性ドリフト・手首ピボット曲線・
文字種別リズム・cmap直接パース自動混植・微細シボ変調・ラメ粒子）および
rec-frame の実インク外接矩形タイトクロップを統合し、
SSRカード最前面オーバーレイ用の高精細透過PNG群を決定論的に生成する。

使い方:
  python scripts/render_typography.py
  python scripts/render_typography.py --preset handwritten-sign --wobble 45
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import functools
import json
import math
import os
from pathlib import Path
import random
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from _font_slots import (
    FONT_NORM_FACTORS as SHARED_NORM_FACTORS,
    get_cmap_chars,
    resolve_font_path,
)
from _typo_modern import (
    KINSOKU_HEAD,
    KINSOKU_TAIL,
    MODERN_PRESETS,
    adjust_short_title_tracking,
    compute_fitted_font_size,
    render_modern_attribute_badge,
    render_modern_ssr_emblem,
    render_modern_text,
    render_royal_diamond_rule,
    resolve_modern_plan,
    wrap_lines_kinsoku,
)
from _utils import (
    FONTS_DIR,
    GOLD_RAMP,
    OUT_DIR,
    PROJECT_ROOT,
    SILVER_RAMP,
    LayoutSpec,
    apply_config_overrides,
    format_attribute_key_text,
    gaussian_blur_f,
    generate_micro_emboss_height,
    load_card_config,
    make_linear_gradient,
    parse_attribute_parts,
    polygon_mask,
    porter_duff_over,
    resolve_layout,
    resolve_photo_path,
    resolve_seed,
    save_png,
    shade_metal_relief,
    smoothstep,
    sync_html_resolution,
    tight_crop_rgba,
)

# 昇格カットイン専用固定スタイル（カード側プリセットやレイアウト切替の影響を一切受けない）
CUTIN_STYLE: Dict[str, Dict[str, Any]] = {
    "cutinMain": {"font": "YujiSyuku-Regular.ttf", "material": "foil-gold",      "stamp": False, "wobble_mul": 0.65},
}
CUTIN_WOBBLE_NORM = 0.28
CUTIN_FOIL_GLITTER = 0.42
CUTIN_PAPER_GRAIN = 0.35

FALLBACK_FONT_FILE = "ZenMaruGothic-Bold.ttf"

# 書体別・視覚サイズ正規化係数（_font_slots.py の実測値と同期。カットインのみ従来互換係数を使用）
FONT_NORM_FACTORS: Dict[str, float] = SHARED_NORM_FACTORS
CUTIN_NORM_FACTORS: Dict[str, float] = {**SHARED_NORM_FACTORS, "cinecaption.ttf": 1.04}

# 書体別キネマティクスプロファイル
FONT_KINEMATICS: Dict[str, Dict[str, float]] = {
    "YujiSyuku-Regular.ttf": {
        "arc_mul": 0.65, "rot_mul": 0.60, "dy_mul": 0.55, "dx_mul": 0.45, "scale_mul": 0.45, "tilt_mul": 0.60,
    },
    "KleeOne-Regular.ttf": {
        "arc_mul": 0.55, "rot_mul": 0.50, "dy_mul": 0.48, "dx_mul": 0.45, "scale_mul": 0.35, "tilt_mul": 0.55,
    },
    "cinecaption.ttf": {
        "arc_mul": 0.45, "rot_mul": 0.40, "dy_mul": 0.40, "dx_mul": 0.35, "scale_mul": 0.30, "tilt_mul": 0.45,
    },
    "SetoFont.ttf": {
        "arc_mul": 0.85, "rot_mul": 1.10, "dy_mul": 1.05, "dx_mul": 0.80, "scale_mul": 1.10, "tilt_mul": 0.85,
    },
    "TekitouPoem.ttf": {
        "arc_mul": 0.90, "rot_mul": 0.95, "dy_mul": 0.95, "dx_mul": 0.85, "scale_mul": 0.95, "tilt_mul": 0.90,
    },
    "TekitouPoem_Bold.ttf": {
        "arc_mul": 0.90, "rot_mul": 0.95, "dy_mul": 0.95, "dx_mul": 0.85, "scale_mul": 0.95, "tilt_mul": 0.90,
    },
    "ZenKurenaido-Regular.ttf": {
        "arc_mul": 0.85, "rot_mul": 0.90, "dy_mul": 0.85, "dx_mul": 0.75, "scale_mul": 0.80, "tilt_mul": 0.85,
    },
}

STAMP_KINEMATICS: Dict[str, float] = {
    "arc_mul": 0.00, "rot_mul": 0.08, "dy_mul": 0.12, "dx_mul": 0.05, "scale_mul": 0.04, "tilt_mul": 0.25,
}

# 質感スタイルプリセット定義
TYPO_PRESETS: Dict[str, Dict[str, Any]] = {
    "foil-brush": {
        "ssr":       {"font": "YujiSyuku-Regular.ttf", "material": "foil-gold",      "stamp": True,  "wobble_mul": 0.35},
        "attribute": {"font": "KleeOne-Regular.ttf",   "material": "foil-champagne", "stamp": True,  "wobble_mul": 0.30},
        "subtitle":  {"font": "KleeOne-Regular.ttf",   "material": "foil-champagne", "stamp": False, "wobble_mul": 0.85},
        "title":     {"font": "YujiSyuku-Regular.ttf", "material": "foil-gold",      "stamp": False, "wobble_mul": 1.00},
        "flavor":    {"font": "KleeOne-Regular.ttf",   "material": "ink-ivory",      "stamp": False, "wobble_mul": 0.75},
        "cardNo":    {"font": "cinecaption.ttf",       "material": "foil-silver",    "stamp": True,  "wobble_mul": 0.40},
        "cutinMain": {"font": "YujiSyuku-Regular.ttf", "material": "foil-gold",      "stamp": False, "wobble_mul": 0.65},
    },
    "handwritten-sign": {
        "ssr":       {"font": "TekitouPoem_Bold.ttf",     "material": "foil-gold",      "stamp": True,  "wobble_mul": 0.45},
        "attribute": {"font": "SetoFont.ttf",             "material": "foil-champagne", "stamp": True,  "wobble_mul": 0.40},
        "subtitle":  {"font": "SetoFont.ttf",             "material": "foil-champagne", "stamp": False, "wobble_mul": 1.00},
        "title":     {"font": "TekitouPoem_Bold.ttf",     "material": "ink-posca",      "stamp": False, "wobble_mul": 1.05},
        "flavor":    {"font": "TekitouPoem.ttf",          "material": "ink-ivory",      "stamp": False, "wobble_mul": 0.90},
        "cardNo":    {"font": "ZenKurenaido-Regular.ttf", "material": "foil-silver",    "stamp": False, "wobble_mul": 0.65},
        "cutinMain": {"font": "TekitouPoem_Bold.ttf",     "material": "foil-gold",      "stamp": False, "wobble_mul": 0.75},
    },
    "crisp-emboss": {
        "ssr":       {"font": "cinecaption.ttf",       "material": "foil-gold",      "stamp": True,  "wobble_mul": 0.25},
        "attribute": {"font": "cinecaption.ttf",       "material": "foil-champagne", "stamp": True,  "wobble_mul": 0.25},
        "subtitle":  {"font": "cinecaption.ttf",       "material": "foil-champagne", "stamp": False, "wobble_mul": 0.50},
        "title":     {"font": "KleeOne-Regular.ttf",   "material": "foil-gold",      "stamp": False, "wobble_mul": 0.60},
        "flavor":    {"font": "KleeOne-Regular.ttf",   "material": "ink-ivory",      "stamp": False, "wobble_mul": 0.50},
        "cardNo":    {"font": "cinecaption.ttf",       "material": "foil-silver",    "stamp": True,  "wobble_mul": 0.25},
        "cutinMain": {"font": "KleeOne-Regular.ttf",   "material": "foil-gold",      "stamp": False, "wobble_mul": 0.45},
    },
}

# マテリアル（箔・インク）物理プロファイル
MATERIALS: Dict[str, Dict[str, Any]] = {
    "foil-gold": {
        "stops": [(255, 253, 240), (254, 240, 138), (245, 168, 28), (253, 224, 71), (255, 250, 220)],
        "unevenness": 0.14,
        "glitter_mul": 1.0,
        "halo_alpha": 0.58,
        "halo_radius": 6.5,
    },
    "foil-champagne": {
        "stops": [(255, 251, 235), (253, 230, 138), (245, 196, 81), (254, 243, 199)],
        "unevenness": 0.10,
        "glitter_mul": 0.45,
        "halo_alpha": 0.55,
        "halo_radius": 5.0,
    },
    "foil-silver": {
        "stops": [(255, 255, 255), (226, 232, 240), (186, 198, 214), (248, 250, 252)],
        "unevenness": 0.16,
        "glitter_mul": 0.65,
        "halo_alpha": 0.50,
        "halo_radius": 4.0,
    },
    "ink-ivory": {
        "stops": [(248, 244, 234), (241, 245, 249)],
        "unevenness": 0.08,
        "glitter_mul": 0.0,
        "halo_alpha": 0.62,
        "halo_radius": 5.5,
    },
    "ink-posca": {
        "stops": [(255, 255, 255), (248, 250, 252)],
        "unevenness": 0.06,
        "glitter_mul": 0.25,
        "halo_alpha": 0.60,
        "halo_radius": 6.0,
    },
}


def get_font_supported_chars(font_file: str) -> Set[int]:
    """fonts_custom/ → fonts/ → Windows/Fonts の順で解決したフォントの収録 Unicode コードポイント集合を返す"""
    font_path = resolve_font_path(font_file)
    if font_path is None:
        return set()
    return get_cmap_chars(str(font_path))


@functools.lru_cache(maxsize=64)
def get_font(font_file: str, size: int) -> ImageFont.FreeTypeFont:
    p = resolve_font_path(font_file)
    if p is not None:
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            pass
    fb = FONTS_DIR / FALLBACK_FONT_FILE
    if fb.is_file():
        return ImageFont.truetype(str(fb), size)
    return ImageFont.load_default()


def classify_char(ch: str) -> str:
    code = ord(ch)
    if (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF):
        return "kanji"
    if (0x3040 <= code <= 0x309F) or (0x30A0 <= code <= 0x30FF):
        return "kana"
    if ch in "!?:;\"'.,~！？♡♥☆★♪〜・…【】「」":
        return "punct"
    return "other"


def measure_text_width(text: str, primary_font_file: str, primary_size: int) -> float:
    p_chars = get_font_supported_chars(primary_font_file)
    f_chars = get_font_supported_chars(FALLBACK_FONT_FILE)
    p_norm = FONT_NORM_FACTORS.get(primary_font_file, 1.0)
    f_norm = FONT_NORM_FACTORS.get(FALLBACK_FONT_FILE, 1.05)
    fb_size = max(8, int(round(primary_size * (f_norm / max(0.5, p_norm)))))
    p_font = get_font(primary_font_file, primary_size)
    f_font = get_font(FALLBACK_FONT_FILE, fb_size)

    total = 0.0
    for ch in text:
        code = ord(ch)
        if p_chars and (code in p_chars):
            cur = p_font
        elif (not f_chars) or (code in f_chars):
            cur = f_font
        else:
            continue
        try:
            total += float(cur.getlength(ch))
        except Exception:
            bb = cur.getbbox(ch)
            total += float(bb[2] - bb[0]) if bb else float(cur.size * 0.5)
    return total


def wrap_text_lines(text: str, font_file: str, font_size: int, max_w: float, max_lines: int = 2) -> List[str]:
    """長文を安全に折り返す（明示改行・前後禁則・日本語句読点・スペース優先）"""
    return wrap_lines_kinsoku(
        text=text,
        max_w=max_w,
        max_lines=max_lines,
        measure_fn=lambda s: measure_text_width(s, font_file, font_size),
    )


def render_humanized_line(
    text: str,
    font_file: str,
    font_size: int,
    max_w: float,
    wobble_strength: float,
    is_stamp: bool,
    seed: int,
    norm_factors: Optional[Dict[str, float]] = None,
) -> Optional[Image.Image]:
    """
    1行分の文字をヒューマナイズ運動モデル（手首曲線 + AR(1)慣性 + 文字種別リズム + 充填率ダンピング）
    でアルファマスク（Lモード）として描画する。
    """
    clean = text.strip()
    if not clean:
        return None

    nf = norm_factors or FONT_NORM_FACTORS
    w = max(0.0, min(1.0, float(wobble_strength)))
    rng = random.Random(seed & 0xFFFFFFFF)

    kin = STAMP_KINEMATICS.copy() if is_stamp else FONT_KINEMATICS.get(font_file, FONT_KINEMATICS["YujiSyuku-Regular.ttf"]).copy()
    arc_mul = kin["arc_mul"]
    rot_mul = kin["rot_mul"]
    dy_mul = kin["dy_mul"]
    dx_mul = kin["dx_mul"]
    scale_mul = kin["scale_mul"]
    tilt_mul = kin["tilt_mul"]

    # 自動縮小（Auto-fit）
    cur_size = font_size
    pad_est = max(8, int(cur_size * 0.3))
    w_raw = measure_text_width(clean, font_file, cur_size)
    if w_raw + pad_est > max_w and w_raw > 1.0:
        cur_size = max(14, int(cur_size * ((max_w - pad_est) / w_raw)))

    p_norm = nf.get(font_file, 1.0)
    f_norm = nf.get(FALLBACK_FONT_FILE, 1.05)
    eff_size = max(12, int(round(cur_size * p_norm)))
    fb_size = max(10, int(round(eff_size * (f_norm / max(0.5, p_norm)))))

    p_chars = get_font_supported_chars(font_file)
    f_chars = get_font_supported_chars(FALLBACK_FONT_FILE)
    p_font = get_font(font_file, eff_size)
    f_font = get_font(FALLBACK_FONT_FILE, fb_size)

    try:
        ascent, descent = p_font.getmetrics()
    except Exception:
        ascent, descent = int(eff_size * 0.8), int(eff_size * 0.2)

    extra_pad_y = max(10, int(round(eff_size * 0.5 * w + 10)))
    line_h_ref = ascent + descent + max(14, int(eff_size * 0.4)) + extra_pad_y * 2
    base_y_offset = extra_pad_y + max(6, int(eff_size * 0.2))

    parsed = []
    total_advance = 0.0
    for ch in clean:
        code = ord(ch)
        if p_chars and (code in p_chars):
            cur_font = p_font
        elif (not f_chars) or (code in f_chars):
            cur_font = f_font
        else:
            continue
        try:
            adv = float(cur_font.getlength(ch))
        except Exception:
            bb = cur_font.getbbox(ch)
            adv = float(bb[2] - bb[0]) if bb else float(cur_font.size * 0.5)
        is_sp = ch.isspace()
        bb = cur_font.getbbox(ch) if not is_sp else None
        parsed.append({
            "char": ch,
            "font": cur_font,
            "advance": adv,
            "bbox": bb,
            "is_space": is_sp,
            "type": classify_char(ch),
            "cum_x": total_advance,
        })
        total_advance += adv

    if not parsed or total_advance <= 0:
        return None

    # 充填率連動ダンピング（長文ほどマクロ揺れを抑えて可読性・収まりを保つ）
    fill_ratio = total_advance / max(1.0, max_w)
    fill_damp = max(0.32, 1.0 - 0.55 * (min(1.0, fill_ratio) ** 1.3))

    wrist_span = max(float(eff_size) * 8.5, 140.0)
    len_gate = max(0.0, min(1.0, (total_advance - eff_size * 0.8) / max(1.0, eff_size * 2.5)))
    arc_amp = rng.uniform(-0.11, 0.11) * fill_damp
    wave_amp = rng.uniform(-0.04, 0.04) * fill_damp
    wave_phase = rng.uniform(0.0, math.pi * 2)

    ar_dy = 0.0
    ar_rot = 0.0
    ar_scale = 0.0

    char_images = []
    total_w = 0
    max_h = 0

    for item in parsed:
        ch = item["char"]
        cur_font = item["font"]
        adv = item["advance"]
        bbox = item["bbox"]
        c_type = item["type"]

        if item["is_space"] or bbox is None or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            ar_dy *= 0.25
            ar_rot *= 0.25
            ar_scale *= 0.25
            sp_w = max(4, int(round(adv)))
            char_images.append((None, sp_w, 0.0))
            total_w += sp_w
            continue

        char_cx = item["cum_x"] + adv * 0.5
        u = (char_cx - total_advance * 0.5) / wrist_span

        if w > 0.001 and len_gate > 0.0:
            curve_dy = (arc_amp * (u ** 2) + wave_amp * math.sin(math.pi * u * 1.5 + wave_phase)) * float(eff_size) * w * arc_mul * len_gate
            d_dy_dx = (2.0 * arc_amp * u + wave_amp * (math.pi * 1.5) * math.cos(math.pi * u * 1.5 + wave_phase)) * (float(eff_size) / wrist_span) * w * arc_mul * len_gate
            tangent_deg = math.degrees(math.atan(d_dy_dx))
        else:
            curve_dy = 0.0
            tangent_deg = 0.0

        ar_dy = 0.55 * ar_dy + 0.45 * rng.uniform(-1.0, 1.0)
        ar_rot = 0.45 * ar_rot + 0.55 * rng.uniform(-1.0, 1.0)
        ar_scale = 0.50 * ar_scale + 0.50 * rng.uniform(-1.0, 1.0)

        if c_type == "kanji":
            rot_mod, dy_mod, scale_add = 0.75, 0.75, 0.012 * w
        elif c_type == "kana":
            rot_mod, dy_mod, scale_add = 1.00, 1.00, -0.012 * w
        elif c_type == "punct":
            rot_mod, dy_mod, scale_add = 1.30, 1.20, 0.024 * w
        else:
            rot_mod, dy_mod, scale_add = 1.00, 1.00, 0.0

        if w > 0.001:
            char_rot = tangent_deg + ar_rot * 2.0 * rot_mod * rot_mul * w
            char_dy = curve_dy + ar_dy * (0.030 * float(eff_size)) * dy_mod * dy_mul * w
            char_dx = rng.uniform(-0.020, 0.025) * float(eff_size) * dx_mul * w
            char_scale = max(0.88, min(1.12, 1.0 + (ar_scale * 0.030 * scale_mul + scale_add) * w))
        else:
            char_rot, char_dy, char_dx, char_scale = 0.0, 0.0, 0.0, 1.0

        pad_x = max(8, int(cur_font.size * 0.4))
        gw = bbox[2] - bbox[0]
        cw = max(int(round(adv)), gw) + pad_x * 2
        ch_h = line_h_ref

        tmp = Image.new("L", (cw, ch_h), 0)
        d = ImageDraw.Draw(tmp)
        draw_x = pad_x - bbox[0]
        glyph_cx = draw_x + (bbox[0] + bbox[2]) * 0.5
        glyph_base_y = base_y_offset + ascent
        # 異なる ascent を持つフォント同士の混植時に約30px浮くのを防ぐためベースライン基準 (anchor="ls") で描画
        d.text((draw_x, glyph_base_y), ch, fill=255, font=cur_font, anchor="ls")

        if abs(char_rot) > 0.08:
            tmp = tmp.rotate(char_rot, resample=Image.Resampling.BICUBIC, expand=False, center=(glyph_cx, glyph_base_y))

        if abs(char_scale - 1.0) > 0.012:
            nw = max(2, int(round(cw * char_scale)))
            nh = max(2, int(round(ch_h * char_scale)))
            resized = tmp.resize((nw, nh), resample=Image.Resampling.BICUBIC)
            ox = int(round((nw - cw) * (glyph_cx / max(1.0, float(cw)))))
            oy = int(round((nh - ch_h) * (glyph_base_y / max(1.0, float(ch_h)))))
            tmp = Image.new("L", (cw, ch_h), 0)
            tmp.paste(resized, (-ox, -oy))

        step_w = max(2, int(round(adv + char_dx)))
        total_w += step_w
        max_h = max(max_h, ch_h)
        char_images.append((tmp, step_w, char_dy))

    if not char_images or total_w <= 0:
        return None

    margin_x = max(24, int(eff_size * 0.8))
    margin_y = max(24, int(eff_size * 0.6))
    canvas = Image.new("L", (total_w + margin_x * 2, max_h + margin_y * 2), 0)

    curr_x = margin_x
    for img_c, step_w, dy in char_images:
        if img_c is not None:
            px = int(round(curr_x))
            py = int(round(margin_y + dy))
            # マスクの最大値合成
            region = canvas.crop((px, py, px + img_c.width, py + img_c.height))
            merged = Image.fromarray(np.maximum(np.array(region), np.array(img_c)), mode="L")
            canvas.paste(merged, (px, py))
        curr_x += step_w

    # 行全体の微小傾斜
    raw_tilt = rng.uniform(-1.6, 1.6) * w * tilt_mul * fill_damp if w > 0.001 else 0.0
    if abs(raw_tilt) > 0.08:
        canvas = canvas.rotate(raw_tilt, resample=Image.Resampling.BICUBIC, expand=True)

    # 実インクタイトクロップ
    arr = np.array(canvas, dtype=np.uint8)
    ys, xs = np.where(arr > 4)
    if len(ys) == 0:
        return None
    pad_crop = 2
    y0 = max(0, int(ys.min()) - pad_crop)
    y1 = min(arr.shape[0], int(ys.max()) + pad_crop + 1)
    x0 = max(0, int(xs.min()) - pad_crop)
    x1 = min(arr.shape[1], int(xs.max()) + pad_crop + 1)
    return canvas.crop((x0, y0, x1, y1))


def apply_foil_and_grain_material(
    mask_l: Image.Image,
    material_name: str,
    foil_glitter: float,
    paper_grain: float,
    is_stamp: bool,
    seed: int,
) -> Image.Image:
    """
    アルファマスクに対し、金属箔グラデ・ラメ粒子・筆記/印圧ムラ・微細シボ変調・
    写真上可読性保護のソフト暗色ハローを適用し、実インク基準でタイトクロップした RGBA 画像を返す。
    """
    mat = MATERIALS.get(material_name, MATERIALS["foil-gold"])
    halo_pad = int(math.ceil(mat["halo_radius"] * 3.0)) + 4
    w_in, h_in = mask_l.size
    w = w_in + halo_pad * 2
    h = h_in + halo_pad * 2

    padded_mask = Image.new("L", (w, h), 0)
    padded_mask.paste(mask_l, (halo_pad, halo_pad))
    alpha = np.array(padded_mask, dtype=np.float32) / 255.0

    np_rng = np.random.default_rng(seed & 0xFFFFFFFF)

    # 1. 金属箔 / インクグラデーション
    rgb = make_linear_gradient(h, w, mat["stops"], angle_deg=126.0)

    # 2. 筆記濃度ムラ / スタンプ片当たり印圧ムラ
    uneven = float(mat["unevenness"])
    if uneven > 0:
        noise = np_rng.uniform(1.0 - uneven * 0.7, 1.0 + uneven * 0.4, (h, w)).astype(np.float32)
        rgb = np.clip(rgb * noise[:, :, None], 0.0, 1.0)
        if is_stamp:
            sx = np_rng.uniform(-0.10, 0.10)
            sy = np_rng.uniform(-0.08, 0.08)
            gx = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
            gy = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
            alpha = np.clip(alpha * np.clip(1.0 + gx * sx + gy * sy, 0.78, 1.10), 0.0, 1.0)

    # 3. 微細シボ高さマップによるインク/箔の乗り変調（AI Slop のベタ塗り感除去）
    if paper_grain > 0.01:
        emboss_h = generate_micro_emboss_height(h, w, np_rng)
        grain_mod = np.clip(1.0 + emboss_h * (0.14 * paper_grain), 0.78, 1.06)
        alpha = np.clip(alpha * grain_mod, 0.0, 1.0)
        # 箔表面の微細凹凸光沢
        rgb = np.clip(rgb * (1.0 + emboss_h[:, :, None] * (0.045 * paper_grain)), 0.0, 1.0)

    # 4. 金属ラメ粒子（Glitter）
    eff_glitter = foil_glitter * float(mat["glitter_mul"])
    if eff_glitter > 0.01:
        sparkle_raw = (np_rng.uniform(0.0, 1.0, (h, w)) > 0.935).astype(np.float32)
        sparkle = sparkle_raw * eff_glitter * np.clip(alpha * 1.4, 0.0, 1.0)
        rgb = np.clip(rgb + sparkle[:, :, None], 0.0, 1.0)

    # 5. 写真上の可読性保護ソフト暗色ハロー（過剰な黒縁ではなく自然な浮き出し影）
    halo_r = float(mat["halo_radius"])
    halo_a = float(mat["halo_alpha"])
    halo_mask_pil = padded_mask.filter(ImageFilter.GaussianBlur(radius=halo_r))
    halo_alpha = (np.array(halo_mask_pil, dtype=np.float32) / 255.0) * halo_a
    # わずかに下方向へオフセット（自然な光学ドロップシャドウ）
    halo_alpha = np.roll(halo_alpha, shift=2, axis=0)
    halo_alpha[:2, :] = 0.0

    # Porter-Duff Over: 前景(rgb, alpha) を 暗色ハロー(ごく深い紺黒 #050814, halo_alpha) の上に合成
    halo_rgb = np.broadcast_to(np.array([5 / 255.0, 8 / 255.0, 20 / 255.0], dtype=np.float32), (h, w, 3))
    out_rgb, out_alpha = porter_duff_over(rgb, alpha, halo_rgb, halo_alpha)

    # 6. 最終タイトクロップ
    return tight_crop_rgba(out_rgb, out_alpha)


def render_multiline_block(
    text: str,
    font_file: str,
    font_size: int,
    max_w: float,
    max_lines: int,
    material_name: str,
    wobble_strength: float,
    foil_glitter: float,
    paper_grain: float,
    is_stamp: bool,
    seed: int,
    norm_factors: Optional[Dict[str, float]] = None,
) -> Optional[Image.Image]:
    """単一行または複数行テキストを描画・縦結合し、マテリアル物理を適用して RGBA を返す"""
    lines = wrap_text_lines(text, font_file, font_size, max_w=max_w, max_lines=max_lines)
    if not lines:
        return None

    line_masks: List[Image.Image] = []
    for idx, ln in enumerate(lines):
        m = render_humanized_line(
            text=ln,
            font_file=font_file,
            font_size=font_size,
            max_w=max_w,
            wobble_strength=wobble_strength,
            is_stamp=is_stamp,
            seed=seed + idx * 131,
            norm_factors=norm_factors,
        )
        if m is not None:
            line_masks.append(m)

    if not line_masks:
        return None

    if len(line_masks) == 1:
        combined_mask = line_masks[0]
    else:
        gap = max(8, int(font_size * 0.35))
        total_w = max(m.width for m in line_masks)
        total_h = sum(m.height for m in line_masks) + gap * (len(line_masks) - 1)
        combined_mask = Image.new("L", (total_w, total_h), 0)
        cy = 0
        for m in line_masks:
            cx = (total_w - m.width) // 2
            combined_mask.paste(m, (cx, cy))
            cy += m.height + gap

    return apply_foil_and_grain_material(
        mask_l=combined_mask,
        material_name=material_name,
        foil_glitter=foil_glitter,
        paper_grain=paper_grain,
        is_stamp=is_stamp,
        seed=seed + 997,
    )


_over = porter_duff_over
_tight_crop = tight_crop_rgba


def render_rarity_crest(
    text: str,
    font_file: str,
    foil_glitter: float,
    paper_grain: float,
    seed: int,
) -> Optional[Image.Image]:
    """
    レアリティ（SSR等）用の脱Web UIクレスト:
    角丸ボックスを廃し、背後の鋭角ダーククリスタル座布団＋上下の金属ピンライン＋
    菱形スター＋3D押し出しベベル付きの金属箔文字を1枚の透過PNGに統合する。
    """
    mask_l = render_humanized_line(text, font_file, 108, max_w=340.0, wobble_strength=0.06, is_stamp=True, seed=seed)
    if mask_l is None:
        return None
    # stroke_width 相当で文字をわずかに太らせ、3Dベベルのハイライト面積を確保する
    mask_arr = gaussian_blur_f(np.asarray(mask_l, dtype=np.float32) / 255.0, 0.9)
    mask_l = Image.fromarray((np.clip((mask_arr - 0.16) / 0.62, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), mode="L")
    tw, th = mask_l.size
    pad_l, pad_r, pad_y = 64, 52, 26
    W, H = tw + pad_l + pad_r, th + pad_y * 2
    cy = H * 0.5

    # 1. 背後の斜めカット暗色座布団（文字より一段低く、右端へ開くシャープな帯）
    sh_y0, sh_y1 = pad_y + 12, H - pad_y - 10
    pts_outer = [(20, sh_y0), (W - 6, sh_y0), (W - 24, sh_y1), (8, sh_y1)]
    pts_inner = [(23, sh_y0 + 2.6), (W - 10, sh_y0 + 2.6), (W - 27, sh_y1 - 2.6), (11, sh_y1 - 2.6)]
    m_out = polygon_mask(W, H, pts_outer, ss=3)
    m_in = polygon_mask(W, H, pts_inner, ss=3)
    m_rim = np.clip(m_out - m_in, 0.0, 1.0)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    x_fade = np.clip(1.25 - (xx / W) * 0.60, 0.30, 1.0)
    sh_grad = np.clip((yy - sh_y0) / max(1.0, float(sh_y1 - sh_y0)), 0.0, 1.0)
    body_rgb = (
        np.array([0.075, 0.095, 0.22])[None, None, :] * (1.0 - sh_grad[..., None])
        + np.array([0.020, 0.028, 0.078])[None, None, :] * sh_grad[..., None]
    )
    diag = np.exp(-(((xx - W * 0.38) * 0.7 + (yy - cy)) / 18.0) ** 2) * 0.14
    body_rgb = np.clip(body_rgb + diag[..., None] * np.array([0.95, 0.80, 0.48]), 0.0, 1.0)
    body_a = m_in * 0.80 * x_fade

    # 2. 金属リム＋左端の4芒星クレスト＋右端のアクセント菱形
    star_cx, star_cy = 24.0, cy
    star_pts = []
    for i in range(8):
        a = math.radians(-90 + i * 45)
        r = (21.0 if i % 2 == 0 else 6.4) if i % 4 == 0 else (12.5 if i % 2 == 0 else 6.4)
        star_pts.append((star_cx + math.cos(a) * r, star_cy + math.sin(a) * r))
    m_star = polygon_mask(W, H, star_pts, ss=3)
    r_cx = W - 18.0
    m_r_gem = polygon_mask(W, H, [(r_cx, cy - 5.5), (r_cx + 5.5, cy), (r_cx, cy + 5.5), (r_cx - 5.5, cy)], ss=3)
    m_metal_deco = np.clip(m_rim * x_fade + m_star + m_r_gem, 0.0, 1.0)
    deco_rgb = shade_metal_relief(m_metal_deco, GOLD_RAMP, bevel_px=1.2, depth=5.0, tone=0.68, shininess=34.0)

    # 座布団＋装飾の落ち影
    bg_shadow = np.roll(np.roll(gaussian_blur_f(np.maximum(m_out * x_fade, m_star), 6.0), 4, axis=0), 3, axis=1) * 0.72
    rgb, a = np.zeros((H, W, 3), dtype=np.float32), bg_shadow
    rgb, a = _over(body_rgb, body_a, rgb, a)
    rgb, a = _over(deco_rgb, m_metal_deco, rgb, a)

    # 3. 箔文字本体（3D押し出し側面＋立体ベベル金属面＋ラメ）
    t_canvas = Image.new("L", (W, H), 0)
    t_canvas.paste(mask_l, (pad_l, pad_y))
    t_mask = np.asarray(t_canvas, dtype=np.float32) / 255.0

    # 右下への3D押し出し（深みのあるブロンズ金側面）
    ext = np.zeros_like(t_mask)
    for step in range(1, 6):
        ext = np.maximum(ext, np.roll(np.roll(t_mask, step, axis=0), step, axis=1))
    ext = np.clip(ext * (1.0 - t_mask), 0.0, 1.0)
    ext_rgb = shade_metal_relief(ext + t_mask * 0.5, GOLD_RAMP, bevel_px=1.0, depth=3.0, tone=0.28, shininess=18.0)

    # 文字背面の暖色バックグロー＋落ち影
    t_glow = gaussian_blur_f(t_mask, 9.0) * 0.42
    t_shadow = np.roll(np.roll(gaussian_blur_f(np.maximum(t_mask, ext), 4.5), 4, axis=0), 3, axis=1) * 0.85
    rgb, a = _over(np.zeros_like(rgb), t_shadow, rgb, a)
    rgb, a = _over(np.broadcast_to(np.array([0.95, 0.75, 0.35], dtype=np.float32), (H, W, 3)), t_glow, rgb, a)
    rgb, a = _over(ext_rgb, ext, rgb, a)

    # 文字表面：高輝度シャンパン〜白金寄りの金属レリーフ＋シボ＋ラメ
    rng = np.random.default_rng((seed * 2654435761 + 19) & 0xFFFFFFFF)
    v_tone = np.clip(0.92 - ((yy - pad_y) / max(1.0, float(th))) * 0.24, 0.62, 0.95)
    face_rgb = shade_metal_relief(t_mask, GOLD_RAMP, bevel_px=1.8, depth=5.5, tone_map=v_tone, shininess=24.0)
    if paper_grain > 0.01:
        emb = generate_micro_emboss_height(H, W, rng)
        face_rgb = np.clip(face_rgb * (1.0 + emb[..., None] * (0.04 * paper_grain)), 0.0, 1.0)
    if foil_glitter > 0.01:
        sp = (rng.uniform(0.0, 1.0, (H, W)) > 0.945).astype(np.float32) * foil_glitter * t_mask
        face_rgb = np.clip(face_rgb + sp[..., None], 0.0, 1.0)

    rgb, a = _over(face_rgb, t_mask, rgb, a)
    return _tight_crop(rgb, a)


def render_attribute_plate(
    text: str,
    font_file: str,
    foil_glitter: float,
    paper_grain: float,
    seed: int,
) -> Optional[Image.Image]:
    """
    属性タグ用の鋭角クリスタル・金属刻印プレート（角丸ピルを廃止）:
    六角カットのダーククリスタル座布団＋シャンパン金の面取りリム＋左端のプリズム結晶ジェム＋箔テキスト。
    """
    foil_txt = render_multiline_block(
        text=text,
        font_file=font_file,
        font_size=26,
        max_w=300.0,
        max_lines=1,
        material_name="foil-champagne",
        wobble_strength=0.05,
        foil_glitter=foil_glitter,
        paper_grain=paper_grain,
        is_stamp=True,
        seed=seed,
    )
    if foil_txt is None:
        return None
    tw, th = foil_txt.size
    pad_l, pad_r, pad_y = 50, 28, 12
    bh = max(48, th + pad_y * 2)
    bw = tw + pad_l + pad_r
    margin = 14
    W, H = bw + margin * 2, bh + margin * 2
    x0, y0 = float(margin), float(margin)
    x1, y1 = x0 + bw, y0 + bh
    cy = (y0 + y1) * 0.5
    c = (y1 - y0) * 0.36  # 斜めカット量

    def hex_pts(inset: float) -> List[Tuple[float, float]]:
        k = inset * 0.7
        return [
            (x0 + c + k, y0 + inset),
            (x1 - c - k, y0 + inset),
            (x1 - inset, cy),
            (x1 - c - k, y1 - inset),
            (x0 + c + k, y1 - inset),
            (x0 + inset, cy),
        ]

    m_out = polygon_mask(W, H, hex_pts(0.0), ss=3)
    m_in = polygon_mask(W, H, hex_pts(2.8), ss=3)
    m_rim = np.clip(m_out - m_in, 0.0, 1.0)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t_y = np.clip((yy - y0) / max(1.0, float(bh)), 0.0, 1.0)
    body_rgb = (
        np.array([0.085, 0.110, 0.25])[None, None, :] * (1.0 - t_y[..., None])
        + np.array([0.024, 0.032, 0.086])[None, None, :] * t_y[..., None]
    )
    sheen = np.exp(-(((xx - W * 0.45) * 0.5 + (yy - cy)) / 14.0) ** 2) * 0.16
    body_rgb = np.clip(body_rgb + sheen[..., None] * np.array([0.85, 0.78, 0.55]), 0.0, 1.0)
    body_a = m_in * 0.84

    rim_rgb = shade_metal_relief(m_rim, GOLD_RAMP, bevel_px=1.0, depth=4.5, tone=0.66, shininess=32.0)

    # 左端の菱形クリスタルジェム
    gx = x0 + c + 15.0
    r_g = 8.0
    m_gem = polygon_mask(W, H, [(gx, cy - r_g), (gx + r_g, cy), (gx, cy + r_g), (gx - r_g, cy)], ss=3)
    m_gem_in = polygon_mask(W, H, [(gx, cy - 4.5), (gx + 4.5, cy), (gx, cy + 4.5), (gx - 4.5, cy)], ss=3)
    gem_rim = np.clip(m_gem - m_gem_in, 0.0, 1.0)
    gem_rim_rgb = shade_metal_relief(gem_rim, GOLD_RAMP, bevel_px=0.8, depth=4.0, tone=0.70)
    # ジェム中心はプリズムシアン〜シャンパンの発光核
    d_gem = np.sqrt((xx - gx) ** 2 + (yy - cy) ** 2)
    gem_core_rgb = (
        np.array([1.0, 0.98, 0.90])[None, None, :] * np.exp(-(d_gem / 3.5) ** 2)[..., None]
        + np.array([0.46, 0.83, 0.93])[None, None, :] * (1.0 - np.exp(-(d_gem / 3.5) ** 2))[..., None]
    )

    shadow = np.roll(np.roll(gaussian_blur_f(m_out, 5.0), 3, axis=0), 2, axis=1) * 0.72
    rgb, a = np.zeros((H, W, 3), dtype=np.float32), shadow
    rgb, a = _over(body_rgb, body_a, rgb, a)
    rgb, a = _over(rim_rgb, m_rim, rgb, a)
    rgb, a = _over(gem_core_rgb, m_gem_in, rgb, a)
    rgb, a = _over(gem_rim_rgb, gem_rim, rgb, a)

    # 箔文字を貼り込み
    t_arr = np.asarray(foil_txt, dtype=np.float32) / 255.0
    tx = int(round(x0 + pad_l))
    ty = int(round(cy - th * 0.5))
    t_rgb = np.zeros((H, W, 3), dtype=np.float32)
    t_a = np.zeros((H, W), dtype=np.float32)
    t_rgb[ty:ty + th, tx:tx + tw] = t_arr[..., :3]
    t_a[ty:ty + th, tx:tx + tw] = t_arr[..., 3]
    rgb, a = _over(t_rgb, t_a, rgb, a)
    return _tight_crop(rgb, a)


VIGNETTE_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "royal-fantasy": {
        "mid": (0.24, 0.58),
        "bot": (0.56, 0.90),
        "default": (0.42, 0.78),
    },
    "pop-horizontal": {
        "mid": (0.10, 0.44),
        "bot": (0.34, 0.76),
        "default": (0.24, 0.58),
    },
    "classic-center": {
        "mid": (0.38, 0.72),
        "bot": (0.72, 0.95),
        "default": (0.58, 0.90),
    },
}


def _parse_css_object_position(pos_str: str) -> Tuple[float, float]:
    """CSS object-position 文字列から正規化アンカー (px, py) in [0, 1] を返す"""
    tokens = str(pos_str or "50% 35%").strip().lower().split()
    kw_map_x = {"left": 0.0, "center": 0.5, "right": 1.0}
    kw_map_y = {"top": 0.0, "center": 0.5, "bottom": 1.0}

    def parse_tok(tok: str, is_y: bool) -> float:
        kmap = kw_map_y if is_y else kw_map_x
        if tok in kmap:
            return kmap[tok]
        if tok.endswith("%"):
            try:
                return max(0.0, min(1.0, float(tok[:-1]) / 100.0))
            except ValueError:
                return 0.35 if is_y else 0.5
        try:
            v = float(tok)
            return max(0.0, min(1.0, v / 100.0 if abs(v) > 1.0 else v))
        except ValueError:
            return 0.35 if is_y else 0.5

    if not tokens:
        return 0.5, 0.35
    if len(tokens) == 1:
        t0 = tokens[0]
        if t0 in ("top", "bottom"):
            return 0.5, kw_map_y[t0]
        return parse_tok(t0, False), 0.5
    return parse_tok(tokens[0], False), parse_tok(tokens[1], True)


def compute_adaptive_vignette(cfg: Dict[str, Any], layout_id: str, layout: LayoutSpec) -> Dict[str, Any]:
    """入力写真の下部 30% 知覚輝度を計測し、レイアウト別レンジ内でビネット濃度を算出する"""
    spec = VIGNETTE_RANGES.get(layout_id, VIGNETTE_RANGES["classic-center"])
    def_mid, def_bot = spec["default"]
    photo_rel = str(cfg.get("photo", "assets/photo.jpg") or "assets/photo.jpg").strip().replace("\\", "/")
    photo_path = resolve_photo_path(photo_rel)

    if not photo_path.is_file():
        return {
            "measured": False,
            "photo": photo_rel,
            "midAlpha": def_mid,
            "bottomAlpha": def_bot,
        }

    try:
        with Image.open(photo_path) as raw_im:
            im = ImageOps.exif_transpose(raw_im).convert("RGB")
    except Exception:
        return {
            "measured": False,
            "photo": photo_rel,
            "midAlpha": def_mid,
            "bottomAlpha": def_bot,
        }

    tw = max(32, layout.card_inner_w // 5)
    th = max(32, layout.card_inner_h // 5)
    iw, ih = max(1, im.width), max(1, im.height)
    fit = str(cfg.get("photoFit", "cover") or "cover").strip().lower()
    try:
        zoom = max(0.25, float(cfg.get("photoZoom", 1.05)))
    except (TypeError, ValueError):
        zoom = 1.05
    px, py = _parse_css_object_position(str(cfg.get("photoPosition", "50% 35%") or "50% 35%"))

    scale = min(tw / iw, th / ih) if fit == "contain" else max(tw / iw, th / ih)
    rw = max(1, int(round(iw * scale)))
    rh = max(1, int(round(ih * scale)))
    resized = im.resize((rw, rh), Image.Resampling.BILINEAR)

    canvas = Image.new("RGB", (tw, th), (11, 16, 36))
    ox = int(round((tw - rw) * px))
    oy = int(round((th - rh) * py))
    canvas.paste(resized, (ox, oy))

    if abs(zoom - 1.0) > 1e-3:
        zw = max(1, int(round(tw * zoom)))
        zh = max(1, int(round(th * zoom)))
        zoomed = canvas.resize((zw, zh), Image.Resampling.BILINEAR)
        if zoom >= 1.0:
            cx0 = (zw - tw) // 2
            cy0 = (zh - th) // 2
            canvas = zoomed.crop((cx0, cy0, cx0 + tw, cy0 + th))
        else:
            bg = Image.new("RGB", (tw, th), (11, 16, 36))
            bg.paste(zoomed, ((tw - zw) // 2, (th - zh) // 2))
            canvas = bg

    y_start = int(round(th * 0.70))
    roi = np.asarray(canvas, dtype=np.float32)[y_start:, :, :] / 255.0
    luma = 0.2126 * roi[..., 0] + 0.7152 * roi[..., 1] + 0.0722 * roi[..., 2]
    luma_mean = float(np.mean(luma))
    luma_p90 = float(np.percentile(luma, 90))
    luma_eff = 0.65 * luma_mean + 0.35 * luma_p90

    t = float(smoothstep(0.18, 0.78, np.array([luma_eff], dtype=np.float32))[0])
    mid_lo, mid_hi = spec["mid"]
    bot_lo, bot_hi = spec["bot"]
    mid_a = round(mid_lo + (mid_hi - mid_lo) * t, 3)
    bot_a = round(bot_lo + (bot_hi - bot_lo) * t, 3)

    return {
        "measured": True,
        "photo": photo_rel,
        "lumaMean": round(luma_mean, 4),
        "lumaP90": round(luma_p90, 4),
        "lumaEffective": round(luma_eff, 4),
        "midAlpha": mid_a,
        "bottomAlpha": bot_a,
    }


def build_source_snapshot(
    cfg: Dict[str, Any],
    layout: LayoutSpec,
    preset_name: str,
    texts_map: Dict[str, str],
    wobble_val: float,
    foil_glitter: float,
    paper_grain: float,
    seed: int,
) -> Dict[str, Any]:
    """render_video.mjs との差分判定用入力スナップショットを構築する"""
    typo_cfg = cfg.get("typography", {}) if isinstance(cfg.get("typography"), dict) else {}
    photo_rel = str(cfg.get("photo", "assets/photo.jpg") or "assets/photo.jpg").strip().replace("\\", "/")
    photo_path = resolve_photo_path(photo_rel)
    if photo_path.is_file():
        st = photo_path.stat()
        photo_size = int(st.st_size)
        photo_mtime = int(st.st_mtime)
    else:
        photo_size = -1
        photo_mtime = -1

    try:
        zoom_val = round(float(cfg.get("photoZoom", 1.05)), 4)
    except (TypeError, ValueError):
        zoom_val = 1.05

    return {
        "orientation": layout.orientation,
        "orientationRaw": str(cfg.get("orientation", "portrait") or "portrait").strip().lower(),
        "preset": preset_name,
        "seed": int(seed),
        "texts": {k: str(v).strip() for k, v in texts_map.items()},
        "typography": {
            "layout": typo_cfg.get("layout", None),
            "palette": typo_cfg.get("palette", None),
            "font": typo_cfg.get("font", None),
            "style": typo_cfg.get("style", None),
            "wobble": round(float(wobble_val), 3),
            "foilGlitter": round(float(foil_glitter), 3),
            "paperGrain": round(float(paper_grain), 3),
        },
        "photo": {
            "path": photo_rel,
            "size": photo_size,
            "mtimeSec": photo_mtime,
            "fit": str(cfg.get("photoFit", "cover") or "cover").strip(),
            "position": str(cfg.get("photoPosition", "50% 35%") or "50% 35%").strip(),
            "zoom": zoom_val,
        },
    }


def main() -> None:
    all_presets = list(MODERN_PRESETS.keys()) + list(TYPO_PRESETS.keys())
    parser = argparse.ArgumentParser(description="SSRGenerate 文字ヒューマナイズ＆箔物理タイポグラフィ生成")
    parser.add_argument("--preset", type=str, default=None, choices=all_presets)
    parser.add_argument("--wobble", type=float, default=None, help="0..100 (legacy presets)")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--overrides", type=str, default=None, help="CLI overrides JSON string")
    parser.add_argument("--overrides-stdin", action="store_true", help="Read CLI overrides JSON from stdin")
    args = parser.parse_args()

    cfg = load_card_config()
    if args.overrides_stdin:
        raw_stdin = sys.stdin.read().strip()
        if raw_stdin:
            cfg = apply_config_overrides(cfg, json.loads(raw_stdin))
    if args.overrides:
        cfg = apply_config_overrides(cfg, json.loads(args.overrides))

    layout = resolve_layout(cfg)
    changed_html = sync_html_resolution(layout)
    if changed_html:
        print(f"[OK] synced HTML resolution ({layout.orientation} {layout.canvas_w}x{layout.canvas_h}): {', '.join(changed_html)}")

    typo_cfg = cfg.get("typography", {}) if isinstance(cfg.get("typography"), dict) else {}

    preset_name = args.preset or typo_cfg.get("preset", "royal-foil")
    if preset_name not in MODERN_PRESETS and preset_name not in TYPO_PRESETS:
        preset_name = "royal-foil"

    wobble_val = args.wobble if args.wobble is not None else typo_cfg.get("wobble", 28)
    wobble_norm = max(0.0, min(1.0, float(wobble_val) / 100.0))
    foil_glitter = float(typo_cfg.get("foilGlitter", 0.42))
    paper_grain = float(typo_cfg.get("paperGrain", 0.35))
    seed = resolve_seed(cfg, section="typography", override=args.seed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    is_modern = preset_name in MODERN_PRESETS
    plan = resolve_modern_plan(preset_name, typo_cfg, orientation=layout.orientation) if is_modern else None

    # タイトル実効縮小率の先行計算（サブタイトル・フレーバー連動 & 2-3文字トラッキング拡大）
    if is_modern and plan is not None:
        title_text = str(cfg.get("title", "")).strip()
        title_def = plan["slots"]["title"]
        title_def["trackingEm"] = adjust_short_title_tracking(
            title_text,
            float(title_def["trackingEm"]),
            bool(title_def.get("trackingExplicit", False)),
        )
        if title_text:
            fitted_title_size, _ = compute_fitted_font_size(
                text=title_text,
                primary=title_def["font"],
                font_size=int(title_def["size"]),
                max_w=float(title_def["maxW"]),
                max_lines=int(title_def["maxLines"]),
                tracking_em=float(title_def["trackingEm"]),
                vf_weight=int(title_def["vfWeight"]),
                norm_factors=plan["norm_factors"],
            )
            ratio = fitted_title_size / max(1.0, float(title_def["size"]))
            if ratio < 0.999:
                sub_def = plan["slots"]["subtitle"]
                scaled_sub = int(round(int(sub_def["size"]) * math.sqrt(ratio)))
                sub_def["size"] = max(20, min(scaled_sub, int(round(fitted_title_size * 0.68))))
                flav_def = plan["slots"]["flavor"]
                flav_def["size"] = max(18, min(int(flav_def["size"]), int(round(fitted_title_size * 0.52))))

    attr_badge, attr_label = parse_attribute_parts(
        raw_attr=str(cfg.get("attribute", "")),
        badge=cfg.get("attributeBadge"),
        label=cfg.get("attributeLabel"),
    )
    attr_key_text = format_attribute_key_text(cfg)

    is_land = layout.orientation == "landscape"
    card_specs = [
        ("ssr",       str(cfg.get("rarity", "SSR")), 82 if is_land else 94, 300 if is_land else 320, 1, "typo_ssr.png"),
        ("attribute", attr_key_text,                 24 if is_land else 26, 280 if is_land else 300, 1, "typo_attr.png"),
        ("subtitle",  str(cfg.get("subtitle", "")),  29 if is_land else 34, 1120 if is_land else 780, 1, "typo_subtitle.png"),
        ("title",     str(cfg.get("title", "")),     64 if is_land else 74, 1180 if is_land else 800, 1, "typo_title.png"),
        ("flavor",    str(cfg.get("flavor", "")),    25 if is_land else 29, 1120 if is_land else 780, 2, "typo_flavor.png"),
        ("cardNo",    str(cfg.get("cardNo", "")),    22 if is_land else 24, 340, 1, "typo_cardno.png"),
    ]
    cutin_specs = [
        ("cutinMain", "昇格  SSR 確定",                  112, 980, 1, "typo_cutin_main.png"),
    ]

    layout_id = plan["layout"] if plan else "classic-center"
    vignette = compute_adaptive_vignette(cfg, layout_id, layout)
    texts_map = {key: text for key, text, _, _, _, _ in card_specs}
    source_snapshot = build_source_snapshot(
        cfg=cfg,
        layout=layout,
        preset_name=preset_name,
        texts_map=texts_map,
        wobble_val=float(wobble_val),
        foil_glitter=foil_glitter,
        paper_grain=paper_grain,
        seed=seed,
    )

    manifest: Dict[str, Any] = {
        "schemaVersion": 2,
        "preset": preset_name,
        "layout": layout_id,
        "mirror": bool(plan["mirror"]) if plan else False,
        "palette": plan["palette_id"] if plan else "legacy",
        "wobble": wobble_val,
        "seed": seed,
        "dimensions": {
            "orientation": layout.orientation,
            "canvasW": layout.canvas_w,
            "canvasH": layout.canvas_h,
            "cardW": layout.card_w,
            "cardH": layout.card_h,
            "cardBorder": layout.card_border,
            "innerW": layout.card_inner_w,
            "innerH": layout.card_inner_h,
        },
        "vignette": vignette,
        "source": source_snapshot,
        "items": {},
    }

    if vignette.get("measured"):
        print(
            f"[OK] vignette ({layout_id}): luma={vignette['lumaEffective']:.2f} "
            f"(mean={vignette['lumaMean']:.2f}, p90={vignette['lumaP90']:.2f}) "
            f"-> mid={vignette['midAlpha']}, bot={vignette['bottomAlpha']}"
        )
    else:
        print(
            f"[WARN] vignette ({layout_id}): photo missing/unreadable ({vignette['photo']}) "
            f"-> fallback mid={vignette['midAlpha']}, bot={vignette['bottomAlpha']}"
        )

    # --- 並列レンダリングワーカー ---
    def render_card_slot(idx: int, spec: Tuple[str, str, int, int, int, str]) -> Optional[Tuple[str, str, int, int, str]]:
        key, text, legacy_fsize, legacy_max_w, legacy_max_lines, filename = spec
        clean_text = text.strip()
        if not clean_text:
            return None
        item_seed = seed + idx * 1009

        if is_modern and plan is not None:
            sdef = plan["slots"][key]
            pal = plan["palette"]
            nf = plan["norm_factors"]
            align = "right" if (plan["layout"] == "pop-horizontal" and key in ("subtitle", "title", "flavor")) else "center"
            if plan["mirror"] and align == "right":
                align = "left"

            if key == "ssr":
                img = render_modern_ssr_emblem(
                    clean_text,
                    font_name=sdef["font"],
                    font_size=int(sdef["size"]),
                    max_w=float(sdef["maxW"]),
                    style_id=str(sdef["style"]),
                    palette=pal,
                    tracking_em=float(sdef["trackingEm"]),
                    compress_x=float(sdef["compressX"]),
                    vf_weight=int(sdef["vfWeight"]),
                    opacity=float(sdef["opacity"]),
                    norm_factors=nf,
                )
            elif key == "attribute":
                img = render_modern_attribute_badge(
                    attr_badge,
                    attr_label,
                    style_id=str(sdef["style"]),
                    palette=pal,
                    norm_factors=nf,
                )
            else:
                img = render_modern_text(
                    clean_text,
                    font_name=sdef["font"],
                    font_size=int(sdef["size"]),
                    max_w=float(sdef["maxW"]),
                    max_lines=int(sdef["maxLines"]),
                    style_id=str(sdef["style"]),
                    palette=pal,
                    tracking_em=float(sdef["trackingEm"]),
                    compress_x=float(sdef["compressX"]),
                    vf_weight=int(sdef["vfWeight"]),
                    opacity=float(sdef["opacity"]),
                    align=align,
                    norm_factors=nf,
                )
        else:
            preset = TYPO_PRESETS[preset_name]
            style = preset[key]
            if key == "ssr":
                img = render_rarity_crest(
                    text=clean_text,
                    font_file=style["font"],
                    foil_glitter=foil_glitter,
                    paper_grain=paper_grain,
                    seed=item_seed,
                )
            elif key == "attribute":
                img = render_attribute_plate(
                    text=clean_text,
                    font_file=style["font"],
                    foil_glitter=foil_glitter,
                    paper_grain=paper_grain,
                    seed=item_seed,
                )
            else:
                img = render_multiline_block(
                    text=clean_text,
                    font_file=style["font"],
                    font_size=legacy_fsize,
                    max_w=float(legacy_max_w),
                    max_lines=legacy_max_lines,
                    material_name=style["material"],
                    wobble_strength=wobble_norm * float(style["wobble_mul"]),
                    foil_glitter=foil_glitter,
                    paper_grain=paper_grain,
                    is_stamp=bool(style["stamp"]),
                    seed=item_seed,
                )

        if img is None:
            return None
        out_path = OUT_DIR / filename
        save_png(img, out_path)
        print(f"[OK] {key}: {filename} ({img.width}x{img.height}) -> '{clean_text}'")
        return key, filename, img.width, img.height, clean_text

    def render_cutin_slot(c_idx: int, spec: Tuple[str, str, int, int, int, str]) -> Optional[Tuple[str, str, int, int, str]]:
        key, text, fsize, max_w, max_lines, filename = spec
        c_style = CUTIN_STYLE[key]
        offset_idx = 7 if key == "cutinMain" else (6 + c_idx)
        item_seed = seed + offset_idx * 1009
        img = render_multiline_block(
            text=text,
            font_file=c_style["font"],
            font_size=fsize,
            max_w=float(max_w),
            max_lines=max_lines,
            material_name=c_style["material"],
            wobble_strength=CUTIN_WOBBLE_NORM * float(c_style["wobble_mul"]),
            foil_glitter=CUTIN_FOIL_GLITTER,
            paper_grain=CUTIN_PAPER_GRAIN,
            is_stamp=bool(c_style["stamp"]),
            seed=item_seed,
            norm_factors=CUTIN_NORM_FACTORS,
        )
        if img is None:
            return None
        out_path = OUT_DIR / filename
        save_png(img, out_path)
        print(f"[OK] {key}: {filename} ({img.width}x{img.height}) -> '{text}' [CUTIN_FIXED]")
        return key, filename, img.width, img.height, text

    def render_rule_slot() -> Optional[Tuple[str, str, int, int, str]]:
        rule_w = 1140 if is_land else 760
        rule_img = render_royal_diamond_rule(width=rule_w, palette=plan["palette"], ss=3)
        rule_path = OUT_DIR / "typo_royal_rule.png"
        save_png(rule_img, rule_path)
        print(f"[OK] royalRule: typo_royal_rule.png ({rule_img.width}x{rule_img.height})")
        return "royalRule", "typo_royal_rule.png", rule_img.width, rule_img.height, "__rule__"

    max_workers = min(8, max(2, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        card_futures = [executor.submit(render_card_slot, idx, spec) for idx, spec in enumerate(card_specs)]
        rule_future = None
        if is_modern and plan is not None and plan["layout"] == "royal-fantasy":
            rule_future = executor.submit(render_rule_slot)
        cutin_futures = [executor.submit(render_cutin_slot, c_idx, spec) for c_idx, spec in enumerate(cutin_specs)]

        # 完了順に関わらず、マニフェスト登録順序を安定化
        for fut in card_futures:
            res = fut.result()
            if res:
                k, fn, w, h, t = res
                manifest["items"][k] = {"src": f"assets/generated/{fn}", "width": w, "height": h, "text": t}

        if rule_future is not None:
            res = rule_future.result()
            if res:
                k, fn, w, h, t = res
                manifest["items"][k] = {"src": f"assets/generated/{fn}", "width": w, "height": h, "text": t}

        for fut in cutin_futures:
            res = fut.result()
            if res:
                k, fn, w, h, t = res
                manifest["items"][k] = {"src": f"assets/generated/{fn}", "width": w, "height": h, "text": t}

    manifest_path = OUT_DIR / "typo-manifest.js"
    manifest_js = (
        "// Auto-generated by scripts/render_typography.py — Do not edit manually.\n"
        f"window.SSR_TYPO_MANIFEST = {json.dumps(manifest, ensure_ascii=False, indent=2)};\n"
    )
    manifest_path.write_text(manifest_js, encoding="utf-8")
    print(f"[OK] manifest -> {manifest_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
