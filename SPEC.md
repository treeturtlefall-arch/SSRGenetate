# SSRGenerate 確定仕様書 (`SPEC.md`)

> 本ドキュメントは SSRGenerate の現在の実装に基づく**確定仕様**です。  
> エージェント向けの常駐ルール・コマンド・検証手順は [`AGENTS.md`](./AGENTS.md)、今後の開発計画は [`ROADMAP.md`](./ROADMAP.md) を参照してください。

---

## 1. 基本・出力仕様

| 項目 | 仕様 | 定義箇所 |
| :--- | :--- | :--- |
| **解像度** | 縦 9:16: `1080 × 1920`（`data-resolution="portrait"`）<br>横 16:9: `1920 × 1080`（`data-resolution="landscape"`） | `index.html`, `compositions/scene-*.html`, `card-config.js` (`orientation`) |
| **フレームレート / 書き出し** | `30fps` / `hyperframes@0.9.72 render -q delivery --crf 12` | `package.json` |
| **出力ファイル** | `renders/SSR_{preset}_{YYYYMMDD}.mp4`（同日重複時は `_2`, `_3` ... 自動連番） | `scripts/render_video.mjs` |
| **総尺** | **16.0 秒**（冒頭 `0.5s` 無音黒フェードイン ＋ 本編 `15.0s` ＋ 末尾 `0.5s` 無音黒フェードアウト） | `index.html`, `scripts/qa_video.py` |
| **カード物理寸法** | 縦: `900px × 1590px`（内窓 `860×1550`）<br>横: `1480px × 860px`（内窓 `1440×820`）<br>共通: 枠幅 `20px` / 外角丸 `40px` / 内窓角丸 `24px` | `scripts/_utils.py`, `compositions/shared-base.css` |
| **写真保護方針** | 入力写真は 100% クリアなまま無加工維持（顔被りは Z 順・軌道・中央減衰マスクで回避） | `compositions/scene-result.css`, `scene-result-setup.js` |
| **決定論性** | Mulberry32 疑似乱数 + NumPy `default_rng(seed)` + `window.__timelines` 登録済み GSAP タイムラインのみ使用 | `compositions/shared-utils.js`, `scripts/*` |

> [!IMPORTANT]
> カード物理寸法（`CARD_W` / `CARD_H` / `CARD_BORDER` / `CARD_OUTER_R` / `CARD_INNER_R`）は `scripts/_utils.py` と `compositions/shared-base.css` で**必ず一致**させること。

---

## 2. タイムライン詳細仕様

### 2-1. ルートコンポジション構成（`index.html` / 全体時刻 `0.0s 〜 16.0s`）

| 要素 ID / コンポジション | 全体時刻 (`data-start` / `data-duration`) | 役割 |
| :--- | :--- | :--- |
| `#preroll-bg` | `0.00s 〜 0.55s` (`dur=0.55`) | `0.0s 〜 0.5s` で `#000000` から深淵の宇宙背景へフェードイン |
| `#comp-summon` (`scene-summon`) | `0.50s 〜 7.90s` (`dur=7.4`) | Phase 1-2: 召喚・オーブ・フェイク昇格（**本編 `0.0s 〜 7.4s`**） |
| `#comp-result` (`scene-result`) | `7.40s 〜 16.00s` (`dur=8.6`) | Phase 3-5: 3Dカード着地・確定演出・3秒リザルト（**本編 `6.9s 〜 15.0s` ＋ 末尾余白 `0.5s`**） |
| `#flash-layer` | `7.10s 〜 8.20s` (`dur=1.1`) | `7.24s` 立ち上がり → `7.48s 〜 7.58s` 純白ホールド → `7.58s 〜 7.80s` 抜け |
| `#edge-fade-out` | `15.45s 〜 16.00s` (`dur=0.55`) | `15.5s 〜 16.0s` で純黒 (`#000000`) へフェードアウト |

