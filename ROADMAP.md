# SSRGenerate ブラッシュアップ統合ロードマップ (`ROADMAP.md`)

> 「AIがポン出しで作ったようなルック」から脱却し、**最新3Dソシャゲ級の15秒SSRガチャ演出**へ引き上げるための統合改善計画です。  
> 複数視点（コード・生成動画・構成・音響）のレビューと実コード検証を統合し、確定した設計方針に沿って Phase 0 〜 Phase 5 に整理しています。

---

## 1. 現状診断：「AIポン出し感」の正体

現行の物理アセット生成エンジン群（`scripts/render_optics.py` / `scripts/render_typography.py` / `scripts/render_material.py`）と 15 秒の構成自体は高い完成度を持っています。しかし、以下の 3 点がボトルネックとなり、全体が「HTML/CSS で組んだデモ」に引き戻されています。

1. **質感と光の断絶（物理アセット × 生 CSS / Tailwind 初期色 × 通常合成光の混在）**
   - 物理発光魔法陣や金属箔タイポのすぐ隣に、素の CSS 球体・角丸ピルバッジ・ベタ塗りカットイン帯・単色四角の紙吹雪・Tailwind 標準パレット色（`#38bdf8`, `#fef08a`, `#f59e0b`, `#f472b6`, `#a855f7`）が混在している。
   - 多くの発光要素で `mix-blend-mode` が未指定（通常合成）のため、光が加算されず「半透明の帯」や「濁ったベージュの靄」に見えている。
2. **確定バグと演出テンポの均質さ・引き算不足**
   - 3D 回転中に裏面が表示されず表面が左右反転するバグや、着地衝撃波・紙吹雪が被写体の顔に被る Z 順バグが存在する。
   - 昇格直前の「溜め（暗転・静寂の真空の間）」がなく、5.2s 付近で全要素が同時に主張しているうえ、3D 回転の減速と着地ショックのフレームが噛み合っていない。
3. **音響と映像の時代ギャップ**
   - 映像の質感に対し、固定ローパス鋸波ブラス＋6 タップ単純ディレイの SE が 90 年代シンセ寄りに留まっている。

---

## 2. 確定した設計方針（Design Principles & Scope）

本ロードマップでは、以下の方針を前提として設計・実装を進めます。

| 項目 | 確定方針 |
| :--- | :--- |
| **1. 終盤 12.0s〜15.0s の仕様** | **「レイアウト固定・光だけ微動」** へアップデートする。カード・文字・星などの配置は 12.0s で完全固定しつつ、ホロ光沢の微細なシマー・スパークルの位相差瞬き・背景ハローの静かな呼吸のみを 15.0s まで動かす。（※`AGENTS.md` の該当仕様記述の更新は **Phase 1 実装時** に実施する） |
| **2. 全体のルック方向性** | **最新3Dソシャゲ寄り**。3D 床パース魔法陣、多面体クリスタル光学オーブ、空間カメラワーク、アナモルフィック光閃、角度連動で立体反射するホログラムカードを目指す。 |
| **3. サウンド方針（標準 / 任意拡張）** | **標準（OSS 配布デフォルト）**: 完全プロシージャル（Python `numpy` / `scipy` のみ）を維持しつつ、90 年代シンセブラスを脱却し**現代ソシャゲ音像**（重厚なサブベース＆ティンパニ打撃＋金属クラッシュシンバル残響＋シマーパッド＋高精細クリスタル／ハープアルペジオ＋`scipy.signal.fftconvolve` によるコンボリューションリバーブ）へ刷新する。<br>**任意拡張（ローカル利用オプション）**: ユーザー所蔵の効果音ライブラリ（ワンショット WAV 等）から選定してミックスする拡張枠も検討する。OSS 配布時のライセンス安全性を確保するため、外部音源は `.gitignore` 対象のローカル専用フォルダ（例: `assets/se_custom/`）へ分離し、未配置時は完全プロシージャル合成へ自動フォールバックする設計とする。 |
| **4. スコープ外（やらないこと）** | **AI 被写体セグメンテーション／顔認識マスクは導入しない**。現行の軽量・オフライン・完全決定論構成（Python `numpy`/`scipy`/`Pillow` + GSAP）を維持し、顔被りは Z 順調整・軌道設計・中央減衰マスクで解決する。 |
| **5. 横画像・横動画対応（Phase 5）** | 風景・周辺情報込みでカード化したい横写真向けに、**動画キャンバス自体を 16:9（1920×1080）にした横型 SSR カード演出（パターン B）** をサポートする。縦（9:16）での演出・音響・運用性のこだわりを Phase 0〜4 で完成させた後、最後尾の Phase 5 として実装する。 |

### 不変の原則（絶対ルール）
- **総尺**: **16.0 秒**（冒頭 `0.5s` 無音・背景フェードイン ＋ 本編 `15.0s` ＋ 末尾 `0.5s` 無音・黒フェードアウト）を厳守する。
- **写真保護**: 入力写真は 100% クリアなまま一切汚さない（写真自体へ処理を加える必要が生じた場合は `/media-use` の `media-treatments` 規範を遵守する）。
- **決定論的レンダリング**: `Math.random()`・`Date.now()`・外部ネットワーク取得を禁止し、シード付き疑似乱数と登録済み GSAP タイムラインのみで描画する。

---

## 3. フェーズ全体マップ

| Phase | テーマ | 狙い | 主な対象ファイル | 優先度 |
| :--- | :--- | :--- | :--- | :---: |
| **Phase 0** | 確定バグ修正 ＆ 光・色基盤の正常化 | 3D破綻・顔被り・濁った光の解消と色・階調の統一 | `index.html`, `compositions/scene-result.*`, `compositions/scene-summon.html`, `scripts/_utils.py`, `package.json` | ★★★ 完了 |
| **Phase 1** | リザルト画面の「脱Web UI化」＆ 光の微動呼吸 | バッジ・SVG・粒子・ホロ反射を最新3Dソシャゲ級へ刷新 | `compositions/scene-result.*`, `compositions/scene-result-setup.js`, `scripts/render_typography.py`, `scripts/render_material.py`, `AGENTS.md` | ★★★ 完了 |
| **Phase 2A** | 取りこぼし修正・タイムライン骨格確定・定量QA | スペキュラはみ出し/曇り膜/光柱修正・昇格語彙差別化・真空の間・着地同期・`qa_video.py` | `index.html`, `compositions/scene-summon.html`, `compositions/scene-result.*`, `scripts/generate_se.py`, `scripts/qa_video.py`, `package.json` | ★★★ 完了 |
| **Phase 2B** | 召喚〜昇格の「脱CSS ＆ 3D空間光学アセット化」＋ 天蓋・空域演出 | カットイン脱ベタ帯・冒頭点火・3D床魔法陣・クリスタルオーブ・不規則ゴッドレイ・天蓋アストロラーベ・流体ウィスプ・星屑 | `scripts/render_optics.py`, `scripts/render_typography.py`, `compositions/scene-summon.*`, `compositions/scene-summon-setup.js`, `compositions/scene-result.*` | ★★★ 完了 |
| **Phase 2.5** | フロントエンド共通化 ＆ アセット生成高速化・ストレージ最適化 | `shared-base.css`/`shared-utils.js`集約、`_optics_core.py`新設・EDT高速化・並列ビルド（41s→7.5s）、ストレージ整理・新方式定量QA検証 | `compositions/shared-*`, `scripts/_optics_core.py`, `scripts/_utils.py`, `scripts/build_all.py`, `scripts/render_*`, `package.json` | ★★★ 完了 |
| **Phase 3** | 音響の「現代ソシャゲ音像化」＆ 映像マイクロポリッシュ（レビュー反映完遂） | 現代ソシャゲ音像刷新・`fftconvolve`残響・真空ダッキング・14.8s余韻・`-14 LUFS`統一・ローカルカスタムSEスロット基盤（`assets/se_custom/`）＋ 映像面7大改善を完了 | `scripts/_audio_dsp.py`, `scripts/_audio_slots.py`, `scripts/generate_se.py`, `assets/se_custom/README.md`, `.gitignore`, `compositions/scene-*`, `scripts/render_*` | ★★☆ 完了 |
| **Phase 3.5** | カードタイポグラフィ点検・刷新（可変フォント・縁取り＆カラー・非対称レイアウト・ヘッダー共通座布団） | 昇格カットイン完全分離・中央配置のうえ、2大標準プリセット（`royal-foil` / `cute-pastel`）・4軸直交スキーマ・ヘッダー共通座布団ギミック（左A×右C）・attributeBadge/Label 分割・出力命名自動化を完遂 | `assets/fonts/*`, `assets/fonts_custom/`, `card-config.js`, `scripts/_font_slots.py`, `scripts/_typo_modern.py`, `scripts/render_typography.py`, `scripts/render_material.py`, `scripts/render_video.mjs`, `compositions/shared-base.css`, `compositions/scene-summon.*`, `compositions/scene-result.*` | ★★☆ 完了 |
| **Phase 4** | 運用性・量産性強化 ＆ 5軸/複数素材検証 | 任意テキスト箔同期・オートレイアウト ＋ 5品質評価軸・不要要素削減・多様な素材検証 | `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js` | ★☆☆ 仕上げ |
| **Phase 5** | 横動画（16:9）× 横型カード対応 | 風景・周辺情報込みの横写真向け 1920×1080 ワイド演出モード追加（詳細設計: [`LANDSCAPE_PLAN.md`](./LANDSCAPE_PLAN.md)） | `card-config.js`, `index.html`, `compositions/*`, `scripts/_utils.py`, `scripts/render_material.py`, `scripts/render_typography.py`, `package.json` | ★☆☆ 拡張 |

