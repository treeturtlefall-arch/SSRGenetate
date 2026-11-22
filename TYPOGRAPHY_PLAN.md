# カードタイポグラフィ刷新 調査・事前検証 ＆ 本実装設計書 (`TYPOGRAPHY_PLAN.md`)

> `ROADMAP.md` の **Phase 3.5「カードタイポグラフィ点検・刷新（可変フォント・縁取り＆カラー・非対称レイアウト）」** に向けた、Phase A〜D の実機検証・プロトタイピング結果・数値仕様・本実装移行ブループリントの統合ドキュメントです。  
> 本設計書に記載するすべての環境値・ベンチマーク・HEX 値・座標・行番号は、実コードおよび Windows 実機検証・コンタクトシート目視確認に基づく確定値です。

---

## 1. 概要・スコープと絶対制約

### スコープ境界（現行維持 ／ 刷新対象）
- **現行維持（完全分離）**: 召喚〜昇格カットイン（`scene-summon` 内の `cutinSub` / `cutinMain`）のフォント・金箔質感・揺らぎは現行の王道スタイル（`YujiSyuku-Regular.ttf` + `foil-gold` / `cinecaption.ttf` + `foil-champagne`）を独立定数 `CUTIN_STYLE` として固定し、カード側プリセットやレイアウト切替の影響を一切受けない構造とする。
- **刷新対象（カード側 6 スロット）**: `scene-result` 上でカードと共に出現する文字群（`rarity`, `attribute`, `subtitle`, `title`, `flavor`, `cardNo`）および背景帯・マイクロ装飾・フレーム中央鋲について、**書体（`font`）× 装飾形状（`style`）× 配色（`palette`）× 配置・モーション（`layout`）の 4 軸直交基盤** を導入する。

### 守るべき不変ルール ＆ 技術制約
1. **総尺と終盤固定ルール**: 全体 **16.0 秒**（冒頭 `0.5s` 無音・黒フェードイン ＋ 本編 `15.0s` ＋ 末尾 `0.5s` 無音・黒フェードアウト）。**本編 `12.00s 〜 15.00s`（全体 `12.50s 〜 15.50s` / `scene-result` 相対 `5.10s 〜 8.10s`）はカード・帯・文字・星・装飾の位置・サイズ・不透明度を完全固定**し、光微動のみ動かす（`scripts/qa_video.py` L246-254 の `tail_max_diff < 2.5` を厳守）。
2. **写真保護**: 入力写真は 100% クリア維持（`SPEC.md` L17）。文字・帯・透過ウォーターマークは中央の顔安全エリア（内窓基準 `x: 22%..78%, y: 16%..66%`）へ侵入させない。
3. **決定論的レンダリング**: `Math.random()` / `Date.now()` / 実行時 `fetch()` 禁止。Mulberry32 疑似乱数・`np.random.default_rng(seed)`・登録済み GSAP タイムラインのみを使用する。
4. **物理寸法同期**: `CARD_W=900`, `CARD_H=1590`, `CARD_BORDER=20`, `CARD_OUTER_R=40`, `CARD_INNER_R=24`, 内窓 `860×1550`（`scripts/_utils.py` L36-42 / `compositions/shared-base.css` L28-32）を基準とする。
5. **OSS ライセンス安全**: 同梱フォントは `SIL OFL 1.1` 等の再配布可能書体に限定し、商用可・再配布不可のローカル書体は `.gitignore` 隔離の `assets/fonts_custom/` へ分離する。
6. **Windows 実機制約**: 本環境の Pillow 12.3.0 は `raqm=False` のため `direction="ttb"` / `features=["vert","vrt2"]` が使用不可。縦書きは Python 1 文字ずつ描画パイプラインの拡張で自前実装する。

---

## 2. Phase A：技術検証・フォント棚卸し・コード結合点

### 2-1. 既存 7 書体の棚卸し実測 ＆ ライセンス監査結果
根拠: `assets/fonts/*`, `assets/fonts/LICENSE-OFL.txt` (L1-93), `scripts/render_typography.py` (`FONT_NORM_FACTORS` L47-55), および実測（`size=100`, `anchor="la"`）。

> [!NOTE]
> **リポジトリ省エネ化対応**: 以下のうち、現行プリセット・カットイン・HUD で不使用となった 5 書体（`KleeOne`, `ZenKurenaido`, `SetoFont`, `TekitouPoem`, `TekitouPoem_Bold`、計約 37.2MB）は `.gitignore` に隔離され Git 追跡を解除済み。フォールバックチェーンも同梱の `ZenMaruGothic` / `ShipporiMincho` 等へ移行している。

| ファイル名 | サイズ / 総CP | 一次ライセンス / 再配布 | JIS 第1 / 第2 | `asc/dsc` (@100) | 龍 / あ ink_h | 調整目安 `norm` | 欠落文字・注意点 |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `YujiSyuku-Regular.ttf` | 8.43MB / 8,013 | **SIL OFL 1.1** (Kinutafontfactory) / **可** | 100% / 100% | `116 / 29` | `88 / 83` | `1.04〜1.05` (維持) | `U+301C(〜)`・`‼⁉`・結合濁点(`U+3099`)欠（`U+FF5E～`・`★☆♡♥ー` 収録。カットイン主字固定） |
| `KleeOne-Regular.ttf` *(除外)* | 8.72MB / 10,178 | **SIL OFL 1.1** (Fontworks) / **可** | 100% / 100% | `116 / 29` | `88 / 86` | `1.04〜1.05` | 結合濁点・`✦✧` のみ欠（主要記号網羅）。`.gitignore` 隔離済み |
| `ZenKurenaido-Regular.ttf` *(除外)* | 4.30MB / 7,815 | **SIL OFL 1.1** (Google Fonts) / **可** | 100% / 100% | `116 / 29` | `94 / 85` | **`0.98〜1.00`** | `ゕゖ`・`U+FF5E(～)`・`U+2015(―)`・`‼⁉` 欠。`.gitignore` 隔離済み |
| `SetoFont.ttf` *(除外)* | 13.05MB / 57,020 | **SIL OFL 1.1** (瀬戸のぞみ v6.20) / **可** | 100% / 100% | `86 / 15` | `90 / 82` | `1.02` | 調査対象記号・結合濁点含め**全網羅**。`.gitignore` 隔離済み |
| `TekitouPoem.ttf` *(除外)* | 5.55MB / 16,125 | **SIL OFL 1.1** (Cockatrice Digital) / **可** | 100% / 100% | `86 / 15` | **`73 / 71`** | **`1.18〜1.22`** | 全網羅（視覚サイズが約15%小）。`.gitignore` 隔離済み |
| `TekitouPoem_Bold.ttf` *(除外)* | 5.53MB / 16,125 | **SIL OFL 1.1** (Cockatrice Digital) / **可** | 100% / 100% | `86 / 15` | **`77 / 76`** | **`1.14〜1.17`** | 全網羅（視覚サイズが約12%小）。`.gitignore` 隔離済み |
| `cinecaption.ttf` | 1.67MB / 4,370 | **独自フリー規約** (chiphead v2.26) / **商用可・再配布可・改変禁止** | **100% / 19.1%** | `86 / 15` | `95 / 90` | **`0.96〜0.98`** (現行1.04) | 仮名 `ゔゕゖヷ〜ヺ`・`♡♥`・`謳`・`〜`・`―` 欠。HUD フェーズ表示等で使用 |