### 2-2. 音声トラック配置（`index.html` / 全体時刻基準）

| 要素 ID | 音源ファイル | `data-start` | `data-duration` | `data-volume` | 主な同期区間 |
| :--- | :--- | ---: | ---: | ---: | :--- |
| `#audio-summon` | `assets/se_summon.wav` | `0.5s` | `3.5s` | `0.85` | 冒頭点火・ウィスプ・オーブ形成（全体 `0.5s 〜 4.0s`） |
| `#audio-upgrade` | `assets/se_upgrade.wav` | `3.0s` | `4.8s` | `0.92` | 鼓動・金昇格・亀裂・真空ダッキング・虹昇格・臨界ライザー（全体 `3.0s 〜 7.8s`） |
| `#audio-fanfare` | `assets/se_fanfare.wav` | `7.3s` | `8.0s` | `0.95` | ホワイトアウト爆発・3D回転・SSR確定ファンファーレ・余韻着地（全体 `7.3s 〜 15.3s`） |

※ `0.0s 〜 0.5s`（冒頭プリロール）および `15.3s 〜 16.0s`（末尾 `0.5s` アウトロ含む）は完全無音。

### 2-3. シーン 1-2：`scene-summon`（本編 `0.0s 〜 7.4s` / 全体 `0.5s 〜 7.9s`）

| 本編時刻 | 全体時刻 | イベント・演出内容 |
| :--- | :--- | :--- |
| `0.00s 〜 0.58s` | `0.50s 〜 1.08s` | 冒頭流れ星（接線方向へ楕円ストレッチした流体リボン尾・左上→右斜め下）、背景オーラ・天蓋ゲート・3D床パース魔法陣出現 |
| `0.04s 〜 1.42s` | `0.54s 〜 1.92s` | RGB 三重螺旋ウィスプ降下（星核ヘッド＋接線回転・楕円ストレッチ流体リボン尾ノード＋スターダスト）＆上部 HUD (`RESONANCE`) 表示 |
| `1.34s 〜 1.72s` | `1.84s 〜 2.22s` | 前面点火スパーク (`#ignition-spark`)、2層パララックス浮遊クリスタル破片漂流開始 |
| `1.45s 〜 3.74s` | `1.95s 〜 4.24s` | 青クリスタルオーブ出現（高コントラスト硬質ファセット＆`#orb-core` 抑制）・収束粒子・青脈動（`2.68s`, `3.35s`）・カメラ微ズーム＆床/天蓋パース溜め（`1.50s〜3.66s`） |
| `3.66s 〜 4.45s` | `4.16s 〜 4.95s` | 黄金天頂雷撃 (`3.66s`) → 金昇格インパクト・カメラ衝撃・瞬間RGB色収差 (`3.78s〜3.79s`)・HUD (`ELEVATION`)・床湧き上がりダストウェーブ |
| `4.50s 〜 5.05s` | `5.00s 〜 5.55s` | 加速鼓動 (`4.50s`) → 臨界オーブ亀裂 (`4.84s`) → 吸い込み収縮 (`4.90s`) |
| `5.06s 〜 5.18s` | `5.56s 〜 5.68s` | **真空の間**：`#vacuum-dimmer` 暗転・周辺光減衰・魔法陣急停止（`dramatic` カーブ） |
| `5.185s 〜 5.60s` | `5.685s 〜 6.10s` | プリズム雷撃 (`5.185s`) → 虹昇格爆発・瞬間RGB色収差・ゴッドレイ・虹光柱 (`5.20s`)・HUD (`OVERDRIVE`) |
| `5.62s 〜 6.60s` | `6.12s 〜 7.10s` | ボーダーレス虹カットイン（`昇格 SSR 確定`・スピードライン・斜め光沢 `#cutin-glint`・横ドリフト＆拡大横飛び退場） |
| `6.48s 〜 7.06s` | `6.98s 〜 7.56s` | 臨界ズームバースト → ホワイトアウトへ遷移（`7.02s` でステージフェードアウト） |

