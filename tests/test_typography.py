"""タイポグラフィモジュール (_typo_classic / _typo_vignette / render_typography) の単体・決定論性テスト。"""
from __future__ import annotations

import numpy as np

from _typo_classic import classify_char, render_multiline_block, wrap_text_lines
from _typo_vignette import _parse_css_object_position
import render_typography


def test_typography_reexports_backward_compat():
    for name in (
        "TYPO_PRESETS",
        "MATERIALS",
        "render_humanized_line",
        "render_multiline_block",
        "render_rarity_crest",
        "render_attribute_plate",
        "compute_adaptive_vignette",
        "build_source_snapshot",
    ):
        assert hasattr(render_typography, name), f"missing re-export: {name}"


def test_classify_char_categories():
    assert classify_char("愛") == "kanji"
    assert classify_char("あ") == "kana"
    assert classify_char("!") == "punct"
    assert classify_char("A") == "other"


def test_parse_css_object_position():
    assert _parse_css_object_position("50% 35%") == (0.5, 0.35)
    assert _parse_css_object_position("left top") == (0.0, 0.0)
    assert _parse_css_object_position("right bottom") == (1.0, 1.0)


def test_wrap_text_lines_respects_explicit_newline():
    lines = wrap_text_lines("一行目\n二行目", "ShipporiMincho-Bold.ttf", 32, max_w=600, max_lines=2)
    assert lines == ["一行目", "二行目"]


def test_render_multiline_block_deterministic():
    img1 = render_multiline_block(
        text="SSR 確定",
        font_file="YujiSyuku-Regular.ttf",
        font_size=48,
        max_w=500.0,
        max_lines=1,
        material_name="foil-gold",
        wobble_strength=0.25,
        foil_glitter=0.4,
        paper_grain=0.3,
        is_stamp=False,
        seed=42,
    )
    img2 = render_multiline_block(
        text="SSR 確定",
        font_file="YujiSyuku-Regular.ttf",
        font_size=48,
        max_w=500.0,
        max_lines=1,
        material_name="foil-gold",
        wobble_strength=0.25,
        foil_glitter=0.4,
        paper_grain=0.3,
        is_stamp=False,
        seed=42,
    )
    assert img1 is not None and img2 is not None
    assert img1.mode == "RGBA"
    assert np.array_equal(np.asarray(img1), np.asarray(img2))
