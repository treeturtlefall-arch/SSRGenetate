"""
SSRGenerate — 物理光学発光（Optical Burn-in）アセット生成エンジン

`scripts/_optics_core.py` の6段階物理光学モデル、`scripts/_optics_masks.py` の
幾何マスク＆オーブ生成、および `scripts/_optics_fx.py` の各種エフェクト生成を統合し、
SSRガチャ演出の高精細透過PNG群を決定論的に並列生成する。

使い方:
  python scripts/render_optics.py
  python scripts/render_optics.py --cutin-only
"""
from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from _optics_core import (
    OPTICAL_SPECTRA,
    aniso_fbm,
    approx_inner_distance,
    bilinear_warp,
    fbm_noise,
    fft_gaussian_blur,
    prepare_optical_mask,
    render_optical_glow,
    value_noise,
)
from _optics_fx import (
    WISP_PALETTES,
    render_bokeh_sprite,
    render_crystal_shards,
    render_cutin_assets,
    render_descent_meteor,
    render_godrays_layer,
    render_light_pillar,
    render_shockwave_ring,
    render_sky_bolts,
    render_wisp_head,
)
from _optics_masks import (
    build_celestial_gate_masks,
    build_magic_circle_masks,
    build_orb_cracks_mask,
    build_result_ring_mask,
    build_sparkle_mask,
    build_star_mask,
    draw_dashed_circle,
    render_crystal_orb_layers,
    render_orb_core_bleach,
)
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

# 後方互換エイリアス
_smoothstep = smoothstep
_srgb_to_unpremul_rgba = srgb_to_unpremul_rgba
_aniso_fbm = aniso_fbm


def _submit_glow(
    ex_pool: ThreadPoolExecutor,
    tasks: List[Future[str]],
    fname: str,
    mask: Image.Image,
    spec: str,
    ref_scale: float,
    exp: float,
    core_g: float,
    hal_v: float,
    irr_v: float,
    is_prism: bool,
    s_val: int,
    prepared: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]] = None,
) -> None:
    def _job() -> str:
        img = render_optical_glow(
            mask_l=mask,
            spectrum_name=spec,
            ref_scale=ref_scale,
            exposure=exp,
            core_glow=core_g,
            halation=hal_v,
            irregularity=irr_v,
            prism_mode=is_prism,
            seed=s_val,
            prepared=prepared,
        )
        save_png(img, OUT_DIR / fname)
        return f"[OK] {fname} ({img.width}x{img.height})"

    tasks.append(ex_pool.submit(_job))


def _prepare_shared_masks(
    ex: ThreadPoolExecutor,
    seed: int,
) -> Dict[str, Any]:
    """複数色で共有するマスク群と距離変換キャッシュを並列事前計算する。"""
    m_outer, m_mid, m_inner = build_magic_circle_masks(1024, seed=seed + 77)
    g_outer, g_inner = build_celestial_gate_masks(1024, seed=seed + 3101)
    cracks_mask = build_orb_cracks_mask(512, seed=seed + 501)
    star_mask = build_star_mask(144)
    sp_mask = build_sparkle_mask(128)
    ring_mask = build_result_ring_mask(1400, seed=seed + 1201)

    prep_mc = {
        "outer": ex.submit(prepare_optical_mask, m_outer, 20.0),
        "mid":   ex.submit(prepare_optical_mask, m_mid, 20.0),
        "inner": ex.submit(prepare_optical_mask, m_inner, 20.0),
    }
    prep_gate = {
        "outer": ex.submit(prepare_optical_mask, g_outer, 20.0),
        "inner": ex.submit(prepare_optical_mask, g_inner, 20.0),
    }
    prep_ring_fut = ex.submit(prepare_optical_mask, ring_mask, 14.0)

    return {
        "rings": [
            ("outer", m_outer, prep_mc["outer"].result()),
            ("mid",   m_mid,   prep_mc["mid"].result()),
            ("inner", m_inner, prep_mc["inner"].result()),
        ],
        "gate_rings": [
            ("outer", g_outer, prep_gate["outer"].result()),
            ("inner", g_inner, prep_gate["inner"].result()),
        ],
        "cracks_mask": cracks_mask,
        "star_mask": star_mask,
        "sp_mask": sp_mask,
        "ring_mask": ring_mask,
        "prep_ring": prep_ring_fut.result(),
    }


