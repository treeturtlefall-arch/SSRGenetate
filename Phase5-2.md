続いて **Phase 5-2「横型カード物理アセット生成（虹フレーム・裏面・内窓深度・グレイン・箔タイポ・カットイン）」** の具体的なコード差分・実装リファレンス（全4ファイル）です。

重要なポイントは **「Portrait（縦 `900×1590`）のときは計算結果が従来と 1px の狂いもなく完全一致すること」** です。以下のコードはその互換性を100%保った設計になっています。

---

### 1. `scripts/render_material.py`（裏面紋章スケーリング・動的カード寸法・1/2グレイン）

* **ポイント**:
  * `_crest_mask` と `_guilloche_mask` に `crest_scale = min(w, h) / 900.0` を導入します。
    * 縦カード（`900×1590`）のときは `min(900, 1590) / 900.0 = 1.0` なので**従来と100%同一**。
    * 横カード（`1480×860`）のときは `crest_scale = 860 / 900.0 ≈ 0.9556`（または上下の内彫りライン `ins = 38px` との余白を美しく保つため、放射スパイク `330px` が内窓内に収まる `min(w, h) / 960.0 ≈ 0.8958`）になります。
    * 特に縦スパイク長 `330px` は、横カード高さ `860px`（中心から上下端まで `430px`、内彫りラインまで `392px`）に対して、`scale = 1.0` のままだと上下の内彫りラインにギリギリ迫りすぎるため、**横長（`w > h`）のときだけ `min(w, h) / 980.0`（`≈ 0.8775`、スパイク半径 `290px`）にスケーリング**すると、縦版では `1.0`（デグレゼロ）、横版では上下に上品な余白が生まれます。
  * `main()` で `layout = resolve_layout(cfg)` を取得し、`frame`, `depth`, `back`, `grain` に `layout` の寸法を渡します。