---

## 4. Phase 0：確定バグ修正 ＆ 光・色基盤の正常化（最優先）

全シーンの破綻と「光の濁り」を最初に解消する基盤フェーズです。

- [x] **0-1. 3Dカード裏面フラット化バグ修正**
  - **対象**: `compositions/scene-result.css` (`#ssr-card`, `.card-face`, `.card-front`, `.card-back`), `compositions/scene-result.html` (`#ssr-card` 回転アニメ・`#card-back-face` 回避コード)
  - **課題**: `#ssr-card` 自身を `opacity: 0 → 1` でアニメーションさせているため（CSS 仕様上、`opacity < 1` や `overflow: hidden` / `isolation: isolate` 等の組み合わせにより `transform-style: preserve-3d` が 2D 平坦化される）、回転中に `backface-visibility: hidden` が効かず表面の写真が左右反転して見えてしまっている。
  - **対策**: `opacity` 制御を `#ssr-card` から外側ラッパー（`#card-stage` 等）へ分離し、`.card-front` と `.card-back` に明確な Z 分離（`translateZ(1px)` / `rotateY(180deg) translateZ(1px)`）を与えて裏面が正常に描画されるようにし、強制非表示の `#card-back-face` 処理を整理する。
- [x] **0-2. 顔被りZ順の修正**
  - **対象**: `compositions/scene-result.css` (`#landing-shockwave` の `z-index: 38`, `#card-stage` の `z-index: 30`, `#celebration-layer` の `z-index: 40`)
  - **課題**: カード着地時の太いリング（`#landing-shockwave`）がカード前面にあり、9.35s 前後で被写体の顔の上に被っている。
  - **対策**: `#landing-shockwave` をカード背面（`z-index < 30`）へ移動し、顔の上にリングが乗らない構成にする。
- [x] **0-3. 発光合成モードの統一 ＆ ホワイトアウト再設計**
  - **対象**: `index.html` (`#flash-layer`), `compositions/scene-summon.html` (`#light-pillar`, `.bg-aura`, `#summon-godrays`), `compositions/scene-result.css` (`#result-rays`, `#result-halo`)
  - **課題**: 発光レイヤーが通常合成で重ねられており、光柱が「灰色の帯」に、`#flash-layer` の `#fef08a` 終端グラデが「濁ったベージュの靄」になっている。
  - **対策**: 発光要素に `mix-blend-mode: screen` / `plus-lighter` を適用する。`#flash-layer` は黄色残光を廃し、純白を 2〜4 フレーム保持したのちクリーンに抜ける光学露出フラッシュへ再設計する。
- [x] **0-4. 脱Tailwind初期色パレット刷新 ＆ 決定論グレイン（バンディング解消）**
  - **対象**: `compositions/scene-summon.html`, `compositions/scene-result.css`, `scripts/_utils.py`, `scripts/render_optics.py`, `scripts/render_material.py`, `package.json`
  - **課題**: `#38bdf8` `#fef08a` `#f59e0b` `#f472b6` `#a855f7` など Tailwind 標準パレットそのままの配色が既製品感を強め、また暗部グロー周辺に同心円状のバンディングが生じている。
  - **対策**: 金は「白 → シャンパン → 琥珀 → 暗褐」の明暗階調を持つパレットへ、虹は薄膜干渉寄りの連続スペクトルへ統一する。暗い背景・エフェクト層（写真内窓は除外）へ決定論シードの極薄グレイン（`scripts/_utils.py` のシボ生成等を応用）を乗せてバンディングと素材寄せ集め感を抑え、MP4 書き出し時のビットレート設定も見直す。

### Phase 0 完了基準（DoD）
- `7.8s〜8.0s` の 3D 回転中に裏面エンブレムが破綻なく表示され、写真の左右反転が起きないこと。
- `9.35s` で着地リングが被写体の顔に被らないこと。
- `7.1s〜7.5s` のホワイトアウトに黄色・ベージュの濁りがなく、暗部グローのバンディングが目立たないこと。

---

## 5. Phase 1：リザルト画面の「脱Web UI化」＆ 空間クリスタル演出・光の微動呼吸

15 秒視聴後の印象を決定づけるリザルト画面（`6.9s〜15.0s`）を、Web ページ部品から最新 3D ソシャゲのプレミアムカード演出へ引き上げます。

- [x] **1-1. `#ssr-emblem` と `#attr-badge` の脱Web UIパーツ化**
  - **対象**: `compositions/scene-result.css`, `compositions/scene-result.html`, `compositions/scene-result-setup.js`, `scripts/render_typography.py`, `scripts/render_material.py`
  - **課題**: `#ssr-emblem` が半透明紺の角丸ボックス＋単色黄色枠に閉じ込められており、`#attr-badge` は `border-radius: 999px` のピル型＋素 HTML テキストのため、下部の物理箔タイポから浮いている。
  - **対策**: `#ssr-emblem` の角丸ボックスを廃止し、厚み（ベベル／押し出し）を持たせた箔タイポ直置き＋背後の斜めカット暗色座布団／クリスタル・金属クレストへ刷新する。`#attr-badge` も `render_typography.py` の生成対象に統合し、鋭角な金属・クリスタル刻印タグへ置き換える。
- [x] **1-2. 四隅装飾・背景リング・カード裏面の素SVG脱却**
  - **対象**: `compositions/scene-result.html`, `compositions/scene-result.css`, `scripts/render_optics.py`, `scripts/render_material.py`
  - **対策**: `.corner-ornament`, `#result-bg-ring`, `#card-back-face` の均一なベクター SVG を廃止し、物理光学発光アセットおよび金属ヘアライン／クリスタル紋章アセットへ差し替える。
- [x] **1-3. カード構図の余白設計（空間感の確保）**
  - **対象**: `compositions/scene-result.css` (`#card-stage`), `scripts/render_material.py`
  - **課題**: カード（`940×1660`）が画面の約 87% を占めており、背後の放射光・ハロー・光学リングが隠れて空間の奥行きが見えにくい。
  - **対策**: カード占有率を画面の 80〜84% 程度へ調整し、背景の 3D 空間演出が額縁として映える余白を確保する。
