"""
SSRGenerate — アセット生成スクリプト共通ユーティリティ

- card-config.js の読み込み (`load_card_config`)
- 決定論的シード解決 (`resolve_seed`)
- 斜め多段ストップ・リニアグラデーション生成 (`make_linear_gradient`)
- 多周波微細シボ高さマップ生成 (`generate_micro_emboss_height`)
- 標準偏差正規化 (`norm_std`)
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
OUT_DIR = ASSETS_DIR / "generated"
CONFIG_PATH = PROJECT_ROOT / "card-config.js"
DEFAULT_SEED = 20261120


def load_card_config() -> Dict[str, Any]:
    """card-config.js から window.SSR_CARD_CONFIG を読み込む"""
    if CONFIG_PATH.exists():
        try:
            res = subprocess.run(
                [
                    "node",
                    "-e",
                    (
                        "const fs=require('fs');"
                        "const window={};"
                        "eval(fs.readFileSync(process.argv[1],'utf8'));"
                        "process.stdout.write(JSON.stringify(window.SSR_CARD_CONFIG||{}));"
                    ),
                    str(CONFIG_PATH),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            return json.loads(res.stdout)
        except Exception:
            pass
    return {}


def resolve_seed(cfg: Dict[str, Any], section: str | None = None, override: int | None = None) -> int:
    """セクション固有シード → ルートシード → デフォルトシードの順で決定論シードを解決する"""
    if override is not None:
        return int(override)
    if section and isinstance(cfg.get(section), dict):
        sec_seed = cfg[section].get("seed")
        if sec_seed is not None:
            return int(sec_seed)
    return int(cfg.get("seed", DEFAULT_SEED))


def norm_std(arr: np.ndarray) -> np.ndarray:
    """配列を平均0・標準偏差1に正規化する"""
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    if std < 1e-6:
        return arr - mean
    return (arr - mean) / std


def make_linear_gradient(
    h: int,
    w: int,
    stops: List[Tuple[int, int, int]],
    angle_deg: float = 135.0,
) -> np.ndarray:
    """多段ストップの斜めリニアグラデーション画像 (H, W, 3) float32 [0, 1] を生成する"""
    n_stops = len(stops)
    if n_stops == 1:
        arr = np.zeros((h, w, 3), dtype=np.float32)
        arr[:, :] = np.array(stops[0], dtype=np.float32) / 255.0
        return arr

    th = math.radians(angle_deg)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = xx / max(1.0, float(w - 1)) - 0.5
    ny = yy / max(1.0, float(h - 1)) - 0.5
    proj = nx * math.cos(th) + ny * math.sin(th)
    pmin, pmax = float(proj.min()), float(proj.max())
    t = (proj - pmin) / max(1e-6, pmax - pmin)

    scaled = np.clip(t * (n_stops - 1), 0.0, float(n_stops - 1) - 1e-6)
    idx = scaled.astype(np.int32)
    frac = (scaled - idx)[:, :, None]
    stops_arr = np.array(stops, dtype=np.float32) / 255.0
    c0 = stops_arr[idx]
    c1 = stops_arr[np.minimum(idx + 1, n_stops - 1)]
    return c0 * (1.0 - frac) + c1 * frac


def generate_micro_emboss_height(h: int, w: int, rng: np.random.Generator) -> np.ndarray:
    """軽量多周波微細シボ高さマップ（平均0・標準偏差1）を生成する"""
    hs1, ws1 = max(8, int(h * 0.65)), max(8, int(w * 0.65))
    n1 = rng.standard_normal((hs1, ws1)).astype(np.float32)
    a1 = np.array(
        Image.fromarray(np.clip((n1 / 5.5 + 0.5) * 255.0, 0, 255).astype(np.uint8), "L").resize(
            (w, h), Image.Resampling.BILINEAR
        ),
        dtype=np.float32,
    )
    hs2, ws2 = max(6, int(h * 0.35)), max(6, int(w * 0.35))
    n2 = rng.standard_normal((hs2, ws2)).astype(np.float32)
    a2 = np.array(
        Image.fromarray(np.clip((n2 / 5.5 + 0.5) * 255.0, 0, 255).astype(np.uint8), "L").resize(
            (w, h), Image.Resampling.BICUBIC
        ),
        dtype=np.float32,
    )
    return norm_std(a1 * 0.6 + a2 * 0.4)