### 2-4. シーン 3-5：`scene-result`（`T0 = 6.9s` / 本編 `6.9s 〜 15.0s` ＋ 余白 `0.5s`）

| 本編時刻 | 全体時刻 | イベント・演出内容 |
| :--- | :--- | :--- |
| `7.02s 〜 7.10s` | `7.52s 〜 7.60s` | リザルトステージ立ち上がり・黄金ゴッドレイ＆光学リング展開 |
| `7.12s 〜 8.88s` | `7.62s 〜 9.38s` | 3Dカード回転（`rotationY: -720° → -195° → -12° → 0°`、5層金属エッジ厚みスライス `.card-edge-slice` は着地後 `8.82s` で非表示化）・表裏スペキュラ反射（裏面 `7.74s〜`、表面 `8.48s〜`）・裏面タメ光（`7.96s〜8.40s` 中央紋章チャージ `#card-back-emblem-glow` ＋外枠プリズム漏れ光 `#card-back-rim-burst`） |
| `8.68s` | `9.18s` | **正面ビタ止め着地**：着地衝撃波（背面）・ズームパンチ・瞬間RGB色収差・3D金箔片18個・2層DOF玉ボケ16個・疎密スパークル22個展開開始 |
| `8.76s 〜 9.56s` | `9.26s 〜 10.06s` | SSR クレスト刻印 (`8.76s`) → 属性プレート (`8.98s`) → 星連続点灯 (`9.00s〜`、0.14s間隔) |
| `8.92s 〜 11.85s` | `9.42s 〜 12.35s` | 中央減衰プリズムホロスイープ 2本（`8.92s`, `10.45s`）＋ 箔タイポ光走査ワイプ（サブタイトル `9.38s` → タイトル `9.60s` → フレーバー `9.96s` → `cardNo` `10.30s`） |
| `12.00s 〜 15.00s` | `12.50s 〜 15.50s` | **レイアウト完全固定・光のみ微動**：カード/文字/星/粒子の位置・サイズ固定のまま、ホロ光沢シマー・外枠リムグレア (`12.95s`)・背景ハロー・スパークル/玉ボケの位相差呼吸を維持 |
| `15.00s 〜 15.50s` | `15.50s 〜 16.00s` | 末尾プリロール余白（親コンポジション `#edge-fade-out` が黒フェードアウト） |

---

## 3. ディレクトリ・ファイル構成

### ルート設定・コンポジション
- `card-config.js` — 写真・テキスト・タイポグラフィ・光学・マテリアル・召喚魔法陣・音声目標 LUFS・乱数シードの一元設定
- `index.html` — ルートコンポジション（音声 3 トラック・プリロール/アウトロ黒フェード・ホワイトアウト・サブコンポジション統合・CLI 変数転送）
- `hyperframes.json` — HyperFrames パス・プロキシ設定
- `meta.json` — プロジェクトメタデータ

### `compositions/`（シーン別サブコンポジション ＆ 共通モジュール）
- `compositions/shared-base.css` — バンドル済みフォント定義（`YujiSyuku`, `CineCaption`, `ShipporiMincho`, `Cinzel`, `ZenMaruGothic`, `Outfit`, `JetBrainsMono`）・カード寸法変数・背景/パレットトークン・フィルムグレイン定義
- `compositions/shared-utils.js` — Mulberry32 PRNG (`createRng`)・相対パス解決 (`resolveAssetPath`)・設定優先解決 (`pickConfigValue`)・SVG色収差フィルタ自動注入＆瞬間RGB色収差 (`ensureChromaShockSvg` / `addChromaShock`)
- `compositions/scene-summon.html` / `scene-summon.css` / `scene-summon-setup.js` — 召喚〜昇格シーンの DOM・GSAP タイムライン・決定論的パーティクル/螺旋軌道セットアップ
- `compositions/scene-result.html` / `scene-result.css` / `scene-result-setup.js` — 3D カード・リザルトシーンの DOM・GSAP タイムライン・タイポマニフェスト適用・星/スパークル/金箔/玉ボケ生成