> [!IMPORTANT]
> **ライセンス整備必須事項**: `assets/fonts/LICENSE-OFL.txt` には現在 `KleeOne` の著作権表記（L1）のみ記載されている。Phase 3.5-1 で `YujiSyuku` / `ZenKurenaido` / `SetoFont` / `TekitouPoem` および新規 OFL 書体の著作権表記を追記し、非 OFL かつ改変禁止である `cinecaption.ttf` は専用規約 `assets/fonts/LICENSE-cinecaption.txt` へ分離すること。

### 2-2. 候補 14 書体（`SIL OFL 1.1` 実測一覧）
Google Fonts 公式リポジトリより取得し、各 TTF の `name[0]`/`name[13]` で `SIL Open Font License, Version 1.1` を確認済み（`size=100`, VF は `Weight=min(700, max)` 計測。推奨 `norm` は和文 `龍_h=90px` 基準 / 欧文 `SSR_h=74px` 基準）。

| ジャンル | ファイル名 | サイズ / CP | VF軸 (`Weight`) | JIS L1 / L2 | `asc/dsc` | 実インク(w,h) (`龍` or `SSR`) | 推奨 `norm` | 破綻テスト欠落文字 |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- | :---: | :--- |
| 極太角ゴ | `DelaGothicOne-Regular.ttf` | 2.51MB / 9,030 | — | 100% / 100% | `116 / 29` | 龍 `(97,77)` / SSR `(266,76)` | **`1.17`** | なし (`{}`) |
| 極太角ゴ | `ReggaeOne-Regular.ttf` | 2.15MB / 8,231 | — | 100% / 100% | `116 / 29` | 龍 `(90,91)` / SSR `(212,82)` | **`0.99`** | なし (`{}`) |
| 極太角ゴ | `RocknRollOne-Regular.ttf` | 2.68MB / 8,230 | — | 100% / 100% | `116 / 29` | 龍 `(90,91)` / SSR `(204,82)` | **`0.99`** | なし (`{}`) |
| 太丸ポップ | `MochiyPopOne-Regular.ttf` | 5.16MB / 14,293 | — | 100% / 100% | `116 / 29` | 龍 `(95,96)` / SSR `(237,89)` | **`0.94`** | `★` |
| 太丸ポップ | `ZenMaruGothic-Bold.ttf` | 3.78MB / 7,812 | — | 100% / 100% | `116 / 29` | 龍 `(94,95)` / SSR `(180,73)` | **`0.95`** | `―` (`U+2015`) |
| 太丸ポップ | `ZenMaruGothic-Black.ttf` | 3.71MB / 7,812 | — | 100% / 100% | `116 / 29` | 龍 `(95,96)` / SSR `(181,74)` | **`0.94`** | `―` (`U+2015`) |
| 洗練明朝 | `ShipporiMincho-Bold.ttf` | 8.56MB / 15,363 | — | 100% / 100% | `116 / 29` | 龍 `(92,96)` / SSR `(207,77)` | **`0.94`** | なし (`{}`) |
| 洗練明朝 | `ShipporiMincho-ExtraBold.ttf` | 8.56MB / 15,363 | — | 100% / 100% | `116 / 29` | 龍 `(92,96)` / SSR `(208,77)` | **`0.94`** | なし (`{}`) |
| 欧文ﾛｰﾏﾝ | `Cinzel-VF.ttf` | 125KB / 367 | `400..900` | — | `98 / 38` | SSR `(191,72)` / 0123 `(213,77)` | **`1.03`** | 和文+`★―`（欧文専用） |
| 欧文ﾒｶ | `ChakraPetch-Bold.ttf` | 78KB / 725 | — | — | `100 / 31` | SSR `(184,70)` / 0123 `(209,70)` | **`1.06`** | 和文+`★`（`―` 収録） |
| 欧文ﾓﾀﾞﾝ | `Outfit-VF.ttf` | 111KB / 360 | `100..900` | — | `100 / 26` | SSR `(179,74)` / 0123 `(209,73)` | **`1.00`** | 和文+`★―`（欧文専用） |
| 等幅番号 | `JetBrainsMono-VF.ttf` | 187KB / 976 | `100..800` | — | `102 / 30` | SSR `(170,75)` / 0123 `(226,75)` | **`0.99`** | 和文+`★―`（等幅専用） |
| 欧文幾何 | `Montserrat-VF.ttf` | 745KB / 1,312 | `100..900` | — | `97 / 26` | SSR `(196,74)` / 0123 `(219,74)` | **`1.00`** | 和文+`★`（`―` 収録） |
| 縦長ﾃﾞｨｽﾌﾟﾚｲ | `BebasNeue-Regular.ttf` | 61KB / 461 | — | — | `90 / 30` | SSR `(110,72)` / 0123 `(154,72)` | **`1.03`** | 和文+`★―`（大文字専用） |

### 2-3. `assets/fonts_custom/` 2層運用 ＆ カテゴリ別フォールバックチェーン
- **`.gitignore` 隔離（`se_custom` 準拠）**: `.gitignore`（L18-20 準拠）へ `assets/fonts_custom/*` と `!assets/fonts_custom/README.md` を追加。商用可・再配布不可書体（例: ラノベPOP V2、にくまるフォント）や `fonts.json`（`slots`, `aliases`, `norm_factor`, `fallback`）はローカル専用とする。
- **`scripts/_font_slots.py`（`_audio_slots.py` 準拠）**: `CUSTOM_FONTS_DIR` を優先探索し、未配置時は警告ログのみで同梱 `assets/fonts/` へ自動フォールバックし決定論ビルドを継続する。
- **カテゴリ別フォールバックチェーン**: 現行の単一 `FALLBACK_FONT_FILE = "TekitouPoem.ttf"`（`render_typography.py` L44）では太ゴシックや繊細字幕から太さギャップが出るため、書体カテゴリ別のフォールバック配列（角ゴシック→`RocknRollOne` / Windows `NotoSansJP`、丸ゴシック→`ZenMaruGothic-Bold`、明朝→`ShipporiMincho-Bold`、細字/手書き→`SetoFont` / `KleeOne` → 最終安全網 `TekitouPoem`）へ拡張する。

