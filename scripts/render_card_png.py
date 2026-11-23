"""
SSRGenerate — フル解像度 SSR カード静止画 PNG 合成エンジン (縦 900x1590 / 横 1480x860)

動画レンダリングとは独立して、フル解像度座標系と
生成済み物理箔タイポグラフィ・虹金属箔フレーム・適応型ビネット・ホログラムシマーを用いて、
終盤静止カード (#ssr-card) と 100% 同一解像度の透過角丸 PNG を高速合成する。

使い方:
  python scripts/render_card_png.py -o renders/SSR_royal-foil_20261123.card.png
  python scripts/render_card_png.py --overrides-stdin -o renders/card.png
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from _utils import (
    OUT_DIR,
    PROJECT_ROOT,
    LayoutSpec,
    apply_config_overrides,
    format_attribute_key_text,
    load_card_config,
    porter_duff_over,
    resolve_layout,
    resolve_photo_path,
    rgba_from_float,
    save_png,
)

MANIFEST_PATH = OUT_DIR / "typo-manifest.js"


def _load_typo_manifest() -> Dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        return {}
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    m = re.search(r"window\.SSR_TYPO_MANIFEST\s*=\s*(\{[\s\S]*\})\s*;", text)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _parse_css_object_position(pos_str: str) -> Tuple[float, float]:
    s = (pos_str or "50% 35%").strip().lower()
    tokens = [t for t in re.split(r"[\s,]+", s) if t]
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


def _make_rounded_rect_mask(w: int, h: int, radius: int, ss: int = 3) -> np.ndarray:
    """アンチエイリアス付きの角丸矩形マスク [0, 1] (H, W) float32"""
    sw, sh = w * ss, h * ss
    im = Image.new("L", (sw, sh), 0)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, sw - 1, sh - 1], radius=radius * ss, fill=255)
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


def _render_fitted_photo(cfg: Dict[str, Any], inner_w: int, inner_h: int) -> np.ndarray:
    """CSS の #card-photo (object-fit, object-position, scale(photoZoom)) を忠実に再現した RGB [0,1] を返す"""
    bg_rgb = np.zeros((inner_h, inner_w, 3), dtype=np.float32)
    bg_rgb[:, :] = np.array([11, 16, 36], dtype=np.float32) / 255.0  # #0b1024

    photo_rel = str(cfg.get("photo", "assets/photo.jpg") or "assets/photo.jpg").strip()
    photo_path = resolve_photo_path(photo_rel)
    if not photo_path.is_file():
        return bg_rgb

    try:
        with Image.open(photo_path) as raw_im:
            im = ImageOps.exif_transpose(raw_im).convert("RGB")
    except Exception:
        return bg_rgb

    iw, ih = max(1, im.width), max(1, im.height)
    fit = str(cfg.get("photoFit", "cover") or "cover").strip().lower()
    try:
        zoom = max(0.25, float(cfg.get("photoZoom", 1.05)))
    except (TypeError, ValueError):
        zoom = 1.05
    px, py = _parse_css_object_position(str(cfg.get("photoPosition", "50% 35%") or "50% 35%"))

    scale = min(inner_w / iw, inner_h / ih) if fit == "contain" else max(inner_w / iw, inner_h / ih)
    rw = max(1, int(round(iw * scale)))
    rh = max(1, int(round(ih * scale)))
    resized = im.resize((rw, rh), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (inner_w, inner_h), (11, 16, 36))
    ox = int(round((inner_w - rw) * px))
    oy = int(round((inner_h - rh) * py))
    canvas.paste(resized, (ox, oy))

    if abs(zoom - 1.0) > 1e-3:
        zw = max(1, int(round(inner_w * zoom)))
        zh = max(1, int(round(inner_h * zoom)))
        zoomed = canvas.resize((zw, zh), Image.Resampling.LANCZOS)
        if zoom >= 1.0:
            cx0 = (zw - inner_w) // 2
            cy0 = (zh - inner_h) // 2
            canvas = zoomed.crop((cx0, cy0, cx0 + inner_w, cy0 + inner_h))
        else:
            bg = Image.new("RGB", (inner_w, inner_h), (11, 16, 36))
            bg.paste(zoomed, ((inner_w - zw) // 2, (inner_h - zh) // 2))
            canvas = bg

    return np.asarray(canvas, dtype=np.float32) / 255.0


def _apply_photo_vignette(
    photo_rgb: np.ndarray,
    layout_id: str,
    is_landscape: bool,
    mid_alpha: float,
    bot_alpha: float,
) -> np.ndarray:
    """scene-result.css の .photo-vignette をレイアウト・向き別に忠実に適用する"""
    h, w, _ = photo_rgb.shape
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    out = photo_rgb.copy()

    if layout_id == "royal-fantasy":
        # linear-gradient(to bottom, rgba(6,9,20,0) 0..62/65%, mid 80/82%, bot 100%)
        y0 = 0.65 if is_landscape else 0.62
        y1 = 0.82 if is_landscape else 0.80
        a = np.where(
            y <= y0,
            0.0,
            np.where(
                y <= y1,
                (y - y0) / max(1e-5, y1 - y0) * mid_alpha,
                mid_alpha + (y - y1) / max(1e-5, 1.0 - y1) * (bot_alpha - mid_alpha),
            ),
        ).astype(np.float32)
        vig_c = np.array([6, 9, 20], dtype=np.float32) / 255.0
        out = out * (1.0 - a[..., None]) + vig_c * a[..., None]
        return np.clip(out, 0.0, 1.0)

    if layout_id == "pop-horizontal":
        # linear-gradient(to bottom, rgba(12,10,22,0) 0..60/64%, mid 78/80%, bot 100%)
        y0 = 0.64 if is_landscape else 0.60
        y1 = 0.80 if is_landscape else 0.78
        a = np.where(
            y <= y0,
            0.0,
            np.where(
                y <= y1,
                (y - y0) / max(1e-5, y1 - y0) * mid_alpha,
                mid_alpha + (y - y1) / max(1e-5, 1.0 - y1) * (bot_alpha - mid_alpha),
            ),
        ).astype(np.float32)
        vig_c = np.array([12, 10, 22], dtype=np.float32) / 255.0
        out = out * (1.0 - a[..., None]) + vig_c * a[..., None]
        return np.clip(out, 0.0, 1.0)

    # classic-center: radial-gradient + linear-gradient
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy = h * (0.44 if is_landscape else 0.42)
    cx = w * 0.50
    # farthest-corner radius from (cx, cy)
    max_r = math.hypot(max(cx, w - cx), max(cy, h - cy))
    r_norm = np.hypot(xx - cx, yy - cy) / max(1.0, max_r)
    r0 = 0.62 if is_landscape else 0.58
    rad_peak = 0.30 if is_landscape else 0.34
    rad_a = np.clip((r_norm - r0) / max(1e-5, 1.0 - r0), 0.0, 1.0) * rad_peak
    c_dark = np.array([4, 6, 17], dtype=np.float32) / 255.0
    out = out * (1.0 - rad_a[..., None]) + c_dark * rad_a[..., None]

    top_peak = 0.24 if is_landscape else 0.30
    y_clear = 0.62 if is_landscape else 0.54
    y_mid = 0.79 if is_landscape else 0.73
    lin_a = np.where(
        y <= 0.16,
        top_peak * (1.0 - y / 0.16),
        np.where(
            y <= y_clear,
            0.0,
            np.where(
                y <= y_mid,
                (y - y_clear) / max(1e-5, y_mid - y_clear) * mid_alpha,
                mid_alpha + (y - y_mid) / max(1e-5, 1.0 - y_mid) * (bot_alpha - mid_alpha),
            ),
        ),
    ).astype(np.float32)
    c_top = np.array([6, 9, 22], dtype=np.float32) / 255.0
    t_bot = np.clip((y - y_mid) / max(1e-5, 1.0 - y_mid), 0.0, 1.0)
    c_lin = c_top[None, :] * (1.0 - t_bot) + c_dark[None, :] * t_bot
    out = out * (1.0 - lin_a[..., None]) + c_lin[:, None, :] * lin_a[..., None]
    return np.clip(out, 0.0, 1.0)


def _apply_holo_static_sheen(inner_rgb: np.ndarray, is_landscape: bool, sheen_opacity: float = 0.84) -> np.ndarray:
    """#holo-mask-zone + #holo-static-sheen (中央被写体0%保護・外縁のみscreen合成)"""
    h, w, _ = inner_rgb.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    # 128deg linear-gradient
    ang = math.radians(128.0)
    dx, dy = math.sin(ang), -math.cos(ang)
    nx = xx / max(1.0, w - 1) - 0.5
    ny = yy / max(1.0, h - 1) - 0.5
    proj = nx * dx + ny * dy
    pmin, pmax = float(proj.min()), float(proj.max())
    t = (proj - pmin) / max(1e-6, pmax - pmin)

    # stops: 0%: (255,252,245)*0.22, 18%: (242,223,179)*0.12, 36..70%: 0, 86%: (118,212,238)*0.14, 100%: (232,141,180)*0.18
    c0 = np.array([255, 252, 245], dtype=np.float32) / 255.0 * 0.22
    c1 = np.array([242, 223, 179], dtype=np.float32) / 255.0 * 0.12
    c4 = np.array([118, 212, 238], dtype=np.float32) / 255.0 * 0.14
    c5 = np.array([232, 141, 180], dtype=np.float32) / 255.0 * 0.18

    sheen = np.zeros((h, w, 3), dtype=np.float32)
    m0 = t <= 0.18
    f0 = (t[m0] / 0.18)[:, None]
    sheen[m0] = c0 * (1.0 - f0) + c1 * f0

    m1 = (t > 0.18) & (t <= 0.36)
    f1 = ((t[m1] - 0.18) / 0.18)[:, None]
    sheen[m1] = c1 * (1.0 - f1)

    m3 = (t > 0.70) & (t <= 0.86)
    f3 = ((t[m3] - 0.70) / 0.16)[:, None]
    sheen[m3] = c4 * f3

    m4 = t > 0.86
    f4 = ((t[m4] - 0.86) / 0.14)[:, None]
    sheen[m4] = c4 * (1.0 - f4) + c5 * f4

    # radial-gradient mask (central subject protection)
    rx = w * (0.46 if is_landscape else 0.50)
    ry = h * (0.50 if is_landscape else 0.42)
    cx = w * 0.50
    cy = h * (0.44 if is_landscape else 0.42)
    er = np.hypot((xx - cx) / max(1.0, rx), (yy - cy) / max(1.0, ry))
    mask = np.where(
        er <= 0.66,
        0.0,
        np.where(
            er <= 0.84,
            (er - 0.66) / 0.18 * 0.26,
            0.26 + np.clip((er - 0.84) / 0.16, 0.0, 1.0) * (0.90 - 0.26),
        ),
    ).astype(np.float32)

    eff_sheen = np.clip(sheen * (mask * sheen_opacity)[..., None], 0.0, 1.0)
    # screen blend
    return np.clip(1.0 - (1.0 - inner_rgb) * (1.0 - eff_sheen), 0.0, 1.0)


def _paste_rgba_over(
    dst_rgb: np.ndarray,
    dst_a: np.ndarray,
    src_img: Image.Image,
    x: int,
    y: int,
    opacity: float = 1.0,
    blend_mode: str = "normal",
) -> None:
    """dst (H, W, 3), dst_a (H, W) に対して src_img (RGBA) を座標 (x, y) でインプレース合成する"""
    dh, dw = dst_a.shape
    sw, sh = src_img.size
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dw, x + sw), min(dh, y + sh)
    if x1 <= x0 or y1 <= y0:
        return

    arr = np.asarray(src_img.convert("RGBA"), dtype=np.float32)[y0 - y : y1 - y, x0 - x : x1 - x] / 255.0
    s_rgb = arr[..., :3]
    s_a = np.clip(arr[..., 3] * opacity, 0.0, 1.0)

    d_rgb = dst_rgb[y0:y1, x0:x1]
    d_a = dst_a[y0:y1, x0:x1]

    if blend_mode == "screen":
        # screen blend weighted by source alpha
        scr_rgb = 1.0 - (1.0 - d_rgb) * (1.0 - s_rgb * s_a[..., None])
        dst_rgb[y0:y1, x0:x1] = np.clip(scr_rgb, 0.0, 1.0)
        dst_a[y0:y1, x0:x1] = np.clip(d_a + s_a * (1.0 - d_a), 0.0, 1.0)
    else:
        out_rgb, out_a = porter_duff_over(s_rgb, s_a, d_rgb, d_a)
        dst_rgb[y0:y1, x0:x1] = out_rgb
        dst_a[y0:y1, x0:x1] = out_a


def _load_slot_image(entry: Optional[Dict[str, Any]], fixed_height: int = 0) -> Optional[Image.Image]:
    if not entry or not entry.get("src"):
        return None
    p = PROJECT_ROOT / str(entry["src"])
    if not p.is_file():
        return None
    im = Image.open(p).convert("RGBA")
    if fixed_height > 0 and im.height > 0 and im.height != fixed_height:
        tw = max(1, int(round((im.width / im.height) * fixed_height)))
        im = im.resize((tw, fixed_height), Image.Resampling.LANCZOS)
    return im


def render_card_image(
    cfg: Optional[Dict[str, Any]] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> Image.Image:
    """
    現在の card-config と typo-manifest.js から、フル解像度 (縦 900x1590 / 横 1480x860) の
    SSR カード静止画 (RGBA Image) を合成して返す。
    """
    c = cfg if cfg is not None else load_card_config()
    m = manifest if manifest is not None else _load_typo_manifest()
    layout: LayoutSpec = resolve_layout(c)
    is_landscape = layout.orientation == "landscape"

    card_w, card_h = layout.card_w, layout.card_h
    border = layout.card_border
    inner_w, inner_h = layout.card_inner_w, layout.card_inner_h
    outer_r, inner_r = layout.card_outer_r, layout.card_inner_r

    typo_layout = str(m.get("layout", "classic-center") or "classic-center")
    typo_mirror = bool(m.get("mirror", False))
    is_modern = typo_layout != "classic-center"
    items: Dict[str, Any] = m.get("items", {}) if isinstance(m.get("items"), dict) else {}

    # 1. 内窓領域 (inner_w x inner_h): 写真 + 適応型ビネット
    inner_rgb = _render_fitted_photo(c, inner_w, inner_h)
    vig = m.get("vignette", {}) if isinstance(m.get("vignette"), dict) else {}
    default_mid = 0.42 if typo_layout == "royal-fantasy" else (0.24 if typo_layout == "pop-horizontal" else 0.58)
    default_bot = 0.78 if typo_layout == "royal-fantasy" else (0.58 if typo_layout == "pop-horizontal" else 0.90)
    mid_a = float(vig.get("midAlpha", default_mid))
    bot_a = float(vig.get("bottomAlpha", default_bot))
    inner_rgb = _apply_photo_vignette(inner_rgb, typo_layout, is_landscape, mid_a, bot_a)
    inner_a = np.ones((inner_h, inner_w), dtype=np.float32)

    # 2. 内窓エッジ落ち影 (mat_window_depth.png)
    mat_cfg = c.get("material", {}) if isinstance(c.get("material"), dict) else {}
    depth_opacity = float(mat_cfg.get("windowDepthOpacity", 1.0))
    depth_path = OUT_DIR / "mat_window_depth.png"
    if depth_path.is_file():
        with Image.open(depth_path) as dim:
            depth_im = dim.convert("RGBA")
            if depth_im.size != (inner_w, inner_h):
                depth_im = depth_im.resize((inner_w, inner_h), Image.Resampling.LANCZOS)
            _paste_rgba_over(inner_rgb, inner_a, depth_im, 0, 0, opacity=depth_opacity)

    # 3. 中央減衰ホログラムシマー (#holo-static-sheen)
    inner_rgb = _apply_holo_static_sheen(inner_rgb, is_landscape, sheen_opacity=0.84)

    # 4. 下部オーバーレイスタック (#card-overlay-layer: 星 -> ロイヤル罫線 -> 二つ名 -> タイトル -> フレーバー)
    if is_landscape:
        if typo_layout == "royal-fantasy":
            pad_top, pad_x, pad_bot, gap = 20, 48, 32, 6
        elif typo_layout == "pop-horizontal":
            pad_top, pad_x, pad_bot, gap = 20, 44, 34, 6
        else:
            pad_top, pad_x, pad_bot, gap = 20, 48, 34, 8
    else:
        if typo_layout == "royal-fantasy":
            pad_top, pad_x, pad_bot, gap = 36, 40, 44, 10
        elif typo_layout == "pop-horizontal":
            pad_top, pad_x, pad_bot, gap = 36, 36, 46, 8
        else:
            pad_top, pad_x, pad_bot, gap = 36, 40, 66, 14

    align_mode = "center"
    if typo_layout == "pop-horizontal":
        align_mode = "left" if typo_mirror else "right"

    stack_elements = []

    # 4a. 星行 (#stars-row)
    try:
        star_count = max(0, min(6, int(c.get("stars", 0) or 0)))
    except (TypeError, ValueError):
        star_count = 0
    star_path = OUT_DIR / "opt_star_gold.png"
    if star_count > 0 and star_path.is_file():
        star_size = 74 if is_landscape else 90
        star_neg_margin = -8 if is_landscape else -10
        with Image.open(star_path) as sim:
            star_im = sim.convert("RGBA").resize((star_size, star_size), Image.Resampling.LANCZOS)
        step_x = star_size + 2 * star_neg_margin
        row_w = star_count * step_x
        row_h = star_size
        # CSS margin: -14px 0 -10px
        stack_elements.append(("stars", (star_im, star_count, step_x, star_neg_margin), row_w, row_h, -14, -10))

    # 4b. ロイヤル二重罫線 (#royal-rule-wrap)
    if typo_layout == "royal-fantasy":
        rule_im = _load_slot_image(items.get("royalRule"))
        if rule_im is not None:
            stack_elements.append(("image", rule_im, rule_im.width, rule_im.height, 0, 4))

    # 4c. 二つ名・タイトル・フレーバー
    for slot_key, cfg_key in (("subtitle", "subtitle"), ("title", "title"), ("flavor", "flavor")):
        raw_txt = str(c.get(cfg_key, "") or "").strip()
        if raw_txt == "__EMPTY__":
            raw_txt = ""
        if not raw_txt:
            continue
        im = _load_slot_image(items.get(slot_key))
        if im is not None:
            stack_elements.append(("image", im, im.width, im.height, 0, 0))

    # 下端 (inner_h - pad_bot) から上に向かって配置座標を計算
    cur_bottom = inner_h - pad_bot
    placed_stack = []
    for idx in range(len(stack_elements) - 1, -1, -1):
        kind, payload, ew, eh, m_top, m_bot = stack_elements[idx]
        cur_bottom -= m_bot
        top_y = cur_bottom - eh
        if align_mode == "right":
            left_x = inner_w - pad_x - ew
        elif align_mode == "left":
            left_x = pad_x
        else:
            left_x = (inner_w - ew) // 2
        placed_stack.append((kind, payload, left_x, top_y))
        cur_bottom = top_y - m_top - (gap if idx > 0 else 0)

    for kind, payload, lx, ty in reversed(placed_stack):
        if kind == "stars":
            star_im, scount, step_x, neg_m = payload
            for s_idx in range(scount):
                sx = lx + s_idx * step_x + neg_m
                _paste_rgba_over(inner_rgb, inner_a, star_im, sx, ty, opacity=1.0, blend_mode="screen")
        else:
            _paste_rgba_over(inner_rgb, inner_a, payload, lx, ty, opacity=1.0)

    # 5. 左上 SSR エンブレム (#ssr-emblem) ＆ 右上 属性バッジ (#attr-badge)
    ssr_im = _load_slot_image(items.get("ssr"), fixed_height=0 if is_modern else 94)
    attr_text = format_attribute_key_text(c)
    attr_im = _load_slot_image(items.get("attribute"), fixed_height=0 if is_modern else 70) if attr_text else None

    if is_landscape:
        if typo_layout == "royal-fantasy":
            ssr_top, ssr_left = 22, 32
            attr_top, attr_right = 28, 30
        elif typo_layout == "pop-horizontal":
            ssr_top, ssr_left = 24, 36
            attr_top, attr_right = 32, 30
        else:
            ssr_top, ssr_left = 16, 16
            attr_top, attr_right = 22, 16
    else:
        if typo_layout == "royal-fantasy":
            ssr_top, ssr_left = 30, 36
            attr_top, attr_right = 36, 34
        elif typo_layout == "pop-horizontal":
            ssr_top, ssr_left = 34, 42
            attr_top, attr_right = 42, 34
        else:
            ssr_top, ssr_left = 16, 16
            attr_top, attr_right = 22, 16

    if is_modern and ssr_im is not None and attr_im is not None:
        attr_top = ssr_top + int(round((ssr_im.height - attr_im.height) / 2.0))

    if ssr_im is not None:
        _paste_rgba_over(inner_rgb, inner_a, ssr_im, ssr_left, ssr_top)
    if attr_im is not None:
        _paste_rgba_over(inner_rgb, inner_a, attr_im, inner_w - attr_right - attr_im.width, attr_top)

    # 6. 右下 カード番号 (#card-no-corner)
    card_no_txt = str(c.get("cardNo", "") or "").strip()
    if card_no_txt and card_no_txt != "__EMPTY__":
        max_no_h = 22 if is_modern else 38
        no_entry = items.get("cardNo")
        no_im = _load_slot_image(no_entry)
        if no_im is not None:
            if no_im.height > max_no_h:
                nw = max(1, int(round((no_im.width / no_im.height) * max_no_h)))
                no_im = no_im.resize((nw, max_no_h), Image.Resampling.LANCZOS)
            no_right = 26 if is_modern else 36
            no_bot = 16 if is_modern else 22
            _paste_rgba_over(inner_rgb, inner_a, no_im, inner_w - no_right - no_im.width, inner_h - no_bot - no_im.height)

    # 7. 内窓角丸マスク (--card-inner-r: 24px) を適用し、カード全体キャンバス (card_w x card_h) に配置
    card_rgb = np.zeros((card_h, card_w, 3), dtype=np.float32)
    card_rgb[:, :] = np.array([9, 13, 31], dtype=np.float32) / 255.0  # .card-front background #090d1f
    card_a = np.ones((card_h, card_w), dtype=np.float32)

    inner_mask = _make_rounded_rect_mask(inner_w, inner_h, inner_r, ss=3)
    card_rgb[border : border + inner_h, border : border + inner_w] = (
        inner_rgb * inner_mask[..., None] + card_rgb[border : border + inner_h, border : border + inner_w] * (1.0 - inner_mask[..., None])
    )

    # 8. 虹金属箔フレーム (mat_rainbow_frame.png) を最前面にオーバーレイ
    frame_path = OUT_DIR / "mat_rainbow_frame.png"
    if frame_path.is_file():
        with Image.open(frame_path) as fim:
            frame_im = fim.convert("RGBA")
            if frame_im.size != (card_w, card_h):
                frame_im = frame_im.resize((card_w, card_h), Image.Resampling.LANCZOS)
            _paste_rgba_over(card_rgb, card_a, frame_im, 0, 0)

    # 9. カード外周の角丸マスク (--card-outer-r: 40px) で外側をクリーンに透過切り抜き
    outer_mask = _make_rounded_rect_mask(card_w, card_h, outer_r, ss=3)
    card_a = np.clip(card_a * outer_mask, 0.0, 1.0)

    return rgba_from_float(card_rgb, card_a)


def main() -> int:
    t0 = time.perf_counter()
    parser = argparse.ArgumentParser(description="SSRGenerate フル解像度 card.png 合成出力")
    parser.add_argument("-o", "--output", type=str, default="renders/card.png", help="Output PNG path")
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

    out_path = Path(args.output) if Path(args.output).is_absolute() else (PROJECT_ROOT / args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    img = render_card_image(cfg=cfg)
    save_png(img, out_path)
    elapsed = time.perf_counter() - t0
    try:
        rel = out_path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        rel = str(out_path)
    print(f"[card-png] Saved full-resolution card ({img.width}x{img.height}) -> {rel} ({elapsed:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
