# 横動画（16:9 / 1920×1080）× 横型カード対応 事前調査＆実装設計書 (`LANDSCAPE_PLAN.md`)

> `ROADMAP.md` の **Phase 5「横動画（16:9 / 1920×1080）× 横型カード対応」** に向けた、Phase 0〜4 完了時点の実コード調査と具体実装タスクのまとめです。

---

## 1. 背景と基本方針

風景・集合写真・横構図スナップなど、周辺情報込みで魅力が活きる横長写真をカード化する際、縦型カード（`900×1590`）へトリミングすると左右が大幅に切り落とされてしまいます。  
そのため Phase 5 では、**動画キャンバス自体を `1920×1080`（16:9）にし、横型SSRカード（`1480×860`）が3D回転して着地するワイドスクリーン演出モード（パターンB）** を追加します。

### 守るべき不変ルール
- **総尺 16.0秒（本編 15.0秒）**: 冒頭 `0.5s` 無音・黒フェードイン ＋ 本編 `15.0s`（`0.0s〜12.0s` 抽選〜SSR確定 / `12.0s〜15.0s` レイアウト完全固定・光のみ微動）＋ 末尾 `0.5s` 無音・黒フェードアウト
- **入力写真は 100% クリア維持**: ホログラム反射やパーティクルが被写体中央を汚さない
- **完全決定論的レンダリング**: `Math.random()` / `Date.now()` / 外部 `fetch()` 不使用
- **縦版（9:16 / `1080×1920`）へのデグレゼロ**: `orientation: "portrait"` 時は従来の出力と完全一致

---

## 2. 最重要の技術制約（HyperFrames の静的解像度判定 ＆ プリフライト同期）

### 2-1. HTML 静的属性のパース制約
HyperFrames CLI の静的検査（`npm run check`）およびレンダラー（`npm run render`）は、HTML ファイル内の以下の **静的属性** を直接パースしてキャンバス寸法を検証・決定します。

- `<html data-resolution="portrait | landscape">`
- `<meta name="viewport" content="width=..., height=..." />`
- `<div id="root" data-width="..." data-height="...">`（および各サブコンポジション `#summon-root`, `#result-root`）

ランタイム JavaScript（`setAttribute`）による書き換えだけでは CLI リンターや初期ビューポートサイズと食い違うため、**Python ビルドスクリプト側で `card-config.js`（および CLI `--variables`）の向き設定を解決し、物理アセット生成と同時に HTML 3ファイルの静的属性を一括同期する設計** とします。

### 2-2. `scripts/render_video.mjs` スマートプリフライトとの統合
Phase 4 で導入した `scripts/render_video.mjs` は、通常テキスト変更時に `render_typography.py` のみを先行実行します。  
しかし **縦横（`orientation`）が切り替わった場合** は、タイポグラフィだけでなく **カード枠・裏面・内窓深度・フィルムグレイン（`render_material.py`）、カットイン光学フレア（`render_optics.py`）、および HTML 3ファイルの静的属性** もすべて横寸法へ更新する必要があります。

- **対策**:
  1. `typo-manifest.js` の `source` スナップショットおよび `manifest["dimensions"]["orientation"]` に解決済みの向き（`"portrait" | "landscape"`）を記録する。
  2. `render_video.mjs` で向きの変更（`dimensions.orientation` の不一致）を検知した場合は、`render_typography.py` に加えて `render_material.py` と `render_optics.py`（または高速な専用更新モード）を自動実行し、HTML 属性と物理アセットの不一致を完全に防ぐ。

---

## 3. 縦横レイアウト寸法スペック対照表

| 項目 | Portrait（縦・現行） | Landscape（横・Phase 5） | 備考 |
| :--- | :---: | :---: | :--- |
| **キャンバス解像度 (`CANVAS_W × H`)** | `1080 × 1920` (9:16) | **`1920 × 1080`** (16:9) | フルHD横画面 |
| **カード外寸 (`CARD_W × CARD_H`)** | `900 × 1590` | **`1480 × 860`** | 画面横幅の約77%・高さ約80%（余白に背景光学リングやスパークルが映える比率） |
| **フレーム枠幅 (`CARD_BORDER`)** | `20px` | **`20px`** | 共通（角丸 `outer: 40px` / `inner: 24px` も共通） |
| **内窓写真領域 (`CARD_INNER_W × H`)** | `860 × 1550` | **`1440 × 820`** | 一般的な横写真（3:2 / 16:9 / 4:3）が自然に収まるワイド内窓 |
| **カード配置 (`#card-stage`)** | `top: 165px`, 左右余白 `90px` | **`top: 110px`**, 左右余白 **`220px`** | 上下 `110px`・左右 `220px` の空間額縁を確保 |
| **フィルムグレイン生成寸法** | `540 × 960` (1/2) | **`960 × 540`** (1/2) | 1/4画素数で高速生成し CSS `100% 100%` で展開 |