```python
# --- scripts/render_material.py の変更箇所 ---

# 1. import に resolve_layout を追加
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
    resolve_layout,
    resolve_seed,
    rgba_from_float,
    save_png,
    shade_metal_relief,
)

# 2. _crest_mask (L300付近): 横カード時に紋章をスケーリング (縦カード時は sc = 1.0 で完全一致)
def _crest_mask(w: int, h: int, cx: float, cy: float, ss: int = 2) -> np.ndarray:
    S_w, S_h = w * ss, h * ss
    im = Image.new("L", (S_w, S_h), 0)
    d = ImageDraw.Draw(im)
    c = (cx * ss, cy * ss)
    sc = (min(w, h) / 980.0) if w > h else (min(w, h) / 900.0)

    def ring(r: float, width: float, val: int = 255) -> None:
        rr = r * sc * ss
        d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], outline=val, width=max(1, int(width * sc * ss)))

    def star(n: int, r_out: float, r_in: float, rot: float, val: int = 255) -> None:
        pts = []
        for i in range(n * 2):
            a = math.radians(rot + i * 180.0 / n)
            r = (r_out if i % 2 == 0 else r_in) * sc * ss
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
    rr = 34 * sc * ss
    d.ellipse([c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr], fill=255)
    # 外周の目盛り
    for i in range(72):
        a = math.radians(i * 5.0)
        r0 = (196 if i % 6 else 192) * sc * ss
        r1 = (206 if i % 6 else 216) * sc * ss
        d.line(
            [(c[0] + math.cos(a) * r0, c[1] + math.sin(a) * r0), (c[0] + math.cos(a) * r1, c[1] + math.sin(a) * r1)],
            fill=235,
            width=max(1, int(2.2 * sc * ss)),
        )
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


# 3. _guilloche_mask (L338付近): ロゼット半径も同様にスケーリング
def _guilloche_mask(w: int, h: int, cx: float, cy: float, ss: int = 2) -> np.ndarray:
    """ロゼット状ギョーシェ彫り（紙幣・証券の地紋）の線画マスク"""
    S_w, S_h = w * ss, h * ss
    im = Image.new("L", (S_w, S_h), 0)
    d = ImageDraw.Draw(im)
    sc = (min(w, h) / 980.0) if w > h else (min(w, h) / 900.0)
    th = np.linspace(0.0, 2.0 * math.pi, 1440, dtype=np.float64)
    families = [
        (36, 400.0 * sc, 0.80, 0.14, 7),
        (28, 300.0 * sc, 0.74, 0.18, 11),
        (48, 560.0 * sc, 0.86, 0.09, 5),
    ]
    for count, R, base, amp, lobes in families:
        for k in range(count):
            ph = k * 2.0 * math.pi / count
            r = R * (base + amp * np.sin(lobes * th + ph))
            xs = (cx + r * np.cos(th)) * ss
            ys = (cy + r * np.sin(th)) * ss
            d.line(list(zip(xs.tolist(), ys.tolist())), fill=255, width=max(1, int(1.1 * ss)))
    return np.asarray(im.resize((w, h), Image.Resampling.LANCZOS), dtype=np.float32) / 255.0


# 4. generate_card_back 内のファセット境界半径 (L385付近) も sc に連動:
    sc = (min(w, h) / 980.0) if w > h else (min(w, h) / 900.0)
    tone = np.full_like(crest, 0.64)
    tone = np.where(rr < 150 * sc, 0.62 + 0.17 * facet8, tone)
    tone = np.where(rr > 214 * sc, 0.60 + 0.17 * facet4, tone)


# 5. main() (L455付近): resolve_layout(cfg) の寸法を渡す
def main() -> None:
    cfg = load_card_config()
    layout = resolve_layout(cfg)
    mat_cfg = cfg.get("material", {})
    glitter = float(mat_cfg.get("frameFoilGlitter", 0.45))
    brush = float(mat_cfg.get("frameBrushStrength", 0.85))
    seed = resolve_seed(cfg, section="material")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def _job_frame() -> str:
        frame_img = generate_rainbow_foil_frame(
            w=layout.card_w,
            h=layout.card_h,
            border=layout.card_border,
            outer_r=layout.card_outer_r,
            inner_r=layout.card_inner_r,
            glitter_strength=glitter,
            brush_strength=brush,
            seed=seed,
        )
        save_png(frame_img, OUT_DIR / "mat_rainbow_frame.png")
        return f"[OK] mat_rainbow_frame.png ({frame_img.width}x{frame_img.height})"

    def _job_depth() -> str:
        depth_img = generate_window_depth(layout.card_inner_w, layout.card_inner_h)
        save_png(depth_img, OUT_DIR / "mat_window_depth.png")
        return f"[OK] mat_window_depth.png ({depth_img.width}x{depth_img.height})"

    def _job_back() -> str:
        back_img = generate_card_back(w=layout.card_w, h=layout.card_h, seed=seed)
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
        gw, gh = layout.canvas_w // 2, layout.canvas_h // 2
        grain_img = generate_film_grain_overlay(gw, gh, sigma=14.0, seed=seed + 101)
        save_png(grain_img, OUT_DIR / "mat_film_grain.png")
        return f"[OK] mat_film_grain.png ({grain_img.width}x{grain_img.height})"
```

---

### 2. `scripts/_typo_modern.py`（横型カード用のスロット寸法 ＆ `resolve_modern_plan` 拡張）

* **ポイント**:
  * 横型カード（内窓 `1440×820`）は高さが縦カード（`1550px`）の約半分強しかない一方、横幅が `1.67` 倍あります。
  * そこで `resolve_modern_plan(preset_name, typo_cfg, orientation="portrait")` に `orientation` 引数を追加し、`orientation == "landscape"` のときだけ下部テキスト（`subtitle`, `title`, `flavor`）と左上/右上ヘッダー（`ssr`）の `size` を約 `84〜88%` に引き締め、`maxW` を `1160〜1220px` へ広げます。

