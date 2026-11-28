"""scripts/_utils.py の設定ロード・レイアウト解決・決定論シードの単体テスト。"""
from __future__ import annotations

from _utils import (
    apply_config_overrides,
    load_card_config,
    parse_attribute_parts,
    resolve_layout,
    resolve_seed,
)


def test_load_card_config_has_required_fields():
    cfg = load_card_config()
    assert isinstance(cfg, dict)
    assert "rarity" in cfg
    assert "title" in cfg


def test_resolve_layout_portrait_and_landscape():
    portrait = resolve_layout({"orientation": "portrait"})
    assert portrait.orientation == "portrait"
    assert (portrait.canvas_w, portrait.canvas_h) == (1080, 1920)
    assert (portrait.card_w, portrait.card_h) == (900, 1590)
    assert portrait.card_border == 20

    landscape = resolve_layout({"orientation": "landscape"})
    assert landscape.orientation == "landscape"
    assert landscape.canvas_w > landscape.canvas_h
    assert landscape.card_w > landscape.card_h


def test_apply_config_overrides_is_non_destructive():
    base = {"title": "Original", "typography": {"preset": "royal-foil", "wobble": 20}}
    merged = apply_config_overrides(base, {"title": "Updated", "typography": {"wobble": 50}})
    assert merged["title"] == "Updated"
    assert merged["typography"]["preset"] == "royal-foil"
    assert merged["typography"]["wobble"] == 50
    assert base["title"] == "Original"


def test_resolve_seed_deterministic():
    cfg = {"seed": 777}
    assert resolve_seed(cfg, section="optics") == resolve_seed(cfg, section="optics")
    assert resolve_seed(cfg, section="typography", override=1234) == 1234


def test_parse_attribute_parts():
    badge, label = parse_attribute_parts(raw_attr="愛 / ANGEL")
    assert badge == "愛"
    assert label == "ANGEL"
