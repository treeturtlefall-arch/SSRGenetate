"""
SSRGenerate — 虹金属箔フレーム＆内窓立体深度アセット生成エンジン

写真は100%クリアなまま一切汚さず、カードを取り囲む「虹フレーム」自体に
物理的な金属ヘアライン研磨・微細エンボス法線勾配・立体ベベル面取り・
ホログラム箔ラメ・圧着反射ムラを焼き込むことで、デジタルCSS枠感を払拭する。

生成ファイル:
  - assets/generated/mat_rainbow_frame.png (940x1660 RGBA, 内窓完全透過)
  - assets/generated/mat_window_depth.png  (912x1632 RGBA, 内窓エッジ落ち影＋断面ハイライト)

使い方:
  python scripts/render_material.py
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from _utils import OUT_DIR, load_card_config, make_linear_gradient, norm_std, resolve_seed

RAINBOW_STOPS: List[Tuple[int, int, int]] = [
    (255, 251, 235),  # #fffbeb
    (250, 204, 21),   # #facc15
    (244, 114, 182),  # #f472b6
    (56, 189, 248),   # #38bdf8
    (168, 85, 247),   # #a855f7
    (250, 204, 21),   # #facc15
    (255, 251, 235),  # #fffbeb
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


def generate_rainbow_foil_frame(
    w: int = 940,
    h: int = 1660,
    border: int = 14,
    outer_r: int = 40,
    inner_r: int = 26,
    glitter_strength: float = 0.45,
    brush_strength: float = 0.85,
    seed: int = 20261120,
) -> Image.Image:
    """
    デジタル感のない「物理金属箔・ホログラム虹フレーム」を生成する（内窓は完全透過）。
    1. 金属ヘアライン研磨目＋多周波微細シボの法線勾配バンプマップ
    2. 外周〜内周の立体ベベル（かまぼこ型面取り＋左上光源ハイライト／右下シャドウ）
    3. 箔圧着の低周波反射ムラ（有機的な光沢のうねり）
    4. マイクロホログラムラメ粒子（Glitter）
    """
    rng = np.random.default_rng((seed * 747796405 + 31337) & 0xFFFFFFFF)

    # 1. フレーム帯の透過マスク（外周角丸 − 内窓角丸）
    outer_mask = _make_rounded_rect_mask(w, h, pad=0, radius=outer_r, ss=2)
    inner_mask = _make_rounded_rect_mask(w, h, pad=border, radius=inner_r, ss=2)
    frame_alpha = np.clip(outer_mask - inner_mask, 0.0, 1.0)

    # 2. ベース虹金グラデーション
    rgb = make_linear_gradient(h, w, RAINBOW_STOPS, angle_deg=135.0)

    # 3. 金属ヘアライン研磨目（斜め微細筋）＋ 微細エンボス法線勾配
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

    dx = np.empty_like(emboss_h)
    dx[:, 1:-1] = (emboss_h[:, 2:] - emboss_h[:, :-2]) * 0.5
    dx[:, 0] = emboss_h[:, 1] - emboss_h[:, 0]
    dx[:, -1] = emboss_h[:, -1] - emboss_h[:, -2]

    dy = np.empty_like(emboss_h)
    dy[1:-1, :] = (emboss_h[2:, :] - emboss_h[:-2, :]) * 0.5
    dy[0, :] = emboss_h[1, :] - emboss_h[0, :]
    dy[-1, :] = emboss_h[-1, :] - emboss_h[-2, :]

    relief = norm_std(dx * lx + dy * ly)
    wave_norm = norm_std(foil_wave)

    # 4. 立体ベベル面取り（フレーム帯の断面が丸く盛り上がり、左上から光が当たる物理陰影）
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

    bevel_light = (
        (dome - 0.55) * 0.20
        + slope_dir * (0.14 * np.cos(u_band * math.pi))
        + spec_ridge * 0.16
        + inner_rim * 0.12
    )

    # 5. ヘアライン・シボ・反射ムラ・立体ベベルを虹金金属面へ合成
    mod = (
        1.0
        + bevel_light
        + relief * (0.095 * brush_strength)
        + wave_norm * (0.075 * brush_strength)
    )
    rgb = np.clip(rgb * mod[:, :, None], 0.0, 1.0)
    spec_bleach = np.clip(spec_ridge * (0.16 + 0.12 * np.maximum(0.0, slope_dir)), 0.0, 0.35)
    rgb = np.clip(rgb + spec_bleach[:, :, None], 0.0, 1.0)

    # 6. ホログラム箔マイクロラメ粒子（フレーム帯上のみ）
    if glitter_strength > 0.01:
        sparkle_raw = (rng.uniform(0.0, 1.0, (h, w)) > 0.955).astype(np.float32)
        sparkle = sparkle_raw * glitter_strength * (0.55 + 0.45 * dome)
        rgb = np.clip(rgb + sparkle[:, :, None], 0.0, 1.0)

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    alpha_u8 = (frame_alpha * 255.0 + 0.5).astype(np.uint8)
    visible = alpha_u8 > 0
    rgba[visible, :3] = (rgb[visible] * 255.0 + 0.5).astype(np.uint8)
    rgba[:, :, 3] = alpha_u8
    return Image.fromarray(rgba, mode="RGBA")


def generate_window_depth(w: int, h: int) -> Image.Image:
    """
    内窓の立体深度オーバーレイ（RGBA）:
    写真中央は100%無傷のまま、額縁の内周エッジだけに左上落ち影＋右下断面ハイライトを落とす。
    """
    s_ref = min(w, h)
    shadow_depth = max(14, int(round(s_ref * 0.024)))
    radius = max(2.0, shadow_depth * 0.34)

    sy = np.ones((h, 1), dtype=np.float32)
    for d in range(shadow_depth):
        t = (shadow_depth - d) / shadow_depth
        sy[d, 0] *= 1.0 - 0.44 * (t ** 1.65)
    for d in range(min(6, shadow_depth)):
        t = (min(6, shadow_depth) - d) / min(6, shadow_depth)
        sy[-(d + 1), 0] *= 1.0 - 0.18 * t
    sy_soft = np.array(
        Image.fromarray((sy * 255.0).astype(np.uint8), mode="L").filter(ImageFilter.GaussianBlur(radius=radius)),
        dtype=np.float32,
    ).ravel() / 255.0

    sx = np.ones((1, w), dtype=np.float32)
    for d in range(shadow_depth):
        t = (shadow_depth - d) / shadow_depth
        sx[0, d] *= 1.0 - 0.38 * (t ** 1.65)
    for d in range(min(6, shadow_depth)):
        t = (min(6, shadow_depth) - d) / min(6, shadow_depth)
        sx[0, -(d + 1)] *= 1.0 - 0.18 * t
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

    # 右下エッジのダイカット断面ハイライト
    rim_px = 3
    hl_rgb = np.array([255.0 / 255.0, 248.0 / 255.0, 220.0 / 255.0], dtype=np.float32)
    for r in range(rim_px):
        a_hl = ((rim_px - r) / rim_px) * 0.45
        rgba[h - 1 - r, :, :3] = hl_rgb
        rgba[h - 1 - r, :, 3] = np.maximum(rgba[h - 1 - r, :, 3], a_hl)
        rgba[:, w - 1 - r, :3] = hl_rgb
        rgba[:, w - 1 - r, 3] = np.maximum(rgba[:, w - 1 - r, 3], a_hl * 0.85)

    return Image.fromarray((np.clip(rgba, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), mode="RGBA")


def main() -> None:
    cfg = load_card_config()
    mat_cfg = cfg.get("material", {})
    glitter = float(mat_cfg.get("frameFoilGlitter", 0.45))
    brush = float(mat_cfg.get("frameBrushStrength", 0.85))
    seed = resolve_seed(cfg, section="material")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 虹金属箔フレーム (940x1660, 内窓完全透過)
    frame_img = generate_rainbow_foil_frame(
        w=940,
        h=1660,
        border=14,
        outer_r=40,
        inner_r=26,
        glitter_strength=glitter,
        brush_strength=brush,
        seed=seed,
    )
    frame_img.save(OUT_DIR / "mat_rainbow_frame.png", format="PNG", optimize=True)
    print(f"[OK] mat_rainbow_frame.png ({frame_img.width}x{frame_img.height})")

    # 2. 内窓立体深度 (912x1632)
    depth_img = generate_window_depth(912, 1632)
    depth_img.save(OUT_DIR / "mat_window_depth.png", format="PNG", optimize=True)
    print(f"[OK] mat_window_depth.png ({depth_img.width}x{depth_img.height})")


if __name__ == "__main__":
    main()