- [x] **1-4. スパークル疎密クラスター化 ＆ 3D箔片・ボケ光粒への置換**
  - **対象**: `compositions/scene-result-setup.js` (`rimAnchors`, `confettiData`), `compositions/scene-result.css`, `compositions/scene-result.html`
  - **課題**: 周囲スパークル 16 個がほぼ等間隔・似たサイズで並び機械的。`.confetti-bit` は単色ベタ塗り長方形の 2D 回転で安っぽい。
  - **対策**: スパークルは**極端なサイズ差（特大 2〜3 個・中 4〜5 個・極小群）と対角線上の疎密クラスター配置**に変更する。紙吹雪は単色四角 `div` を廃止し、`rotateX` / `rotateY` で明滅しながら舞う金箔・プリズム結晶片および遠近感のあるボケ光粒（Bokeh）へ置換し、中央の顔エリアを通過しない軌道へ制御する。
- [x] **1-5. ホログラム反射の立体化（回転中スペキュラ＋写真保護マスク）**
  - **対象**: `compositions/scene-result.css` (`#holo-sweep-1`, `#holo-sweep-2`, `#holo-static-sheen`), `compositions/scene-result.html`
  - **課題**: 回転中（`7.8s〜9.1s`）に表面のスペキュラ反射がなく、着地後の `#holo-sweep` は白い帯がそのまま写真中央を横切って被写体の顔を白く霞ませている。
  - **対策**: 3D 回転中の角度変化に同期した鋭いスペキュラ反射を追加する。着地後スイープはプリズム／ダイヤ柄テクスチャを仕込み、写真中央部は弱く減衰させつつ金属フレームと箔文字エッジで強くキラッと反射するマスク処理へ改修する。
- [x] **1-6. 12.0s〜15.0s の「レイアウト固定・光のみ微動」実装 ＆ `AGENTS.md` 更新**
  - **対象**: `compositions/scene-result.html`, `AGENTS.md`
  - **対策**: 12.0s 以降はカード・文字・星の位置とサイズを完全固定したまま、ごく控えめなホロ光沢シマー・スパークルの位相差瞬き・背景ハローの静かな呼吸を 15.0s まで維持する。あわせて `AGENTS.md` の「12.0s〜15.0s（リザルト画面固定）」仕様記述を本方針へ更新する。

### Phase 1 完了基準（DoD）
- リザルト画面に角丸ピルや素のベクター線などの Web UI 感が残っていないこと。
- 入力写真が 100% クリアで、ホロスイープや粒子で顔が汚れたり霞んだりしないこと。
- `12.0s〜15.0s` でレイアウトは不動のまま、光沢・スパークル・背景光のみが上品に呼吸していること。

---

## 6. Phase 2A：取りこぼしバグ修正 ＆ 15秒タイムライン骨格確定 ＆ 定量QA（Step 1）

物理アセット増産に入る前に、Phase 0/1 で残った映像破綻の取りこぼしを塞ぎ、15 秒の因果・緩急・着地同期の骨格と自動定量 QA 基盤を確定させる最優先フェーズです。

- [x] **2A-1. 回転スペキュラはみ出し修正 ＆ 露出役割分離・光柱先行修正**
  - **対象**: `compositions/scene-result.css`, `compositions/scene-result.html`, `index.html`, `compositions/scene-summon.html`
  - **課題**: `.card-front` にクリップがないため `8.3s〜8.9s` で `#spin-spec-front` がカード外下辺へはみ出している。また `#flash-layer` が `screen`＋全面白で `3.8s` 金フラッシュがグレー曇り膜になり、`7.1s` 白飛びも抜けが遅く霧状に残る。`#light-pillar` も上下減衰のない灰色縦帯に見えている。
  - **対策**: `preserve-3d` を壊さない内側クリップラッパー `#spin-spec-front-clip` を追加してスペキュラをカード形状へ厳密クリップする。`#flash-layer` は `7.0s` 専用の通常合成純白ホワイトアウト（急峻 `expo.in` → 3F保持 → `expo.out` 抜け）へ専念させ、`3.8s` は放射金閃光 (`#flash-gold`)、`5.2s` は中心バースト＋水平アナモルフィック閃光 (`#flash-rainbow-core` / `#flash-rainbow-streak`) へ分離する。`#light-pillar` は上下フェードマスク＋細白芯＋着色グロー（金→虹遷移）へ先行改修する。
- [x] **2A-2. 演出の因果チェーン ＆ 昇格語彙の差別化（5.10〜5.18s 真空の間）**
  - **対象**: `compositions/scene-summon.html`
  - **課題**: 青・金・虹が毎回同じレシピ（脈動＋ボーダー衝撃波＋減衰なし矩形 x/y シェイク）を反復し、`5.2s` 直前も周囲が明るいまま爆発するためコントラストが弱い。
  - **対策**: `#summon-camera` を導入し、矩形 x/y シェイクを廃止。青＝予兆脈動＋明滅＋吸い込み収縮（大衝撃波・シェイクなし）、金＝放射閃光＋減衰ズームパンチ、虹直前 `5.10s〜5.18s`＝**真空の間**（`#vacuum-dimmer` と周囲オーラ/魔法陣の減光で闇へ落とし、オーブ収縮と亀裂白芯だけ残す）、`5.20s`＝水平光閃＋強減衰ズームパンチで圧倒的解放へ差別化する。
- [x] **2A-3. 3Dカード回転→着地の完全同期 ＆ SE仮同期**
  - **対象**: `compositions/scene-result.html`, `compositions/scene-result-setup.js`, `scripts/generate_se.py`
  - **課題**: `7.18s〜9.33s` の `power3.out` が終盤 `0.8s` 近くほぼ正面で停滞ダレを起こし、`9.32s` 着地ショックや回転スウッシュ音と噛み合っていない。
  - **対策**: 飛び出し高速回転→裏面タメ (`-195°`, `7.92s`)→加速反転→`8.68s` 正面ビタ止め（`back.out(2.6)`）の 3 段階カーブへ刷新し、着地フレームと背面衝撃波・減衰ズームパンチ・色収差・`#ssr-emblem` 打刻・パーティクル発生・仮同期 SE を 1 フレーム単位で同期させる（`12.0s` 以降はレイアウト完全固定を維持）。
- [x] **2A-4. 自動定量QAスクリプト `scripts/qa_video.py` 導入**
  - **対象**: `scripts/qa_video.py`, `package.json`
  - **対策**: `ffmpeg` + `numpy` でグレー曇り膜フレーム数・真空の間輝度比・着地直前ダレ秒数・終盤レイアウト固定＆微動・音声 LUFS/末尾 RMS を自動計測し、Exit Code で判定する `npm run qa` を整備する。

### Phase 2A 定量完了基準（DoD）
- グレー曇り膜フレーム（`mean > 150` かつ `p95 - p5 < 70` かつ `mean < 245`）が全編で **2 フレーム以下**。
- 真空の間（`5.10s〜5.18s`）の最小平均輝度が、`4.75s〜4.85s` 基準平均輝度の **50% 未満**。
- 着地直前 `0.35s` 窓（`8.33s〜8.68s`）内の低動き（`diff < 2.5`）連続ダレが **0.20s 以下** かつ着地フレーム（`8.68s`）と衝撃波・色収差・SSR打刻が同期していること。
- `8.58s` 付近で `#spin-spec-front` がカード外へはみ出さず、`7.85s〜8.05s` で裏面エンブレムが鮮明に視認できること。

---

## 6B. Phase 2B：召喚〜昇格フェーズの「脱CSS ＆ 3D空間光学アセット化」（Step 2）

確定した 15 秒骨格に対して、前半 7 秒（`0.0s〜7.0s`）の見た目の「Web デモ感」を最新 3D ソシャゲ水準へ一気に引き上げます（レバレッジの高い順に着手）。

