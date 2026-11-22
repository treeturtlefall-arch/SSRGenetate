"""
SSRGenerate — 全アセット一括並列生成ランナー

`npm run build:assets` から呼び出され、互いに独立した4つの生成スクリプト
（タイポグラフィ・光学・マテリアル・効果音）を並列プロセスで同時実行する。
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple

from _utils import load_card_config, resolve_layout, sync_html_resolution

SCRIPTS_DIR = Path(__file__).resolve().parent
JOBS = [
    ("typo",     SCRIPTS_DIR / "render_typography.py"),
    ("optics",   SCRIPTS_DIR / "render_optics.py"),
    ("material", SCRIPTS_DIR / "render_material.py"),
    ("se",       SCRIPTS_DIR / "generate_se.py"),
]


def _run_job(name: str, script_path: Path, cfg_json: str = "") -> Tuple[str, float, str]:
    t0 = time.perf_counter()
    env = os.environ.copy()
    if cfg_json:
        env["SSR_RESOLVED_CONFIG_JSON"] = cfg_json
    res = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=True,
    )
    elapsed = time.perf_counter() - t0
    return name, elapsed, res.stdout.strip()


def main() -> int:
    t_start = time.perf_counter()
    cfg = load_card_config()
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    layout = resolve_layout(cfg)
    changed_html = sync_html_resolution(layout)
    print(f"=== SSRGenerate Parallel Asset Builder ({layout.orientation}: {layout.canvas_w}x{layout.canvas_h}, card {layout.card_w}x{layout.card_h}) ===")
    if changed_html:
        print(f"[HTML Sync] Updated resolution attributes in: {', '.join(changed_html)}")
    with ProcessPoolExecutor(max_workers=len(JOBS)) as ex:
        futures = {ex.submit(_run_job, name, path, cfg_json): name for name, path in JOBS}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                _, elapsed, out = fut.result()
                print(f"\n--- [{name}] completed in {elapsed:.2f}s ---")
                if out:
                    print(out)
            except subprocess.CalledProcessError as err:
                print(f"\n[ERROR] Job '{name}' failed (exit {err.returncode}):", file=sys.stderr)
                if err.stdout:
                    print(err.stdout, file=sys.stderr)
                if err.stderr:
                    print(err.stderr, file=sys.stderr)
                return 1

    total = time.perf_counter() - t_start
    print(f"\n=== All assets built successfully in {total:.2f}s ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