### 2-4. 混植ペアリング・ベースライン `30px` ズレ解消・トラッキング仕様
- **混植ベースライン問題（`render_typography.py` L470）**: 現行 `d.text((draw_x, base_y_offset), ch, ..., font=cur_font)` はデフォルト `anchor="la"` 固定のため、Google Fonts 系（`ascent=116`）と国内 TTF 系（`ascent=86`）を混植すると（例: `YujiSyuku@104` 中の `TekitouPoem@105` `〜`）、**約 `30px`（0.3em）上に浮く**。**`anchor="ls"`（共通ベースライン座標 `glyph_base_y`）** への修正により、実機コンタクトシートでもベースライン飛び **0px** を確認済み。
- **トラッキング**: 現行 `render_humanized_line` L487（`adv + char_dx`）に `letter_spacing_em` 引数を追加する。

| ジャンル | タイトル和文 (`title`) | サブタイトル欧文 (`subtitle`) | カード番号 (`cardNo`) | サイズ比 (`sub` / `no` 対 `title`) | トラッキング (`title` / `sub` / `no`) |
| :--- | :--- | :--- | :--- | :---: | :--- |
| 王道ロイヤル | `YujiSyuku` or `ShipporiMincho-ExtraBold` | `Cinzel` | `JetBrainsMono` | `0.38〜0.43` / `0.30〜0.33` | `+0.03em` / `+0.16em` / `+0.08em` |
| 2Dアニメ・バトル | `DelaGothicOne` or `ReggaeOne` | `ChakraPetch` | `JetBrainsMono` | `0.34〜0.40` / `0.28〜0.32` | `-0.02em` / `+0.14em` / `+0.06em` |
| 可愛いポップ | `ZenMaruGothic-Black` or `MochiyPopOne` | `Outfit` | `JetBrainsMono` | `0.36〜0.42` / `0.30` | `+0.02em` / `+0.12em` / `+0.06em` |
| ストリート誌 | `RocknRollOne` | `BebasNeue` / `ChakraPetch` | `JetBrainsMono` | `0.34〜0.40` / `0.28` | `-0.01em` / `+0.14em` / `+0.08em` |
| アート写真集 | `ShipporiMincho-Bold` or `KleeOne` | `Montserrat` | `JetBrainsMono` | `0.35〜0.40` / `0.29` | `+0.06em` / `+0.20em` / `+0.10em` |

### 2-5. Windows Python / Pillow 実機制約 ＆ 自前縦書きルール
- **環境実測**: Python `3.11.14` / Pillow `12.3.0` / `freetype2 2.14.3` / **`raqm=False`**（`libraqm`/`fribidi`/`harfbuzz` DLL および `fontTools` 不在）。
- **API 挙動**:
  - `direction="ttb"` / `features=["vert","vrt2"]` はすべて `KeyError: 'setting text direction, language or font features is not supported without libraqm'` で失敗する。既存 7 書体の GSUB には全 7 書体に `vert`、3 書体（`KleeOne`, `YujiSyuku`, `ZenKurenaido`）に `vrt2` があるが `raqm=False` 下では利用不可。
  - **可変フォント（VF）**: `get_variation_axes()` / `set_variation_by_axes()` / `set_variation_by_name()` は `freetype2 2.14.3` で正常動作（非 VF `YujiSyuku` では `OSError`）。ただし `set_variation_by_axes` はインスタンスを in-place 変更し **`font_variant()` では軸値がリセットされる**ため、`get_font()`（`render_typography.py` L230 `@functools.lru_cache`）のキャッシュキーに `(font_file, size, axes_tuple)` を必ず含める。
- **自前 1 文字縦書きルール（`render_typography.py` 拡張）**:
  - **句読点 (`、` `。`)**: 回転せず**右上象限へオフセット**配置。
  - **長音符 (`ー`)・三点リーダー (`…`)・ダッシュ (`―`)**: **時計回り 90°回転 (`rotate(-90)`)**（※`ZenMaruGothic`/`ZenKurenaido` は `U+2015(―)` 欠落のため `ー` 置換またはフォールバック）。
  - **括弧類 (`「` `」`)**: `rotate(-90)`＋開き括弧は下寄せ・閉じ括弧は上寄せ。
  - **小書き仮名 (`ゃゅょっ`)**: 正立のまま右 `+10%`・上 `-6%` 程度オフセット。
  - **半角英数字**: 連続英字（例: `SSR`）は縦横比に応じ `rotate(-90)` 横回転またはセル中央正立積み、記号（`！`）は中央配置＋文字種別可変縦ピッチ詰め。

### 2-6. コード結合点点検・HTMLフォールバック方針・文字単位アニメ見積もり
- **結合点（`scripts/render_typography.py` 他）**:
  - `TYPO_PRESETS` (L87-118) と `main()` (L868-928) で `cutinSub`/`cutinMain` がカード側 6 スロットと同一辞書・同一 `wobble`/`foilGlitter`/`paperGrain` を共有しているため完全分離が必要。`scene-summon-setup.js` (L32-45) は `cutinSub`/`cutinMain` のみ参照（HTML フォールバックなし）、`scene-result-setup.js` (`bindTypoSlot` L49-86) はカード側 6 スロットのみ参照。
  - `apply_foil_and_grain_material` (L528-596) は `halo_pad` (L541) がソフトハロー前提のため太二重縁取り時はパディング不足でクリップする。`render_multiline_block` L643 は中央揃え固定、`render_humanized_line` L511-513 は `raw_tilt`（±1.6°）ランダム傾きを持つ。
  - `scene-result.css` は `#card-overlay-layer` (L514-525) 中央下揃え固定、`#card-no-corner` (L666-675) 右下固定、`#title-wipe-glint` (`scene-result.html` L221) `x: -235 -> 235` 固定座標、`clipPath` (L217, L220 等) 負マージン `-10px` 固定という干渉点がある。