- [x] **2B-1. カットインの脱ベタ帯 ＆ 0.0s冒頭点火フック・業務UI整理**
  - **対象**: `compositions/scene-summon.html`, `compositions/scene-summon.css` (`#cutin-band`, `#summon-caption`, `#ignition-spark`), `scripts/render_typography.py` (`cutinSub`, `cutinMain`), `scripts/render_optics.py` (`opt_cutin_flare.png`, `opt_cutin_speedlines.png`)
  - **課題**: `#cutin-band` の上下 6px 黄色線＋ベタ塗りネオン帯が最も HTML/CSS 感を出し、文字も帯に対して小さい。また 0.0s から魔法陣が既に出ており、「召喚中...」が業務 UI 風。
  - **対策**: `#cutin-band` の上下ボーダーとベタ塗りを廃止し、画面一瞬引き締め＋鋭い水平アナモルフィック・レンズフレア＋スピードライン＋箔ノイズ上を大判の箔タイポが抜ける構成へ刷新する（過剰な `★` 等の記号を整理）。0.0s には暗闇からの光点点火・魔法陣描画フックを追加し、`#summon-status` は廃止または上下端の極小シネマティック英字装飾へ移す。
- [x] **2B-2. 3D床パース魔法陣 ＆ 空間カメラワーク**
  - **対象**: `scripts/render_optics.py` (`build_magic_circle_masks`), `compositions/scene-summon.html`, `compositions/scene-summon.css` (`#magic-circle-perspective`, `#magic-circle-wrap`)
  - **対策**: 魔法陣マスクにルーン帯・目盛り・太細二重線・頂点ノードを追加して情報階層を強化する。`#magic-circle-wrap` に `perspective` + `rotateX` による 3D 床パースを導入し、青→金→虹の昇格に合わせてカメラが奥から寄る・煽る立体カメラワークを与える。
- [x] **2B-3. 多面体クリスタルオーブ ＆ 有機的分岐亀裂の物理アセット化**
  - **対象**: `scripts/render_optics.py` (`build_orb_cracks_mask`, 新規オーブ生成関数), `compositions/scene-summon.html`, `compositions/scene-summon.css` (`#orb-blue`, `#orb-gold`, `#orb-rainbow`, `#orb-cracks`)
  - **課題**: 単層 CSS 球や円グラフ状の `conic-gradient` 虹オーブが周囲の物理魔法陣から浮いている。亀裂も直線的。
  - **対策**: `render_optics.py` で「中心の白飛びエネルギー核＋逆回転する内部クリスタル多面体ファセット／プラズマ渦＋外縁フレネル光輪」の多層透過 PNG を生成して差し替える。亀裂は分岐・テーパー付きへ改修し、隙間から虹色の光が漏れる表現を強める。
- [x] **2B-4. ゴッドレイ（前後半両方）・縦ストリーク光柱・光学衝撃波の物理アセット化**
  - **対象**: `scripts/render_optics.py`, `compositions/scene-summon.html`, `compositions/scene-summon.css`, `compositions/scene-result.html`, `compositions/scene-result.css`
  - **課題**: `repeating-conic-gradient` による均等プロペラ放射線（前半 `#summon-godrays` と後半 `#result-rays` の両方）、CSS グラデの光柱 `#light-pillar`、太い単色ボーダーの `.shockwave` / `#landing-shockwave` がデジタル感を生んでいる。
  - **対策**: `idea.md` の `rave_lasers.hlsl` 式から太細不規則なゴッドレイ PNG を 2 枚生成し、**前半 `#summon-godrays` と後半 `#result-rays` の両方**を異速・逆回転の物理放射光へ差し替える。`#light-pillar` は `aurora_claude.hlsl` 式の縦ストリーク 2 層光学アセットへ、衝撃波は中心から外へ滲む光学リング＋微細光粒の飛散へ置換する。
- [x] **2B-5. 画面上部・天蓋空域のプレミアム演出（Celestial Gate / Fluid Wisp / Sky Bolts / Parallax Shards / Centered HUD）**
  - **対象**: `scripts/render_optics.py`, `compositions/scene-summon.html`, `compositions/scene-summon.css`, `compositions/scene-summon-setup.js`
  - **課題**: 床面魔法陣と中央オーブの強化に伴い、画面上部（空域）の空間的密度がやや寂しく、演出全体の縦スケール感が不足していた。また、直進的・固まり感のある流星や、下部が寂しくなる浮遊星屑の配置バランス、虹昇格後の星屑ノイズ感が課題となっていた。
  - **対策**:
    1. **3D 天蓋アストロラーベゲート (`opt_gate_*`)**: 天井に仰角パース（`rotateX: -68°〜-44°`）の二重同心環ゲートを配置し、青・金・虹の昇格と同期して回転・拡大・色展開。
    2. **流体ウィスプ流星 (`opt_meteor_blue.png`)**: 固まりの直進落下を廃止し、3 本の滑らかな正弦波スプライン軌道（計 54 ノード＋54 追従ダスト）で中央オーブへ吸い込まれる有機的流体軌道へ刷新。
    3. **天頂雷撃 (`opt_bolt_gold.png`, `opt_bolt_prism.png`)**: 金・虹昇格トリガー瞬間に天蓋からオーブへ垂直に貫通する有機的分岐ボルトを投下。
    4. **全域パララックス浮遊星屑 ＆ 昇格波動**: `y = 100〜1860px` 全域を漂う遠近二層の多面体クリスタル片＋星を配置。金・虹昇格時には床面から上方へ立ち上る 20 粒のバースト波を追加。虹昇格後（`5.20s+`）は星屑の不透明度を抑制（`0.42 / 0.30`）して主役（カード・オーブ・カットイン）を明瞭化。
    5. **天蓋連動 1.3 倍 昇格 HUD**: 天蓋アストロラーベの中心孔に正確にセンタリングした 1.3 倍サイズの上端 HUD（`RESONANCE` → `ELEVATION` → `OVERDRIVE`）を実装し、下端不要キャプションを完全撤去。

### Phase 2B 完了基準（DoD）
- `0.0s〜7.0s` に素 CSS パーツ（単層球・等間隔放射線・ボーダーリング・上下枠線ベタ帯）が残っていないこと、および後半 `#result-rays` からも等間隔プロペラ放射線が消えていること。
- 3D 床パース魔法陣、クリスタルオーブ、天蓋アストロラーベゲート、流体ウィスプ、浮遊星屑により空間の全域（上下・奥行き）に圧倒的な立体感・空気感が満ちていること。
- 虹昇格後の画面整理とカットイン箔タイポの視認性が保たれていること。

---

## 6.5. Phase 2.5：フロントエンド共通化 ＆ アセット生成パイプライン高速化・ストレージ最適化

Phase 2 までの急速な機能追加によって生じたコードの重複、生成スクリプトの実行コスト（40秒超）、および大容量検証動画によるストレージ肥大化を解消し、プロジェクト全体の保守性と開発サイクル速度を劇的に向上させるリファクタリングを実施。

- [x] **2.5-1. フロントエンド共通基盤の抽出 ＆ 設定値フォールバック同期**
  - **対象**: `compositions/shared-base.css` (新設), `compositions/shared-utils.js` (新設), `compositions/scene-summon.*`, `compositions/scene-result.*`
  - **成果**:
    - フォント `@font-face`、CSSカスタムプロパティ（`--gold-*`, `--prism-*` 等の共通色・カード寸法）、`.clip`, `.film-grain-overlay` 等の共通スタイルを `shared-base.css` へ集約。
    - 決定論乱数生成器（`createRng` / Mulberry32）、相対パス解決（`resolveAssetPath`）、設定値優先フォールバック（`pickConfigValue`）、着地RGB色収差（`addChromaShock`）を `shared-utils.js` に共通モジュール化。
    - `scene-result` / `scene-summon` の HTML/CSS/JS 全体で 2 スペースインデント統一、重複コードの排除、および初期フォールバック値を `card-config.js` に完全一致同期。
    - `npm run check`（lint + runtime + layout + motion + contrast）にて **0 errors, 0 warnings** を確認。
