# 横動画（16:9 / 1920×1080）× 横型カード対応 事前調査＆実装設計書 (`LANDSCAPE_PLAN.md`)

> `ROADMAP.md` の **Phase 5「横動画（16:9 / 1920×1080）× 横型カード対応」**（および前段となる Phase 3・Phase 4 との連携）に向けた実コード調査と具体実装タスクのまとめです。

---

## 1. 背景と基本方針

風景・集合写真・横構図スナップなど、周辺情報込みで魅力が活きる横長写真をカード化する際、縦型カード（`900×1590`）へトリミングすると左右が大幅に切り落とされてしまいます。  
そのため Phase 5 では、**動画キャンバス自体を `1920×1080`（16:9）にし、横型SSRカードが3D回転して着地するワイドスクリーン演出モード（パターンB）** を追加します。

### 守るべき不変ルール
- **総尺 15.0秒以内**（`0.0s〜12.0s` 抽選〜SSR確定 / `12.0s〜15.0s` レイアウト固定・光のみ微動）
- **入力写真は 100% クリア維持**（ホログラム反射やパーティクルが被写体中央を汚さない）
- **完全決定論的レンダリング**（`Math.random()` / `Date.now()` 不使用）
- **縦版（9:16 / `1080×1920`）へのデグレゼロ**

---

## 2. 調査で判明した最重要の技術制約（HyperFrames の解像度判定）

HyperFrames CLI の静的検査（`npm run check`）およびレンダラー（`npm run render`）は、HTML ファイル内の以下の **静的属性** を直接パースしてキャンバス寸法を検証・決定します。

- `<html data-resolution="portrait | landscape">`
- `<meta name="viewport" content="width=..., height=..." />`
- `<div id="root" data-width="..." data-height="...">`（および各サブコンポジションのルート要素）

ランタイム JavaScript（`setAttribute`）による書き換えだけでは、CLI の静的リンターや初期ビューポートサイズと食い違うため、**`npm run build:assets`（Python ビルドスクリプト側）で `card-config.js` の向き設定を解決し、物理アセット生成と同時に HTML の静的属性（またはレイアウトマニフェスト）を一括同期する設計** が最もクリーンで安全です。

---

## 3. 縦横レイアウト寸法スペック対照表

| 項目 | Portrait（縦・現行） | Landscape（横・Phase 5） | 備考 |
| :--- | :---: | :---: | :--- |
| **キャンバス解像度** | `1080 × 1920` (9:16) | **`1920 × 1080`** (16:9) | フルHD横画面 |
| **カード外寸 (`CARD_W × CARD_H`)** | `900 × 1590` | **`1480 × 860`** | 画面横幅の約77%・高さ約80%（余白に背景光学リングやスパークルが映える比率） |
| **フレーム枠幅 (`CARD_BORDER`)** | `20px` | **`20px`** | 共通（角丸 `outer: 40px` / `inner: 24px` も共通） |
| **内窓写真領域 (`CARD_INNER_W × H`)** | `860 × 1550` | **`1440 × 820`** | 一般的な横写真（3:2 / 16:9 / 4:3）が自然に収まるワイド内窓 |
| **カード配置 (`#card-stage`)** | `top: 165px`, 左右余白 `90px` | **`top: 110px`**, 左右余白 **`220px`** | 上下 `110px`・左右 `220px` の空間額縁を確保 |

---

## 4. モジュール別の具体的な改修タスク（5つの柱）

### ① 設定と縦横自動判定の共通基盤
- **対象ファイル**:
  - `card-config.js`
  - `scripts/_utils.py`
- **現状の課題**:
  - `scripts/_utils.py` の `L30-L37` で `CARD_W = 900`, `CARD_H = 1590` が固定定数になっている。
- **実装内容**:
  1. `card-config.js` に `orientation: "portrait"`（`"portrait" | "landscape" | "auto"`）を追加。
  2. `scripts/_utils.py` に `resolve_layout(cfg)` を新設。`"auto"` 指定時は Pillow (`Image.open`) で `cfg["photo"]` の実画像サイズを読み取り、`width > height` なら `"landscape"`、それ以外は `"portrait"` を返す。
  3. 解決した `orientation` に応じて `(CANVAS_W, CANVAS_H, CARD_W, CARD_H, CARD_INNER_W, CARD_INNER_H)` を返すヘルパーを提供し、全スクリプトから参照する。
  4. HTML 3ファイル（`index.html`, `compositions/scene-summon.html`, `compositions/scene-result.html`）の `data-resolution` / `viewport` / `data-width` / `data-height` を解決済み解像度へ自動同期する関数（`sync_html_resolution`）をビルドパイプラインに組み込む。

---

