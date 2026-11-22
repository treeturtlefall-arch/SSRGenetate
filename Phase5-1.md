ローカル環境のAIエージェントが迷わずそのまま適用・拡張できるよう、**Phase 5-1「縦横レイアウト切替アーキテクチャ＆プリフライト同期の整備」** の具体的なコード差分・実装リファレンスをファイル順（全6箇所）でまとめました。

### Phase 5-1 の設計ポイント（ローカルAIへの伝達事項）
1. **並列ビルド（`build_all.py`）でのファイル競合（Race Condition）回避**:
   * `build_all.py` は4つの Python スクリプトを `ProcessPoolExecutor` で同時実行します。各スクリプトが同時に `index.html` 等を書き換えると Windows 環境でファイルロック競合が起きるため、**HTML 3ファイルの静的属性書き換え（`sync_html_resolution`）は `render_typography.py`（および `build_all.py` の親プロセス）のみが担当**します。
2. **CLI オーバーライドの環境変数伝播（`SSR_CARD_CONFIG_OVERRIDES`）**:
   * `npm run render -- --variables '{"orientation":"landscape"}'` のように CLI から一時的に向きを変えた際、`render_video.mjs` が `render_material.py` や `render_optics.py` を再実行しても同じ設定を参照できるよう、`scripts/_utils.py` の `load_card_config()` が環境変数 `SSR_CARD_CONFIG_OVERRIDES`（JSON）を自動マージするようにします。

---

### 1. `card-config.js`（`orientation` キーの追加）

`photo` の直前あたりに `orientation: "portrait"` を追加します。

```js
window.SSR_CARD_CONFIG = {
  // 動画キャンバス＆カードの向き（"portrait" = 1080x1920 縦 | "landscape" = 1920x1080 横 | "auto" = 入力写真の縦横比から自動判定）
  orientation: "portrait",

  // 入力写真のパス（index.html からの相対パス）
  photo: "assets/photo.jpg",
```

---

### 2. `scripts/_utils.py`（`LayoutSpec`・`resolve_layout`・`sync_html_resolution`・環境変数オーバーライド対応）

`PIL.ImageOps` と `os`, `re`, ` dataclasses.dataclass` を使い、縦横寸法の解決と HTML 3ファイルの静的属性同期を追加します。