- [x] **2.5-2. 物理光学コア分離 ＆ Pythonアセット生成エンジンの高速化・並列化**
  - **対象**: `scripts/_optics_core.py` (新設), `scripts/_utils.py`, `scripts/build_all.py` (新設), `scripts/render_optics.py`, `scripts/render_material.py`, `scripts/render_typography.py`, `package.json`
  - **成果**:
    - `_optics_core.py` に 6 段階物理光学発光コア（H&D分光・FFT異方性PSFガウスぼかし・FBMノイズ・マルチオクターブ合成）を抽出し、`render_optics.py` を軽量化。
    - ピュア Python の `approx_inner_distance` を `scipy.ndimage.distance_transform_edt`（C最適化）へ置き換え、距離変換処理を数十倍高速化。
    - Pillow の全探索最適化（`optimize=True`）が最大のボトルネックであったため、`_utils.save_png` で `compress_level=6`（標準高速圧縮）へ一本化。フィルムグレイン解像度を `540x960`（1/2）に最適化し画質を損なわずにファイルサイズを 1.6MB → 403KB へ削減。
    - `render_optics.py` 内を `ThreadPoolExecutor` によるマルチスレッド生成・保存へ移行し、さらに `build_all.py`（新設）にて 4 スクリプト（typo, optics, material, se）を `ProcessPoolExecutor` でマルチプロセス並列実行するアーキテクチャへ刷新。
    - `npm run build:assets` の所要時間を **41.09秒 → 7.51秒（約5.5倍高速化）** へ短縮。
- [x] **2.5-3. ストレージ整理 ＆ .gitignore 強化**
  - **成果**: `renders/` 配下の旧検証用 MP4 9本（約 325MB）および未追跡ファイル `repomix-output.xml` を安全に削除し、`.gitignore` に `repomix-output.xml` を追加。
- [x] **2.5-4. 新方式レンダリング ＆ 定量QA検証（旧MP4との比較）**
  - **成果**: `npx hyperframes render` により `renders/ssr_gacha_refactored.mp4`（15.0秒 / 450フレーム）を出力し、`scripts/qa_video.py` による自動合否判定を実施。
  - **映像基準全項目PASS**:
    - グレー曇り膜フレーム: **2枚**（許容 <=2枚 PASS ※旧MP4は8枚でFAIL）
    - 真空の間（5.10s〜5.18s）の最小輝度: **9.9%**（許容 <50% PASS ※旧MP4は99.9%でFAIL）
    - 着地前ダレ連続時間: **0.00s**（許容 <=0.20s PASS）
    - 終盤レイアウト固定（12.0s〜15.0s）: 最大差分 **0.693**（許容 <2.5 PASS）
    - 終盤光微動（12.0s〜15.0s）: 微動ピクセル比率 **4.31%**（許容 >0.1% PASS）
  - **音声課題の確認**: 統合ラウドネスが `-12.4 LUFS`（目標 -15.5〜-12.5 に対し 0.1dB 超過）、14.0秒以降がデジタル無音（RMS -120dB）となっている点を確認。これらを次フェーズ（Phase 3）の必須要件として引き継ぎ。

---

## 7. Phase 3：サウンドの「現代ソシャゲ音像化」＆ 後半マイクロポリッシュ4点

映像側の秒数が完全に固まった段階で、音響を製品級へ刷新し、あわせて縦版（9:16）後半リザルトの最後の微調整 4 点を仕上げます。

- [x] **3-1. ファンファーレ音色の刷新（現代ソシャゲ音像・完全プロシージャル）**
  - **対象**: `scripts/_audio_dsp.py` (新設), `scripts/generate_se.py`
  - **成果**: 90年代固定 LPF 鋸波ブラスを廃止し、ステレオ・シマーストリングスパッド＋重厚サブドロップ＆ティンパニ打撃＋金属クラッシュシンバル＋チェレスタ＆物理風ハープ撥弦＋動的ローパス＆アタックピッチ滑り込み付きモダンホーン（補助）へ刷新。
- [x] **3-2. コンボリューションリバーブ化**
  - **対象**: `scripts/_audio_dsp.py` (`make_hall_ir`, `convolution_reverb`)
  - **成果**: `scipy.signal.fftconvolve` による高密度ホール・インパルス応答（初期反射＋空気吸収減衰＋シマー残響＋Wet 180Hz HPF）へ置換し、ディレイのパタパタ感を解消。
- [x] **3-3. 無音ブレーク同期・末尾余韻・ラウドネス適正化**
  - **対象**: `scripts/generate_se.py`, `scripts/_audio_dsp.py` (`measure_lufs`, `soft_limit`)
  - **成果**: コンボリューションリバーブ後に真空の間（`5.06s〜5.18s`）の急峻ダッキングを適用し、終盤 `12.0s〜14.8s`（全体 `12.5s〜15.3s`）へ光呼吸に寄り添う Cmaj9 シマー余韻＆外枠グレア音を配置。さらに再生冒頭の音切れ・末尾のぶつ切りを防ぐため前後 `0.5s` 無音＆映像フェードイン／アウト余白（総尺 16.0s）を追加。BS.1770-4 準拠 3トラック統合マスタリング＋4x TruePeak 対応ソフトリミッターにより、実測 QA（`renders/ssr_gacha_16s_meteor_v2.mp4`）で **LUFS=-14.1（基準 -15.5〜-12.5 PASS）・TruePeak=-2.3dBFS・Head(0-0.5s)=-120.0dB・Tail(14.5-15.0s)=-38.6dB・Pad(15.5-16.0s)=-120.0dB・Edge Padding(0.0/0.0)** を達成。
- [x] **3-4. （任意拡張）ユーザー所蔵SEライブラリ併用オプションの実装**
  - **対象**: `scripts/_audio_slots.py` (新設), `scripts/generate_se.py`, `assets/se_custom/README.md` (新設), `.gitignore`
  - **成果**: `.gitignore` で完全隔離された `assets/se_custom/` に全11スロット（`ignition`, `heartbeat`, `gold_hit`, `orb_crack`, `rainbow_shatter`, `cutin_whoosh`, `riser`, `whiteout_impact`, `card_whoosh`, `card_land`, `star_chime`）と `slots.json` による `layer` / `replace` 制御を実装。8/16/24/32-bit・IEEE float・任意SR・モノラル自動変換、自動ピッチ展開、リバーブ・LUFS 一体適用に対応し、未配置時は 100% プロシージャルへ自動フォールバック。
- [x] **3-5. 映像マイクロポリッシュ完遂 ＆ 外部レビュー指摘全項目クリア（縦版 9:16 映像完成）**
  - **対象**: `scripts/render_optics.py`, `scripts/render_typography.py`, `scripts/render_material.py`, `scripts/_utils.py`, `compositions/scene-summon.*`, `compositions/scene-summon-setup.js`, `compositions/scene-result.*`, `compositions/scene-result-setup.js`
  - **成果**:
    1. **表面四隅フィリグリー撤去（裏面は 4 隅維持）**: `mat_rainbow_frame.png`（表面）から四隅の L 字フィリグリーを外して左上 `#ssr-emblem`・右上 `#attr-badge` との干渉を完全解消。裏面（`mat_card_back.png`）には 4 隅フィリグリーを移植・維持。
    2. **テキスト＆星出現の脱 Web フェードイン**: 5 つ星点灯時の白閃光フラッシュ（`.star-flare`）を追加し、肩書・タイトル（光走査ライン＋着地スケール）・フレーバー・カード番号を左→右の光走査ワイプ（`clip-path` 単位整合）へ刷新。
    3. **右端スパークル見切れ解消 ＆ ホロスイープ白幕感軽減**: スパークルクラスター座標を内側へ寄せ、`#holo-sweep-1/-2` の帯幅を半減（`190px`）して鋭いプリズム閃光へ調整。
    4. **13.2s 外枠リムグレア追加**: `12.0s〜15.0s` のレイアウト完全固定を保ったまま、`12.95s〜13.85s` でカード外枠リム上を細い高輝度グレア `#frame-rim-glare` が走る演出を追加。
    5. **冒頭ウィスプの RGB 三原色 3D 円錐三重螺旋 ＆ 専用星核ヘッド**: 冒頭 3 条のウィスプを青・赤・緑の三原色パレットへ分離し、120° 位相差の 3D 円錐螺旋評価式（`evalHelixPoint`）と GSAP keyframes（28 ステップ）で有機的螺旋描画。各先端に専用星核ヘッド（`opt_wisp_head_*`）、針状白芯＋広大オーラ（`opt_meteor_*`）を配置。
    6. **前面点火フラッシュ（1.34s）＆ 魔法陣配置調整**: オーブ中央収束時の着弾点火フラッシュ（`#ignition-spark`）を床魔法陣・オーブの手前へ配置移動し、床魔法陣の縦位置（`top: 52%`）をオーブ中心と整合。
    7. **クリスタルオーブの宝石化 ＆ 虹カットイン背景引き算**: オーブのフレネルバイアスと鏡面ハイライトを強化して網目感を解消。虹カットイン時はカメラ減光（`opacity: 0.45`）＋暗幕拡大（500px）＋箔タイポ拡大（112px）で主役を引き立てるメリハリを実現。
    8. **Windows 並列 I/O 堅牢化**: `_utils.py` の `save_png` をメモリバッファ経由・リトライ付き（最大5回）とし、`ThreadPoolExecutor` の並列競合エラーを完全解消。