### `scripts/`（決定論的アセット生成 ＆ QA スクリプト）
- `scripts/_utils.py` — `card-config.js` 読み込み、シード解決、色変換、Porter-Duff Over 合成、微細シボ、金属レリーフ陰影、カード寸法定数
- `scripts/_optics_core.py` — H&D 分光スペクトル、FFT 異方性 PSF ぼかし、EDT 距離変換、FBM ノイズ、6段階物理光学発光パイプライン
- `scripts/_font_slots.py` — `assets/fonts_custom/` 優先解決・TTF `cmap` パーサー・書体別視覚サイズ正規化係数一元管理
- `scripts/_typo_modern.py` — 4軸直交スキーマ (`font × style × palette × layout`) ＆ 2x/3x SSAA・EDT 縁取りモダンタイポ生成エンジン
- `scripts/_audio_dsp.py` — 現代ソシャゲ音像シンセ、`fftconvolve` ホール残響、BS.1770-4 LUFS / TruePeak 計測、ソフトリミッター
- `scripts/_audio_slots.py` — `assets/se_custom/`（11 スロット＋`slots.json`）の WAV デコード・44.1kHz ステレオ変換・フォールバック管理
- `scripts/build_all.py` — 下位 4 スクリプトを並列実行する一括ビルダー（`npm run build:assets`）
- `scripts/render_typography.py` — 書字キネマティクス＆箔/モダンタイポ透過 PNG＋`typo-manifest.js` 生成（`npm run build:typo`）
- `scripts/render_optics.py` — 物理光学発光アセット透過 PNG 並列生成（`npm run build:optics`）
- `scripts/render_material.py` — 虹金属箔フレーム・裏面・ホロプリズム・金箔結晶片・内窓深度・フィルムグレイン生成（`npm run build:material`）
- `scripts/generate_se.py` — 16.0 秒仮想マスター基準のステレオ WAV 効果音 3 本生成（`npm run build:se`）
- `scripts/render_video.mjs` — `card-config.js` ＋ CLI `--variables` / `--variables-file` の自動箔タイポ同期＆自動命名 MP4 書き出しラッパー（`npm run render`）
- `scripts/qa_video.py` — 出力 MP4 の自動定量 QA（`npm run qa`）

### `assets/` ＆ `renders/`（素材・生成物）
- `assets/photo.jpg` — 入力写真（`.gitignore` で画像類は除外）
- `assets/fonts/` — バンドル済み日本語/欧文フォント群（現行プリセット・カットイン・HUD用 9書体、OFL / `cinecaption` 個別ライセンス。未使用/旧書体は `.gitignore` 隔離でリポジトリ省エネ化）
- `assets/fonts_custom/` — ローカル専用カスタムフォントスロット（`.gitignore` 隔離、`README.md` のみ追跡）
- `assets/generated/` — 生成画像群と `typo-manifest.js`
  - タイポ: `typo_ssr.png`, `typo_attr.png`, `typo_subtitle.png`, `typo_title.png`, `typo_flavor.png`, `typo_cardno.png`, `typo_royal_rule.png`, `typo_cutin_main.png`, `typo-manifest.js`
  - 光学: `opt_mc_{blue,gold,rainbow}_{outer,mid,inner}.png`, `opt_gate_{blue,gold,rainbow}_{outer,inner}.png`, `opt_orb_{blue,gold,rainbow}_{shell,facet}.png`, `opt_orb_core_bleach.png`, `opt_orb_cracks.png`, `opt_godrays_{prism,gold}_{a,b}.png`, `opt_pillar_{gold,rainbow}.png`, `opt_shock_{gold,rainbow}.png`, `opt_cutin_{flare,speedlines}.png`, `opt_result_ring.png`, `opt_meteor_{blue,red,green}.png`, `opt_wisp_head_{blue,red,green}.png`, `opt_bolt_{gold,prism}.png`, `opt_shard_{far,near}_{0,1,2}.png`, `opt_star_gold.png`, `opt_sparkle_{gold,white,pink,cyan}.png`, `opt_bokeh_{gold,rose,aqua,white}_{far,near}.png`
  - マテリアル: `mat_rainbow_frame.png`, `mat_window_depth.png`, `mat_card_back.png`, `mat_holo_prism.png`, `mat_flake_{0..5}.png`, `mat_film_grain.png`
