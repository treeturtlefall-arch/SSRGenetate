"""
SSRGenerate — ローカル専用カスタムフォントスロット解決 (`assets/fonts_custom/`)

`scripts/_audio_slots.py` と同じ設計思想で、`.gitignore` 隔離された
`assets/fonts_custom/` を最優先探索し、未配置時は同梱 `assets/fonts/` へ
安全にフォールバックする。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from _utils import CUSTOM_FONTS_DIR, FONTS_DIR


def load_custom_fonts_manifest() -> Dict[str, Any]:
    """assets/fonts_custom/fonts.json があれば読み込む"""
    manifest_path = CUSTOM_FONTS_DIR / "fonts.json"
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_font_path(font_name: str) -> Optional[Path]:
    """fonts_custom/ → fonts/ → Windows/Fonts の順でフォントファイルを解決する"""
    if not font_name:
        return None
    for base in (CUSTOM_FONTS_DIR, FONTS_DIR, Path(r"C:\Windows\Fonts")):
        cand = base / font_name
        if cand.is_file():
            return cand
    return None


def resolve_slot_font(slot_key: str, default_font: str, manifest: Optional[Dict[str, Any]] = None) -> str:
    """fonts.json の slots 上書きがあれば優先し、存在しない場合は default_font へフォールバック"""
    mf = manifest if manifest is not None else load_custom_fonts_manifest()
    slots = mf.get("slots", {}) if isinstance(mf, dict) else {}
    override = slots.get(slot_key)
    if isinstance(override, str) and override.strip():
        if resolve_font_path(override.strip()) is not None:
            return override.strip()
    return default_font
