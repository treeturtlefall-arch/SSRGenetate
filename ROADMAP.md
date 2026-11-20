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
- **総尺**: 15.0 秒以内を厳守する。
- **写真保護**: 入力写真は 100% クリアなまま一切汚さない（写真自体へ処理を加える必要が生じた場合は `/media-use` の `media-treatments` 規範を遵守する）。
- **決定論的レンダリング**: `Math.random()`・`Date.now()`・外部ネットワーク取得を禁止し、シード付き疑似乱数と登録済み GSAP タイムラインのみで描画する。

---

## 3. フェーズ全体マップ

| Phase | テーマ | 狙い | 主な対象ファイル | 優先度 |
| :--- | :--- | :--- | :--- | :---: |
| **Phase 0** | 確定バグ修正 ＆ 光・色基盤の正常化 | 3D破綻・顔被り・濁った光の解消と色・階調の統一 | `index.html`, `compositions/scene-result.*`, `compositions/scene-summon.html`, `scripts/_utils.py`, `package.json` | ★★★ 完了 |
| **Phase 1** | リザルト画面の「脱Web UI化」＆ 光の微動呼吸 | バッジ・SVG・粒子・ホロ反射を最新3Dソシャゲ級へ刷新 | `compositions/scene-result.*`, `compositions/scene-result-setup.js`, `scripts/render_typography.py`, `scripts/render_material.py`, `AGENTS.md` | ★★★ 完了 |
| **Phase 2A** | 取りこぼし修正・タイムライン骨格確定・定量QA | スペキュラはみ出し/曇り膜/光柱修正・昇格語彙差別化・真空の間・着地同期・`qa_video.py` | `index.html`, `compositions/scene-summon.html`, `compositions/scene-result.*`, `scripts/generate_se.py`, `scripts/qa_video.py`, `package.json` | ★★★ 完了 |
| **Phase 2B** | 召喚〜昇格の「脱CSS ＆ 3D空間光学アセット化」 | カットイン脱ベタ帯・冒頭点火・3D床魔法陣・クリスタルオーブ・不規則ゴッドレイ（前後半） | `scripts/render_optics.py`, `scripts/render_typography.py`, `compositions/scene-summon.html`, `compositions/scene-result.*` | ★★☆ 高 |
| **Phase 3** | 音響の「現代ソシャゲ音像化」＆ 後半マイクロポリッシュ4点 | 脱ブラス・`fftconvolve`残響・14.8s余韻・-14 LUFS適正化 ＋ 縦版9:16の最後の一手仕上げ | `scripts/generate_se.py`, `.gitignore`, `compositions/scene-result.*`, `compositions/scene-result-setup.js`, `scripts/render_material.py` | ★★☆ 中〜高 |
| **Phase 4** | 運用性・量産性強化 ＆ 5軸/複数素材検証 | 任意テキスト箔同期・オートレイアウト ＋ 5品質評価軸・不要要素削減・多様な素材検証 | `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js` | ★☆☆ 仕上げ |
| **Phase 5** | 横動画（16:9）× 横型カード対応 | 風景・周辺情報込みの横写真向け 1920×1080 ワイド演出モード追加 | `card-config.js`, `index.html`, `compositions/*`, `scripts/_utils.py`, `scripts/render_material.py`, `scripts/render_typography.py`, `package.json` | ★☆☆ 拡張 |

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

- [ ] **2B-1. カットインの脱ベタ帯 ＆ 0.0s冒頭点火フック・業務UI整理**
  - **対象**: `compositions/scene-summon.html` (`#cutin-band`, `#summon-status`), `scripts/render_typography.py` (`cutinSub`, `cutinMain`)
  - **課題**: `#cutin-band` の上下 6px 黄色線＋ベタ塗りネオン帯が最も HTML/CSS 感を出し、文字も帯に対して小さい。また 0.0s から魔法陣が既に出ており、「召喚中...」が業務 UI 風。
  - **対策**: `#cutin-band` の上下ボーダーとベタ塗りを廃止し、画面一瞬引き締め＋鋭い水平アナモルフィック・レンズフレア＋スピードライン＋箔ノイズ上を大判の箔タイポが抜ける構成へ刷新する（過剰な `★` 等の記号を整理）。0.0s には暗闇からの光点点火・魔法陣描画フックを追加し、`#summon-status` は廃止または上下端の極小シネマティック英字装飾へ移す。
- [ ] **2B-2. 3D床パース魔法陣 ＆ 空間カメラワーク**
  - **対象**: `scripts/render_optics.py` (`build_magic_circle_masks`), `compositions/scene-summon.html` (`#magic-circle-wrap`)
  - **対策**: 魔法陣マスクにルーン帯・目盛り・太細二重線・頂点ノードを追加して情報階層を強化する。`#magic-circle-wrap` に `perspective` + `rotateX` による 3D 床パースを導入し、青→金→虹の昇格に合わせてカメラが奥から寄る・煽る立体カメラワークを与える。