def _submit_orb_and_beam_tasks(
    ex: ThreadPoolExecutor,
    tasks: List[Future[str]],
    canvas_w: int,
    seed: int,
) -> None:
    """多面体オーブ・ゴッドレイ・光柱・衝撃波・カットイン光学素材の並列タスクを登録。"""
    for i, cname in enumerate(("blue", "gold", "rainbow")):
        def _orb_job(cn: str = cname, idx: int = i) -> str:
            sh_img, fc_img = render_crystal_orb_layers(cn, size=512, seed=seed + 2101 + idx * 37)
            save_png(sh_img, OUT_DIR / f"opt_orb_{cn}_shell.png")
            save_png(fc_img, OUT_DIR / f"opt_orb_{cn}_facet.png")
            return f"[OK] opt_orb_{cn}_{{shell,facet}}.png (512x512)"

        tasks.append(ex.submit(_orb_job))

    def _core_job() -> str:
        core_img = render_orb_core_bleach(size=512)
        save_png(core_img, OUT_DIR / "opt_orb_core_bleach.png")
        return "[OK] opt_orb_core_bleach.png (512x512)"

    tasks.append(ex.submit(_core_job))

    for mode in ("prism", "gold"):
        for var in ("a", "b"):
            def _gr_job(m: str = mode, v: str = var) -> str:
                gr_img = render_godrays_layer(mode=m, variant=v, size=1200, seed=seed + 2301)
                fname = f"opt_godrays_{m}_{v}.png"
                save_png(gr_img, OUT_DIR / fname)
                return f"[OK] {fname} ({gr_img.width}x{gr_img.height})"

            tasks.append(ex.submit(_gr_job))

    for style in ("gold", "rainbow"):
        def _pl_job(st: str = style) -> str:
            pl_img = render_light_pillar(style=st, w=512, h=1680, seed=seed + 2501)
            save_png(pl_img, OUT_DIR / f"opt_pillar_{st}.png")
            sw_img = render_shockwave_ring(style=st, size=640, seed=seed + 2701)
            save_png(sw_img, OUT_DIR / f"opt_shock_{st}.png")
            return f"[OK] opt_pillar_{st}.png & opt_shock_{st}.png"

        tasks.append(ex.submit(_pl_job))

    def _cutin_job() -> str:
        flare_img, speed_img = render_cutin_assets(canvas_w=canvas_w, seed=seed + 2901)
        save_png(flare_img, OUT_DIR / "opt_cutin_flare.png")
        save_png(speed_img, OUT_DIR / "opt_cutin_speedlines.png")
        return f"[OK] opt_cutin_flare.png ({flare_img.width}x360) & opt_cutin_speedlines.png ({speed_img.width}x420)"

    tasks.append(ex.submit(_cutin_job))


def _submit_result_and_sky_tasks(
    ex: ThreadPoolExecutor,
    tasks: List[Future[str]],
    shared: Dict[str, Any],
    mc_styles: List[Tuple[str, str, bool, float, float]],
    cg: float,
    hal: float,
    irr: float,
    seed: int,
) -> None:
    """リザルトリング・玉ボケ・天蓋ゲート・ウィスプ/天啓光撃・破片の並列タスクを登録。"""
    ring_styles = [
        ("rainbow", "summon_gold", True,  1.08, hal * 1.20),
        ("gold",    "summon_gold", False, 0.95, hal * 1.15),
        ("blue",    "summon_blue", False, 1.00, hal * 1.12),
    ]
    for r_idx, (r_cname, r_spec, r_prism, r_exp, r_hal) in enumerate(ring_styles):
        def _res_ring_job(
            cn: str = r_cname,
            sp: str = r_spec,
            pr: bool = r_prism,
            ex_v: float = r_exp,
            ha_v: float = r_hal,
            s_off: int = r_idx * 41,
        ) -> str:
            img = render_optical_glow(
                mask_l=shared["ring_mask"],
                spectrum_name=sp,
                ref_scale=14.0,
                exposure=ex_v,
                core_glow=cg,
                halation=ha_v,
                irregularity=irr,
                prism_mode=pr,
                seed=seed + 1201 + s_off,
                prepared=shared["prep_ring"],
            )
            save_png(img, OUT_DIR / f"opt_result_ring_{cn}.png")
            if cn == "gold":
                save_png(img, OUT_DIR / "opt_result_ring.png")
            return f"[OK] opt_result_ring_{cn}.png ({img.width}x{img.height})"

        tasks.append(ex.submit(_res_ring_job))

    def _bokeh_job() -> str:
        bokeh_tints = {
            "gold": (1.00, 0.84, 0.52),
            "rose": (1.00, 0.62, 0.78),
            "aqua": (0.55, 0.88, 1.00),
            "white": (1.00, 0.97, 0.92),
        }
        for i, (cname, tint) in enumerate(bokeh_tints.items()):
            for depth, blur in (("far", 1.6), ("near", 9.0)):
                bk = render_bokeh_sprite(
                    tint,
                    size_px=160,
                    radius=44.0 if depth == "far" else 40.0,
                    blur=blur,
                    seed=seed + 1301 + i,
                )
                save_png(bk, OUT_DIR / f"opt_bokeh_{cname}_{depth}.png")
        return "[OK] opt_bokeh_{gold,rose,aqua,white}_{far,near}.png (160x160)"

    tasks.append(ex.submit(_bokeh_job))

    for s_idx, (cname, spec, is_prism, exp, h_val) in enumerate(mc_styles):
        for r_idx, (rname, mask, prep) in enumerate(shared["gate_rings"]):
            _submit_glow(
                ex, tasks, f"opt_gate_{cname}_{rname}.png", mask, spec,
                20.0, exp * 0.96, cg, h_val, irr, is_prism,
                seed + 3100 + s_idx * 97 + r_idx * 19, prepared=prep,
            )

    def _meteor_bolts_job() -> str:
        for c_idx, cname in enumerate(("blue", "red", "green")):
            meteor_img = render_descent_meteor(style=cname, w=256, h=256, seed=seed + 3401 + c_idx * 13)
            save_png(meteor_img, OUT_DIR / f"opt_meteor_{cname}.png")
            head_img = render_wisp_head(style=cname, size=256, seed=seed + 3451 + c_idx * 13)
            save_png(head_img, OUT_DIR / f"opt_wisp_head_{cname}.png")
        bolt_gold_img, bolt_prism_img = render_sky_bolts(seed=seed + 3601)
        save_png(bolt_gold_img, OUT_DIR / "opt_bolt_gold.png")
        save_png(bolt_prism_img, OUT_DIR / "opt_bolt_prism.png")
        return "[OK] opt_meteor_{blue,red,green}.png, opt_wisp_head_{blue,red,green}.png & opt_bolt_{gold,prism}.png"

    tasks.append(ex.submit(_meteor_bolts_job))

    def _shards_job() -> str:
        shards = render_crystal_shards(seed=seed + 3801)
        for fname, s_img in shards.items():
            save_png(s_img, OUT_DIR / fname)
        return "[OK] opt_shard_{far,near}_{0,1,2}.png (6 files)"

    tasks.append(ex.submit(_shards_job))