### ② 物理アセット生成スクリプト群の横寸法対応
- **対象ファイル**:
  - `scripts/render_material.py`
  - `scripts/render_typography.py`
  - `scripts/render_optics.py`
- **現状の課題と実装内容**:
  1. **虹フレーム・内窓深度 (`render_material.py`)**:
     - `generate_rainbow_foil_frame(w, h)` と `generate_window_depth(w, h)` はすでに任意の `w, h` に対応しているため、`1480×860`（内窓 `1440×820`）を渡すだけでそのまま生成可能。
  2. **カード裏面 (`render_material.py` L290-L350)**:
     - `_crest_mask`（放射スパイク長 `330px`・外周リング等）および `_guilloche_mask`（ロゼット半径 `300 / 400 / 560px`）が縦カード（高さ `1590px`）前提の固定ピクセル値になっており、横カード（高さ `860px`）では上下の枠を突き抜ける。
     - **対策**: `scale = min(w, h) / 900.0`（横カード時は `860 / 900 ≈ 0.955`、または紋章が美しく収まる `min(w, h) / 1020.0 ≈ 0.84`）を掛けて中央紋章とギョーシェ半径をスケーリングする。
  3. **フィルムグレイン (`render_material.py` L501)**:
     - `generate_film_grain_overlay(1080, 1920)` の固定引数を `CANVAS_W, CANVAS_H`（横時は `1920, 1080`）へ変更する。
  4. **箔タイポグラフィ (`render_typography.py` L900-L909)**:
     - 横カードは**横幅が広い（内窓 `1440px`）一方、高さが短い（内窓 `820px`）**ため、下部テキスト群が縦に積み上がると写真の主要被写体を隠してしまう。
     - **対策**: Landscape 時は `specs` のフォントサイズを約 80〜85% に引き締める一方、`max_w` を `780px → 1180px` へ広げ、フレーバーテキストを横長1行（最大2行）でコンパクトに収める。
     - あわせて `typo-manifest.js` のルートに `"layout": {"orientation": ..., "canvasW": ..., "canvasH": ..., "cardW": ..., "cardH": ...}` を書き出し、フロントエンド JS が参照できるようにする。
  5. **カットイン光学アセット (`render_optics.py` L976-L1027)**:
     - 魔法陣・オーブ・星・スパークル・玉ボケは正方形スプライトのため変更不要。
     - `render_cutin_assets` の `opt_cutin_flare.png` / `opt_cutin_speedlines.png` は `fw = CANVAS_W`（横時は幅 `1920px`）で生成することで、ワイド画面での引き伸ばしボケを防ぐ。

---

### ③ 召喚フェーズ（Scene 1-2）の 16:9 空間レイアウト調整
- **対象ファイル**:
  - `compositions/scene-summon.html`
  - `compositions/scene-summon.css`
- **現状の課題と実装内容**:
  1. **キャンバスサイズと横幅100%要素**:
     - `html, body`, `#summon-root`, `.clip`, `#summon-camera` の固定 `1080px / 1920px` を CSS 変数（または `html[data-resolution="landscape"]` ルール）で `1920px / 1080px` に切り替える。
     - `#flash-rainbow-streak` と `#cutin-band`、`#cutin-flare` の `width: 1080px` を `width: 100%` に変更し、1920px 全幅を貫くアナモルフィック光閃・カットインにする。
  2. **3D床パース魔法陣とオーブの縦方向バランス**:
     - 縦高さが `1920px → 1080px` になるため、`#orb-wrap`（420×420）と `#magic-circle-wrap`（1024×1024）をそのまま置くと画面上下が窮屈になる。
     - **対策**: Landscape 時は `#magic-circle-wrap` の基準位置を `top: 60%` 付近、初期・昇格時のスケールを約 `0.85〜0.90` 倍に調整し、`#orb-wrap` も約 `0.85` 倍に抑えることで、16:9 ワイド空間の床の奥行きを広く見せる。
  3. **収束パーティクルの楕円配置 (`scene-summon.html` L146)**:
     - `dist = 390 + rng() * 240` の円形配置に対し、Landscape 時は `startX` を `1.35` 倍、`startY` を `0.78` 倍のワイド楕円分布にすることで、16:9 画面の左右端からもエネルギーが収束する迫力を出す。

---

### ④ リザルトフェーズ（Scene 3-5）の横型カード＆パーティクル座標対応
- **対象ファイル**:
  - `compositions/scene-result.html`
  - `compositions/scene-result.css`
  - `compositions/scene-result-setup.js`