- [ ] **2B-3. 多面体クリスタルオーブ ＆ 有機的分岐亀裂の物理アセット化**
  - **対象**: `scripts/render_optics.py` (`build_orb_cracks_mask`, 新規オーブ生成関数), `compositions/scene-summon.html` (`#orb-blue`, `#orb-gold`, `#orb-rainbow`, `#orb-cracks`)
  - **課題**: 単層 CSS 球や円グラフ状の `conic-gradient` 虹オーブが周囲の物理魔法陣から浮いている。亀裂も直線的。
  - **対策**: `render_optics.py` で「中心の白飛びエネルギー核＋逆回転する内部クリスタル多面体ファセット／プラズマ渦＋外縁フレネル光輪」の多層透過 PNG を生成して差し替える。亀裂は分岐・テーパー付きへ改修し、隙間から虹色の光が漏れる表現を強める。
- [ ] **2B-4. ゴッドレイ（前後半両方）・縦ストリーク光柱・光学衝撃波の物理アセット化**
  - **対象**: `scripts/render_optics.py`, `compositions/scene-summon.html`, `compositions/scene-result.html`, `compositions/scene-result.css`
  - **課題**: `repeating-conic-gradient` による均等プロペラ放射線（前半 `#summon-godrays` と後半 `#result-rays` の両方）、CSS グラデの光柱 `#light-pillar`、太い単色ボーダーの `.shockwave` / `#landing-shockwave` がデジタル感を生んでいる。
  - **対策**: `idea.md` の `rave_lasers.hlsl` 式から太細不規則なゴッドレイ PNG を 2 枚生成し、**前半 `#summon-godrays` と後半 `#result-rays` の両方**を異速・逆回転の物理放射光へ差し替える。`#light-pillar` は `aurora_claude.hlsl` 式の縦ストリーク 2 層光学アセットへ、衝撃波は中心から外へ滲む光学リング＋微細光粒の飛散へ置換する。

### Phase 2B 完了基準（DoD）
- `0.0s〜7.0s` に素 CSS パーツ（単層球・等間隔放射線・ボーダーリング・上下枠線ベタ帯）が残っていないこと、および後半 `#result-rays` からも等間隔プロペラ放射線が消えていること。
- 3D 床パース魔法陣とクリスタルオーブにより空間の奥行きが感じられること。

---

## 7. Phase 3：サウンドの「現代ソシャゲ音像化」＆ 後半マイクロポリッシュ4点

映像側の秒数が完全に固まった段階で、音響を製品級へ刷新し、あわせて縦版（9:16）後半リザルトの最後の微調整 4 点を仕上げます。

- [ ] **3-1. ファンファーレ音色の刷新（現代ソシャゲ音像・完全プロシージャル）**
  - **対象**: `scripts/generate_se.py` (`synth_brass_note`, `build_se_fanfare`, `build_se_upgrade`)
  - **課題**: 上位 10 倍音鋸波＋固定カットオフのローパス＋平坦 ADSR による 90 年代シンセブラス感・着メロ感が目立っている。
  - **対策**: Python（`numpy` / `scipy`）のみで、**重厚なサブベース＆ティンパニ打撃 ＋ 金属クラッシュシンバル残響（高域バンドパスノイズ） ＋ 広がりのあるシマーパッド＆高精細クリスタル／ハープアルペジオ**を中心とする現代ソシャゲ音像へ再構築する（ブラス要素を残す場合もアタック時フィルタ開閉エンベロープと微細ピッチ表現に留め、主役を交代させる）。
- [ ] **3-2. コンボリューションリバーブ化**
  - **対象**: `scripts/generate_se.py` (`simple_stereo_reverb`)
  - **課題**: 6 タップの単純ディレイでは残響密度が薄くパタパタ感が出る。
  - **対策**: `scipy.signal.fftconvolve` を用い、指数減衰するステレオノイズ IR（インパルス応答）を畳み込む簡易コンボリューションリバーブへ置き換え、高密度なホール残響を実現する。
- [ ] **3-3. 無音ブレーク同期・末尾余韻・ラウドネス適正化**
  - **対象**: `scripts/generate_se.py` (`build_se_upgrade`, `build_se_fanfare`, `save_wav`)
  - **課題**: 最後の和音が `12.6s` 付近で終了して終盤がデジタル無音になりやすく、統合ラウドネスも `-12.4 LUFS` 付近とやや大きめ。
  - **対策**: `5.10s〜5.18s` の真空の間（暗転）に合わせて SE の無音ブレークを同期させる。終盤は `12.0s〜15.0s` の光微動に寄り添う静かなシマー／ルームトーン余韻を `14.8s` まで滑らかにフェードさせ、統合ラウドネスを SNS 基準（`-14 LUFS ±1.5 LU`）へ適正化する。