```python
# --- scripts/_utils.py の import 部に追加 ---
from dataclasses import dataclass
import os
import re
from PIL import Image, ImageDraw, ImageOps

# --- CARD_* 定数定義（L34〜44）の下に追加 ---
@dataclass(frozen=True)
class LayoutSpec:
    orientation: str      # "portrait" | "landscape"
    canvas_w: int         # 1080 | 1920
    canvas_h: int         # 1920 | 1080
    card_w: int           # 900  | 1480
    card_h: int           # 1590 | 860
    card_border: int      # 20
    card_outer_r: int     # 40
    card_inner_r: int     # 24
    card_inner_w: int     # 860  | 1440
    card_inner_h: int     # 1550 | 820


PORTRAIT_LAYOUT = LayoutSpec(
    orientation="portrait",
    canvas_w=1080,
    canvas_h=1920,
    card_w=900,
    card_h=1590,
    card_border=CARD_BORDER,
    card_outer_r=CARD_OUTER_R,
    card_inner_r=CARD_INNER_R,
    card_inner_w=900 - CARD_BORDER * 2,
    card_inner_h=1590 - CARD_BORDER * 2,
)

LANDSCAPE_LAYOUT = LayoutSpec(
    orientation="landscape",
    canvas_w=1920,
    canvas_h=1080,
    card_w=1480,
    card_h=860,
    card_border=CARD_BORDER,
    card_outer_r=CARD_OUTER_R,
    card_inner_r=CARD_INNER_R,
    card_inner_w=1480 - CARD_BORDER * 2,
    card_inner_h=860 - CARD_BORDER * 2,
)

HTML_TARGETS = (
    PROJECT_ROOT / "index.html",
    PROJECT_ROOT / "compositions" / "scene-summon.html",
    PROJECT_ROOT / "compositions" / "scene-result.html",
)


def apply_config_overrides(cfg: Dict[str, Any], overrides: Any) -> Dict[str, Any]:
    """CLI --variables / 環境変数 SSR_CARD_CONFIG_OVERRIDES を card-config 辞書へマージする"""
    if not isinstance(overrides, dict):
        return cfg
    out = dict(cfg)
    typo = dict(out.get("typography", {})) if isinstance(out.get("typography"), dict) else {}

    str_keys = (
        "orientation",
        "photo",
        "photoFit",
        "photoPosition",
        "rarity",
        "attribute",
        "attributeBadge",
        "attributeLabel",
        "subtitle",
        "title",
        "flavor",
        "cardNo",
        "resultRingMode",
    )
    for k in str_keys:
        if k in overrides and overrides[k] is not None:
            val_s = str(overrides[k])
            if k == "orientation" and not val_s.strip():
                continue
            out[k] = val_s

    for nk, conv in (("photoZoom", float), ("stars", int), ("seed", int)):
        if nk in overrides and overrides[nk] is not None and str(overrides[nk]).strip() != "":
            try:
                val = conv(overrides[nk])
                if math.isfinite(float(val)):
                    out[nk] = val
            except (TypeError, ValueError):
                pass

    if "preset" in overrides and isinstance(overrides["preset"], str) and overrides["preset"].strip():
        typo["preset"] = overrides["preset"].strip()

    if isinstance(overrides.get("typography"), dict):
        for tk, tv in overrides["typography"].items():
            if tv is not None:
                typo[tk] = tv

    out["typography"] = typo
    return out


def load_card_config() -> Dict[str, Any]:
    """card-config.js から window.SSR_CARD_CONFIG を読み込み、環境変数オーバーライドがあれば適用する"""
    cfg: Dict[str, Any] = {}
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
            cfg = json.loads(res.stdout)
        except Exception:
            cfg = {}

    env_ov = os.environ.get("SSR_CARD_CONFIG_OVERRIDES", "").strip()
    if env_ov:
        try:
            cfg = apply_config_overrides(cfg, json.loads(env_ov))
        except Exception:
            pass
    return cfg


def resolve_photo_path(photo_rel: str) -> Path:
    raw = str(photo_rel or "assets/photo.jpg").strip()
    p = Path(raw)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / raw.lstrip("./\\")


def resolve_layout(cfg: Dict[str, Any] | None = None) -> LayoutSpec:
    """
    cfg["orientation"] ("portrait" | "landscape" | "auto") を解決して LayoutSpec を返す。
    "auto" の場合は EXIF 回転補正後の入力写真サイズで width > height なら landscape とする。
    """
    c = cfg if cfg is not None else load_card_config()
    raw_ori = str(c.get("orientation", "portrait") or "portrait").strip().lower()
    if raw_ori == "landscape":
        return LANDSCAPE_LAYOUT
    if raw_ori == "auto":
        photo_path = resolve_photo_path(str(c.get("photo", "assets/photo.jpg")))
        if photo_path.is_file():
            try:
                with Image.open(photo_path) as im:
                    im_t = ImageOps.exif_transpose(im)
                    w, h = im_t.size
                if w > h:
                    return LANDSCAPE_LAYOUT
            except Exception:
                pass
    return PORTRAIT_LAYOUT


def sync_html_resolution(layout: LayoutSpec) -> List[str]:
    """
    index.html, scene-summon.html, scene-result.html の静的属性
    (data-resolution, viewport, data-width, data-height) を解決済み LayoutSpec に一括同期する。
    変更があったファイル名のリストを返す（差分がない場合はディスク書き込みを行わない）。
    """
    updated: List[str] = []
    ori = layout.orientation
    cw, ch = layout.canvas_w, layout.canvas_h

    for html_path in HTML_TARGETS:
        if not html_path.is_file():
            continue
        src = html_path.read_text(encoding="utf-8")
        out = re.sub(r'data-resolution="(?:portrait|landscape)"', f'data-resolution="{ori}"', src)
        out = re.sub(
            r'(<meta\s+name="viewport"\s+content=")width=\d+,\s*height=\d+("\s*/?>)',
            rf"\g<1>width={cw}, height={ch}\2",
            out,
        )
        out = re.sub(r'data-width="\d+"', f'data-width="{cw}"', out)
        out = re.sub(r'data-height="\d+"', f'data-height="{ch}"', out)
        if out != src:
            html_path.write_text(out, encoding="utf-8")
            updated.append(html_path.name)
    return updated
```

---

### 3. `scripts/build_all.py` ＆ `scripts/render_typography.py` への同期フック組み込み

* **`scripts/build_all.py`**: 並列ジョブ開始前に一度だけ `sync_html_resolution(resolve_layout())` を呼んでおきます。
* **`scripts/render_typography.py`**: `apply_cli_overrides` を `_utils.py` の `apply_config_overrides` に統合し、`main()` 内で `layout = resolve_layout(cfg)` と `sync_html_resolution(layout)` を実行します。また `manifest["dimensions"]` と `manifest["source"]["orientation"]` に `layout` の実測値を出力します。

