# SSRGenerate ブラッシュアップ統合ロードマップ (`ROADMAP.md`)

> 「AIがポン出しで作ったようなルック」から脱却し、**最新3Dソシャゲ級の15秒SSRガチャ演出**へ引き上げるための統合改善計画です。  
> 複数視点（コード・生成動画・構成・音響）のレビューと実コード検証を統合し、確定した設計方針に沿って Phase 0 〜 Phase 4 に整理しています。

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

### 不変の原則（絶対ルール）
- **総尺**: 15.0 秒以内を厳守する。
- **写真保護**: 入力写真は 100% クリアなまま一切汚さない（写真自体へ処理を加える必要が生じた場合は `/media-use` の `media-treatments` 規範を遵守する）。
- **決定論的レンダリング**: `Math.random()`・`Date.now()`・外部ネットワーク取得を禁止し、シード付き疑似乱数と登録済み GSAP タイムラインのみで描画する。

---

## 3. フェーズ全体マップ

| Phase | テーマ | 狙い | 主な対象ファイル | 優先度 |
| :--- | :--- | :--- | :--- | :---: |
| **Phase 0** | 確定バグ修正 ＆ 光・色基盤の正常化 | 3D破綻・顔被り・濁った光の解消と色・階調の統一 | `index.html`, `compositions/scene-result.*`, `compositions/scene-summon.html`, `scripts/_utils.py`, `package.json` | ★★★ 最優先 |
| **Phase 1** | リザルト画面の「脱Web UI化」＆ 光の微動呼吸 | バッジ・SVG・粒子・ホロ反射を最新3Dソシャゲ級へ刷新 | `compositions/scene-result.*`, `compositions/scene-result-setup.js`, `scripts/render_typography.py`, `scripts/render_material.py`, `AGENTS.md` | ★★★ 高 |
| **Phase 2** | 召喚〜昇格の「3D空間光学化」＆ 緩急再設計 | 3D床魔法陣・クリスタルオーブ・引き算の溜め・着地同期 | `scripts/render_optics.py`, `scripts/render_typography.py`, `compositions/scene-summon.html`, `compositions/scene-result.html`, `index.html` | ★★☆ 高 |
| **Phase 3** | サウンドの「現代ソシャゲ音像化」＆ 空間残響 | 脱シンセブラス・コンボリューション残響・余韻・音圧整合 | `scripts/generate_se.py`, `.gitignore` | ★★☆ 中〜高 |
| **Phase 4** | 運用性・量産性の強化 | 任意テキスト変更時の箔タイポ同期とレイアウト自動適応 | `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js` | ★☆☆ 仕上げ |

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

- [ ] **1-1. `#ssr-emblem` と `#attr-badge` の脱Web UIパーツ化**
  - **対象**: `compositions/scene-result.css`, `compositions/scene-result.html`, `compositions/scene-result-setup.js`, `scripts/render_typography.py`, `scripts/render_material.py`
  - **課題**: `#ssr-emblem` が半透明紺の角丸ボックス＋単色黄色枠に閉じ込められており、`#attr-badge` は `border-radius: 999px` のピル型＋素 HTML テキストのため、下部の物理箔タイポから浮いている。
  - **対策**: `#ssr-emblem` の角丸ボックスを廃止し、厚み（ベベル／押し出し）を持たせた箔タイポ直置き＋背後の斜めカット暗色座布団／クリスタル・金属クレストへ刷新する。`#attr-badge` も `render_typography.py` の生成対象に統合し、鋭角な金属・クリスタル刻印タグへ置き換える。
- [ ] **1-2. 四隅装飾・背景リング・カード裏面の素SVG脱却**
  - **対象**: `compositions/scene-result.html`, `compositions/scene-result.css`, `scripts/render_optics.py`, `scripts/render_material.py`
  - **対策**: `.corner-ornament`, `#result-bg-ring`, `#card-back-face` の均一なベクター SVG を廃止し、物理光学発光アセットおよび金属ヘアライン／クリスタル紋章アセットへ差し替える。
- [ ] **1-3. カード構図の余白設計（空間感の確保）**
  - **対象**: `compositions/scene-result.css` (`#card-stage`), `scripts/render_material.py`
  - **課題**: カード（`940×1660`）が画面の約 87% を占めており、背後の放射光・ハロー・光学リングが隠れて空間の奥行きが見えにくい。
  - **対策**: カード占有率を画面の 80〜84% 程度へ調整し、背景の 3D 空間演出が額縁として映える余白を確保する。