- **HTML フォールバック再現性（`bindTypoSlot` 不一致時 / `--variables` 上書き時）**:
  - **採用方針**: Chromium/ANGLE 環境では、`-webkit-text-stroke` + `paint-order: stroke fill` は `stroke-linejoin: round` 不可による漢字の角トゲ飛び出しや `background-clip: text` との DOM 分離煩雑さがあり、多重 `text-shadow` は `4px` 超で花びら状ジャギーが出る。よって **SVG `<filter>`（`feGaussianBlur` + `feComponentTransfer` 擬似円形膨張＋`feFlood`＋`feComposite`）× CSS `background-clip: text` グラデ** の組み合わせを採用し、金属箔ラメ・物理シボ・`wobble` を除く色・二重縁・シャドウ・配置を単一要素のまま忠実近似する（フィルタ領域 `x="-15%" y="-30%" width="130%" height="160%"` 等へ拡張要）。
- **文字単位アニメ見積もり**:
  - **第 1 段階推奨（方式 C1: 帯/行スキュー連動ワイプ）**: `typo-manifest.js` に行/帯の bbox と文字幅を出し、動的 `#title-wipe-glint`（`±(w * 0.55)`）＋傾斜 `linear-gradient` マスクワイプで動かす。二重縁取り連続性 100%、描画負荷極小、HTML フォールバック完全一致（追加コスト: Python +40〜60行 / JS +20〜30行）。
  - **オプション（方式 C2: 距離場排他分割 PNG）**: 1 文字ずつの `y`/`scale`/`skew` ポップが必要な場合は、単純個別 PNG（縁段差・欠片混入）や 1 枚 PNG + `clip-path` スライス（太縁重なり破綻）を避け、結合済み二重縁取り RGBA を各文字への最短距離ラベルで**排他ピクセル分割**して `c0..cn.png` 出力する（`data-layout-ignore` 付与、HTML フォールバック時は C1 へ縮退。追加コスト: Python +150〜220行 / JS +70〜100行）。

---

## 3. Phase B：縁取りアルゴリズム比較 ＆ 装飾レシピ・直交辞書

### 3-1. 縁取り 4 手法比較実測（`覇王覚醒 SSR!`, `size=100`, `sw=8px`, 4書体平均）
| 手法 | 全体 median | 純粋二重縁 (`r=14`) | 最大突出 / 斜め面積 | 評価・結論 |
|---|---:|---:|---|---|
| `1a: EDT (二値+1pxAA)` | `26.8 ms` | `6.86 ms` | `8.0 px` / `1507` | 高速だが斜め曲線に微段差感 |
| **`1b: EDT (AAサブピクセル)`** | **`41.0 ms`** | **`12.66 ms`** | **`8.2〜8.6 px` / —** | **【標準採用】** 斜め太り・ジャギー・角の箱化ゼロ。$O(N)$ で 1 回の距離場を内縁/外縁/ベベルに共用可 |
| `2a/e: チェス盤膨張` | `21.2 / 23.7 ms` | — | `11.3 px` ($\sqrt{2}$倍) / `1797` (+19%) | **不適**: `!` 点が正方形化し斜め線 +19% 太り |
| `2b: ダイヤモンド膨張` | `45.4 ms` | — | `8.0 px` / `1309` (-13%) | **不適**: `!` 点がひし形化し斜め線が痩せる |
| `2d: 円盤 grey` | `59.4 ms` | `108.36 ms` | `8.2 px` / `1507` | **不適**: $O(r^2)$ のため太縁で急激に低速化 |
| `3a: 2x SSAA + EDT` | `113.8 ms` | — | `9.0 px` (2x基準) | **極小文字補完用**: `cardNo`/`flavor` 等のみ選択可 |
| `4a/b: Pillow stroke_width` | `22.7 / 8.3 ms` | — | `9.0〜9.2 px` | **不適**: `render_humanized_line` 後段の揺れ・シボマスクと非互換 |

### 3-2. 装飾レシピの最適パラメータ ＆ 実測ベンチマーク（`NotoSansJP-Black 84px`, `629x154`）
- **二重縁取り**: `1:2`（例: `in=3px, out=6px`）が暗明両背景での境界視認性と潰れ回避の最良バランス。下層から `porter_duff_over` で積み黒滲みゼロ（`12.60 ms` / cached SDF）。
- **ステッカー縁**: `w=10px`＋`scipy.ndimage.binary_fill_holes` で複雑漢字内部のピンホールを除去。`45°` ソリッド影（`15.74 ms`）または斜線ハッチ影（`pitch=7px, -45deg` AA付, `19.19 ms`）。
- **3D 押し出し**: `0.8px` 刻みスカラー累積＋外周リム（`2.5px`）で側面ジャギーを解消（`45.97 ms`）。
- **EDT 勾配ベベル**: C0 連続サブピクセル補間距離場 `d_in = where(inside, raw_in - 1 + alpha, alpha)` に対する `np.gradient` 法線。硬質チゼル（`sigma=0.35`, `14.24 ms`）は金属箔やアニメロゴに、ソフト（`smoothstep` + `sigma=0.75`, `14.13 ms`）はポップ系に適合。
- **インライン加工**: ツートン硬境界（`aa=1.6〜1.8px`, `4.12 ms`）、光沢カットライン（`line`/`wave`/`arc`, 実インク外接矩形正規化 + `1.35px` リム, `5.14 ms`）、微細斜めストライプ（`pitch=6px, contrast=0.18`, `5.14 ms`）、薄膜プリズム帯（輝度保存型 Overlay 推奨、`opacity=0.25..0.45`, `14.74 ms`）。
- **複合コンボ合計（mask+SDF込）**: アニメロゴ `36.73 ms` / ステッカー `54.86 ms` / 金箔チゼル3D `70.51 ms`（8 項目一括ビルドでも 1 秒未満）。

### 3-3. Phase B 直交装飾パラメータ辞書（`style` 軸の内部スキーマ）
色 HEX ではなくトークン参照（`"$fillTop"`, `"$outline"` 等）と組み合わせて運用する。