```python
# --- scripts/build_all.py の main() 冒頭に追加 ---
from _utils import load_card_config, resolve_layout, sync_html_resolution

def main() -> int:
    t_start = time.perf_counter()
    layout = resolve_layout(load_card_config())
    changed_html = sync_html_resolution(layout)
    print(f"=== SSRGenerate Parallel Asset Builder ({layout.orientation}: {layout.canvas_w}x{layout.canvas_h}, card {layout.card_w}x{layout.card_h}) ===")
    if changed_html:
        print(f"[HTML Sync] Updated resolution attributes in: {', '.join(changed_html)}")
    # 以降 ProcessPoolExecutor ...
```

```python
# --- scripts/render_typography.py の変更ポイント ---
# 1. build_source_snapshot に orientation_raw と resolved_orientation を記録:
    return {
        "orientation": layout.orientation,
        "orientationRaw": str(cfg.get("orientation", "portrait") or "portrait").strip().lower(),
        "preset": preset_name,
        # ...（以下既存通り）
    }

# 2. main() 内で layout を解決して HTML 静的属性と manifest["dimensions"] を同期:
    layout = resolve_layout(cfg)
    changed_html = sync_html_resolution(layout)
    if changed_html:
        print(f"[OK] synced HTML resolution ({layout.orientation} {layout.canvas_w}x{layout.canvas_h}): {', '.join(changed_html)}")

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
```

---

### 4. `compositions/shared-base.css` ＆ `index.html` ＆ `compositions/scene-result.html`（CSS変数化とCLI変数追加）

HTML属性（`data-resolution="landscape"`）が切り替わっただけでキャンバスとカードのベース寸法が自動的に `1920×1080` / `1480×860` に切り替わるように CSS 変数を定義します。

#### `compositions/shared-base.css`
```css
:root {
  /* ...既存トークン... */
  /* scripts/_utils.py の LayoutSpec と同期 */
  --canvas-w: 1080px;
  --canvas-h: 1920px;
  --card-w: 900px;
  --card-h: 1590px;
  --card-border: 20px;
  --card-outer-r: 40px;
  --card-inner-r: 24px;
}

html[data-resolution="landscape"] {
  --canvas-w: 1920px;
  --canvas-h: 1080px;
  --card-w: 1480px;
  --card-h: 860px;
}

html,
body {
  width: var(--canvas-w);
  height: var(--canvas-h);
  overflow: hidden;
  background: transparent;
  color: var(--ink-ivory);
  font-family: var(--font-jp);
  -webkit-font-smoothing: antialiased;
}

.scene-root {
  position: relative;
  width: var(--canvas-w);
  height: var(--canvas-h);
  overflow: hidden;
  isolation: isolate;
}

.clip {
  position: absolute;
  inset: 0;
  width: var(--canvas-w);
  height: var(--canvas-h);
  overflow: hidden;
  pointer-events: none;
}
```

#### `index.html`（変数配列への `orientation` 追加 ＆ `<style>` の CSS 変数化）
`index.html` と `compositions/scene-result.html` の `data-composition-variables` に以下を1行追加します：
```json
{"id":"orientation","type":"string","label":"Orientation (portrait | landscape | auto)","default":""},
```
そして `index.html` の `<style>` 内の固定 `1080px / 1920px` を変数化します：
```css
      :root {
        --in-oklab: ;
        --bg-edge-black: #000000;
        --canvas-w: 1080px;
        --canvas-h: 1920px;
      }

      html[data-resolution="landscape"] {
        --canvas-w: 1920px;
        --canvas-h: 1080px;
      }

      html,
      body,
      #root,
      .clip {
        width: var(--canvas-w);
        height: var(--canvas-h);
      }
```

---

### 5. `scripts/render_video.mjs`（向き変更検知時のマテリアル・光学・タイポ一括同期）

`render_video.mjs` で `orientation` の変化（または `"auto"` 時の写真縦横変化）を検知し、向きが変わったときは **`render_material.py`・`render_optics.py`・`render_typography.py` の3本を環境変数 `SSR_CARD_CONFIG_OVERRIDES` 付きで自動実行**します。