- **現状の課題と実装内容**:
  1. **カード寸法と CSS 変数 (`scene-result.css`)**:
     - `html[data-resolution="landscape"]` 時に `--card-w: 1480px; --card-h: 860px;`、`#card-stage { top: 110px; }` に切り替える。
     - 背景の `#result-bg-ring`（現在 `1700×1700`）は、横画面では上下にはみ出しすぎないよう `1120×1120`〜`1280×1280` 程度、またはカードの左右余白（各220px）から魔法陣の円弧が美しく覗くサイズに調整する。
  2. **回転スペキュラとホログラムスイープの走査距離 (`scene-result.html` L169-L185)**:
     - 縦カード幅（900px）前提で `#spin-spec-back/front` の移動先が `x: 1420〜1460`、`#holo-sweep-1/2` が `x: 1850` に設定されている。
     - 横カード（幅 1480px）ではカードの右端まで到達する前に止まってしまうため、`cardW` に連動して移動距離を `+580px`（例: `spin-spec` は `x: 2020`、`holo-sweep` は `x: 2450`）へ自動拡張する。
  3. **下部テキストオーバーレイとビネットの省スペース化 (`scene-result.css`)**:
     - 横カード（内窓高さ `820px`）で写真中央〜上部を広くクリアに保つため、Landscape 時は `#card-overlay-layer` の `padding: 20px 56px 36px; gap: 6px;`、星サイズ `.star-item` を `90px → 72px` に引き締める。
     - `.photo-vignette` の下部暗色グラデーション開始位置も `54% → 64%` に下げ、風景の空や被写体の顔に暗い影がかからないようにする。
  4. **【最重要】スパークル・金箔フレーク・玉ボケの座標スケーリング (`scene-result-setup.js` L147-L308)**:
     - **問題点**: 現在、`sparkleClusters`（`x: ±468..504`, `y: ±510..838`）、`flakeData`（`startX: ±360..445`, `startY: ±590`）、`bokehData`（`endX: ±435..525`, `endY: ±775..920`）がすべて縦カード（半幅 `450px`、半高 `795px`）基準のハードコード座標になっている。このまま横カード（半幅 `740px`、半高 `430px`）で表示すると、**左右のスパークルや金箔がカード内部の写真ド真ん中に出現し、上下のスパークルは画面外へ消えてしまう**。
     - **対策**:
       - スパークル座標を「縦カード半寸（`baseHalfW = 450`, `baseHalfH = 795`）に対する正規化比率」として扱い、実行時の `(cardHalfW, cardHalfH)` に合わせてスケーリングする（または Landscape 用の4隅クラスター座標テーブルに分岐する）。
       - 金箔フレーク（`flakeData`）の `startX` を `side * (cardHalfW - 60 + rng() * 85)`、`startY` を `(rng() - 0.5) * (cardH * 0.74)` に変更し、常にカードの左右外縁から外側へ舞うようにする。
       - 玉ボケ（`bokehData`）も `cardHalfW` / `cardHalfH` の外周余白レーン（左右は `±(cardHalfW + 30..160)`、上下は `±(cardHalfH + 25..95)`）へ配置する計算式に汎用化する。

---

### ⑤ 定量QAスクリプト（`scripts/qa_video.py`）の解像度フリー化
- **対象ファイル**: `scripts/qa_video.py`
- **現状の課題**:
  - `L74` の `decode_gray_frames(video_path, w=270, h=480)` が縦動画（9:16）比率固定になっている。
- **実装内容**:
  - `probe_streams` で取得した `info["width"]` と `info["height"]` を参照し、`width > height` の場合は `(w=480, h=270)`、それ以外は `(w=270, h=480)` で縮小デコードするように1行追加する（輝度・ダレ・終盤固定・LUFS の判定ロジック自体はそのまま 100% 機能する）。

---

## 5. Phase 3・Phase 4 開発時に意識すべき先回りポイント

Phase 5 へ進む前の **Phase 3・Phase 4** で以下を意識しておくと、手戻りがゼロになります。

1. **Phase 3（音響刷新 ＆ 後半マイクロポリッシュ4点）**:
   - 音響（`scripts/generate_se.py`）は 15.0秒タイムラインに完全同期しているため、**縦動画・横動画で 100% 共通利用可能**。
   - `3-5` のマイクロポリッシュ（テキスト走査ワイプ出現・`13.2s` の外枠リムグレア等）を実装する際、`px` 固定値ではなく `%` や CSS 変数（`--card-w`, `--card-h`）基準で組んでおく。
2. **Phase 4（任意テキスト変更時の箔タイポ自動同期 ＆ オートレイアウト）**:
   - `render_typography.py` が生成する `assets/generated/typo-manifest.js` に、テキスト情報だけでなく **`layout` オブジェクト（`orientation`, `canvasW`, `canvasH`, `cardW`, `cardH`）を出力する仕様** を先行導入しておくと、Phase 5 のフロントエンド切替基盤がそのまま整う。