```js
// style 軸パラメータ構造（Phase B-2 確定スキーマ、色はトークン参照）
{
  fill: {
    mode: "gradient",          // "solid" | "gradient" | "twotone" | "metal"
    angleDeg: 90,              // -180..180（90=縦グラデ）
    splitPos: 0.52,            // twotone: 0.20..0.80（推奨 0.48..0.55）
    splitAngleDeg: -4.0,       // twotone: -25..25
    splitAaPx: 1.6,            // twotone: 0.5..4.0（推奨 1.5..2.0）
  },
  inline: {
    glossCut: { enabled: false, type: "wave", pos: 0.48, slopeDeg: -3.5, amp: 0.06, freq: 1.6, glossAlpha: 0.34, rimAlpha: 0.62 },
    stripes:  { enabled: false, angleDeg: 45.0, pitchPx: 6.0, duty: 0.45, contrast: 0.18 },
    prism:    { enabled: false, angleDeg: -26.0, bandPos: 0.48, bandWidth: 0.45, cycles: 1.35, opacity: 0.38 },
  },
  bevel: {
    enabled: false,
    type: "chisel",            // "chisel" | "soft"
    mode: "anime",             // "anime" (fill色保持) | "metal" (GOLD/SILVER_RAMP)
    widthPx: 6.5,              // 2.0..14.0（推奨 fontSize*0.07..0.09）
    depth: 5.5, lightDeg: -125.0, lightElev: 0.74, shininess: 30.0,
    specStrength: 0.65, hlStrength: 0.65, shStrength: 0.45,
  },
  stroke: {
    mode: "double",            // "none" | "single" | "double" | "sticker" | "extrude3d"
    innerWidthPx: 3.0,         // double 推奨: outer の 1/2
    outerWidthPx: 6.0,         // double: 4..10, sticker: 8..12
    fillHoles: false,          // sticker 時 true 推奨
    shadowOffset: [8, 8], shadowAlpha: 0.94, shadowHatch: false, hatchPitchPx: 7.0,
    extrudeDepthPx: 11.0, extrudeAngleDeg: 52.0, extrudeMetalSide: false,
    outerRimPx: 2.5,
  },
}
```

---

## 4. Phase C：4軸直交スキーマ・レイアウト・配色・マイクロ装飾・モーション

### 4-1. `font × style × palette × layout` 4軸直交 `card-config.js` スキーマ
`preset` でバンドル既定を一括展開しつつ、任意の 1 軸またはスロットのみを deep-merge 上書きできるため、組み合わせ爆発を起こさず自由な掛け合わせが可能。

```js
typography: {
  preset: "anime-pop",       // バンドル既定キー（旧 "foil-brush" 等もエイリアス互換）
  font: {                    // [軸1] 書体・組版・揺らぎのみ（色・縁・配置を知らない）
    bundle: "anime-pop",
    wobble: 10,              // 0..100（太ゴシック/明朝は低値 0..12、手書きは 28..45）
    slots: { title: { family: "DelaGothicOne-Regular.ttf", trackingEm: -0.02 } },
  },
  style: {                   // [軸2] 装飾形状・縁幅・光沢のみ（HEX・座標を知らない）
    bundle: "anime-double",
    foilGlitter: 0.35,
    paperGrain: 0.20,
    stroke: { mode: "double", innerWidthPx: 3.0, outerWidthPx: 7.0 },
  },
  palette: {                 // [軸3] 役割トークンHEXのみ（書体・縁幅・配置を知らない）
    bundle: "idol-pop",      // "idol-pop" | "cute-pastel" | "street-neon" | "royal-gold" | "royal-silver" | "industrial-spec" | "auto-photo"
    tokens: { /* 個別トークンHEX上書き可 */ },
  },
  layout: {                  // [軸4] 座標・帯・鏡像・モーションのみ（書体・HEXを知らない）
    id: "diagonal-ribbon",   // "classic-center" | "diagonal-ribbon" | "street-graphic" | "royal-fantasy" | "editorial-industrial"
    mirror: false,           // true で左右アンカー・帯角度符号・揃えを反転（文字画像は非反転）
    showMicroDecor: true,
  },
  seed: 20261120,
}
```

### 4-2. 5 レイアウト系統の空間仕様（内窓 `860×1550px` 基準）
- **内窓安全マージン**: `mat_window_depth.png`（`render_material.py` L239）の上左落ち影 `21px` と内角丸 `24px` を避けるため、原則 **内窓端から `28px` 以上**（`x: 28..832, y: 28..1522`）に配置。
- **表面フレーム中央鋲との非干渉予約領域**: 上 `(404,0,496,36)`・下 `(404,1554,496,1590)`・左 `(0,749,36,841)`・右 `(864,749,900,841)` の各辺中央 ±70px × 内窓最大 24px（`[380..520, 0..24]`, `[380..520, 1526..1550]`, `[0..24, 725..865]`, `[836..860, 725..865]`）。
- **顔保護コアゾーン**: `x: 22%..78% (189..671px)`, `y: 16%..66% (248..1023px)`。下部メインは `y >= 1080px`、上部要素は `y <= 230px` または左右外縁へ収める。

| 項目 | `classic-center` (互換) | ① `diagonal-ribbon` (アイドル/ポップ) | ② `street-graphic` (ストリート/誌) | ③ `royal-fantasy` (ハイエンド/ファンタジー) | ④ `editorial-industrial` (写真集/インダストリアル) |
|---|---|---|---|---|---|
| **帯角度** | `0°` | **`-7.5°`** (`mirror`時 `+7.5°`) | 帯 `-4.0°` / `skewX(-16deg)` | `0°`（精密水平） | `0°`（直角＋左軸縦） |
| **レアリティ (`rarity`)** | 左上 `left:16, top:16` | 左上リボン帯 `left:-18, top:44` (`390×104px`) + スターバースト | 左上平行四辺形タグ `left:28, top:28` (`360×78px`) | 左上クレスト `left:32, top:28` | 左上インデックス `left:32, top:28` |
| **`★×5` グルーピング** | テキスト直上中央 (`90px`×5) | **左上帯の直下** (`left:36, top:154`, `52px`×5) | **左上タグ右隣に横連結** (`42px`×5) | **左上 `rarity` 直下細罫線上** (`50px`×5+`◆`) | **左上 `rarity` 横/直下小整列** (`40px`×5) |
| **属性 (`attribute`)** | 右上 `right:16, top:22` | 右上 `right:28, top:28`, 高 `56px` | 右上メタ枠 `right:28, top:28` (`w<=260`) | 右上 `right:32, top:30` | 右上 `right:32, top:28` |
| **主タイトル帯** | 下部中央 `bottom:66` (`y≈1180..1484`) | **右下スラント帯** `right:-24, bottom:92` (`740px`幅, 右寄せ, `y≈1130..1458`) | **下部斜めカット帯** `left:28, right:28, bottom:54` (左寄せ+透かし `y>=1060`) | **下部二重罫線枠** `left:44, right:44, bottom:72` (`772px`幅, 左寄せ) | **左下強揃えブロック** `left:36, bottom:60` (`<=630px`幅＋右大余白＋左縦バー) |
| **`subtitle` / `flavor`** | 中央縦積 (`max_w:780`) | `sub`:帯直下右寄せ / `flavor`:帯下右寄せ(`660`) | `sub`:帯上辺タブ / `flavor`:帯下メタ行(`700`) | `sub`:`title`直上(+`0.20em`) / `flavor`:下段(`700`) | `sub`:**左余白縦書き** (`left:32, top:150..1020`) / `flavor`:左下(`600`) |
| **`#card-no-corner`** | 右下 `right:36, bottom:22` | **左下退避** `left:36, bottom:24` | メタ行右端統合 (`bottom:24, right:32`) | 右下 `right:36, bottom:22`（枠下余白） | 右下 `right:36, bottom:28`（`mirror`時 左下退避） |
| **文字サイズ階層** (`t/s/f/r/a/n`) | `74/34/29/94/26/24` | `82/30/25/88/24/22` | `84/26/24/64/22/20` (+透かし`180`) | `72/26/26/82/24/21` | `76/28/25/78/22/22` |