- [ ] **1-4. スパークル疎密クラスター化 ＆ 3D箔片・ボケ光粒への置換**
  - **対象**: `compositions/scene-result-setup.js` (`rimAnchors`, `confettiData`), `compositions/scene-result.css`, `compositions/scene-result.html`
  - **課題**: 周囲スパークル 16 個がほぼ等間隔・似たサイズで並び機械的。`.confetti-bit` は単色ベタ塗り長方形の 2D 回転で安っぽい。
  - **対策**: スパークルは**極端なサイズ差（特大 2〜3 個・中 4〜5 個・極小群）と対角線上の疎密クラスター配置**に変更する。紙吹雪は単色四角 `div` を廃止し、`rotateX` / `rotateY` で明滅しながら舞う金箔・プリズム結晶片および遠近感のあるボケ光粒（Bokeh）へ置換し、中央の顔エリアを通過しない軌道へ制御する。
- [ ] **1-5. ホログラム反射の立体化（回転中スペキュラ＋写真保護マスク）**
  - **対象**: `compositions/scene-result.css` (`#holo-sweep-1`, `#holo-sweep-2`, `#holo-static-sheen`), `compositions/scene-result.html`
  - **課題**: 回転中（`7.8s〜9.1s`）に表面のスペキュラ反射がなく、着地後の `#holo-sweep` は白い帯がそのまま写真中央を横切って被写体の顔を白く霞ませている。
  - **対策**: 3D 回転中の角度変化に同期した鋭いスペキュラ反射を追加する。着地後スイープはプリズム／ダイヤ柄テクスチャを仕込み、写真中央部は弱く減衰させつつ金属フレームと箔文字エッジで強くキラッと反射するマスク処理へ改修する。
- [ ] **1-6. 12.0s〜15.0s の「レイアウト固定・光のみ微動」実装 ＆ `AGENTS.md` 更新**
  - **対象**: `compositions/scene-result.html`, `AGENTS.md`
  - **対策**: 12.0s 以降はカード・文字・星の位置とサイズを完全固定したまま、ごく控えめなホロ光沢シマー・スパークルの位相差瞬き・背景ハローの静かな呼吸を 15.0s まで維持する。あわせて `AGENTS.md` の「12.0s〜15.0s（リザルト画面固定）」仕様記述を本方針へ更新する。

### Phase 1 完了基準（DoD）
- リザルト画面に角丸ピルや素のベクター線などの Web UI 感が残っていないこと。
- 入力写真が 100% クリアで、ホロスイープや粒子で顔が汚れたり霞んだりしないこと。
- `12.0s〜15.0s` でレイアウトは不動のまま、光沢・スパークル・背景光のみが上品に呼吸していること。

---

## 6. Phase 2：召喚〜昇格フェーズの「3D空間光学化」＆ 演出の引き算・緩急再設計

前半 7 秒（`0.0s〜7.4s`）および遷移タイミングを「Web デモ」から「最新 3D ソシャゲ演出」へ刷新するフェーズです。

- [ ] **2-1. 3D床パース魔法陣 ＆ 空間カメラワーク**
  - **対象**: `scripts/render_optics.py` (`build_magic_circle_masks`), `compositions/scene-summon.html` (`#magic-circle-wrap`)
  - **対策**: 魔法陣マスクにルーン帯・目盛り・太細二重線・頂点ノードを追加して情報階層を強化する。`#magic-circle-wrap` に `perspective` + `rotateX` による 3D 床パースを導入し、青→金→虹の昇格に合わせてカメラが奥から寄る・煽る立体カメラワークを与える。
- [ ] **2-2. 多面体クリスタルオーブ ＆ 有機的分岐亀裂の物理アセット化**
  - **対象**: `scripts/render_optics.py` (`build_orb_cracks_mask`, 新規オーブ生成関数), `compositions/scene-summon.html` (`#orb-blue`, `#orb-gold`, `#orb-rainbow`, `#orb-cracks`)
  - **課題**: 単層 CSS 球や円グラフ状の `conic-gradient` 虹オーブが周囲の物理魔法陣から浮いている。亀裂も直線的。
  - **対策**: `render_optics.py` で「中心の白飛びエネルギー核＋逆回転する内部クリスタル多面体ファセット／プラズマ渦＋外縁フレネル光輪」の多層透過 PNG を生成して差し替える。亀裂は分岐・テーパー付きへ改修し、隙間から虹色の光が漏れる表現を強める。