```python
# --- scripts/_typo_modern.py の追加・変更箇所 ---

# MODERN_PRESETS の直下に横カード用のスロット調整テーブルを追加:
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


# resolve_modern_plan (L731付近) に orientation 引数を追加:
def resolve_modern_plan(
    preset_name: str,
    typo_cfg: Dict[str, Any],
    orientation: str = "portrait",
) -> Dict[str, Any]:
    """4軸直交スキーマ (preset + font/style/palette/layout 個別上書き + fonts_custom + orientation) を解決する"""
    base = MODERN_PRESETS[preset_name]
    custom_mf = load_custom_fonts_manifest()
    land_ov_map = LANDSCAPE_SLOT_OVERRIDES.get(preset_name, {}) if orientation == "landscape" else {}

    # ... (1. layout 軸, 2. palette 軸, 3. norm_factors は既存通り) ...

    slots: Dict[str, Dict[str, Any]] = {}
    for skey, sdef in base["slots"].items():
        cur = dict(sdef)
        if skey in land_ov_map:
            cur.update(land_ov_map[skey])
        cur["trackingExplicit"] = False
        # 以降の fonts_custom / card-config.js 個別スロット上書き処理は既存通り
```

---

### 3. `scripts/render_typography.py`（ビネット計測の内窓比率追従・Royal罫線幅・レガシー横枠対応）

* **ポイント**:
  1. `compute_adaptive_vignette(cfg, layout_id, layout)` が `tw = max(32, layout.card_inner_w // 5)`, `th = max(32, layout.card_inner_h // 5)`（縦 `172×310` / 横 `288×164`）で写真下部 30% の輝度を計測するようにします。
  2. `resolve_modern_plan(preset_name, typo_cfg, orientation=layout.orientation)` に向きを渡します。
  3. `render_royal_diamond_rule` の幅を縦 `760px` / 横 `1140px` に自動切り替えします。
  4. レガシー3プリセット（`foil-brush` 等）用の `card_specs` も横時は `title: 64px (max_w=1180)`, `subtitle: 29px (max_w=1120)`, `flavor: 25px (max_w=1120)` に切り替えます。

```python
# --- scripts/render_typography.py の変更箇所 ---

# 1. import を整理 (_utils から LayoutSpec, apply_config_overrides, resolve_layout, resolve_photo_path, sync_html_resolution を読み込む)
from _utils import (
    FONTS_DIR,
    GOLD_RAMP,
    OUT_DIR,
    PROJECT_ROOT,
    SILVER_RAMP,
    LayoutSpec,
    apply_config_overrides,
    gaussian_blur_f,
    generate_micro_emboss_height,
    load_card_config,
    make_linear_gradient,
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

# 2. compute_adaptive_vignette (L755付近) に layout: LayoutSpec を渡して tw, th を動的にする:
def compute_adaptive_vignette(cfg: Dict[str, Any], layout_id: str, layout: LayoutSpec) -> Dict[str, Any]:
    """入力写真の下部 30% 知覚輝度を計測し、レイアウト別レンジ内でビネット濃度を算出する"""
    spec = VIGNETTE_RANGES.get(layout_id, VIGNETTE_RANGES["classic-center"])
    def_mid, def_bot = spec["default"]
    photo_rel = str(cfg.get("photo", "assets/photo.jpg") or "assets/photo.jpg").strip().replace("\\", "/")
    photo_path = resolve_photo_path(photo_rel)
    # ... (画像オープン処理は既存通り) ...

    tw = max(32, layout.card_inner_w // 5)  # Portrait: 172, Landscape: 288
    th = max(32, layout.card_inner_h // 5)  # Portrait: 310, Landscape: 164
    # ... (以降の resize / zoom / y_start = int(round(th * 0.70)) 輝度計算はそのまま動作) ...


# 3. main() 内の plan 解決・card_specs・royalRule 生成部:
    layout = resolve_layout(cfg)
    changed_html = sync_html_resolution(layout)
    if changed_html:
        print(f"[OK] synced HTML resolution ({layout.orientation} {layout.canvas_w}x{layout.canvas_h}): {', '.join(changed_html)}")

    is_modern = preset_name in MODERN_PRESETS
    plan = resolve_modern_plan(preset_name, typo_cfg, orientation=layout.orientation) if is_modern else None

    # ... (タイトル実効縮小率の先行計算・attr_key_text 構築は既存通り) ...

    is_land = layout.orientation == "landscape"
    card_specs = [
        ("ssr",       str(cfg.get("rarity", "SSR")), 82 if is_land else 94, 300 if is_land else 320, 1, "typo_ssr.png"),
        ("attribute", attr_key_text,                 24 if is_land else 26, 280 if is_land else 300, 1, "typo_attr.png"),
        ("subtitle",  str(cfg.get("subtitle", "")),  29 if is_land else 34, 1120 if is_land else 780, 1, "typo_subtitle.png"),
        ("title",     str(cfg.get("title", "")),     64 if is_land else 74, 1180 if is_land else 800, 1, "typo_title.png"),
        ("flavor",    str(cfg.get("flavor", "")),    25 if is_land else 29, 1120 if is_land else 780, 2, "typo_flavor.png"),
        ("cardNo",    str(cfg.get("cardNo", "")),    22 if is_land else 24, 340, 1, "typo_cardno.png"),
    ]

    # ... (vignette = compute_adaptive_vignette(cfg, layout_id, layout)) ...

    # --- 1b. Royal 細二重罫線アセット（royal-fantasy 時） ---
    if is_modern and plan is not None and plan["layout"] == "royal-fantasy":
        rule_w = 1140 if is_land else 760
        rule_img = render_royal_diamond_rule(width=rule_w, palette=plan["palette"], ss=3)
        rule_path = OUT_DIR / "typo_royal_rule.png"
        save_png(rule_img, rule_path)
        manifest["items"]["royalRule"] = {
            "src": "assets/generated/typo_royal_rule.png",
            "width": rule_img.width,
            "height": rule_img.height,
            "text": "__rule__",
        }
        print(f"[OK] royalRule: typo_royal_rule.png ({rule_img.width}x{rule_img.height})")
```

