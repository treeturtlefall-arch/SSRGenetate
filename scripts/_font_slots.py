"""
SSRGenerate — ローカル専用カスタムフォントスロット解決 (`assets/fonts_custom/`)

`scripts/_audio_slots.py` と同じ設計思想で、`.gitignore` 隔離された
`assets/fonts_custom/` を最優先探索し、未配置時は同梱 `assets/fonts/` へ
安全にフォールバックする。
"""
from __future__ import annotations

import functools
import json
import struct
from pathlib import Path
from typing import Any, Dict, Optional, Set

from _utils import CUSTOM_FONTS_DIR, FONTS_DIR

# 書体別・視覚サイズ正規化係数（Phase A/D 実測値の一元定義）
FONT_NORM_FACTORS: Dict[str, float] = {
    "YujiSyuku-Regular.ttf": 1.04,
    "KleeOne-Regular.ttf": 1.05,
    "SetoFont.ttf": 1.02,
    "TekitouPoem.ttf": 1.20,
    "TekitouPoem_Bold.ttf": 1.15,
    "ZenKurenaido-Regular.ttf": 0.99,
    "cinecaption.ttf": 0.97,
    "ShipporiMincho-Bold.ttf": 0.94,
    "ShipporiMincho-ExtraBold.ttf": 0.94,
    "Cinzel-VF.ttf": 1.03,
    "ZenMaruGothic-Bold.ttf": 0.95,
    "ZenMaruGothic-Black.ttf": 0.94,
    "Outfit-VF.ttf": 1.00,
    "JetBrainsMono-VF.ttf": 0.99,
}


@functools.lru_cache(maxsize=64)
def get_cmap_chars(font_path_str: str) -> Set[int]:
    """TTF/OTF の cmap テーブル (Format 4 / 12) を直接パースし、収録 Unicode コードポイント集合を返す"""
    chars: Set[int] = set()
    p = Path(font_path_str)
    if not p.is_file():
        return chars
    try:
        with open(p, "rb") as f:
            f.read(4)
            num_tables, = struct.unpack(">H", f.read(2))
            f.seek(12)
            cmap_offset = None
            for _ in range(num_tables):
                tag = f.read(4)
                _, offset, _ = struct.unpack(">III", f.read(12))
                if tag == b"cmap":
                    cmap_offset = offset
                    break
            if not cmap_offset:
                return chars
            f.seek(cmap_offset)
            _, num_subtables = struct.unpack(">HH", f.read(4))
            subtables = []
            for _ in range(num_subtables):
                _, _, offset = struct.unpack(">HHI", f.read(8))
                subtables.append(cmap_offset + offset)
            for sub_off in subtables:
                f.seek(sub_off)
                fmt, = struct.unpack(">H", f.read(2))
                if fmt == 4:
                    _, _, seg_x2 = struct.unpack(">HHH", f.read(6))
                    seg_count = seg_x2 // 2
                    f.seek(sub_off + 14)
                    end_codes = struct.unpack(f">{seg_count}H", f.read(seg_count * 2))
                    f.seek(sub_off + 14 + seg_count * 2 + 2)
                    start_codes = struct.unpack(f">{seg_count}H", f.read(seg_count * 2))
                    id_deltas = struct.unpack(f">{seg_count}h", f.read(seg_count * 2))
                    iro_pos = f.tell()
                    id_range_offsets = struct.unpack(f">{seg_count}H", f.read(seg_count * 2))
                    for i in range(seg_count):
                        s, e = start_codes[i], end_codes[i]
                        if s == 0xFFFF:
                            break
                        if id_range_offsets[i] == 0:
                            for c in range(s, e + 1):
                                if (c + id_deltas[i]) & 0xFFFF != 0:
                                    chars.add(c)
                        else:
                            for c in range(s, e + 1):
                                off = iro_pos + i * 2 + id_range_offsets[i] + (c - s) * 2
                                f.seek(off)
                                gidx, = struct.unpack(">H", f.read(2))
                                if gidx != 0 and (gidx + id_deltas[i]) & 0xFFFF != 0:
                                    chars.add(c)
                elif fmt == 12:
                    f.seek(sub_off + 12)
                    num_groups, = struct.unpack(">I", f.read(4))
                    for _ in range(num_groups):
                        sc, ec, _ = struct.unpack(">III", f.read(12))
                        for c in range(sc, ec + 1):
                            chars.add(c)
    except Exception:
        pass
    return chars


def build_norm_factors(custom_mf: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """標準係数と fonts_custom/fonts.json の norm_factors をマージした辞書を返す"""
    merged = dict(FONT_NORM_FACTORS)
    if isinstance(custom_mf, dict) and isinstance(custom_mf.get("norm_factors"), dict):
        for k, v in custom_mf["norm_factors"].items():
            merged[str(k)] = float(v)
    return merged


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