- `assets/se_summon.wav`, `assets/se_upgrade.wav`, `assets/se_fanfare.wav` — 生成済み効果音
- `assets/se_custom/` — ローカル専用カスタム SE 拡張スロット（`.gitignore` 隔離、`README.md` のみ追跡）
- `renders/ssr_gacha_{preset}.mp4` — レンダリング出力 MP4（明示 `-o` 未指定時のデフォルト命名。`.gitignore` 対象）

---

## 4. 設定スキーマ（`card-config.js` ＆ CLI `--variables`）

### 4-1. `window.SSR_CARD_CONFIG` 主キー一覧

| キー | 既定値 / 選択肢 | 参照元 | 用途 |
| :--- | :--- | :--- | :--- |
| `photo`, `photoFit`, `photoPosition`, `photoZoom` | `"assets/photo.jpg"`, `"cover"`, `"50% 35%"`, `1.05` | `scene-result-setup.js` | 写真パス・トリミング・ズーム |
| `rarity`, `stars` | `"SSR"`, `0`（`0` で非表示、`1..6` クランプ） | `scene-result-setup.js`, `render_typography.py` | レアリティ表記と星の数 |
| `attribute`, `subtitle`, `title`, `flavor`, `cardNo` | 文字列（空文字で非表示） | `scene-result-setup.js`, `render_typography.py` | カード表示テキスト |
| `typography` | `preset` (`"royal-foil"` / `"cute-pastel"`、レガシー `"foil-brush"` / `"handwritten-sign"` / `"crisp-emboss"`), 4軸上書き (`layout`, `palette`, `font`, `style`), `wobble` (`0..100`), `foilGlitter`, `paperGrain`, `seed` | `render_typography.py`, `_typo_modern.py` | モダン/箔タイポグラフィ・レイアウト（カットインは分離固定） |
| `optics` | `halation`, `coreGlow`, `irregularity`, `seed` | `render_optics.py` | 6段階物理光学発光パラメータ |
| `material` | `frameFoilGlitter`, `frameBrushStrength`, `windowDepthOpacity`, `chromaShockPx`, `seed` | `render_material.py`, `scene-summon.html`, `scene-result-setup.js` | 虹フレーム・内窓深度・瞬間色収差量 |
| `summon` | `magicCircleSpeed` (`1.0`), `magicCircleCurve` (`"dramatic"` / `"steady"` / `"overdrive"`), `magicCircleRingRatios` (`[1.0, -1.3, 1.7]`) | `scene-summon-setup.js` | 召喚魔法陣の回転速度・加減速カーブ |
| `audio.targetLufs` | 任意（未設定時は `-14.0` LUFS） | `generate_se.py` | 統合ラウドネス目標値 |
| `seed` | `20261120` | 全生成スクリプト・セットアップ JS | 全体の決定論ルートシード |