---

## 4. モジュール別の具体的な改修タスク（5つの柱）

### ① 設定と縦横自動判定・HTML解像度同期の共通基盤
- **対象ファイル**:
  - `card-config.js`
  - `scripts/_utils.py`
  - `scripts/render_video.mjs`
  - `index.html`, `compositions/scene-summon.html`, `compositions/scene-result.html`, `compositions/shared-base.css`
- **実装内容**:
  1. `card-config.js` に `orientation: "portrait"`（`"portrait" | "landscape" | "auto"`）を追加。`index.html` と `scene-result.html` の `data-composition-variables` にも `orientation` を追加する。
  2. `scripts/_utils.py` に `resolve_layout(cfg)` を新設。`"auto"` 指定時は Pillow (`ImageOps.exif_transpose(Image.open(...))`) で `cfg["photo"]` の実画像サイズを読み取り、`width > height` なら `"landscape"`、それ以外は `"portrait"`（画像不在時のフォールバックも `"portrait"`）を返す。
  3. 解決した `orientation` に応じて `LayoutSpec(orientation, canvas_w, canvas_h, card_w, card_h, card_inner_w, card_inner_h)` を返すヘルパーを提供し、各生成スクリプトから参照する。
  4. HTML 3ファイル（`index.html`, `compositions/scene-summon.html`, `compositions/scene-result.html`）の `data-resolution` / `viewport` / `data-width` / `data-height` を解決済み解像度へ自動同期する関数 `sync_html_resolution(layout)` を `_utils.py` に用意し、ビルド時に実行する。
  5. `index.html` および `compositions/shared-base.css` のキャンバス寸法を CSS 変数 `--canvas-w` / `--canvas-h`（`html[data-resolution="landscape"]` で `1920px / 1080px`、`--card-w: 1480px; --card-h: 860px;`）で切り替えられるように整理する。

---

### ② 物理アセット生成スクリプト群の横寸法対応
- **対象ファイル**:
  - `scripts/render_material.py`
  - `scripts/_typo_modern.py`
  - `scripts/render_typography.py`
  - `scripts/render_optics.py`
- **現状の課題と実装内容**:
  1. **虹フレーム・4辺中央鋲・内窓深度 (`render_material.py`)**:
     - `generate_rainbow_foil_frame(w, h)`（および `_compose_center_studs`）と `generate_window_depth(w, h)` は任意の `w, h` に対応しているため、解決済みの `card_w, card_h`（横時は `1480×860` / 内窓 `1440×820`）を渡す。
  2. **カード裏面の中央紋章・ギョーシェ彫りスケーリング (`render_material.py`)**:
     - `_crest_mask`（放射スパイク長 `330px`・外周リング等）および `_guilloche_mask`（ロゼット半径 `300 / 400 / 560px`）が縦カード（高さ `1590px`）前提の固定ピクセル値になっており、横カード（高さ `860px`）では上下の枠を突き抜ける。
     - **対策**: `scale = min(w, h) / 900.0`（または紋章が上下枠内に美しく収まる `min(w, h) / 960.0`）を掛けて中央紋章とギョーシェ半径をスケーリングする。
  3. **フィルムグレインの1/2解像度追従 (`render_material.py`)**:
     - `generate_film_grain_overlay(canvas_w // 2, canvas_h // 2)` とし、横時は `960×540` で生成する。
  4. **モダン＆レガシー箔タイポグラフィとビネット自動計測 (`_typo_modern.py`, `render_typography.py`)**:
     - 横カードは**横幅が広い（内窓 `1440px`）一方、高さが短い（内窓 `820px`）**ため、下部テキスト群が縦に大きく積み上がると写真の主要被写体を隠してしまう。
     - **対策**:
       - `_typo_modern.py` の `MODERN_PRESETS`（および `render_typography.py` のレガシー `card_specs`）において、Landscape 時は `title` / `subtitle` / `flavor` のフォントサイズを約 `82〜86%` に引き締める一方、`maxW` を `740..780px → 1140..1220px` へ広げ、フレーバーも横長1行（最大2行）でコンパクトに収める。
       - `render_royal_diamond_rule`（Royal 下部二重罫線）の幅も縦 `760px` / 横 `1160px` に自動調整する。
       - `compute_adaptive_vignette`（写真下部 30% の輝度計測）のシミュレーションキャンバス `tw, th = 172, 310` を `max(32, card_inner_w // 5), max(32, card_inner_h // 5)`（横時は `288, 164`）へ変更し、横カードの実際のトリミング領域に一致させる。
       - `typo-manifest.js` の既存 `dimensions` オブジェクト（`orientation`, `canvasW`, `canvasH`, `cardW`, `cardH`, `innerW`, `innerH`）に解決済みレイアウト値を出力する。
  5. **カットイン光学アセットの横幅対応 (`render_optics.py`)**:
     - `render_cutin_assets` の `opt_cutin_flare.png` / `opt_cutin_speedlines.png` の幅 `fw / sw = 1080` を `canvas_w`（横時は `1920px`）で生成し、ワイド画面での引き伸ばしボケを防ぐ。