- [x] **3-6. 召喚前半〜3Dカード回転マイクロポリッシュ（外部レビュー反映・第2弾）**
  - **対象**: `compositions/scene-summon-setup.js`, `compositions/scene-summon.html`, `compositions/scene-summon.css`, `scripts/render_optics.py`, `compositions/scene-result.html`, `compositions/scene-result.css`
  - **成果**（実測 QA `renders/ssr_gacha_polish.mp4`: Gray Veil=2枚, Vacuum=10.4%, Pre-Landing Stall=0.00s, Tail Fixed max_diff=0.674, Shimmer=4.3%, LUFS=-14.1, TruePeak=-2.3dBFS で全項目 PASS）:
    1. **流れ星＆RGB三重螺旋の流体リボン化**: 冒頭の流れ星演出を維持したまま、流れ星尾ノードおよび RGB 三重螺旋の芯ノードへ進行方向接線角（角度アンラップ付き）＋楕円ストレッチを適用し、ビーズ状の粒感を払拭して滑らかな光の帯へ刷新。
    2. **青フェイク区間のカメラ溜め ＆ 青オーブ宝石感強化**: 本編 `1.50s〜3.66s` にカメラ微ズーム（`scale: 1.065`）＆床/天蓋パース微変化の溜めを追加。`render_optics.py` の青オーブのファセット明暗差・境界引き締め・鏡面ハイライトを強化し、青区間の `#orb-core` 不透明度を `0.42` へ抑えて硬質なクリスタル感を実現（金昇格 `3.78s` で解放）。
    3. **虹カットインの勢い補強**: `#cutin-typo-wrap` に斜め光沢スイープ `#cutin-glint` を追加し、表示中の横ドリフト＆微拡大（`x: -24 -> 34`, `scale: 1.0 -> 1.02`）＋拡大横飛び退場（`x: 340, scale: 1.12`）へ刷新。
    4. **3Dカード回転の金属厚み表現 ＆ 裏面タメ光**: 表裏を `translateZ(5px)` に分離し、金属側面風の厚み 5 層スライス（`.card-edge-slice`、正面着地後 `8.82s` で非表示化）を追加。さらに裏面タメ区間（本編 `7.96s〜8.40s`）へ中央紋章チャージ光（`#card-back-emblem-glow`）と外枠プリズム漏れ光（`#card-back-rim-burst`）を追加。

### Phase 3 定量完了基準（DoD）
- `npm run qa -- --check-audio` にて統合ラウドネスが **`-14.0 LUFS (±1.5 LU)`** に収まり、`14.5s` までデジタル無音にならない滑らかな余韻が残ること。
- `9.3s〜14.8s` に 90 年代シンセ臭・ディレイのパタパタ感・唐突な無音途切れがないこと。
- 後半リザルトの四隅装飾干渉・テキスト出現の Web 感・終盤の静止画見えが解消されていること。

---

## 7.5. Phase 3.5：カードタイポグラフィ点検・刷新（可変フォント・縁取り＆カラー・非対称レイアウト）

Phase 4（量産・運用性の仕上げ）に入る前に、カードリザルト画面の文字表現を点検し、多様な画像ジャンル（可愛い写真・アーティスティックな写真・2Dアニメ調イラスト等）に最適化できるタイポグラフィ基盤を整備します。

- **スコープ境界（現行維持 ／ 刷新対象）**:
  - **現行維持**: 昇格時にカットインする文字（`cutinSub` / `cutinMain`）のフォントおよび金箔質感は現行の王道スタイルをそのまま維持し、カード側プリセット変更の影響を受けないように分離する。
  - **刷新対象**: カードと共に出現する文字群（`title`, `subtitle`, `flavor`, `rarity`, `attribute`, `cardNo`）の「書体選択の柔軟性」「縁取り・カラーバリエーション」「非対称レイアウト」を拡張する。
- **参考デザイン方針（SRカードリファレンス分析）**:
  - 左上の斜め帯＋スターバースト付きレアリティバッジと、右下のスラントしたカラーストライプ帯＋太字タイトル（縦ツートングラデ＋白インライン＋濃色太縁の二重縁取り）＋直下の英字/サブタイトル＋帯周りスパークルという「対角コーナー非対称構成」を主要リファレンスの 1 つとして取り込む。

- [x] **3.5-0. フォント周りの事前点検（棚卸し・課題監査チェックリスト）**
  - **対象**: `assets/fonts/*`, `scripts/render_typography.py`, `compositions/shared-base.css`, `compositions/scene-result.*`
  - **点検項目**:
    1. **現行フォント資産と不足ジャンルの棚卸し**: `assets/fonts/` の既存 7 書体（`YujiSyuku-Regular.ttf`, `KleeOne-Regular.ttf`, `SetoFont.ttf`, `TekitouPoem.ttf`, `TekitouPoem_Bold.ttf`, `ZenKurenaido-Regular.ttf`, `cinecaption.ttf`）は筆文字・手書き・細身字幕に偏っており、「2Dアニメ／ゲーム見出し用の太角ゴシック・ポップ体」「可愛い系の太丸ゴシック」「アート／写真集用の洗練明朝・欧文ディスプレイ」が欠落している点を点検し、商用利用可能なオープンライセンス（OFL / Apache 2.0 等）の候補書体と `assets/fonts/LICENSE-OFL.txt` のライセンス表記を確定する。
    2. **カットイン文字とカード文字の結合点チェック**: 現行 `scripts/render_typography.py` の `TYPO_PRESETS` では `cutinSub`/`cutinMain` とカード文字が同一プリセット内に同居しているため、カード側プリセットを切り替えた際にカットイン文字が意図せず変化しないよう分離仕様を確認する。
    3. **可読性・縁取り・配色の境界条件チェック**: 現行 `apply_foil_and_grain_material` はソフト暗色ハローのみで硬質縁取り・二重縁取り・縦グラデ・ヴィヴィッド配色に未対応。明背景／高彩度アニメ背景／暗背景のそれぞれで文字が沈まず、かつ被写体の顔を邪魔しないコントラスト・縁幅基準を点検する。
    4. **レイアウト＆演出同期の制約チェック**: 現行 `compositions/scene-result.css` の `#card-overlay-layer` は中央下揃え固定、出現アニメも単一方向の光走査ワイプ前提。非対称配置・スラント帯導入時に `#card-no-corner`・`#stars-row`・`#attr-badge`・ホロ保護マスク・着地後ワイプ演出と干渉しないか、および被写体の位置（左寄り／右寄り／中央）に応じた退避余地を点検する。