### 4-3. 役割トークン 11 個 ＆ 脱 Tailwind 禁止色 6 パレット HEX 表
Phase 0-4 の禁止色（Tailwind 初期色 `#38BDF8`, `#FEF08A`, `#F59E0B`, `#F472B6`, `#A855F7` 等 49 色）との重複ゼロを検証済み。明背景（`out-Bright CR >= 12.41:1`）・高彩度アニメ・暗所ポートレート（`in-Dark CR >= 6.16:1` / `fillTop-Dark >= 13.32:1`）の 3 環境すべてで高可読性を確認。

| パレット (`palette.bundle`) | `fillTop` | `fillBottom` | `inline` | `outline` | `shadow` | `glow` | `ribbonA` | `ribbonB` | `accent` | `plateBg` | `plateText` | `fill-out CR` |
|---|---|---|---|---|---|---|---|---|---|---|---|---:|
| **`idol-pop`** | `#FFE38C` | `#FF4B6E` | `#FFF9F2` | `#1C1030` | `#2E144D` | `#FFB870` | `#E0315E` | `#FF9642` | `#2CE6D0` | `#1E1338` | `#FFF4E0` | `5.56:1` |
| **`cute-pastel`** | `#FFD6E6` | `#FF7AA8` | `#FFFDF9` | `#3D234A` | `#6B4C8C` | `#FFCCE0` | `#4DBFB8` | `#FFC2D9` | `#FFE48F` | `#382046` | `#FFEBF3` | `5.59:1` |
| **`street-neon`** | `#DCFF66` | `#00D8B4` | `#F7FFF0` | `#0B0F1A` | `#E8287A` | `#32F5C8` | `#101626` | `#E8287A` | `#FFE047` | `#0E1422` | `#DCFF66` | `10.46:1` |
| **`royal-gold`** | `#FFFDF2` | `#D4A24C` | `#F2DFB3` | `#1C120B` | `#090B14` | `#F5D68E` | `#161B30` | `#C9953B` | `#E8F0FA` | `#0F1426` | `#F2DFB3` | `7.95:1` |
| **`royal-silver`** | `#FFFFFF` | `#9AA8BE` | `#E8EFFA` | `#121826` | `#080C16` | `#B8D4F5` | `#141C2E` | `#8496B4` | `#F2DFB3` | `#101728` | `#EEF4FC` | `7.36:1` |
| **`industrial-spec`** | `#F4F6F8` | `#B8C2CE` | `#FF6B2C` | `#12151C` | `#090B0F` | `#FF7E42` | `#1A1E28` | `#FF6B2C` | `#E8B84B` | `#161A22` | `#F4F6F8` | `10.13:1` |

- **`auto-photo`（OKLab k-means++, `k=5`, 処理時間 `4〜26ms`）の設計位置づけ**:
  - **結論: 任意オプション（`palette.bundle: "auto-photo"`）に留め、標準デフォルトは上記キュレーション済み 6 パレットとする。**
  - 実写写真（`assets/photo.jpg` 等）では肌色や雑多背景の平均化により黄土/茶/オリーブ寄りの地味な主色へ寄りやすく、低彩度二極端画像では端ピクセルの色ノイズを拾いやすいため（採用時は無彩色フォールバック閾値 `max_s < 0.22` ＋暗黄/暗茶回避ガードを併用）。

### 4-4. マイクロ装飾パーツ 6 種カタログ（`0.65x + YUV4:2:0` 耐性検証済み）
実写縮小・動画圧縮時の消失検証（`lw=0.8/1.0px` は途切れ・癒着で NG、`lw=2.0px / 14px` で輝度保持率 `91.7%`）に基づき、**最小線幅 `1.5px`（推奨 `1.8〜2.0px`）・最小文字 `13px`（推奨 `14〜16px`）** を基準とする。

| パーツ名 | 推奨描画方式 | 寸法・座標・最小線幅仕様 | 配置・非干渉・透過制約 |
|---|---|---|---|
| **1. 表面フレーム中央鋲** (`frame_center_studs`) | Python 透過 PNG (`mat_rainbow_frame.png` へ `3x SSAA` + `shade_metal_relief` 焼込) | 上/下 `92×36px`・左/右 `36×92px`（内周突出 `12px`） | 上 `(404,0,496,36)`・下 `(404,1554,496,1590)`・左 `(0,749,36,841)`・右 `(864,749,900,841)`。既存3バッジと **`overlap=(0x0)`** |
| **2. 極小英文コピー** (`micro_copy`) | CSS / SVG | `13〜16px`（推奨 `14px`）、`letter-spacing: 0.18..0.28em` | 内窓端から `>= 28px`、上辺バッジ下または帯縁沿い、`α 0.58..0.85` |
| **3. `///` 斜線・バーコード・座標** (`tech_telemetry`) | インライン SVG（推奨） | 斜線 `lw >= 1.8..2.2px` (20°〜26°)、バー最小幅 `>= 2.0px`、文字 `13〜15px` | `#card-no-corner` 対角側または下部メタ行、`α 0.65..0.88` |
| **4. 十字レティクル** (`reticle_crosshair`) | インライン SVG | `28×28〜44×44px`、`lw >= 1.5..2.0px` (推奨 `1.8px`)、中心ギャップ `14%` | 下部左右コーナー余白・帯両端（顔保護外）、`α 0.60..0.85` |
| **5. 細二重罫線＋菱形 `◆/◇`** (`hairline_diamond_rule`) | インライン SVG | 主線 `1.5..1.8px` / 副線 `1.2..1.5px`、線間ギャップ `>= 4.0px`、`◆` `10..15px` | 下部テキスト枠・区切り線（内窓端 `>= 32px`）、`α 0.60..0.88` |
| **6. 極大透過ウォーターマーク** (`giant_watermark`) | CSS テキスト / SVG (`clip-path` 限定) | `160〜280px` 太字サンセリフ | 裸配置は汚れに見えるため**下部ビネット暗部・スラント帯内部へ `clip-path` 限定**、**`α <= 0.05..0.10`**（写真上 `<= 0.08`） |

