"""
SSRGenerate — 左「SSR (Pattern A)」× 右「属性 (Pattern C)」ブラッシュアップ検証シート生成 v2

v2 修正点:
  1. Pastel ハートメダリオンを 4x SSAA パラメトリック曲線で再構築（くびれ・下端のドット溢れ＆もっこりを完全解消）
  2. 座布団の「帯本体中心」と文字の「実インク中心（ドロップシャドウ除外）」を厳密に一致させる上下センタリング
  3. メダリオン内1文字も「実インク中心」をダイヤ中心／ハートの視覚重心にビタ合わせ

使い方:
  python scripts/compare_header_badges.py
出力:
  renders/compare_header_ac_royal.png
  renders/compare_header_ac_pastel.png
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, gaussian_filter

from _typo_modern import (
    MODERN_PRESETS,
    PALETTES,
    _compute_sdf,
    _render_mask_ls,
    _shift_subpixel,
    _stroke_mask,
    hex_to_rgb01,
    render_modern_text,
)
from _utils import (
    ASSETS_DIR,
    CARD_BORDER,
    CARD_H,
    CARD_W,
    GOLD_RAMP,
    OUT_DIR,
    PROJECT_ROOT,
    gaussian_blur_f,
    porter_duff_over,
    rgba_from_float,
    save_png,
    shade_metal_relief,
    smoothstep,
    tight_crop_rgba,
)

# 左右で完全統一する共通座布団の帯高さ・余白
SHARED_BAND_H = 44
ZABUTON_PAD = 14


def measure_ink_center_y(im: Image.Image, alpha_thresh: float = 0.80) -> float:
    """ドロップシャドウ等の半透明領域を除外し、文字本体の視覚的な上下中心 Y 座標を返す"""
    arr = np.asarray(im, dtype=np.float32) / 255.0
    a = arr[..., 3]
    ys = np.where(a >= alpha_thresh)[0]
    if len(ys) == 0:
        ys = np.where(a > 0.25)[0]
    if len(ys) == 0:
        return im.height * 0.5
    return (float(ys.min()) + float(ys.max()) + 1.0) * 0.5


def measure_ink_center_x(im: Image.Image, alpha_thresh: float = 0.80) -> float:
    """ドロップシャドウ等の半透明領域を除外し、文字本体の視覚的な左右中心 X 座標を返す"""
    arr = np.asarray(im, dtype=np.float32) / 255.0
    a = arr[..., 3]
    xs = np.where(a >= alpha_thresh)[1]
    if len(xs) == 0:
        xs = np.where(a > 0.25)[1]
    if len(xs) == 0:
        return im.width * 0.5
    return (float(xs.min()) + float(xs.max()) + 1.0) * 0.5


# =========================================================================
# 1. 共通座布団ジェネレータ（帯本体の正確な中心 Y = ZABUTON_PAD + h / 2.0）
# =========================================================================
def render_shared_zabuton(
    w: int,
    h: int,
    theme: str,
    palette: Dict[str, str],
    skew_px: float = 15.0,
    fishtail_right: bool = False,
) -> Image.Image:
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
        ty = np.clip((yy - pad) / max(1.0, float(h)), 0.0, 1.0)
        c_top = np.array([0.09, 0.12, 0.28], dtype=np.float32)
        c_bot = np.array([0.02, 0.03, 0.09], dtype=np.float32)
        body_rgb = c_top[None, None, :] * (1.0 - ty[..., None]) + c_bot[None, None, :] * ty[..., None]
        shimmer = np.exp(-(((xx - mw * 0.42) * 0.65 + (yy - mh * 0.5)) / 14.0) ** 2) * 0.22
        shimmer2 = np.exp(-(((xx - mw * 0.58) * 0.65 + (yy - mh * 0.5)) / 5.0) ** 2) * 0.18
        body_rgb = np.clip(body_rgb + (shimmer + shimmer2)[..., None] * np.array([0.95, 0.82, 0.50]), 0.0, 1.0)
        body_a = mask * 0.88

        outer_rim = mask * smoothstep(4.2, 2.5, d_in)
        inner_pin = np.exp(-((d_in - 6.0) / 0.85) ** 2) * 0.55 * inside
        metal_mask = np.clip(outer_rim + inner_pin, 0.0, 1.0)
        metal_rgb = shade_metal_relief(metal_mask, GOLD_RAMP, bevel_px=1.2, depth=5.2, tone=0.68, shininess=34.0)

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


# =========================================================================
# 2. メダリオン専用スリム縁取り文字（Pastelハート内で輪郭を潰さない白抜き＋プラム細縁）
# =========================================================================
def render_pastel_medallion_char(ch: str, size: int, palette: Dict[str, str]) -> Image.Image:
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
        norm_factors={},
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


# =========================================================================
# 3. 拡大属性メダリオン（Royal: 78px ダイヤ / Pastel: 4x SSAA パラメトリックハート）
# =========================================================================
def render_attribute_medallion(
    theme: str,
    palette: Dict[str, str],
    badge_char: str = "",
) -> Tuple[Image.Image, float]:
    """(medallion_rgba, visual_center_y) を返す"""
    if theme == "royal":
        size = 78
        ss = 3
        S = size * ss
        c = S * 0.5
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        cy, cx = size * 0.5, size * 0.5

        im_base = Image.new("L", (S, S), 0)
        d = ImageDraw.Draw(im_base)
        r_out = S * 0.46
        d.polygon([(c, c - r_out), (c + r_out, c), (c, c + r_out), (c - r_out, c)], fill=255)
        m_base = np.asarray(im_base.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

        im_in = Image.new("L", (S, S), 0)
        d_in_draw = ImageDraw.Draw(im_in)
        r_in = S * 0.37
        d_in_draw.polygon([(c, c - r_in), (c + r_in, c), (c, c + r_in), (c - r_in, c)], fill=255)
        m_gem = np.asarray(im_in.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
        m_bezel = np.clip(m_base - m_gem, 0.0, 1.0)

        im_star = Image.new("L", (S, S), 0)
        ds = ImageDraw.Draw(im_star)
        pts = []
        for i in range(16):
            a = math.radians(-90 + i * 22.5)
            r = (S * 0.30 if i % 4 == 0 else S * 0.21) if i % 2 == 0 else S * 0.08
            pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
        ds.polygon(pts, fill=255)
        m_star = np.asarray(im_star.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0

        bezel_rgb = shade_metal_relief(m_bezel, GOLD_RAMP, bevel_px=1.3, depth=5.8, tone=0.70, shininess=36.0)
        star_rgb = shade_metal_relief(m_star, GOLD_RAMP, bevel_px=1.0, depth=4.5, tone=0.82, shininess=40.0)

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
            )
            kx = int(round(cx - measure_ink_center_x(k_im)))
            ky = int(round(cy - measure_ink_center_y(k_im)))
            out_im.alpha_composite(k_im, (kx, ky))
        return out_im, cy

    else:
        # Pastel: 4x SSAA 滑らかなパラメトリック・ハート曲線（ドット溢れ・もっこり完全ゼロ）
        size = 86
        ss = 4
        S = size * ss
        cx_s, cy_s = S * 0.5, S * 0.5

        # 左右対称の3次ベジェ曲線で、くびれ・下端の反り(くちばし)が一切ない理想のぷっくりハートを生成
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
        # ハート外接矩形の中心をキャンバス中央に厳密配置
        hx = hx - (hx.min() + hx.max()) * 0.5
        hy = hy - (hy.min() + hy.max()) * 0.5
        scale_h = (S * 0.72) / max(hx.max() - hx.min(), hy.max() - hy.min())
        pts = [(float(cx_s + x * scale_h), float(cy_s + y * scale_h)) for x, y in zip(hx, hy)]

        im_h = Image.new("L", (S, S), 0)
        ImageDraw.Draw(im_h).polygon(pts, fill=255)
        m_heart = np.asarray(im_h, dtype=np.float32) / 255.0
        inside = m_heart >= 0.5
        d_out = distance_transform_edt(~inside).astype(np.float32)

        # ハートの視覚的重心（文字を置くのに最も自然な中央点）を計算
        ys_in = np.where(inside)[0]
        heart_centroid_y = float(np.mean(ys_in)) / ss
        # 帯と合わせたときのメダリオンの垂直基準中心（外接中心と重心のバランス）
        heart_box_cy = (float(ys_in.min()) + float(ys_in.max())) * 0.5 / ss

        yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
        c_out = hex_to_rgb01(palette["outline"])
        c_in = hex_to_rgb01(palette["inline"])

        y_min_h, y_max_h = float(ys_in.min()), float(ys_in.max())
        ty = np.clip((yy - y_min_h) / max(1.0, y_max_h - y_min_h), 0.0, 1.0)
        c_top = np.array([1.00, 0.58, 0.78], dtype=np.float32)
        c_bot = np.array([0.92, 0.22, 0.52], dtype=np.float32)
        h_rgb = c_top[None, None, :] * (1.0 - ty[..., None]) + c_bot[None, None, :] * ty[..., None]

        # 左上のぷっくりツヤ玉（4x解像度で滑らかに）
        spec = np.exp(-(((xx - S * 0.34) / (S * 0.072)) ** 2 + ((yy - S * 0.32) / (S * 0.048)) ** 2)) * 0.82 * inside
        h_rgb = np.clip(h_rgb + spec[..., None], 0.0, 1.0)

        # 4x 解像度上で白ステッカー縁（3.8px相当）＋ローズプラム外縁（2.6px相当）を生成
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
            k_im = render_pastel_medallion_char(ch, size=30, palette=palette)
            # ハートの視覚的重心（上部が広いので外接中心よりわずかに上）へ実インク中心をビタ合わせ
            kx = int(round(size * 0.5 - measure_ink_center_x(k_im)))
            ky = int(round(heart_centroid_y - measure_ink_center_y(k_im)))
            out_im.alpha_composite(k_im, (kx, ky))

        return out_im, heart_box_cy


# =========================================================================
# 4. 左「SSR (Pattern A)」＆ 右「属性 (Pattern C)」
# =========================================================================
def build_ssr_pattern_a(theme: str, palette: Dict[str, str]) -> Image.Image:
    preset_id = "royal-foil" if theme == "royal" else "cute-pastel"
    s_ssr = MODERN_PRESETS[preset_id]["slots"]["ssr"]
    ssr_txt = render_modern_text(
        "SSR",
        font_name=s_ssr["font"],
        font_size=int(s_ssr["size"]),
        max_w=float(s_ssr["maxW"]),
        max_lines=1,
        style_id=str(s_ssr["style"]),
        palette=palette,
        tracking_em=float(s_ssr["trackingEm"]),
        compress_x=float(s_ssr["compressX"]),
        vf_weight=int(s_ssr["vfWeight"]),
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

    # 帯本体の厳密な中心 Y に SSR の実インク中心 Y をビタ合わせ
    band_cy = zy + ZABUTON_PAD + SHARED_BAND_H * 0.5
    tx = zx + (zab.width - tw) // 2 - 5
    ty = int(round(band_cy - measure_ink_center_y(ssr_txt)))
    canvas.alpha_composite(ssr_txt, (max(0, tx), max(0, ty)))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    return tight_crop_rgba(arr[..., :3], arr[..., 3], pad=2)


def build_attr_pattern_c(
    badge_char: str,
    label_text: str,
    theme: str,
    palette: Dict[str, str],
) -> Image.Image:
    med, med_cy = render_attribute_medallion(theme, palette, badge_char=badge_char)

    is_ascii = all(ord(c) < 128 for c in label_text)
    if theme == "royal":
        font_name = "Cinzel-VF.ttf" if is_ascii else "ShipporiMincho-ExtraBold.ttf"
        style_id = "royal-gold-clean"
        tracking = 0.11 if is_ascii else 0.06
        fsize = 27 if is_ascii else 26
    else:
        font_name = "Outfit-VF.ttf" if is_ascii else "ZenMaruGothic-Black.ttf"
        style_id = "pop-sticker-rose"
        tracking = 0.06 if is_ascii else 0.04
        fsize = 26 if is_ascii else 25

    t_lbl = render_modern_text(
        label_text,
        font_name=font_name,
        font_size=fsize,
        max_w=196.0,
        max_lines=1,
        style_id=style_id,
        palette=palette,
        tracking_em=tracking,
        vf_weight=800,
    )

    med_overlap = int(med.width * 0.42)
    z_w = max(176, t_lbl.width + med_overlap + 42)
    zab = render_shared_zabuton(z_w, SHARED_BAND_H, theme, palette, skew_px=15, fishtail_right=False)

    zab_x = int(med.width * 0.34)
    cw = zab_x + zab.width + 4
    ch = max(med.height, zab.height, t_lbl.height) + 12
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

    # 帯本体の厳密な中心 Y を基準に、メダリオンとラベル文字の実インク中心をすべて揃える
    zab_y = (ch - zab.height) // 2
    band_cy = zab_y + ZABUTON_PAD + SHARED_BAND_H * 0.5
    canvas.alpha_composite(zab, (zab_x, zab_y))

    med_y = int(round(band_cy - med_cy))
    canvas.alpha_composite(med, (0, max(0, med_y)))

    # テキストはメダリオン右端〜帯本体右端の中央に、実インク中心で厳密配置
    area_left = med.width - 4
    area_right = zab_x + ZABUTON_PAD + z_w - (12 if theme == "royal" else 8)
    area_cx = (area_left + area_right) * 0.5
    tx = int(round(area_cx - measure_ink_center_x(t_lbl)))
    ty = int(round(band_cy - measure_ink_center_y(t_lbl)))
    canvas.alpha_composite(t_lbl, (max(0, tx), max(0, ty)))

    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    return tight_crop_rgba(arr[..., :3], arr[..., 3], pad=2)


# =========================================================================
# 5. 実写真＋虹フレーム上のバリエーション検証シート出力
# =========================================================================
def build_card_header_base(crop_h: int = 224) -> Image.Image:
    card = Image.new("RGBA", (CARD_W, CARD_H), (12, 16, 36, 255))
    photo_path = ASSETS_DIR / "photo.jpg"
    inner_w, inner_h = CARD_W - CARD_BORDER * 2, CARD_H - CARD_BORDER * 2

    if photo_path.is_file():
        ph = Image.open(photo_path).convert("RGBA")
        scale = max(inner_w / ph.width, inner_h / ph.height) * 1.05
        nw, nh = int(ph.width * scale), int(ph.height * scale)
        ph_rs = ph.resize((nw, nh), Image.Resampling.LANCZOS)
        ox = (nw - inner_w) // 2
        oy = int((nh - inner_h) * 0.35)
        ph_crop = ph_rs.crop((ox, oy, ox + inner_w, oy + inner_h))
    else:
        yy, xx = np.mgrid[0:inner_h, 0:inner_w].astype(np.float32)
        ph_crop = rgba_from_float(
            np.stack([np.clip(0.35 + 0.55 * (xx / inner_w), 0, 1), np.clip(0.68 - 0.15 * (yy / inner_h), 0, 1), np.clip(0.52 + 0.25 * (xx / inner_w), 0, 1)], axis=-1),
            np.ones((inner_h, inner_w), dtype=np.float32),
        )

    card.paste(ph_crop, (CARD_BORDER, CARD_BORDER))
    depth_path = OUT_DIR / "mat_window_depth.png"
    if depth_path.is_file():
        card.alpha_composite(Image.open(depth_path).convert("RGBA"), (CARD_BORDER, CARD_BORDER))
    frame_path = OUT_DIR / "mat_rainbow_frame.png"
    if frame_path.is_file():
        card.alpha_composite(Image.open(frame_path).convert("RGBA"), (0, 0))
    return card.crop((0, 0, CARD_W, crop_h))


def render_sheet(
    theme: str,
    cases: List[Tuple[str, str, str]],
    out_path: Path,
) -> None:
    palette = PALETTES["royal-gold" if theme == "royal" else "cute-pastel"]
    header_base = build_card_header_base(crop_h=224)
    ssr_im = build_ssr_pattern_a(theme, palette)

    row_h = 224 + 42
    sheet = Image.new("RGBA", (CARD_W + 40, row_h * len(cases) + 24), (8, 11, 24, 255))
    d = ImageDraw.Draw(sheet)

    for idx, (desc, badge, label) in enumerate(cases):
        y0 = 14 + idx * row_h
        d.text(
            (24, y0),
            f"[{theme.upper()}]  {desc}",
            fill=(242, 223, 179, 255),
        )

        row_im = header_base.copy()
        attr_im = build_attr_pattern_c(badge, label, theme, palette)

        ssr_x, ssr_y = 42, 42
        row_im.alpha_composite(ssr_im, (ssr_x, ssr_y))

        attr_x = CARD_W - 44 - attr_im.width
        attr_y = ssr_y + (ssr_im.height - attr_im.height) // 2
        row_im.alpha_composite(attr_im, (attr_x, max(24, attr_y)))

        sheet.alpha_composite(row_im, (20, y0 + 26))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_png(sheet, out_path)
    print(f"[OK] Saved -> {out_path.relative_to(PROJECT_ROOT)} ({sheet.width}x{sheet.height})")


def main() -> None:
    renders_dir = PROJECT_ROOT / "renders"
    royal_cases = [
        ("1. Standard (BABY)", "光", "BABY"),
        ("2. Short / Min-Width (SUN)", "光", "SUN"),
        ("3. Long / Auto-Fit (STARLIGHT)", "輝", "STARLIGHT"),
        ("4. Japanese Label", "光", "ひかり"),
        ("5. Empty Badge / Icon Only (BABY)", "", "BABY"),
    ]
    pastel_cases = [
        ("1. Standard (ANGEL)", "愛", "ANGEL"),
        ("2. Short / Min-Width (CUTE)", "愛", "CUTE"),
        ("3. Long / Auto-Fit (PRINCESS)", "星", "PRINCESS"),
        ("4. Japanese Label", "愛", "てんし"),
        ("5. Empty Badge / Icon Only (ANGEL)", "", "ANGEL"),
    ]
    render_sheet("royal", royal_cases, renders_dir / "compare_header_ac_royal.png")
    render_sheet("pastel", pastel_cases, renders_dir / "compare_header_ac_pastel.png")


if __name__ == "__main__":
    main()