---

### ③ 召喚フェーズ（Scene 1-2）の 16:9 空間レイアウト＆軌道調整
- **対象ファイル**:
  - `compositions/scene-summon.html`
  - `compositions/scene-summon.css`
  - `compositions/scene-summon-setup.js`
- **現状の課題と実装内容**:
  1. **キャンバスサイズと全幅要素 (`scene-summon.css`)**:
     - `#summon-camera` を `width: var(--canvas-w); height: var(--canvas-h);` 化する。
     - `#flash-rainbow-streak`、`#cutin-band`、`#cutin-flare` の `width: 1080px` を `width: 100%` に変更し、1920px 全幅を貫くアナモルフィック光閃・カットインにする。
  2. **3D床パース魔法陣・天蓋ゲート・オーブ・雷撃・光柱の縦バランス (`scene-summon.css`)**:
     - 縦高さが `1920px → 1080px` になるため、`html[data-resolution="landscape"]` 時は以下を調整する：
       - `#magic-circle-wrap` / `#celestial-gate-wrap`: 基準スケールや上下オフセットを約 `0.78〜0.85` 倍に抑え、16:9 ワイド空間の奥行きを広く見せる。
       - `#orb-wrap`: `width/height` またはスケールを約 `0.85` 倍に調整。
       - `.sky-bolt`（`#bolt-gold`, `#bolt-prism`）: 現行 `top: 72px; height: 980px;` は縦画面のオーブ中心（`y≈902px`）合わせのため、横画面（オーブ中心 `y≈508px`）では `top: 32px; height: 540px;` に調整して雷撃先端が正確にオーブ中心へ着弾するようにする。
       - `#light-pillar, #light-pillar-rainbow`: `top: 40px; height: 940px;` に調整し、上下フェードが画面内に収まるようにする。
       - `#summon-top-hud`: `top: 138px → 64px` に引き上げ、天蓋開口部とのバランスを保つ。
  3. **流れ星・三重螺旋ウィスプ・収束粒子・浮遊クリスタル破片の 16:9 座標対応 (`scene-summon-setup.js`)**:
     - `isLandscape = document.documentElement.getAttribute("data-resolution") === "landscape"`（または `canvasW / canvasH`）を参照し、以下のハードコード座標をスケーリングする：
       - **冒頭流れ星 (`evalIntroMeteor`)**: 横画面時は `x = -180 + (canvasW + 320) * p`, `y = 140 + 420 * p` とし、16:9 画面の左上から右下までワイドに駆け抜けさせる。
       - **RGB三重螺旋ウィスプ (`evalHelixPoint`)**: 横画面時は開始高さを `-755 → -460` に抑える一方、水平旋回半径を `1.25` 倍に広げてワイド画面に映える螺旋軌道にする。
       - **オーブ収束粒子 (`convergeData`)**: 横画面時は `startX` を `1.35` 倍、`startY` を `0.78` 倍の楕円分布にする。
       - **2層パララックス浮遊クリスタル破片 (`farShards`, `nearShards`, `waveShards`, `skySparkles`)**:
         - `farShards` / `skySparkles`: `x0` を `55..(canvasW - 55)`、`y0` を `60..(canvasH - 80)` のフルレンジに汎用化する。
         - `nearShards`: 右側レーン（現行 `835 + rng() * 195`）が横画面の中央オーブに被らないよう、`canvasW - 245 + rng() * 195`（横時は `1675..1870px`）へ汎用化する。
         - `waveShards`: 湧き上がり開始位置 `yMin / yMax`（現行 `1280..1980`）を `canvasH * 0.68 .. canvasH * 1.03` に汎用化し、横画面でも床魔法陣からしっかり湧き上がるようにする。