- [ ] **2-3. ゴッドレイ・光柱・衝撃波の物理アセット化**
  - **対象**: `scripts/render_optics.py`, `compositions/scene-summon.html`, `compositions/scene-result.html`
  - **課題**: `repeating-conic-gradient` による均等プロペラ放射線、均一な縦帯の `#light-pillar`、太い単色ボーダーの `.shockwave` / `#landing-shockwave` がデジタル感を生んでいる。
  - **対策**: ゴッドレイは太細不規則な光束 PNG を 2 枚生成して異速・逆回転で重ねる。`#light-pillar` は上下減衰＋細白芯＋縦ノイズオーラの 2 層光学アセットへ、衝撃波は中心から外へ滲む光学リング＋微細光粒の飛散へ置換する。
- [ ] **2-4. カットイン帯の脱ベタ帯 ＆ 冒頭フック・業務UI整理**
  - **対象**: `compositions/scene-summon.html` (`#cutin-band`, `#summon-status`), `scripts/render_typography.py` (`cutinSub`, `cutinMain`)
  - **課題**: `#cutin-band` の上下 6px 黄色線＋ベタ塗りネオン帯が最も HTML/CSS 感を出し、文字も帯に対して小さい。また 0.0s から魔法陣が既に出ており、光柱に被る「召喚中...」が業務 UI 風。
  - **対策**: `#cutin-band` の上下ボーダーとベタ塗りを廃止し、画面一瞬引き締め＋鋭い水平アナモルフィック・レンズフレア＋スピードライン＋箔ノイズ上を大判の箔タイポが抜ける構成へ刷新する（過剰な `★` 等の記号を整理）。0.0s には暗闇からの光点点火・魔法陣描画フックを追加し、`#summon-status` は廃止または上下端の極小シネマティック英字装飾へ移す。
- [ ] **2-5. 演出の引き算（因果チェーン）＆ 昇格語彙の差別化**
  - **対象**: `compositions/scene-summon.html`, `index.html`
  - **課題**: 青→金→虹で毎回同じレシピ（衝撃波＋x/y シェイク）が繰り返され、5.2s では 9 要素が同時主張している。
  - **対策**: 昇格ごとに演出語彙を変え（例：ズームパンチ、放射ブラー、水平光閃）、**「予兆（収縮・亀裂） → 爆発解放 → 余韻」の因果チェーン**でタイミングをずらす。特に虹昇格直前（約 `5.0s〜5.2s`）に「オーブ急収縮＋周囲オーラ・魔法陣の 2〜4 フレーム暗転」という**真空の間**を挟み、爆発のコントラストを最大化する。
- [ ] **2-6. 3D回転着地のイージング完全同期**
  - **対象**: `compositions/scene-result.html` (`#ssr-card` 回転・着地タイムライン)
  - **課題**: `7.18s〜9.33s` の `power3.out` が終盤 0.7 秒間ほぼ正面でダラダラ減速し、着地ショック（`9.32s`）と噛み合っていない。
  - **対策**: 高速回転から `expo.out` / 鋭い `back.out` でビタ止めする瞬間と、着地ショック・背面衝撃波・色収差・`#ssr-emblem` 打刻のフレームを完全一致させる。

### Phase 2 完了基準（DoD）
- `0.0s〜7.0s` に素 CSS パーツ（単層球・等間隔放射線・ボーダーリング・上下枠線ベタ帯）が残っていないこと。
- 3D 床パース魔法陣とクリスタルオーブにより空間の奥行きが感じられること。
- `5.15s` 前後の溜め→ `5.20s` の虹爆発、および `9.3s` 付近の回転停止→着地インパクトが 1 フレームの違和感なく同期していること。

---

## 7. Phase 3：サウンドの「現代ソシャゲ音像化」＆ 空間残響

映像の高級感と釣り合う音圧・空間・余韻へ `scripts/generate_se.py` を再構築します。

- [ ] **3-1. ファンファーレ音色の刷新（現代ソシャゲ音像・完全プロシージャル）**
  - **対象**: `scripts/generate_se.py` (`synth_brass_note`, `build_se_fanfare`, `build_se_upgrade`)
  - **課題**: 上位 10 倍音鋸波＋固定カットオフのローパス＋平坦 ADSR による 90 年代シンセブラス感が目立っている。
  - **対策**: Python（`numpy` / `scipy`）のみで、**重厚なサブベース＆ティンパニ打撃 ＋ 金属クラッシュシンバル残響（高域バンドパスノイズ） ＋ 広がりのあるシマーパッド＆高精細クリスタル／ハープアルペジオ**を中心とする現代ソシャゲ音像へ再構築する（ブラス要素を残す場合もアタック時フィルタ開閉エンベロープと微細ピッチ表現に留め、主役を交代させる）。