### 4-5. ジャンル別 GSAP 登場モーション相対時刻表（`scene-result.html`）
基準: `T0 = 6.9s`（相対 `t = globalSec - 6.9`）。`#title-wipe-glint`（`scene-result.html` L221）の固定 `x: -235 -> 235` は撤去し実幅連動 `±(w * 0.55)` へ、`clipPath` 負マージンは `-10px -> -28px` へ拡張する。全系統とも **`10.85s`（相対 `3.95s`）までに完全静止**し、`12.00s` 以降の完全固定を厳守する。

| 本編時刻 (`相対t`) | ① `diagonal-ribbon` | ② `street-graphic` | ③ `royal-fantasy` | ④ `editorial-industrial` |
| :--- | :--- | :--- | :--- | :--- |
| **`8.76s` (`1.86`)** | 左上帯滑り込み (`x:-180->0`, `0.28s`)→`8.92s` `rarity` 打刻+閃光 | 左上タグ+星が斜め `clipPath` 一閃 (`0.24s`) | 上部 `rarity` 打刻＋菱形展開 (`0.38s`) | 左上インデックス＋小星ステップ点灯 (`0.28s`) |
| **`8.98s` (`2.08`)** | 右上属性＋左上帯下 `★×5` (`0.09s`刻み弾け `9.00..9.56s`) | 右上メタ枠高速マスク出現 (`0.26s`) | 右上属性＋`★×5` 中央 `◆` から対称展開 | 右上属性＋左縦アクセントバー延伸 (`scaleY:0->1`) |
| **`9.25s` (`2.35`)** | 右下スラント帯滑り込み (`x:+260->0`, `0.34s`) | 透かし滲み(`0->0.12`)+下部帯マスクスラッシュ (`0.28s`) | 下部細二重罫線が中央 `◆` から伸長 (`scaleX:0->1`) | `9.38s` 縦書き `subtitle` 上→下垂直ワイプ (`0.38s`) |
| **`9.48s` (`2.58`)** | `title` 斜めマスク抜け+バウンス (`1.08->1.0`)+動的閃光 | `title` 横スライド+スキュー復帰 (`skewX:-12->0`) | `9.50s` `subtitle`→`9.68s` `title` 金箔シルエットスイープ | `9.62s` `title` 左縦バーから水平スライド＋走査 |
| **`9.78s〜10.85s`** | `sub`(`9.74s`)→`flavor`(`9.96s`)→左下 `cardNo`(`10.22s`) → **`10.65s` 静止** | `sub` タブ(`9.72s`)→下部メタ行+`cardNo`(`9.95..10.35s`) → **`10.60s` 静止** | `flavor`(`10.05s`)→`cardNo`(`10.35s`) 水平ワイプ → **`10.85s` 静止** | `flavor`(`9.92s`)→右下バーコード/`cardNo`(`10.28s`) → **`10.80s` 静止** |
| **`12.00s〜15.00s`** | **完全固定**（ホロ・スパークル・玉ボケ・`12.95s` 外枠リムグレアのみ微動） | 同左 | 同左 | 同左 |

---

## 5. Phase D：採用プリセット・破綻テスト・本実装移行マップ ＆ QAゲート

### 5-1. コンタクトシート目視選別済み 採用プリセット（5 新標準 ＋ 1 レガシー互換）
1. **`royal-foil`**（王道ロイヤル）: `ShipporiMincho-ExtraBold` / `YujiSyuku` × `Cinzel` × `JetBrainsMono` / `metal-3d` / `royal-gold` / `royal-fantasy`（※旧 `foil-brush`・`classic-center` 互換）
2. **`anime-pop`**（2Dアニメ・バトル）: `DelaGothicOne` or `ReggaeOne` × `ChakraPetch` × `JetBrainsMono` / `anime-double` / `idol-pop` / `diagonal-ribbon`
3. **`cute-pastel`**（可愛いポップ）: `ZenMaruGothic-Black` or `MochiyPopOne` × `Outfit` × `JetBrainsMono` / `sticker-hatch` / `cute-pastel` / `diagonal-ribbon`
4. **`street-graphic`**（ストリート誌）: `RocknRollOne` × `BebasNeue` / `ChakraPetch` × `JetBrainsMono` / `neon-extrude` / `street-neon` / `street-graphic`
5. **`editorial-art`**（アート・写真集）: `ShipporiMincho-Bold` or `KleeOne` × `Montserrat` × `JetBrainsMono` / `editorial-clean` / `royal-silver` or `industrial-spec` / `editorial-industrial`
- *レガシー互換*: **`handwritten-sign`**（`TekitouPoem_Bold` / `SetoFont` 維持）
- *目視講評上の注意*: `DelaGothicOne` は極太・扁平（`norm=1.17`）のため大見出し（`74〜86px`）向き、`MochiyPopOne`（`★` 欠落）・`ZenMaruGothic`（`―` 欠落）・`cinecaption`（`謳`, `〜` 欠落）はカテゴリ別フォールバックチェーンで同一太さ系（`SetoFont` / `KleeOne` 等）を優先接続すること。

### 5-2. 破綻テスト文字列 7 ケース（`stress_strings.py`）
| ID | 文字列 | 検証目的 |
|---|---|---|
| `short` | `覇王` (`alt`: `一閃`) | 極端短文字の重心・余白・`len_gate` |
| `standard` | `ちいさな覇王` (`alt`: `蒼穹の継承者`) | 基準字面・トラッキング・収まり |
| `long` | `境界の彼方で咲き誇る約束の星屑と永遠の凱歌` | Auto-fit 縮小・2 行折り返し・二重縁行間干渉 |
| `kanji_rare` | `薔薇色の憂鬱・綺羅星と翡翠の龍謳` | 高画数難字潰れ・JIS 第 2 水準フォールバック |
| `kana_marks` | `ぴょんっ！ぱぴぷぺぽー〜っ！！` | 半濁点/小書き縁癒着・`U+301C(〜)` 欠落飛び |
| `mixed_latin_sym` | `SSR+ [Ver.2.0] #077 / 100% ★MAX!` | 和欧混植 `anchor="ls"`・記号欠落・トラッキング |
| `vertical_jp` | `「覚醒」、SSR―最強への道！` | 自前縦書きの句読点・長音/ダッシュ・括弧・英字回転 |