- [x] **3.5-1. 昇格カットインとの設定分離 ＆ ジャンル別ヴァリアブルフォント基盤**
  - **対象**: `assets/fonts/*`, `assets/fonts/LICENSE-OFL.txt`, `card-config.js`, `scripts/render_typography.py`, `compositions/shared-base.css`
  - **課題**: プリセット切替がカットイン側まで波及し、また同梱フォントが手書き・筆文字寄りなため、可愛い写真・アート写真・2Dアニメ画像で書体の世界観が噛み合わない。
  - **対策**:
    - `cutinSub` / `cutinMain` を独立した固定既定（または専用 `cutinPreset`）へ分離し、カード側設定変更の影響を受けないようにする。
    - ジャンル別フォントを追加選定・同梱し、`FONT_NORM_FACTORS`・`FONT_KINEMATICS`（太ゴシックやモダン明朝ではデフォルト `wobble` を抑えて精密整列させる制御を含む）・`compositions/shared-base.css` のフォールバック定義を整備する。
    - `card-config.js` にジャンル別プリセット（例：`royal-foil` / `anime-pop` / `cute-pastel` / `editorial-art` / `handwritten-sign`）を用意しつつ、スロット単位（`title`, `subtitle`, `flavor`, `rarity` 等）でフォントを個別上書きできるヴァリアブル構造にする。

- [x] **3.5-2. 縁取り（単縁・二重縁・3Dベベル）＆ カラー／マテリアル体系・表面中央鋲の拡充**
  - **対象**: `scripts/render_typography.py`, `scripts/render_material.py`, `card-config.js`, `compositions/scene-result.css`
  - **課題**: 現行 `MATERIALS` は金・銀・白の 5 種＋ソフト暗色ハローのみで、アニメ調のくっきり二重縁取りやヴィヴィッド／パステル配色が表現できない。また表面フレームは四隅フィリグリー撤去後に均一な角丸枠となり、豪華な裏面との質感落差がある。
  - **対策**:
    - `scipy.ndimage.distance_transform_edt` 等を用いたアンチエイリアス縁取り描画を `scripts/render_typography.py` に追加し、縁取りスタイル（`none` / `single` / `double`［白インライン＋濃色太縁］ / `bevel-extrude`）とグラデーション角度（縦ツートン・斜め・金属帯）を選択可能にする。
    - マテリアル＆カラーパレットを「金属箔系（Gold / Champagne / Silver / Rose Gold / Prism）」「ヴィヴィッド＆アニメ調（例：Gold-to-White×Deep Navy 二重縁、Cyan×Cobalt、Vivid Pink×Plum、Emerald×Forest 等）」「パステル可愛い系」「アート・ミニマル系」へ拡充し、`card-config.js` からの任意カラー指定も許可する。
    - レアリティクレスト（`render_rarity_crest`）および属性プレート（`render_attribute_plate`）にもテーマカラー連動（金箔／ヴィヴィッド帯＋スターバースト等）のバリエーションを用意し、カード全体の色調を統一する。
    - `scripts/render_material.py` の表面虹フレーム（`mat_rainbow_frame.png`）について、四隅バッジ（`#ssr-emblem` / `#attr-badge` / `#card-no-corner`）と干渉しない「上辺・下辺・左右辺の中央」のみに微小な金属ノッチ／菱形鋲を追加し、特注トレカとしての格を補強する。

- [x] **3.5-3. 脱・中央揃え：非対称・スラント帯など複数レイアウトプリセットの実装**
  - **対象**: `card-config.js`, `scripts/render_typography.py`, `compositions/scene-result.html`, `compositions/scene-result.css`, `compositions/scene-result-setup.js`
  - **課題**: 中央下揃えの一本調子な縦積みレイアウトだけでは視覚的リズムに欠け、2Dアニメ調の躍動感やアート写真的な余白美を活かしきれない。また `#title-wipe-glint` の走査範囲が固定座標（`x: -235 -> 235`）にハードコードされており、星（★×5）も下部テキスト上部に小さく孤立して視線が分散しやすい。
  - **対策**:
    - `card-config.js` にレイアウト指定（例：`typography.layout`）を導入し、以下の構成を切り替え可能にする：
      - `classic-center`：現行の中央下揃え（従来互換）
      - `diagonal-ribbon`：添付参考画像ベースの対角非対称レイアウト（左上スラント帯＋スターバースト付きレアリティ、右下スラントカラー帯＋斜め右寄せタイトル＆直下の英字/サブタイトル＋帯沿いスパークル。被写体の顔を邪魔しない Z 字視線誘導）
      - `editorial-left`：左下アシンメトリー左揃え＋細線アクセント＋余白重視の雑誌表紙／写真集風レイアウト
      - `pop-sticker`：軽やかな傾き・星併置の可愛い／カジュアル向けレイアウト（必要に応じて左右反転オプションや縦書き `vertical-jp` も検討）
    - レイアウトに合わせて文字出現アニメ（帯スライドイン・光走査ワイプ方向・`#title-wipe-glint` の固定座標脱却と文字マスク連動スペキュラ統合・星 `★×5` の SSR ロゴ直下または帯上縁への UI グルーピング再設計）および下部ビネットの強弱を最適化し、`12.0s〜15.0s` のレイアウト完全固定仕様を厳守する。

- [x] **3.5-4. ジャンル別プリセット組み合わせ検証 ＆ スナップショット比較**
  - **対象**: 代表 3〜4 ジャンル（王道ポートレート／可愛い写真／アーティスティック写真／2Dアニメ画像）での出力比較
  - **対策**: 各ジャンルに対応プリセットを適用して `npm run check` および重点フレーム（`5.6s` カットイン、`10.5s` テキスト出現、`13.5s` 固定リザルト）を抽出し、カットインの不変性・文字可読性・顔保護・世界観の一致を目視および `npm run qa` で確認する。

- [x] **3.5-5. ヘッダー共通座布団ギミック ＆ 属性セクション分割 ＆ 召喚カットイン整理 ＆ 出力命名自動化**
  - **対象**: `card-config.js`, `scripts/_typo_modern.py`, `scripts/render_typography.py`, `scripts/render_video.mjs`, `compositions/scene-summon.*`, `compositions/scene-result.*`, `package.json`
  - **課題**:
    - 左上 `SSR`（裸の文字）と右上 `属性`（単色角丸ピル箱）で造形言語が不一致で Web UI / パワポ感が残っていた。
    - `attribute: "光属性 / BABY"` の 1 行文字列はスラッシュで間延びし、パース依存の曖昧さがあった。
    - 召喚カットイン（全体 6.5s 付近）の英語サブテキスト `RAINBOW ASCENSION` が過剰で主役（「昇格 SSR 確定」）の視認性を圧迫していた。
    - レンダリング出力が固定名（`ssr_gacha.mp4`）のため、プリセットや生成日付ごとのアーカイブが困難だった。
  - **対策**:
    1. **ヘッダー共通座布団ギミック（左 A × 右 C）**: 左右の帯高さを `44px` で完全統一し、左上 `SSR` はハーフ座布団から文字が上下に大きく飛び出すオーバーハング構造（Pattern A）、右上 `属性` は左端の拡大メダリオン（Royal: 78px サファイア/ダイヤ、Pastel: 86px 4x SSAA 3次ベジェハート）＋共通座布団帯（Pattern C）へ刷新。文字本体の実インク中心（`alpha >= 0.80`）を基準に帯中心・メダリオン視覚重心へ厳密センタリング。
    2. **属性セクション分割**: `card-config.js` に `attributeBadge: "愛"`（メダリオン内1文字、空で素アイコン表示）と `attributeLabel: "ANGEL"`（帯ラベル、最小幅 176px 確保＋長文オートフィット）の 2 キー設計を導入（従来の `attribute` 文字列にも完全後方互換）。
    3. **召喚カットイン整理**: 不要な `RAINBOW ASCENSION` を完全撤去し、残った「昇格 SSR 確定」をカットイン帯の上下センターへ配置（光の走査グレアも文字中央を貫通）。
    4. **出力命名自動化**: `scripts/render_video.mjs` を導入し、`npm run render` でプリセット名とローカル日付から `renders/SSR_{preset}_{YYYYMMDD}.mp4`（同日連番 `_2`, `_3` 付き）を自動命名・出力。