def main() -> None:
    parser = argparse.ArgumentParser(description="Render optical assets")
    parser.add_argument(
        "--cutin-only",
        action="store_true",
        help="Render only cutin flare and speedlines (fast resolution sync)",
    )
    args = parser.parse_args()

    cfg = load_card_config()
    layout = resolve_layout(cfg)
    seed = resolve_seed(cfg, section="optics")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.cutin_only and (OUT_DIR / "opt_orb_core_bleach.png").exists():
        flare_img, speed_img = render_cutin_assets(canvas_w=layout.canvas_w, seed=seed + 2901)
        save_png(flare_img, OUT_DIR / "opt_cutin_flare.png")
        save_png(speed_img, OUT_DIR / "opt_cutin_speedlines.png")
        print(
            f"[OK] [cutin-only] opt_cutin_flare.png ({flare_img.width}x360) & "
            f"opt_cutin_speedlines.png ({speed_img.width}x420)"
        )
        return

    opt_cfg = cfg.get("optics", {})
    hal = float(opt_cfg.get("halation", 1.05))
    cg = float(opt_cfg.get("coreGlow", 1.15))
    irr = float(opt_cfg.get("irregularity", 0.85))

    mc_styles = [
        ("blue",    "summon_blue", False, 1.02, hal * 0.95),
        ("gold",    "summon_gold", False, 1.12, hal * 1.10),
        ("rainbow", "summon_gold", True,  1.22, hal * 1.25),
    ]

    with ThreadPoolExecutor(max_workers=8) as ex:
        shared = _prepare_shared_masks(ex, seed)
        tasks: List[Future[str]] = []

        # 1. 魔法陣 3色 × 3層
        for s_idx, (cname, spec, is_prism, exp, h_val) in enumerate(mc_styles):
            for r_idx, (rname, mask, prep) in enumerate(shared["rings"]):
                _submit_glow(
                    ex, tasks, f"opt_mc_{cname}_{rname}.png", mask, spec,
                    20.0, exp, cg, h_val, irr, is_prism,
                    seed + s_idx * 100 + r_idx * 17, prepared=prep,
                )

        # 2. オーブ臨界亀裂
        _submit_glow(
            ex, tasks, "opt_orb_cracks.png", shared["cracks_mask"], "summon_gold",
            20.0, 1.32, cg * 1.20, hal * 1.20, irr, True, seed + 501,
        )

        # 3-5. オーブ・ゴッドレイ・光柱・衝撃波・カットイン
        _submit_orb_and_beam_tasks(ex, tasks, layout.canvas_w, seed)

        # 6. リザルト星5つ
        _submit_glow(
            ex, tasks, "opt_star_gold.png", shared["star_mask"], "star_gold",
            18.0, 1.18, cg * 1.10, hal * 0.95, irr * 0.65, False, seed + 701,
        )

        # 7. 周囲スパークル 4色
        for i, (cname, spec) in enumerate([
            ("gold",  "sparkle_gold"),
            ("white", "sparkle_white"),
            ("pink",  "sparkle_pink"),
            ("cyan",  "sparkle_cyan"),
        ]):
            _submit_glow(
                ex, tasks, f"opt_sparkle_{cname}.png", shared["sp_mask"], spec,
                16.0, 1.15, cg * 1.15, hal * 1.05, irr * 0.70, False, seed + 901 + i * 31,
            )

        # 8-12. リザルトリング・玉ボケ・天蓋ゲート・ウィスプ/光撃・破片
        _submit_result_and_sky_tasks(ex, tasks, shared, mc_styles, cg, hal, irr, seed)

        for fut in tasks:
            print(fut.result())


if __name__ == "__main__":
    main()
