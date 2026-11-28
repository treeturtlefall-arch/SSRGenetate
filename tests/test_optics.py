"""光学モジュール (_optics_masks / _optics_fx / render_optics) のスモーク＆決定論性テスト。"""
from __future__ import annotations

import numpy as np

from _optics_fx import render_bokeh_sprite, render_cutin_assets
from _optics_masks import build_sparkle_mask, build_star_mask, render_orb_core_bleach
import render_optics


def test_optics_reexports_backward_compat():
    for name in (
        "build_magic_circle_masks",
        "build_celestial_gate_masks",
        "render_crystal_orb_layers",
        "render_cutin_assets",
        "render_sky_bolts",
        "render_crystal_shards",
    ):
        assert hasattr(render_optics, name), f"missing re-export: {name}"


def test_star_and_sparkle_masks_shape_and_determinism():
    s1 = build_star_mask(144)
    s2 = build_star_mask(144)
    assert s1.size == (144, 144)
    assert np.array_equal(np.asarray(s1), np.asarray(s2))

    sp1 = build_sparkle_mask(128)
    assert sp1.size == (128, 128)
    assert np.asarray(sp1).max() > 0


def test_orb_core_and_bokeh_deterministic():
    c1 = render_orb_core_bleach(size=128)
    c2 = render_orb_core_bleach(size=128)
    assert c1.size == (128, 128)
    assert np.array_equal(np.asarray(c1), np.asarray(c2))

    b1 = render_bokeh_sprite((1.0, 0.84, 0.52), size_px=96, radius=24.0, blur=2.0, seed=42)
    b2 = render_bokeh_sprite((1.0, 0.84, 0.52), size_px=96, radius=24.0, blur=2.0, seed=42)
    assert b1.mode == "RGBA"
    assert np.array_equal(np.asarray(b1), np.asarray(b2))


def test_cutin_assets_dimensions_and_determinism():
    f1, s1 = render_cutin_assets(canvas_w=1080, seed=101)
    f2, s2 = render_cutin_assets(canvas_w=1080, seed=101)
    assert f1.size == (1080, 360)
    assert s1.size == (1080, 420)
    assert np.array_equal(np.asarray(f1), np.asarray(f2))
    assert np.array_equal(np.asarray(s1), np.asarray(s2))