---

### 4. `scripts/render_optics.py`（カットインフレア＆スピードラインの横幅 `1920px` 対応）

* **ポイント**:
  * 魔法陣・天蓋・オーブ・星・スパークル・玉ボケ・浮遊破片は正方形スプライトのため縦横共通で使えます。
  * 画面全幅に貼られる `opt_cutin_flare.png` と `opt_cutin_speedlines.png` だけ、`render_cutin_assets(canvas_w=layout.canvas_w, seed=...)` として横画面時は `1920×360` / `1920×420` で生成します。
  * スピードラインの本数も横幅比（`int(round(44 * (canvas_w / 1080.0)))`、横時は `78` 本）に比例させることで、16:9 ワイド画面でも密度が薄まりません（縦 `1080px` 時は `44` 本で完全一致）。

```python
# --- scripts/render_optics.py の変更箇所 ---

# 1. _utils からの import に resolve_layout を追加
from _utils import (
    OUT_DIR,
    linear_to_srgb,
    load_card_config,
    resolve_layout,
    resolve_seed,
    save_png,
    smoothstep,
    srgb_to_unpremul_rgba,
)

# 2. render_cutin_assets (L522付近) に canvas_w 引数を追加:
def render_cutin_assets(canvas_w: int = 1080, seed: int = 0) -> Tuple[Image.Image, Image.Image]:
    """脱ベタ帯カットイン用の水平アナモルフィックフレア(canvas_w x 360)とスピードライン(canvas_w x 420)を生成"""
    rng = np.random.default_rng((seed * 99991 + 17) & 0xFFFFFFFF)

    # 1. opt_cutin_flare.png (canvas_w x 360)
    fw, fh = int(canvas_w), 360
    yy, xx = np.mgrid[0:fh, 0:fw].astype(np.float32)
    nx = (xx - (fw - 1) * 0.5) / ((fw - 1) * 0.5)
    ny = (yy - (fh - 1) * 0.5) / ((fh - 1) * 0.5)
    edge_fade = (1.0 - smoothstep(0.76, 0.98, np.abs(nx))) * (1.0 - smoothstep(0.60, 0.96, np.abs(ny)))

    core_line = np.exp(-((ny / 0.022) ** 2)) * np.exp(-((nx / 0.72) ** 2)) * 1.6
    mid_band = np.exp(-((ny / 0.11) ** 2)) * np.exp(-((nx / 0.82) ** 2)) * 0.65
    diamond = np.exp(-(np.abs(nx) / 0.22 + np.abs(ny) / 0.16)) * 1.25
    halo_band = np.exp(-((ny / 0.34) ** 2)) * np.exp(-((nx / 0.90) ** 2)) * 0.28

    lr_mix = (0.5 + 0.5 * np.tanh(nx * 2.2))[..., None]
    col_left = np.array([0.28, 0.78, 1.00], dtype=np.float32)[None, None, :]
    col_right = np.array([1.00, 0.38, 0.68], dtype=np.float32)[None, None, :]
    col_band = col_left * (1.0 - lr_mix) + col_right * lr_mix
    lin_flare = (
        (core_line + diamond)[..., None] * np.array([1.0, 0.99, 0.96], dtype=np.float32)
        + (mid_band + halo_band)[..., None] * col_band
    ) * edge_fade[..., None]
    flare_img = srgb_to_unpremul_rgba(linear_to_srgb(1.0 - np.exp(-np.maximum(lin_flare, 0.0) * 1.3)))

    # 2. opt_cutin_speedlines.png (canvas_w x 420)
    sw, sh = int(canvas_w), 420
    sl = np.zeros((sh, sw, 3), dtype=np.float32)
    y_1d = np.arange(sh, dtype=np.float32)[:, None]
    x_1d = np.arange(sw, dtype=np.float32)[None, :]
    v_fade = smoothstep(0.04, 0.28, y_1d / sh) * (1.0 - smoothstep(0.72, 0.96, y_1d / sh))
    h_fade = 1.0 - smoothstep(0.80, 0.98, np.abs((x_1d - sw * 0.5) / (sw * 0.5)))

    palette = [
        np.array([1.00, 0.96, 0.84], dtype=np.float32),
        np.array([0.52, 0.88, 1.00], dtype=np.float32),
        np.array([0.96, 0.58, 0.78], dtype=np.float32),
    ]
    n_lines = int(round(44 * (sw / 1080.0)))
    w_scale = sw / 1080.0
    for i in range(n_lines):
        yc = float(rng.uniform(28, sh - 28))
        xc = float(rng.uniform(140 * w_scale, sw - 140 * w_scale))
        half_len = float(rng.uniform(90 * w_scale, 420 * w_scale))
        thick = float(rng.uniform(0.8, 2.2))
        amp = float(rng.uniform(0.30, 0.95))
        line_y = np.exp(-((y_1d - yc) / thick) ** 2)
        line_x = (np.maximum(0.0, 1.0 - np.abs(x_1d - xc) / half_len) ** 1.6) * amp
        col = palette[i % len(palette)]
        sl += (line_y @ line_x)[..., None] * col[None, None, :]

    sl *= (v_fade @ h_fade)[..., None]
    speed_img = srgb_to_unpremul_rgba(linear_to_srgb(1.0 - np.exp(-np.maximum(sl, 0.0) * 1.2)))
    return flare_img, speed_img


# 3. main() 内で layout = resolve_layout(cfg) を取得し _cutin_job に渡す:
        layout = resolve_layout(cfg)
        # ...
        def _cutin_job() -> str:
            flare_img, speed_img = render_cutin_assets(canvas_w=layout.canvas_w, seed=seed + 2901)
            save_png(flare_img, OUT_DIR / "opt_cutin_flare.png")
            save_png(speed_img, OUT_DIR / "opt_cutin_speedlines.png")
            return f"[OK] opt_cutin_flare.png ({flare_img.width}x360) & opt_cutin_speedlines.png ({speed_img.width}x420)"
```

---

これで **Phase 5-2** の全物理アセット生成が縦横両対応になります。
最後に **Phase 5-3（召喚 `scene-summon.*`・リザルト `scene-result.*` の 16:9 コンポジション対応 ＆ `qa_video.py` の解像度フリー化）** の実装コード例も続けてお出ししましょうか？