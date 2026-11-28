"""
SSRGenerate — 写真適応ビネット計測 ＆ 入力スナップショット構築モジュール

入力写真の下部30%知覚輝度から最適なビネット濃度を算出し、
render_video.mjs との差分判定用スナップショットを構築する。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image, ImageOps

from _utils import (
    PROJECT_ROOT,
    LayoutSpec,
    resolve_photo_path,
    smoothstep,
)


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