- [ ] **3-4. （任意拡張）ユーザー所蔵SEライブラリ併用オプションの検討**
  - **対象**: `scripts/generate_se.py`, `.gitignore`
  - **対策**: 個人環境向けに、衝撃音・ガラス破砕・クラッシュシンバル等のユーザー所蔵ワンショット WAV をローカル専用フォルダ（例: `assets/se_custom/`、`.gitignore` 対象）に配置した場合のみ読み込んでミックスし、未配置時は 100% プロシージャル合成へ自動フォールバックする拡張設計を検討する（OSS 配布時の著作権・ライセンス混入防止）。
- [ ] **3-5. 後半（リザルト）マイクロポリッシュ 4 点（縦版 9:16 完成）**
  - **対象**: `compositions/scene-result.html`, `compositions/scene-result.css`, `compositions/scene-result-setup.js`, `scripts/render_material.py`
  - **対策**:
    1. 左上 `#ssr-emblem`・右上 `#attr-badge` とフレーム四隅の L 字フィリグリーの微干渉を解消する（上 2 隅のフィリグリー位置調整または下 2 隅中心の装飾整理）。
    2. タイトル等テキスト出現（`9.38s〜10.5s`）の Web 的フェードイン（`opacity + y` 浮上）を、左→右への光の走査ワイプ（`clip-path`＋閃光ライン）または一瞬のスケール打刻へ刷新する。
    3. カード左右余白（各 90px）に対する特大スパークルの押し込み感を解消するため、コーナー頂点アンカー化またはカード幅の微調整を行う。
    4. `12.0s〜15.0s` のレイアウト完全固定を保ったまま、`13.2s` 付近でカード外枠リム上を細い高輝度グレアが 1 回ハッキリ滑る演出を追加し、終盤 3 秒の「生きているホログラム」感を明確化する。

### Phase 3 定量完了基準（DoD）
- `npm run qa -- --check-audio` にて統合ラウドネスが **`-14.0 LUFS (±1.5 LU)`** に収まり、`14.5s` までデジタル無音にならない滑らかな余韻が残ること。
- `9.3s〜14.8s` に 90 年代シンセ臭・ディレイのパタパタ感・唐突な無音途切れがないこと。
- 後半リザルトの四隅装飾干渉・テキスト出現の Web 感・終盤の静止画見えが解消されていること。

---

## 8. Phase 4：運用性・量産性の強化 ＆ 品質評価・複数素材検証（仕上げ）

任意の写真・テキストを流し込んで運用する際の品質一貫性を仕上げます。

- [ ] **4-1. 任意テキスト変更時の箔タイポ自動同期 ＆ オートレイアウト強化**
  - **対象**: `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js`
  - **課題**: `compositions/scene-result-setup.js` の `bindTypoSlot` は `typo-manifest.js` 内の文字列と完全一致する場合のみ箔 PNG を使い、`--variables` 等でテキストを変更すると素の HTML テキストへフォールバックしてしまう。
  - **対策**: テキスト変更時に `render_typography.py` を自動連動させて物理箔 PNG を再生成するワンコマンド実行導線（またはレンダリング前フック）を整備する。あわせて長文タイトル・フレーバーや多行折り返し時の文字サイズ・配置自動調整を強化する。
- [ ] **4-2. 5品質評価軸 ＆ 複数入力素材による汎用性検証**
  - **対象**: 検証チェックリスト、多様な入力画像（顔写真・人物以外の物体写真・風景・イラスト）
  - **対策**: 以下の 5 品質評価軸で「足し算だけでなく不要要素を削るレビュー」を実施し、どの種類の画像を入れても品質と視認性が破綻しないことを確認する：
    - `Material`（素材ごとの質感一貫性） / `Lighting`（光源と反射・影の整合） / `Depth`（奥行き・カメラ移動） / `Timing`（予兆・溜め・解放・余韻） / `Hierarchy`（主役と脇役の優先順位）

### Phase 4 完了基準（DoD）
- `card-config.js` または CLI 変数でタイトル・属性・フレーバーを差し替えても、素 HTML フォールバックにならず物理箔タイポのままレイアウト崩れなく MP4 生成できること。
- 人物・物体・風景・イラストの複数素材で 5 評価軸の破綻がないこと。

---

## 9. Phase 5：横動画（16:9 / 1920×1080）× 横型カード対応（拡張）

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

# 3. 重点時刻のフレーム抽出＆目視確認
#    (0.2s 導入 / 2.75s 青脈動 / 3.82s 金昇格 / 4.85s 亀裂予兆 / 5.14s 真空の間 /
#     5.24s 虹爆発 / 5.6s カットイン / 6.98s 純白保持 / 7.15s 白飛び抜け /
#     7.98s 裏面タメ / 8.58s 回転中スペキュラ / 8.70s 着地インパクト / 10.5s テキスト / 13.5s 終盤微動)
npx hyperframes snapshot --at 0.2,2.75,3.82,4.85,5.14,5.24,5.6,6.98,7.15,7.98,8.58,8.70,10.5,13.5

# 4. MP4 本レンダリング（renders/ssr_gacha.mp4）
npm run render

# 5. 定量QAチェック（全映像基準 PASS を確認。Phase 3以降は --check-audio を付与）
npm run qa
```