- [ ] **3-2. コンボリューションリバーブ化**
  - **対象**: `scripts/generate_se.py` (`simple_stereo_reverb`)
  - **課題**: 6 タップの単純ディレイでは残響密度が薄くパタパタ感が出る。
  - **対策**: `scipy.signal.fftconvolve` を用い、指数減衰するステレオノイズ IR（インパルス応答）を畳み込む簡易コンボリューションリバーブへ置き換え、高密度なホール残響を実現する。
- [ ] **3-3. 無音ブレーク同期・末尾余韻・ラウドネス適正化**
  - **対象**: `scripts/generate_se.py` (`build_se_upgrade`, `build_se_fanfare`, `save_wav`)
  - **課題**: `12.5s` で残響が急に途切れて `13.0s` 以降がデジタル無音になっており、統合ラウドネスも `-12.4 LUFS` 付近とやや大きめ。
  - **対策**: Phase 2 の虹昇格直前の真空の間（暗転）に合わせて SE の無音ブレークを同期させる。終盤は `12.0s〜15.0s` の光微動に寄り添う静かなシマー／ルームトーン余韻を `14.8s` まで滑らかにフェードさせ、統合ラウドネスを SNS 基準（`-14 LUFS` 目安）へ適正化する。
- [ ] **3-4. （任意拡張）ユーザー所蔵SEライブラリ併用オプションの検討**
  - **対象**: `scripts/generate_se.py`, `.gitignore`
  - **対策**: 個人環境向けに、衝撃音・ガラス破砕・クラッシュシンバル等のユーザー所蔵ワンショット WAV をローカル専用フォルダ（例: `assets/se_custom/`、`.gitignore` 対象）に配置した場合のみ読み込んでミックスし、未配置時は 100% プロシージャル合成へ自動フォールバックする拡張設計を検討する（OSS 配布時の著作権・ライセンス混入防止）。

### Phase 3 完了基準（DoD）
- `9.3s〜14.8s` に 90 年代シンセ臭・ディレイのパタパタ感・唐突な無音途切れがないこと。
- 虹昇格直前の暗転と着地インパクトに音のアタック・無音ブレークが完全同期し、外部音源なしでも完結して再生できること。

---

## 8. Phase 4：運用性・量産性の強化（仕上げ）

任意の写真・テキストを流し込んで運用する際の品質一貫性を仕上げます。

- [ ] **4-1. 任意テキスト変更時の箔タイポ自動同期 ＆ オートレイアウト強化**
  - **対象**: `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js`
  - **課題**: `compositions/scene-result-setup.js` の `bindTypoSlot` は `typo-manifest.js` 内の文字列と完全一致する場合のみ箔 PNG を使い、`--variables` 等でテキストを変更すると素の HTML テキストへフォールバックしてしまう。
  - **対策**: テキスト変更時に `render_typography.py` を自動連動させて物理箔 PNG を再生成するワンコマンド実行導線（またはレンダリング前フック）を整備する。あわせて長文タイトル・フレーバーや多行折り返し時の文字サイズ・配置自動調整を強化する。

### Phase 4 完了基準（DoD）
- `card-config.js` または CLI 変数でタイトル・属性・フレーバーを差し替えても、素 HTML フォールバックにならず物理箔タイポのままレイアウト崩れなく MP4 生成できること。

---

## 9. 各フェーズ共通の検証ワークフロー

各 Phase 完了時は必ず以下の手順でビルド・静的チェック・フレーム目視・動画書き出しを行います。

```bash
# 1. 物理アセット・SE の再生成
npm run build:assets

# 2. HyperFrames 静的・ランタイム検査（エラー 0 件を確認）
npm run check

# 3. 重点時刻のフレーム抽出＆目視確認
#    (0.2s 導入 / 2.0s 青オーブ / 3.82s 金昇格 / 5.12s 暗転溜め / 5.25s 虹爆発 /
#     5.6s カットイン / 7.1s 白飛び / 7.85s 裏面視認 / 8.6s 回転中反射 /
#     9.35s 着地 / 11.0s ホロスイープ / 13.5s 終盤微動)
npx hyperframes snapshot --at 0.2,2.0,3.82,5.12,5.25,5.6,7.1,7.85,8.6,9.35,11.0,13.5

# 4. MP4 本レンダリング（renders/ssr_gacha.mp4）
npm run render
```
