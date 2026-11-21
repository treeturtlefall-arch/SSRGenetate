"""
SSRGenerate — 虹金属箔フレーム・カード裏面・ホロ質感アセット生成エンジン

写真は100%クリアなまま一切汚さず、カードを取り囲む「虹フレーム」自体に
物理的な金属ヘアライン研磨・微細エンボス法線勾配・立体ベベル面取り・
ホログラム箔ラメ・圧着反射ムラ・4辺中央の金属ノッチ＆菱形鋲（裏面は四隅フィリグリー）を焼き込み、
デジタルCSS枠感を払拭する。

生成ファイル（寸法は scripts/_utils.py の CARD_* 定数に追従）:
  - assets/generated/mat_rainbow_frame.png (CARD_W x CARD_H RGBA, 内窓透過＋4辺中央金属鋲)
  - assets/generated/mat_window_depth.png  (CARD_INNER_W x CARD_INNER_H RGBA, 内窓エッジ落ち影＋断面ハイライト)
  - assets/generated/mat_card_back.png     (CARD_W x CARD_H RGBA, ギョーシェ彫り＋金属レリーフ紋章＋四隅フィリグリーの裏面)
  - assets/generated/mat_holo_prism.png    (360x360 RGB タイル, ダイヤ格子×薄膜干渉プリズム。screen 合成用)
  - assets/generated/mat_flake_{0..5}.png  (72x72 RGBA, 金箔・プリズム結晶片)
  - assets/generated/mat_film_grain.png    (540x960 L, 暗部バンディング解消グレイン)

使い方:
  python scripts/render_material.py
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import math
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from _utils import (
    CARD_BORDER,
    CARD_H,
    CARD_INNER_H,
    CARD_INNER_R,
    CARD_INNER_W,
    CARD_OUTER_R,
    CARD_W,
    GOLD_RAMP,
    OUT_DIR,
    gaussian_blur_f,
    generate_film_grain_overlay,
    generate_micro_emboss_height,
    load_card_config,
    make_linear_gradient,
    norm_std,
    polygon_mask,
    porter_duff_over,
    resolve_seed,
    rgba_from_float,
    save_png,
    shade_metal_relief,
)

# 薄膜干渉（Iridescence）＋シャンパンゴールド基調の連続スペクトル
RAINBOW_STOPS: List[Tuple[int, int, int]] = [
    (255, 252, 245),  # 白金パール (#fffcf5)
    (242, 213, 143),  # シャンパンゴールド (#f2d58f)
    (232, 141, 180),  # 干渉ローズ (#e88db4)
    (162, 134, 235),  # 薄膜バイオレット (#a286eb)
    (118, 212, 238),  # プリズムアクア (#76d4ee)
    (242, 213, 143),  # シャンパンゴールド (#f2d58f)
    (255, 252, 245),  # 白金パール (#fffcf5)
]

# プリズム結晶片用の明暗ランプ（暗部 → 薄膜色 → 白飛び）
PRISM_RAMP: List[Tuple[int, int, int]] = [
    (34, 26, 64),
    (96, 120, 214),
    (118, 212, 238),
    (232, 141, 180),
    (242, 213, 143),
    (255, 252, 245),
]


def _make_rounded_rect_mask(w: int, h: int, pad: int, radius: int, ss: int = 2) -> np.ndarray:
    """2xスーパーサンプリングでアンチエイリアス付きの角丸矩形マスク [0, 1] を生成"""
    S_w, S_h = w * ss, h * ss
    im = Image.new("L", (S_w, S_h), 0)
    d = ImageDraw.Draw(im)
    p = pad * ss
    r = radius * ss
    d.rounded_rectangle([p, p, S_w - 1 - p, S_h - 1 - p], radius=r, fill=255)
    resized = im.resize((w, h), Image.Resampling.LANCZOS)
    return np.array(resized, dtype=np.float32) / 255.0


FILM_CYCLE = np.array(
    [(242, 213, 143), (232, 141, 180), (162, 134, 235), (118, 212, 238)], dtype=np.float32
) / 255.0


def thin_film_rgb(t: np.ndarray) -> np.ndarray:
    """薄膜干渉風の循環スペクトル（シャンパン → ローズ → バイオレット → アクア → シャンパン）"""
    n = len(FILM_CYCLE)
    s = (t % 1.0) * n
    i0 = np.floor(s).astype(np.int64) % n
    i1 = (i0 + 1) % n
    f = (s - np.floor(s))[..., None]
    f = f * f * (3.0 - 2.0 * f)
    return (FILM_CYCLE[i0] * (1.0 - f) + FILM_CYCLE[i1] * f).astype(np.float32)


# ==============================================================================
# 1. 虹金属箔フレーム（四隅の金属フィリグリーを焼き込み）
# ==============================================================================
def _corner_filigree_mask(size: int, border: int, ss: int = 3) -> np.ndarray:
    """左上コーナー用の L 字ブラケット＋菱形ジェムのマスク（size x size）"""
    S = size * ss
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)

    def P(x: float, y: float) -> Tuple[float, float]:
        return ((border + x) * ss, (border + y) * ss)

    # 外側 L（太）
    d.line([P(9, 70), P(9, 9), P(70, 9)], fill=255, width=int(4.0 * ss), joint="curve")
    # 内側 L（細）
    d.line([P(18, 46), P(18, 18), P(46, 18)], fill=230, width=int(2.0 * ss), joint="curve")
    # 腕先の菱形ノード
    for cx, cy, r in [(9, 78, 4.2), (78, 9, 4.2), (18, 52, 2.6), (52, 18, 2.6)]:
        d.polygon([P(cx, cy - r), P(cx + r, cy), P(cx, cy + r), P(cx - r, cy)], fill=255)
    # 角の菱形ジェム
    g = 8.5
    d.polygon([P(9, 9 - g), P(9 + g, 9), P(9, 9 + g), P(9 - g, 9)], fill=255)
    return np.asarray(im.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


def _make_center_stud_stamp(orientation: str = "top", ss: int = 3) -> Tuple[np.ndarray, int, int]:
    """
    900x1590 カードの4辺中央（フレーム幅 20px 上＋内周へ最大12px）に収まる
    微小金属ノッチ＆菱形ジュエル鋲のマスクを 3x SSAA で生成する。
    """
    w, h = 92, 36
    Sw, Sh = w * ss, h * ss
    im = Image.new("L", (Sw, Sh), 0)
    d = ImageDraw.Draw(im)

    cx = Sw * 0.5
    bar_pts = [
        (cx - 38 * ss, 9 * ss),
        (cx - 26 * ss, 6 * ss),
        (cx + 26 * ss, 6 * ss),
        (cx + 38 * ss, 9 * ss),
        (cx + 32 * ss, 18 * ss),
        (cx - 32 * ss, 18 * ss),
    ]
    d.polygon(bar_pts, fill=235)

    for dx in (-25, 25):
        r = 2.2 * ss
        rx, ry = cx + dx * ss, 12 * ss
        d.ellipse([rx - r, ry - r, rx + r, ry + r], fill=255)

    cy_j = 17.5 * ss
    jw, jh = 11.5 * ss, 13.5 * ss
    diamond_pts = [
        (cx, cy_j - jh),
        (cx + jw, cy_j),
        (cx, cy_j + jh),
        (cx - jw, cy_j),
    ]
    d.polygon(diamond_pts, fill=255)

    d.line([(cx - 34 * ss, 12 * ss), (cx - 14 * ss, 12 * ss)], fill=120, width=max(1, int(1.4 * ss)))
    d.line([(cx + 14 * ss, 12 * ss), (cx + 34 * ss, 12 * ss)], fill=120, width=max(1, int(1.4 * ss)))

    mask = np.asarray(im.resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0
    if orientation == "bottom":
        mask = mask[::-1, :]
    elif orientation == "left":
        mask = np.transpose(mask, (1, 0))
    elif orientation == "right":
        mask = np.transpose(mask[::-1, :], (1, 0))
    return mask, mask.shape[1], mask.shape[0]


def _compose_center_studs(
    base_rgb: np.ndarray,
    base_alpha: np.ndarray,
    w: int,
    h: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """4辺中央の金属ノッチ＆菱形鋲（落ち影付き）をフレーム上へ合成する"""
    stud_mask = np.zeros((h, w), dtype=np.float32)

    m_top, mw, mh = _make_center_stud_stamp("top")
    stud_mask[0:mh, w // 2 - mw // 2 : w // 2 - mw // 2 + mw] = np.maximum(
        stud_mask[0:mh, w // 2 - mw // 2 : w // 2 - mw // 2 + mw], m_top
    )
    m_bot, mw, mh = _make_center_stud_stamp("bottom")
    stud_mask[h - mh : h, w // 2 - mw // 2 : w // 2 - mw // 2 + mw] = np.maximum(
        stud_mask[h - mh : h, w // 2 - mw // 2 : w // 2 - mw // 2 + mw], m_bot
    )
    m_left, mw, mh = _make_center_stud_stamp("left")
    stud_mask[h // 2 - mh // 2 : h // 2 - mh // 2 + mh, 0:mw] = np.maximum(
        stud_mask[h // 2 - mh // 2 : h // 2 - mh // 2 + mh, 0:mw], m_left
    )
    m_right, mw, mh = _make_center_stud_stamp("right")
    stud_mask[h // 2 - mh // 2 : h // 2 - mh // 2 + mh, w - mw : w] = np.maximum(
        stud_mask[h // 2 - mh // 2 : h // 2 - mh // 2 + mh, w - mw : w], m_right
    )

    stud_rgb = shade_metal_relief(stud_mask, GOLD_RAMP, bevel_px=1.2, depth=5.5, tone=0.66, shininess=38.0)
    shadow = np.roll(np.roll(gaussian_blur_f(stud_mask, 2.0), 2, axis=0), 2, axis=1) * 0.72
    shadow_rgb = np.broadcast_to(np.array([0.016, 0.024, 0.066], dtype=np.float32), (h, w, 3))
    out_rgb, out_a = porter_duff_over(shadow_rgb, shadow, base_rgb, base_alpha)
    return porter_duff_over(stud_rgb, stud_mask, out_rgb, out_a)


def generate_rainbow_foil_frame(
    w: int = CARD_W,
    h: int = CARD_H,
    border: int = CARD_BORDER,
    outer_r: int = CARD_OUTER_R,
    inner_r: int = CARD_INNER_R,
    glitter_strength: float = 0.45,
    brush_strength: float = 0.85,
    seed: int = 20261120,
    with_filigree: bool = False,
    with_center_studs: bool = True,
) -> Image.Image:
    """
    デジタル感のない「物理金属箔・ホログラム虹フレーム」を生成する（内窓は透過）。
    1. 金属ヘアライン研磨目＋多周波微細シボの法線勾配バンプマップ
    2. 外周〜内周の立体ベベル（かまぼこ型面取り＋左上光源ハイライト／右下シャドウ）
    3. 箔圧着の低周波反射ムラ（有機的な光沢のうねり）
    4. マイクロホログラムラメ粒子（Glitter）
    5. 内窓四隅の金属フィリグリー（落ち影付き）
    """
    rng = np.random.default_rng((seed * 747796405 + 31337) & 0xFFFFFFFF)

    outer_mask = _make_rounded_rect_mask(w, h, pad=0, radius=outer_r, ss=2)
    inner_mask = _make_rounded_rect_mask(w, h, pad=border, radius=inner_r, ss=2)
    frame_alpha = np.clip(outer_mask - inner_mask, 0.0, 1.0)

    rgb = make_linear_gradient(h, w, RAINBOW_STOPS, angle_deg=135.0)

    def noise_layer(lh: int, lw: int, resample: Image.Resampling) -> np.ndarray:
        n = rng.standard_normal((max(4, lh), max(4, lw))).astype(np.float32)
        p = Image.fromarray(np.clip((n / 5.5 + 0.5) * 255.0, 0, 255).astype(np.uint8), mode="L")
        return np.array(p.resize((w, h), resample), dtype=np.float32)

    hair_h = noise_layer(int(h * 0.85), int(w * 0.06), Image.Resampling.BILINEAR)
    hair_v = noise_layer(int(h * 0.06), int(w * 0.85), Image.Resampling.BILINEAR)
    micro_g = noise_layer(int(h * 0.65), int(w * 0.65), Image.Resampling.BILINEAR)
    foil_wave = noise_layer(int(h / 28.0), int(w / 28.0), Image.Resampling.BICUBIC)

    emboss_h = norm_std(hair_h * 0.36 + hair_v * 0.36 + micro_g * 0.28)
    light_angle = math.radians(-132.0)
    lx, ly = math.cos(light_angle), math.sin(light_angle)
    dy, dx = np.gradient(emboss_h)
    relief = norm_std(dx * lx + dy * ly)
    wave_norm = norm_std(foil_wave)

    y_px = np.arange(h, dtype=np.float32)[:, None]
    x_px = np.arange(w, dtype=np.float32)[None, :]
    d_left = x_px
    d_right = (w - 1) - x_px
    d_top = y_px
    d_bot = (h - 1) - y_px
    dist_edge = np.minimum(np.minimum(d_left, d_right), np.minimum(d_top, d_bot))

    u_band = np.clip(dist_edge / max(1.0, float(border)), 0.0, 1.0)
    dome = np.sin(u_band * math.pi)
    slope_dir = np.where((d_top <= d_bot) & (d_top <= np.minimum(d_left, d_right)), 1.0, 0.0)
    slope_dir += np.where((d_left < d_right) & (d_left < np.minimum(d_top, d_bot)), 0.75, 0.0)
    slope_dir -= np.where((d_bot < d_top) & (d_bot <= np.minimum(d_left, d_right)), 0.85, 0.0)
    slope_dir -= np.where((d_right < d_left) & (d_right < np.minimum(d_top, d_bot)), 0.65, 0.0)

    spec_ridge = np.exp(-((u_band - 0.28) / 0.14) ** 2)
    inner_rim = np.exp(-((u_band - 0.88) / 0.09) ** 2)
    groove = np.exp(-((u_band - 0.62) / 0.05) ** 2)  # 中央の彫り溝（二重線のメリハリ）

    bevel_light = (
        (dome - 0.55) * 0.20
        + slope_dir * (0.14 * np.cos(u_band * math.pi))
        + spec_ridge * 0.16
        + inner_rim * 0.12
        - groove * 0.30
    )

    mod = 1.0 + bevel_light + relief * (0.095 * brush_strength) + wave_norm * (0.075 * brush_strength)
    rgb = np.clip(rgb * mod[:, :, None], 0.0, 1.0)
    spec_bleach = np.clip(spec_ridge * (0.16 + 0.12 * np.maximum(0.0, slope_dir)), 0.0, 0.35)
    rgb = np.clip(rgb + spec_bleach[:, :, None], 0.0, 1.0)

    if glitter_strength > 0.01:
        sparkle_raw = (rng.uniform(0.0, 1.0, (h, w)) > 0.955).astype(np.float32)
        sparkle = sparkle_raw * glitter_strength * (0.55 + 0.45 * dome)
        rgb = np.clip(rgb + sparkle[:, :, None], 0.0, 1.0)

    if not with_filigree:
        if with_center_studs:
            rgb, frame_alpha = _compose_center_studs(rgb, frame_alpha, w, h)
        return rgba_from_float(rgb, frame_alpha)

    # --- 四隅の金属フィリグリー ---
    csz = border + 96
    fil_tl = _corner_filigree_mask(csz, border)
    fil = np.zeros((h, w), dtype=np.float32)
    fil[:csz, :csz] = np.maximum(fil[:csz, :csz], fil_tl)
    fil[:csz, w - csz:] = np.maximum(fil[:csz, w - csz:], fil_tl[:, ::-1])
    fil[h - csz:, :csz] = np.maximum(fil[h - csz:, :csz], fil_tl[::-1, :])
    fil[h - csz:, w - csz:] = np.maximum(fil[h - csz:, w - csz:], fil_tl[::-1, ::-1])
    fil *= inner_mask  # 内窓側のみ

    fil_rgb = shade_metal_relief(fil, GOLD_RAMP, bevel_px=1.3, depth=5.0, tone=0.66, shininess=36.0)
    shadow = np.roll(np.roll(gaussian_blur_f(fil, 2.2), 2, axis=0), 2, axis=1) * 0.78 * inner_mask

    # 合成順: 写真 ← 落ち影 ← フィリグリー ← フレーム帯 ← 中央鋲
    shadow_rgb = np.broadcast_to(np.array([0.016, 0.024, 0.066], dtype=np.float32), (h, w, 3))
    out_rgb, out_a = porter_duff_over(fil_rgb, fil, shadow_rgb, shadow)
    final_rgb, final_a = porter_duff_over(rgb, frame_alpha, out_rgb, out_a)
    if with_center_studs:
        final_rgb, final_a = _compose_center_studs(final_rgb, final_a, w, h)
    return rgba_from_float(final_rgb, final_a)


# ==============================================================================
# 2. 内窓立体深度
# ==============================================================================
def generate_window_depth(w: int, h: int) -> Image.Image:
    """
    内窓の立体深度オーバーレイ（RGBA）:
    写真中央は100%無傷のまま、額縁の内周エッジだけに左上落ち影＋右下断面ハイライトを落とす。
    """
    s_ref = min(w, h)
    shadow_depth = max(14, int(round(s_ref * 0.024)))
    radius = max(2.0, shadow_depth * 0.34)
    tail_d = min(6, shadow_depth)
    d_arr = np.arange(shadow_depth, dtype=np.float32)
    t_lead = (shadow_depth - d_arr) / shadow_depth
    t_tail = (tail_d - np.arange(tail_d, dtype=np.float32)) / tail_d

    sy = np.ones((h, 1), dtype=np.float32)
    sy[:shadow_depth, 0] *= 1.0 - 0.44 * (t_lead ** 1.65)
    sy[-tail_d:, 0] *= 1.0 - 0.18 * t_tail[::-1]
    sy_soft = np.array(
        Image.fromarray((sy * 255.0).astype(np.uint8), mode="L").filter(ImageFilter.GaussianBlur(radius=radius)),
        dtype=np.float32,
    ).ravel() / 255.0

    sx = np.ones((1, w), dtype=np.float32)
    sx[0, :shadow_depth] *= 1.0 - 0.38 * (t_lead ** 1.65)
    sx[0, -tail_d:] *= 1.0 - 0.18 * t_tail[::-1]
    sx_soft = np.array(
        Image.fromarray((sx * 255.0).astype(np.uint8), mode="L").filter(ImageFilter.GaussianBlur(radius=radius)),
        dtype=np.float32,
    ).ravel() / 255.0

    shadow_factor = sy_soft[:, None] * sx_soft[None, :]
    shadow_alpha = np.clip(1.0 - shadow_factor, 0.0, 1.0)

    rgba = np.zeros((h, w, 4), dtype=np.float32)
    rgba[:, :, 0] = 4.0 / 255.0
    rgba[:, :, 1] = 6.0 / 255.0
    rgba[:, :, 2] = 17.0 / 255.0
    rgba[:, :, 3] = shadow_alpha

    rim_px = 3
    hl_rgb = np.array([255.0 / 255.0, 248.0 / 255.0, 220.0 / 255.0], dtype=np.float32)
    for r in range(rim_px):
        a_hl = ((rim_px - r) / rim_px) * 0.45
        rgba[h - 1 - r, :, :3] = hl_rgb
        rgba[h - 1 - r, :, 3] = np.maximum(rgba[h - 1 - r, :, 3], a_hl)
        rgba[:, w - 1 - r, :3] = hl_rgb
        rgba[:, w - 1 - r, 3] = np.maximum(rgba[:, w - 1 - r, 3], a_hl * 0.85)

    return Image.fromarray((np.clip(rgba, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), mode="RGBA")


# ==============================================================================
# 3. カード裏面（ギョーシェ彫り＋金属レリーフ紋章）
# ==============================================================================
def _crest_mask(w: int, h: int, cx: float, cy: float, ss: int = 2) -> np.ndarray:
    S_w, S_h = w * ss, h * ss
    im = Image.new("L", (S_w, S_h), 0)
    d = ImageDraw.Draw(im)
    c = (cx * ss, cy * ss)

    def ring(r: float, width: float, val: int = 255) -> None:
        rr = r * ss
        d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], outline=val, width=max(1, int(width * ss)))

    def star(n: int, r_out: float, r_in: float, rot: float, val: int = 255) -> None:
        pts = []
        for i in range(n * 2):
            a = math.radians(rot + i * 180.0 / n)
            r = (r_out if i % 2 == 0 else r_in) * ss
            pts.append((c[0] + math.cos(a) * r, c[1] + math.sin(a) * r))
        d.polygon(pts, fill=val)

    ring(182, 11)
    ring(160, 3)
    ring(118, 2.5, 220)
    # 放射スパイク（4方向ロング＋45°ショート）
    star(4, 330, 16, -90)
    star(4, 228, 12, -45, 235)
    # 8芒星
    star(8, 140, 58, -90)
    # 中央ディスク
    rr = 34 * ss
    d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], fill=255)
    # 外周の目盛り
    for i in range(72):
        a = math.radians(i * 5.0)
        r0 = (196 if i % 6 else 192) * ss
        r1 = (206 if i % 6 else 216) * ss
        d.line(
            [(c[0] + math.cos(a) * r0, c[1] + math.sin(a) * r0), (c[0] + math.cos(a) * r1, c[1] + math.sin(a) * r1)],
            fill=235,
            width=max(1, int(2.2 * ss)),
        )
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


def _guilloche_mask(w: int, h: int, cx: float, cy: float, ss: int = 2) -> np.ndarray:
    """ロゼット状ギョーシェ彫り（紙幣・証券の地紋）の線画マスク"""
    S_w, S_h = w * ss, h * ss
    im = Image.new("L", (S_w, S_h), 0)
    d = ImageDraw.Draw(im)
    th = np.linspace(0.0, 2.0 * math.pi, 1440, dtype=np.float64)
    families = [
        (36, 400.0, 0.80, 0.14, 7),
        (28, 300.0, 0.74, 0.18, 11),
        (48, 560.0, 0.86, 0.09, 5),
    ]
    for count, R, base, amp, lobes in families:
        for k in range(count):
            ph = k * 2.0 * math.pi / count
            r = R * (base + amp * np.sin(lobes * th + ph))
            xs = (cx + r * np.cos(th)) * ss
            ys = (cy + r * np.sin(th)) * ss
            d.line(list(zip(xs.tolist(), ys.tolist())), fill=255, width=max(1, int(1.1 * ss)))
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


def generate_card_back(w: int = CARD_W, h: int = CARD_H, seed: int = 20261120) -> Image.Image:
    rng = np.random.default_rng((seed * 2246822519 + 7) & 0xFFFFFFFF)
    cx, cy = w * 0.5, h * 0.5
    outer = _make_rounded_rect_mask(w, h, pad=0, radius=CARD_OUTER_R, ss=2)

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rn = np.sqrt(((xx - cx) / (w * 0.62)) ** 2 + ((yy - cy) / (h * 0.62)) ** 2)
    base = np.clip(1.0 - rn, 0.0, 1.0) ** 1.4
    c_in = np.array([0.105, 0.115, 0.27], dtype=np.float32)
    c_out = np.array([0.018, 0.024, 0.062], dtype=np.float32)
    rgb = c_out[None, None, :] + (c_in - c_out)[None, None, :] * base[..., None]

    # ダイヤ格子キルティング（ごく淡い）
    p = 46.0
    u = (xx + yy) / p
    v = (xx - yy) / p
    lattice = np.maximum(
        np.exp(-((np.abs((u % 1.0) - 0.5) - 0.5) * p / 0.9) ** 2),
        np.exp(-((np.abs((v % 1.0) - 0.5) - 0.5) * p / 0.9) ** 2),
    )
    rgb += lattice[..., None] * np.array([0.10, 0.085, 0.05])[None, None, :] * 0.55

    # ギョーシェ地紋（シャンパン金の細線、中心ほど強い）
    gu = _guilloche_mask(w, h, cx, cy)
    g_fade = np.clip(1.15 - rn * 0.9, 0.25, 1.0)
    rgb += gu[..., None] * np.array([0.95, 0.80, 0.48])[None, None, :] * 0.30 * g_fade[..., None]

    # 中央紋章（金属レリーフ）
    crest = _crest_mask(w, h, cx, cy)
    # 芒（スパイク）ごとに稜線の左右で明暗を分け、カット宝飾のファセット感を出す
    theta = np.arctan2(yy - cy, xx - cx)
    rr = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    facet8 = np.tanh(8.0 * np.sin(8.0 * (theta + math.pi / 2.0)))
    facet4 = np.tanh(8.0 * np.sin(4.0 * (theta + math.pi / 2.0)))
    tone = np.full_like(crest, 0.64)
    tone = np.where(rr < 150, 0.62 + 0.17 * facet8, tone)
    tone = np.where(rr > 214, 0.60 + 0.17 * facet4, tone)
    crest_rgb = shade_metal_relief(crest, GOLD_RAMP, bevel_px=2.0, depth=7.0, tone_map=tone, shininess=30.0)
    halo = gaussian_blur_f(crest, 22.0) * 0.55
    rgb += halo[..., None] * np.array([0.85, 0.62, 0.26])[None, None, :]
    shadow = np.roll(np.roll(gaussian_blur_f(crest, 3.0), 4, axis=0), 3, axis=1) * 0.7
    rgb = rgb * (1.0 - shadow[..., None] * (1.0 - crest[..., None]))
    rgb = rgb * (1.0 - crest[..., None]) + crest_rgb * crest[..., None]

    # 内側の彫りライン（角丸ヘアライン＋四隅ノード）
    ins = CARD_BORDER + 18
    line_outer = _make_rounded_rect_mask(w, h, pad=ins, radius=CARD_INNER_R, ss=2)
    line_inner = _make_rounded_rect_mask(w, h, pad=ins + 3, radius=CARD_INNER_R - 2, ss=2)
    hair = np.clip(line_outer - line_inner, 0.0, 1.0)
    hair_rgb = shade_metal_relief(hair, GOLD_RAMP, bevel_px=0.8, depth=3.0, tone=0.62)
    rgb = rgb * (1.0 - hair[..., None]) + hair_rgb * hair[..., None]

    # 四隅の金属フィリグリー（裏面のみ維持）
    inner_mask = _make_rounded_rect_mask(w, h, pad=CARD_BORDER, radius=CARD_INNER_R, ss=2)
    csz = CARD_BORDER + 96
    fil_tl = _corner_filigree_mask(csz, CARD_BORDER)
    fil = np.zeros((h, w), dtype=np.float32)
    fil[:csz, :csz] = np.maximum(fil[:csz, :csz], fil_tl)
    fil[:csz, w - csz:] = np.maximum(fil[:csz, w - csz:], fil_tl[:, ::-1])
    fil[h - csz:, :csz] = np.maximum(fil[h - csz:, :csz], fil_tl[::-1, :])
    fil[h - csz:, w - csz:] = np.maximum(fil[h - csz:, w - csz:], fil_tl[::-1, ::-1])
    fil *= inner_mask
    fil_rgb = shade_metal_relief(fil, GOLD_RAMP, bevel_px=1.3, depth=5.0, tone=0.66, shininess=36.0)
    fil_shadow = np.roll(np.roll(gaussian_blur_f(fil, 2.2), 2, axis=0), 2, axis=1) * 0.78 * inner_mask
    rgb = rgb * (1.0 - fil_shadow[..., None] * (1.0 - fil[..., None]))
    rgb = rgb * (1.0 - fil[..., None]) + fil_rgb * fil[..., None]

    # 微細シボ＋ビネット
    emb = generate_micro_emboss_height(h, w, rng)
    rgb = rgb * (1.0 + emb[..., None] * 0.035)
    rgb = rgb * (0.78 + 0.22 * np.clip(1.0 - rn * 0.7, 0.0, 1.0))[..., None]
    return rgba_from_float(np.clip(rgb, 0.0, 1.0), outer)


# ==============================================================================
# 4. ホログラム・プリズムタイル（ダイヤ格子×薄膜干渉）
# ==============================================================================
def generate_holo_prism_tile(size: int = 360, period: int = 36, seed: int = 20261120) -> Image.Image:
    """
    screen 合成前提のシームレスタイル（黒 = 無効果）。
    高輝度な一部ファセットと繊細な干渉シマーのみが浮かび上がり、写真の上に網目ノイズを作らない光学設計。
    """
    n_cells = size // period  # size は period の整数倍
    rng = np.random.default_rng((seed * 1103515245 + 12345) & 0xFFFFFFFF)
    hue_tab = rng.uniform(0.0, 1.0, (n_cells, n_cells)).astype(np.float32)
    # 多くのセルはほぼ暗く、約25%のファセットだけがキラッと反射する疎密分布
    raw_r = rng.uniform(0.0, 1.0, (n_cells, n_cells)).astype(np.float32)
    lum_tab = (0.04 + 0.72 * np.power(raw_r, 3.6)).astype(np.float32)

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    u = (xx + yy) / period
    v = (xx - yy) / period
    a = np.floor(u).astype(np.int64) % n_cells
    b = np.floor(v).astype(np.int64) % n_cells
    fu, fv = u % 1.0, v % 1.0

    hue = hue_tab[a, b] + 0.22 * np.sin(2.0 * math.pi * (xx + yy) / size)
    # セル中心が滑らかに明るく、境界で自然に落ちるソフトファセット（白い網目線は描かない）
    cell_dome = np.sin(fu * math.pi) * np.sin(fv * math.pi)
    lum = lum_tab[a, b] * (0.35 + 0.65 * cell_dome)
    # 明るいファセットの稜線だけに微かなプリズムハイライト
    edge_hi = np.maximum(
        np.exp(-((np.minimum(fu, 1.0 - fu)) * period / 1.1) ** 2),
        np.exp(-((np.minimum(fv, 1.0 - fv)) * period / 1.1) ** 2),
    ) * (lum_tab[a, b] ** 1.6) * 0.22
    glitter = (rng.uniform(0.0, 1.0, (size, size)) > 0.994).astype(np.float32) * (0.4 + 0.6 * lum_tab[a, b])

    rgb = thin_film_rgb(hue) * (lum + edge_hi)[..., None] + glitter[..., None] * 0.85
    arr = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


# ==============================================================================
# 5. 金箔・プリズム結晶片
# ==============================================================================
def generate_foil_flakes(count: int = 6, size: int = 72, seed: int = 20261120) -> List[Image.Image]:
    rng = np.random.default_rng((seed * 69069 + 1) & 0xFFFFFFFF)
    flakes: List[Image.Image] = []
    for i in range(count):
        n_vert = int(rng.integers(3, 6))
        angs = np.sort(rng.uniform(0.0, 2.0 * math.pi, n_vert))
        rad = rng.uniform(0.42, 0.92, n_vert) * size * 0.42
        aspect = rng.uniform(0.45, 0.85)
        c = size * 0.5
        pts = [(c + math.cos(t) * r, c + math.sin(t) * r * aspect) for t, r in zip(angs, rad)]
        mask = polygon_mask(size, size, pts, ss=4)
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        tone = 0.35 + 0.6 * np.clip((xx + yy * 0.6) / (size * 1.6), 0.0, 1.0)
        ramp = GOLD_RAMP if i % 2 == 0 else PRISM_RAMP
        rgb = shade_metal_relief(mask, ramp, bevel_px=1.1, depth=4.0, tone_map=tone, shininess=22.0)
        flakes.append(rgba_from_float(rgb, mask))
    return flakes


def main() -> None:
    cfg = load_card_config()
    mat_cfg = cfg.get("material", {})
    glitter = float(mat_cfg.get("frameFoilGlitter", 0.45))
    brush = float(mat_cfg.get("frameBrushStrength", 0.85))
    seed = resolve_seed(cfg, section="material")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def _job_frame() -> str:
        frame_img = generate_rainbow_foil_frame(glitter_strength=glitter, brush_strength=brush, seed=seed)
        save_png(frame_img, OUT_DIR / "mat_rainbow_frame.png")
        return f"[OK] mat_rainbow_frame.png ({frame_img.width}x{frame_img.height})"

    def _job_depth() -> str:
        depth_img = generate_window_depth(CARD_INNER_W, CARD_INNER_H)
        save_png(depth_img, OUT_DIR / "mat_window_depth.png")
        return f"[OK] mat_window_depth.png ({depth_img.width}x{depth_img.height})"

    def _job_back() -> str:
        back_img = generate_card_back(seed=seed)
        save_png(back_img, OUT_DIR / "mat_card_back.png")
        return f"[OK] mat_card_back.png ({back_img.width}x{back_img.height})"

    def _job_prism() -> str:
        prism_img = generate_holo_prism_tile(seed=seed)
        save_png(prism_img, OUT_DIR / "mat_holo_prism.png")
        return f"[OK] mat_holo_prism.png ({prism_img.width}x{prism_img.height})"

    def _job_flakes() -> str:
        for i, fl in enumerate(generate_foil_flakes(seed=seed)):
            save_png(fl, OUT_DIR / f"mat_flake_{i}.png")
        return "[OK] mat_flake_0..5.png (72x72)"

    def _job_grain() -> str:
        grain_img = generate_film_grain_overlay(540, 960, sigma=14.0, seed=seed + 101)
        save_png(grain_img, OUT_DIR / "mat_film_grain.png")
        return f"[OK] mat_film_grain.png ({grain_img.width}x{grain_img.height})"

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = [
            ex.submit(fn)
            for fn in (_job_frame, _job_depth, _job_back, _job_prism, _job_flakes, _job_grain)
        ]
        for fut in futures:
            print(fut.result())


if __name__ == "__main__":
    main()