### 4-2. CLI 変数オーバーライド（`--variables` / `--variables-file`）
- `index.html` および `compositions/scene-result.html` は `orientation`, `photo`, `title`, `subtitle`, `rarity`, `attributeBadge`, `attributeLabel`, `flavor`, `cardNo`, `preset`, `photoFit`, `photoPosition`, `photoZoom`, `resultRingMode` の 14 変数を `data-composition-variables` として公開している。
- `npm run render -- --variables ...`（または `--variables-file <path>`）を実行すると、`scripts/render_video.mjs` が `card-config.js` と CLI 変数をマージし、`typo-manifest.js`（`schemaVersion: 2`）の `source` スナップショットと比較する。テキスト・プリセット・写真情報等に差分がある場合は自動で `scripts/render_typography.py --overrides-stdin` を先行実行して物理箔 PNG と入力写真下部 30% 輝度に応じたビネット値（`vignette.midAlpha` / `vignette.bottomAlpha`）を再生成し、出力ファイル名も上書き後のプリセットへ同期する。
- `hyperframes render` を直接実行した場合などで `typo-manifest.js` と文字列が一致しないときは、自動的に HTML テキスト描画へフォールバックする。

---

## 5. 音響・カスタム SE 仕様

- **出力フォーマット**: 44.1kHz / 16-bit PCM ステレオ WAV（3 ファイル）。
- **DSP / マスタリング**: `scipy.signal.fftconvolve` によるホール・コンボリューションリバーブ、本編 `5.06s 〜 5.18s`（`se_upgrade.wav` 内 `2.56s 〜 2.68s`）の真空ダッキング、`0.5s`/`3.0s`/`7.3s` オフセットでの 16.0 秒仮想マスター組み立て、BS.1770-4 準拠 `-14.0 LUFS`（2パス収束）＋ `-3.1 dBFS` ソフトリミッター（4x TruePeak `-2.85 dBTP` 安全余裕確保）。
- **ローカルカスタム SE スロット（`assets/se_custom/`）**:
  - 対応 11 スロット: `ignition`, `heartbeat`, `gold_hit`, `orb_crack`, `rainbow_shatter`, `cutin_whoosh`, `riser`, `whiteout_impact`, `card_whoosh`, `card_land`, `star_chime`。
  - `.wav` 未配置時は 100% プロシージャル合成へ自動フォールバックする。個別設定（`mode: "layer" | "replace"`, `gain`, `proc_duck`, `offset_sec`, `trim_sec`）は `slots.json` で指定する（詳細は `assets/se_custom/README.md`）。

---

## 6. 自動定量 QA 基準（`scripts/qa_video.py`）

`npm run qa -- renders/ssr_gacha.mp4 --check-audio` で検証される定量合格基準（`PREROLL_SEC = 0.5` を加算した全体時刻基準）：

| チェック項目 | 計測対象ウィンドウ（全体時刻） | 合格基準 |
| :--- | :--- | :--- |
| **Stream** | 映像・音声ストリーム全体 | `width > 0`, `height > 0`, `fps > 0`, `duration <= 16.05s` |
| **Edge Padding** | 先頭フレーム (`0.0s`)・最終フレーム | `head_mean < 5.0` かつ `tail_mean < 5.0` |
| **Gray Veil** | 全フレーム | `mean > 150 & (p95 - p5) < 70 & mean < 245` のフレームが `<= 2` |
| **Vacuum Pause** | `5.60s 〜 5.68s` vs 基準 `5.25s 〜 5.35s` | 最小輝度比 `< 50.0%` |
| **Pre-Landing Stall** | `8.83s 〜 9.18s` | `frame diff < 2.5` の連続時間が `<= 0.20s` |
| **Tail Result** | `12.70s 〜 15.30s`（微動確認 `13.5s` vs `14.5s`） | `max diff < 2.5`（Shimmer 変化画素率 `> 0.1%` は WARN 目安） |
| **Audio**（`--check-audio`） | 全体・冒頭 `0.0-0.5s`・`14.5-15.0s`・`15.5-16.0s` | Integrated `-15.5 <= LUFS <= -12.5` / `head < -60.0 dBFS` / `14.5-15.0s > -65.0 dBFS` / `15.5-16.0s < -60.0 dBFS` |