### 5-3. 本実装移行マップ（`ROADMAP.md` 3.5-0 〜 3.5-4 対応）
| 対象ファイル / 関数・箇所 | 適用内容 | 注意点 |
|---|---|---|
| `.gitignore`, `assets/fonts_custom/README.md`, `assets/fonts/LICENSE-*.txt` | `fonts_custom/*` Git 隔離、`LICENSE-OFL.txt` 追記・`LICENSE-cinecaption.txt` 分離、選定 OFL 書体格納 | `fonts_custom/` 空でも 100% フォールバックビルド |
| `scripts/_utils.py`, `scripts/_font_slots.py` (新設) | `CUSTOM_FONTS_DIR` 定数、`_audio_slots.py` 準拠の `fonts.json` スロット解決 | `CARD_*` 物理寸法は不変維持 |
| `card-config.js` (L37-43), `index.html` (L5-11, L172-184), `scene-result.html` (L5-11) | 4 軸直交スキーマ化、必要に応じ `--variables` へ `typoPreset`/`typoLayout`/`typoMirror` 同期 | 旧 `preset` 文字列形式との後方互換マップ維持 |
| `compositions/shared-base.css` (L1-33) | 新規 OFL 書体 `@font-face` と `--font-title` / `--font-sub` / `--font-mono` 追加 | 既存 `--font-display` / `--font-ui`（`scene-summon` HUD 等）は維持 |
| `scripts/render_typography.py` (`TYPO_PRESETS`, `FONT_NORM_FACTORS`, `get_font`, `render_humanized_line`, `render_multiline_block`, `apply_foil_and_grain_material`, `render_rarity_crest`, `render_attribute_plate`, `main`) | `CUTIN_STYLE` 分離、`norm` 補正、VF 軸対応キャッシュキー、`anchor="ls"`＋カテゴリ別フォールバック、縦書き・`align`・`tracking`、AA EDT＋直交装飾合成＋`halo_pad` 拡張、6 パレット＋トークン連動、`typo-manifest.js` 拡張 | `halo_pad` 拡張不足による太縁/影クリップ防止、`wobble=0` のカットイン非波及 |
| `scripts/render_material.py` (`generate_rainbow_foil_frame` L126-227) | `with_center_studs=True` 追加（4 辺中央鋲 `3x SSAA` + `shade_metal_relief` 焼込） | `with_filigree=False` 維持、既存バッジ `overlap=0×0` |
| `compositions/scene-result.html`, `scene-result.css`, `scene-result-setup.js` | `<filter id="typo-double-stroke">`, マイクロ装飾 DOM（`data-layout-ignore` 付与）, 4 系統＋`mirror` CSS（`#card-no-corner` 退避含む）, 動的 `#title-wipe-glint` & `clipPath -28px`, 10.85s 静止 GSAP タイムライン | `.star-item` 明背景時の視認性、`12.00s` 以降の文字/帯不動厳守 |

### 5-4. 自動 QA ＆ 視覚検証ゲート（Phase 3.5-4）
- **G1. ビルド・隔離・決定論**: `npm run build:assets` エラー 0、`git status` で `fonts_custom/` 追跡外確認、同一 `seed` 2 回連続実行で PNG/マニフェスト完全一致、カード設定変更時も **`typo_cutin_sub.png` / `typo_cutin_main.png` 不変**。
- **G2. 静的・ランタイム検査**: 全 5 レイアウト＋`mirror: true`＋`--variables '{"title":"強制FB"}'` で `npm run check` **0 errors**。
- **G3. 重点フレーム視覚確認**: `npx hyperframes snapshot --at 6.12,9.80,10.50,12.50,14.00`＋`read_file` で、カットイン不変（`6.12s`）、出現ワイプ時縁取り非クリップ（`9.80〜10.50s`）、顔保護・中央鋲非干渉・`#card-no-corner` 退避・破綻テスト 7 種・3 環境背景可読性・HTML フォールバック（`12.50/14.00s`）を目視確認。
- **G4. 本レンダリング ＆ 定量 QA**: `npm run render` → `npm run qa -- renders/ssr_gacha.mp4 --check-audio` で **`OVERALL: PASS`**（特に `Tail Fixed (12.7-15.3s) max_diff < 2.5` と `-15.5 <= LUFS <= -12.5` を確認）。

---

## 6. 再利用可能な検証スクリプト・成果物アーカイブ一覧

Phase A〜D で作成・実機検証済みのスクリプト・候補フォント・コンタクトシートは以下の作業ディレクトリに保存されている（リポジトリ外・参照/再利用可能）：

- **ルート**: `C:\Users\coffe\.gemini\antigravity\brain\fad55166-2fa3-48ad-8094-6bb3dc82e7ee\scratch\`
  - **Phase A（Pillow 実機検証・自前縦書きプロト）**:
    - `verify_pillow.py` / `verify_pillow_extra.py` — Pillow 12.3.0 / `raqm` / VF 軸 / `GSUB` / 実インク bbox 検証
    - `test_vertical_proto.py` / `vert_proto_YujiSyuku-Regular.png` / `vert_proto_TekitouPoem_Bold.png` — 自前 1 文字縦書きプロトタイプ
  - **Phase B（縁取り 4 手法 ＆ 装飾レシピ比較）**:
    - `phase_b/bench_outlines.py` → `phase_b/outline_4methods_compare.png`, `phase_b/outline_zoom_detail.png`
    - `phase_b/proto_styles.py` → `phase_b/style_recipes_compare.png`
  - **Phase C（配色マトリクス・k-means 評価・マイクロ装飾）**:
    - `phase_c/palette_matrix.py` → `phase_c/palette_matrix_preview.png`
    - `phase_c/test_kmeans_palette.py` → `phase_c/kmeans_palette_eval.png`
    - `phase_c/proto_ornaments.py` → `phase_c/micro_ornaments_preview.png`
  - **Phase D（破綻テスト・候補フォント・本番コンタクトシート生成）**:
    - `phase_d/stress_strings.py` — 破綻テスト文字列 7 ケース定義モジュール
    - `phase_d/fonts_candidates/` — Google Fonts 公式 `SIL OFL 1.1` 取得済み 14 書体
    - `phase_d/generate_contact_sheet.py` → `phase_d/contact_sheet_fonts_x_styles.png`, `phase_d/contact_sheet_stress_tests.png`, `phase_d/contact_sheet_card_mockups.png`