```js
// --- scripts/render_video.mjs の主な追加・変更箇所 ---

// 1. applyCliOverrides 内 (strKeys に "orientation" を追加):
  const strKeys = [
    "orientation",
    "photo",
    // ...
  ];
  for (const k of strKeys) {
    if (Object.prototype.hasOwnProperty.call(overrides, k) && overrides[k] !== null && overrides[k] !== undefined) {
      const s = String(overrides[k]);
      if (k === "orientation" && !s.trim()) continue;
      out[k] = s;
    }
  }

// 2. Python と同じ EXIF / auto 判定を含む向き解決、または buildExpectedSource への orientationRaw 追加:
function buildExpectedSource(cfg) {
  // ...既存処理...
  const orientationRaw = String(cfg.orientation ?? "portrait").trim().toLowerCase() || "portrait";
  return {
    orientationRaw,
    preset: presetName,
    // ...既存フィールド...
  };
}

// 3. checkTypoSyncStatus で orientation 変更および HTML data-resolution 不一致をチェック:
function readIndexHtmlResolution() {
  const indexPath = path.join(PROJECT_ROOT, "index.html");
  if (!fs.existsSync(indexPath)) return "portrait";
  const m = fs.readFileSync(indexPath, "utf8").match(/data-resolution="(portrait|landscape)"/);
  return m ? m[1] : "portrait";
}

function checkTypoSyncStatus(expectedSource, manifest) {
  const reasons = [];
  let needsLayoutRebuild = false;

  if (!manifest || manifest.schemaVersion !== 2 || !manifest.source) {
    return { needsSync: true, needsLayoutRebuild: true, reasons: ["manifest-missing-or-outdated"] };
  }

  const actual = manifest.source;
  const manifestOri = manifest.dimensions?.orientation || "portrait";
  const htmlOri = readIndexHtmlResolution();

  if (expectedSource.orientationRaw !== (actual.orientationRaw ?? "portrait")) {
    reasons.push(`orientation(${actual.orientationRaw ?? "portrait"}->${expectedSource.orientationRaw})`);
    needsLayoutRebuild = true;
  }
  if (expectedSource.orientationRaw === "auto" && !deepEqual(expectedSource.photo, actual.photo)) {
    reasons.push("auto-orientation-photo-changed");
    needsLayoutRebuild = true;
  }
  if (htmlOri !== manifestOri) {
    reasons.push(`html-resolution-mismatch(${htmlOri}!=${manifestOri})`);
    needsLayoutRebuild = true;
  }
  // ...既存の preset / texts / typography / photo チェック...

  return { needsSync: reasons.length > 0, needsLayoutRebuild, reasons };
}

// 4. プリフライト実行部:
if (shouldSyncTypo) {
  const envWithOverrides = {
    ...process.env,
    SSR_CARD_CONFIG_OVERRIDES: JSON.stringify(cliVars),
  };

  // 最初に render_typography.py を実行（HTML 3ファイルの data-resolution 同期 + マニフェスト更新）
  console.log(`[typo-sync] Regenerating typography (${syncReasonText.join(", ")})...`);
  const pyTypo = spawnSync("python", ["scripts/render_typography.py", "--overrides-stdin"], {
    cwd: PROJECT_ROOT,
    input: JSON.stringify(cliVars),
    env: envWithOverrides,
    encoding: "utf8",
    stdio: ["pipe", "inherit", "inherit"],
    shell: false,
  });
  if (pyTypo.error || (pyTypo.status ?? 1) !== 0) process.exit(pyTypo.status ?? 1);

  // 解決後のマニフェストの orientation が変化していた場合は material & optics も再生成
  const updatedManifest = loadTypoManifest();
  const prevOri = manifest?.dimensions?.orientation || "portrait";
  const nextOri = updatedManifest?.dimensions?.orientation || "portrait";
  if (forceTypo || syncStatus.needsLayoutRebuild || prevOri !== nextOri) {
    console.log(`[layout-sync] Ensuring material & optics assets for orientation=${nextOri}...`);
    for (const script of ["scripts/render_material.py", "scripts/render_optics.py"]) {
      const r = spawnSync("python", [script], {
        cwd: PROJECT_ROOT,
        env: envWithOverrides,
        stdio: "inherit",
        shell: false,
      });
      if (r.error || (r.status ?? 1) !== 0) process.exit(r.status ?? 1);
    }
  }
}
```

---

これで **Phase 5-1** の骨格が完成します。
続けて **Phase 5-2（Python 物理アセット生成スクリプト群 `render_material.py` / `_typo_modern.py` / `render_typography.py` / `render_optics.py` の横型カード対応）** の実装コード例も作成しましょうか？