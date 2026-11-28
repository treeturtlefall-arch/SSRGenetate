"""
SSRGenerate — 文字ヒューマナイズ＆箔物理タイポグラフィ生成エンジン

`scripts/_typo_classic.py`（クラシック手書きキネマティクス＆箔物理）、
`scripts/_typo_modern.py`（モダンタイポグラフィ）、および
`scripts/_typo_vignette.py`（写真適応ビネット＆スナップショット）を統合し、
SSRカード最前面オーバーレイ用の高精細透過PNG群とマニフェストを決定論的に生成する。

使い方:
  python scripts/render_typography.py
  python scripts/render_typography.py --preset handwritten-sign --wobble 45
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from _typo_classic import (
    CUTIN_NORM_FACTORS,
    FALLBACK_FONT_FILE,
    FONT_KINEMATICS,
    FONT_NORM_FACTORS,
    MATERIALS,
    STAMP_KINEMATICS,
    TYPO_PRESETS,
    apply_foil_and_grain_material,
    classify_char,
    get_font,
    get_font_supported_chars,
    measure_text_width,
    render_attribute_plate,
    render_humanized_line,
    render_multiline_block,
    render_rarity_crest,
    wrap_text_lines,
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
from _typo_vignette import (
    VIGNETTE_RANGES,
    _parse_css_object_position,
    build_source_snapshot,
    compute_adaptive_vignette,
)
from _utils import (
    OUT_DIR,
    PROJECT_ROOT,
    LayoutSpec,
    apply_config_overrides,
    format_attribute_key_text,
    load_card_config,
    parse_attribute_parts,
    resolve_layout,
    resolve_seed,
    save_png,
    sync_html_resolution,
)

# 昇格カットイン専用固定スタイル（カード側プリセットやレイアウト切替の影響を一切受けない）
CUTIN_STYLE: Dict[str, Dict[str, Any]] = {
    "cutinMain": {"font": "YujiSyuku-Regular.ttf", "material": "foil-gold", "stamp": False, "wobble_mul": 0.65},
}
CUTIN_WOBBLE_NORM = 0.28
CUTIN_FOIL_GLITTER = 0.42
CUTIN_PAPER_GRAIN = 0.35


def _parse_args_and_config() -> Tuple[argparse.Namespace, Dict[str, Any], LayoutSpec]:
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
        print(
            f"[OK] synced HTML resolution ({layout.orientation} {layout.canvas_w}x{layout.canvas_h}): "
            f"{', '.join(changed_html)}"
        )
    return args, cfg, layout


def _adjust_modern_title_plan(plan: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    """タイトル実効縮小率の先行計算（サブタイトル・フレーバー連動 & 2-3文字トラッキング拡大）。"""
    title_text = str(cfg.get("title", "")).strip()
    title_def = plan["slots"]["title"]
    title_def["trackingEm"] = adjust_short_title_tracking(
        title_text,
        float(title_def["trackingEm"]),
        bool(title_def.get("trackingExplicit", False)),
    )
    if not title_text:
        return

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


def _build_card_specs(cfg: Dict[str, Any], layout: LayoutSpec, attr_key_text: str) -> List[Tuple[str, str, int, int, int, str]]:
    is_land = layout.orientation == "landscape"
    return [
        ("ssr",       str(cfg.get("rarity", "SSR")), 82 if is_land else 94, 300 if is_land else 320, 1, "typo_ssr.png"),
        ("attribute", attr_key_text,                 24 if is_land else 26, 280 if is_land else 300, 1, "typo_attr.png"),
        ("subtitle",  str(cfg.get("subtitle", "")),  29 if is_land else 34, 1120 if is_land else 780, 1, "typo_subtitle.png"),
        ("title",     str(cfg.get("title", "")),     64 if is_land else 74, 1180 if is_land else 800, 1, "typo_title.png"),
        ("flavor",    str(cfg.get("flavor", "")),    25 if is_land else 29, 1120 if is_land else 780, 2, "typo_flavor.png"),
        ("cardNo",    str(cfg.get("cardNo", "")),    22 if is_land else 24, 340, 1, "typo_cardno.png"),
    ]


def _render_single_card_slot(
    idx: int,
    spec: Tuple[str, str, int, int, int, str],
    *,
    is_modern: bool,
    plan: Optional[Dict[str, Any]],
    preset_name: str,
    attr_badge: str,
    attr_label: str,
    wobble_norm: float,
    foil_glitter: float,
    paper_grain: float,
    seed: int,
) -> Optional[Tuple[str, str, int, int, str]]:
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
        style = TYPO_PRESETS[preset_name][key]
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
    save_png(img, OUT_DIR / filename)
    print(f"[OK] {key}: {filename} ({img.width}x{img.height}) -> '{clean_text}'")
    return key, filename, img.width, img.height, clean_text


def _render_cutin_slot(
    c_idx: int,
    spec: Tuple[str, str, int, int, int, str],
    seed: int,
) -> Optional[Tuple[str, str, int, int, str]]:
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
    save_png(img, OUT_DIR / filename)
    print(f"[OK] {key}: {filename} ({img.width}x{img.height}) -> '{text}' [CUTIN_FIXED]")
    return key, filename, img.width, img.height, text


def main() -> None:
    args, cfg, layout = _parse_args_and_config()
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
    if is_modern and plan is not None:
        _adjust_modern_title_plan(plan, cfg)

    attr_badge, attr_label = parse_attribute_parts(
        raw_attr=str(cfg.get("attribute", "")),
        badge=cfg.get("attributeBadge"),
        label=cfg.get("attributeLabel"),
    )
    attr_key_text = format_attribute_key_text(cfg)

    card_specs = _build_card_specs(cfg, layout, attr_key_text)
    cutin_specs = [("cutinMain", "昇格  SSR 確定", 112, 980, 1, "typo_cutin_main.png")]

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

    is_land = layout.orientation == "landscape"

    def render_rule_slot() -> Tuple[str, str, int, int, str]:
        rule_w = 1140 if is_land else 760
        rule_img = render_royal_diamond_rule(width=rule_w, palette=plan["palette"], ss=3)
        save_png(rule_img, OUT_DIR / "typo_royal_rule.png")
        print(f"[OK] royalRule: typo_royal_rule.png ({rule_img.width}x{rule_img.height})")
        return "royalRule", "typo_royal_rule.png", rule_img.width, rule_img.height, "__rule__"

    max_workers = min(8, max(2, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        card_futures = [
            executor.submit(
                _render_single_card_slot,
                idx,
                spec,
                is_modern=is_modern,
                plan=plan,
                preset_name=preset_name,
                attr_badge=attr_badge,
                attr_label=attr_label,
                wobble_norm=wobble_norm,
                foil_glitter=foil_glitter,
                paper_grain=paper_grain,
                seed=seed,
            )
            for idx, spec in enumerate(card_specs)
        ]
        rule_future = (
            executor.submit(render_rule_slot)
            if (is_modern and plan is not None and plan["layout"] == "royal-fantasy")
            else None
        )
        cutin_futures = [
            executor.submit(_render_cutin_slot, c_idx, spec, seed)
            for c_idx, spec in enumerate(cutin_specs)
        ]

        for fut in card_futures:
            res = fut.result()
            if res:
                k, fn, w, h, t = res
                manifest["items"][k] = {"src": f"assets/generated/{fn}", "width": w, "height": h, "text": t}

        if rule_future is not None:
            k, fn, w, h, t = rule_future.result()
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