---

### ④ リザルトフェーズ（Scene 3-5）の横型カード＆パーティクル座標対応
- **対象ファイル**:
  - `compositions/scene-result.html`
  - `compositions/scene-result.css`
  - `compositions/scene-result-setup.js`
- **現状の課題と実装内容**:
  1. **カード寸法と背景光学リング (`scene-result.css`)**:
     - `html[data-resolution="landscape"]` 時に `--card-w: 1480px; --card-h: 860px;`、`#card-stage { top: 110px; }` に切り替える。
     - 背景の `#result-bg-ring`（縦 `1700×1700`）は、横画面ではカードの左右余白（各 `220px`）や上下余白から魔法陣の円弧が美しく覗くサイズ（`1320×1320`〜`1480×1480`）に調整する。
  2. **回転スペキュラとホログラムスイープの走査距離 (`scene-result.css`, `scene-result.html`)**:
     - 縦カード幅（`900px`）前提で `#spin-spec-back/front` の移動先が `x: 1420〜1460`、`#holo-sweep-1/2` が `x: 1850` に設定されている。
     - 横カード（幅 `1480px`）ではカードの右端まで到達する前に止まってしまうため、`cardW` に連動した走査距離（横時は `spin-spec` を `x: 2040`、`holo-sweep` を `x: 2450`）へ自動拡張する。
     - `#holo-mask-zone` / `#spin-spec-front` の中央被写体保護マスクも横長楕円（`ellipse 44% 48% at 50% 44%`）に適合させる。
  3. **下部テキストオーバーレイとビネットの省スペース化 (`scene-result.css`)**:
     - 横カード（内窓高さ `820px`）で写真中央〜上部を広くクリアに保つため、Landscape 時は `#card-overlay-layer` の下パディングと `gap` を引き締め、星サイズ `.star-item` も `90px → 72px` に調整する。
     - `.photo-vignette` の下部暗色グラデーション開始位置も `54%..62% → 64%..68%` に下げ、風景の水平線や被写体の顔に暗い影がかからないようにする。
  4. **【最重要】スパークル・金箔フレーク・玉ボケの座標スケーリング (`scene-result-setup.js`)**:
     - **問題点**: 現在、`sparkleClusters`（`x: ±315..494`, `y: ±150..838`）、`flakeData`（`startX: ±360..445`, `startY: ±590`）、`bokehData`（`endX: ±435..525`, `endY: ±775..920`）がすべて縦カード（半幅 `450px`、半高 `795px`）基準のハードコード座標になっている。このまま横カード（半幅 `740px`、半高 `430px`）で表示すると、**左右のスパークルや金箔がカード内部の写真ド真ん中に出現し、上下のスパークルは画面外へ消えてしまう**。
     - **対策**:
       - スパークル座標を「縦カード半寸（`baseHalfW = 450`, `baseHalfH = 795`）に対する正規化比率」として扱い、実行時の `(cardHalfW, cardHalfH)` に合わせてスケーリングする（右下 `cardNo` との非干渉退避も維持）。
       - 金箔フレーク（`flakeData`）の `startX` を `side * (cardHalfW - 80 + rng() * 85)`、`startY` を `(rng() - 0.5) * (cardH * 0.74)` に変更し、常にカードの左右外縁から外側へ舞うようにする。
       - 玉ボケ（`bokehData`）も `cardHalfW` / `cardHalfH` の外周余白レーン（左右は `±(cardHalfW + 25..150)`、上下は `±(cardHalfH + 15..85)`）へ配置する計算式に汎用化する。

---

### ⑤ 定量QAスクリプト（`scripts/qa_video.py`）の解像度フリー化
- **対象ファイル**: `scripts/qa_video.py`
- **現状の課題**:
  - `L158` の `decode_gray_frames(video_path)` がデフォルト引数 `w=270, h=480`（縦 9:16 固定）で呼ばれている。
- **実装内容**:
  - `probe_streams` で取得した `info["width"]` と `info["height"]` を参照し、`width > height` の場合は `(w=480, h=270)`、それ以外は `(w=270, h=480)` で縮小デコードする（輝度・グレー曇り・真空の間・着地前ダレ・終盤固定・LUFS の判定ロジック自体はそのまま 100% 機能する）。