### Phase 3.5 完了基準（DoD）
- 昇格カットイン（`5.6s` 付近）のフォント・質感に影響を与えずに、カード側タイポグラフィのフォント・縁取り・カラー・レイアウトを `card-config.js` から自在に切り替えられること。
- 可愛い写真・アーティスティックな写真・2Dアニメ調画像それぞれに馴染むプリセット（二重縁取り＋スラント帯の対角レイアウトを含む）が破綻なく描画され、写真上の可読性と顔保護が両立していること。
- 左上 `SSR` と右上 `属性` が共通座布団ギミックとして一体化し、単色ベタ塗りボタン感やドット溢れのない高品質なソシャゲ UI アセットとして描画されること。
- すべてのレイアウトプリセットで `npm run check`（0 errors, 0 warnings）および `npm run qa`（12.0s〜15.0s レイアウト固定・光微動を含む）を PASS すること。

---

## 8. Phase 4：運用性・量産性の強化 ＆ 品質評価・複数素材検証（仕上げ）

任意の写真・テキストを流し込んで運用する際の品質一貫性を仕上げます。

- [ ] **4-1. 任意テキスト変更時の箔タイポ自動同期 ＆ オートレイアウト・ビネット自動適応強化**
  - **対象**: `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js`
  - **課題**: `compositions/scene-result-setup.js` の `bindTypoSlot` は `typo-manifest.js` 内の文字列と完全一致する場合のみ箔 PNG を使い、`--variables` 等でテキストを変更すると素の HTML テキストへフォールバックしてしまう。また明るい背景写真では下部ビネット濃度が不足する場合がある。
  - **対策**: テキスト変更時に `render_typography.py` を自動連動させて物理箔 PNG を再生成するワンコマンド実行導線（またはレンダリング前フック）を整備する。Phase 3.5 で導入する可変フォント・縁取り・非対称レイアウトプリセットを含め、長文タイトル・フレーバーや多行折り返し時の文字サイズ・配置自動調整（オートレイアウト）を強化し、あわせて入力写真（CLI `--variables photo=...` 差し替え含む）の下部 30% 平均輝度に応じた `.photo-vignette` 濃度の自動適応も実装する。
- [ ] **4-2. 5品質評価軸 ＆ 複数入力素材による汎用性検証（＋任意音響アタック強化）**
  - **対象**: 検証チェックリスト、多様な入力画像（顔写真・人物以外の物体写真・風景・イラスト）、`scripts/generate_se.py`, `scripts/_audio_dsp.py`
  - **対策**: 以下の 5 品質評価軸で「足し算だけでなく不要要素を削るレビュー」を実施し、どの種類の画像（および Phase 3.5 のジャンル別タイポプリセットとの組み合わせ）を入れても品質と視認性が破綻しないことを確認する：
    - `Material`（素材ごとの質感一貫性） / `Lighting`（光源と反射・影の整合） / `Depth`（奥行き・カメラ移動） / `Timing`（予兆・溜め・解放・余韻） / `Hierarchy`（主役と脇役の優先順位）
  - （任意）着地〜ファンファーレ頭（`card_land` / Cmaj9 着地）への高域ウィンドチャイム／金属トライアングルの煌めきおよびホーン頭倍音パンチの追加（`-14.0 LUFS` 維持）を検討・適用する。

### Phase 4 完了基準（DoD）
- `card-config.js` または CLI 変数でタイトル・属性・フレーバーを差し替えても、素 HTML フォールバックにならず物理箔タイポ（および Phase 3.5 の選択フォント・縁取り・レイアウト）のままレイアウト崩れなく MP4 生成できること。
- 人物・物体・風景・イラストの複数素材で 5 評価軸の破綻がないこと。

---

## 9. Phase 5：横動画（16:9 / 1920×1080）× 横型カード対応（拡張）

> **事前調査・詳細実装設計書**: 横画面対応における HyperFrames 解像度同期の制約、モジュール別の改修箇所（裏面紋章スケーリング・ホロ走査距離・スパークル/金箔/玉ボケ座標のカード半寸相対化など）、および Phase 3・4 との連携ポイントは **[`LANDSCAPE_PLAN.md`](./LANDSCAPE_PLAN.md)** にまとめています。Phase 5 着手時は必ず参照してください。

縦（9:16）の演出・音響・運用性が Phase 0〜4 で完成した後に着手する、風景・集合写真など横長素材向けのワイドスクリーン対応フェーズです（パターン B）。

- [ ] **5-1. 縦横レイアウト切替アーキテクチャの整備**
  - **対象**: `card-config.js`, `scripts/_utils.py`, `package.json`, `index.html`（または横専用エントリ／設定切替）
  - **対策**: `card-config.js` にレイアウト指定（例：`orientation: "portrait" | "landscape" | "auto"`、`auto` 時は入力写真の縦横比から自動判定）を追加し、`1080×1920`（縦）と `1920×1080`（横）をクリーンに切り替えられる構成にする。
- [ ] **5-2. 横型カード物理アセット生成（虹フレーム・裏面・内窓深度・グレイン）**
  - **対象**: `scripts/_utils.py`, `scripts/render_material.py`, `scripts/render_typography.py`
  - **対策**: `CARD_W / CARD_H` を横型カード比率（例：画面幅の約 75〜80% を占める `1440×860` 付近の 16:10 / 3:2 比率）へ切り替え、虹金属箔フレーム（四隅フィリグリー一体）・ギョーシェ裏面・内窓深度・`1920×1080` フィルムグレインおよび横幅に合わせた箔タイポを自動生成する。
- [ ] **5-3. 召喚＆リザルトコンポジションの 16:9 レスポンシブ対応**
  - **対象**: `compositions/scene-summon.html`, `compositions/scene-result.html`, `compositions/scene-result.css`, `compositions/scene-result-setup.js`
  - **対策**: 1920×1080 キャンバスに合わせて 3D 床パース魔法陣・アナモルフィック光閃・カットイン・背景光学リング・疎密スパークル・3D 金箔片・玉ボケの座標および中央写真保護マスクを調整する。タイトル・星・フレーバーはカード下端の薄い暗色グラデ上へコンパクトに配置し、風景の水平線や主要被写体をクリアに保つ。

### Phase 5 完了基準（DoD）
- 横長写真を指定して `1920×1080`（16:9）の 15 秒 SSR ガチャ演出 MP4 が、縦版と同等の物理質感・写真保護・`12.0s〜15.0s` 光微動を保ったまま出力できること。
- 既存の縦版（`1080×1920`）の品質・出力結果に一切のデグレがないこと。

---

## 10. 各フェーズ共通の検証ワークフロー

各 Phase 完了時は必ず以下の手順でビルド・静的チェック・フレーム目視・動画書き出し・定量 QA を行います。

```bash
# 1. 物理アセット・SE の再生成
npm run build:assets

# 2. HyperFrames 静的・ランタイム検査（エラー 0 件を確認）
npm run check

# 3. 重点時刻のフレーム抽出＆目視確認（16.0s 全体時刻基準 = 本編 + 0.5s プリロール）
#    (0.8s 流れ星+螺旋 / 1.2s 三重螺旋 / 3.4s 青オーブ / 4.32s 金昇格 / 5.64s 真空の間 /
#     5.74s 虹爆発 / 6.4s カットイン / 7.48s 純白保持 / 7.65s 白飛び抜け /
#     8.48s 裏面タメ / 9.02s 回転厚み / 9.20s 着地インパクト / 11.0s テキスト / 14.0s 終盤微動)
npx hyperframes snapshot --at 0.8,1.2,3.4,4.32,5.64,5.74,6.4,7.48,7.65,8.48,9.02,9.20,11.0,14.0

# 4. MP4 本レンダリング（renders/SSR_{preset}_{YYYYMMDD}.mp4）
npm run render

# 5. 定量QAチェック（全映像・音響基準 PASS を確認）
npm run qa -- renders/SSR_cute-pastel_20261122.mp4 --check-audio
```
