<div align="center">

# ✨ SSRGenerate

### 写真 1 枚から **16.0 秒のソシャゲ風 SSR ガチャ当選演出 MP4** ＆ **フル解像度カード PNG** を生成する HyperFrames + Python エンジン

![Engine](https://img.shields.io/badge/Engine-HyperFrames%200.9.72-blueviolet?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Audio](https://img.shields.io/badge/Audio--14.0%20LUFS-Stereo%20WAV-orange?style=flat-square)
![Deterministic](https://img.shields.io/badge/Render-100%25%20Deterministic-2ea44f?style=flat-square)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](./LICENSE)

[設計思想](#なぜ-ssrgenerate-なのか) • [主な機能](#主な機能) • [動作環境](#動作環境) • [クイックスタート](#クイックスタート) • [カード静止画生成](#カード静止画生成-cardpng) • [カスタマイズ](#カスタマイズ) • [コマンド一覧](#コマンド一覧)

</div>

---

## なぜ SSRGenerate なのか

一般的な動画テンプレートやブラウザエフェクトの寄せ集めでは、写真の被写体にパーティクルが被ったり、毎回ランダムな位置に飛んで再現性が失われたりしがちです。SSRGenerate は **決定論的レンダリング** と **物理ベースの光学・箔マテリアル合成** を組み合わせ、写真 1 枚から破綻のないプレミアムなガチャ演出を生成します。

| 設計項目 | 一般的なテンプレート演出 | SSRGenerate |
| :--- | :--- | :--- |
| **写真の保護** | フィルタやパーティクルが顔に被る | 入力写真を **100% 無加工** で維持し、Z 順・軌道・中央減衰マスクで被りを回避 |
| **再現性** | `Math.random()` で毎回結果が変わる | Mulberry32 疑似乱数 + `np.random.default_rng(seed)` による **完全決定論的** 描画 |
| **タイポグラフィ** | CSS テキストシャドウの単調な文字 | Python (Pillow / SciPy) で **物理箔・2x SSAA 縁取り・ドロップシャドウ** を事前焼成 |
| **光学・マテリアル** | 単純な CSS `blur()` と半透明グラデーション | H&D 分光ハレーションモデル・金属ヘアライン・ホログラムラメを PNG 合成 |
| **カード単体出力** | 動画からの低品質なフレーム切り出し | 動画と同じ座標・物理箔を用いた **フル解像度透過角丸 `card.png`** を同時出力 |

---

## 主な機能

- **16.0 秒の一貫した SSR ガチャ演出**  
  冒頭 `0.5s` 無音フェードイン ＋ 本編 `15.0s`（召喚・螺旋ウィスプ・青→金→虹昇格カットイン・3D カード回転着地・終盤 3 秒完全固定リザルト）＋ 末尾 `0.5s` 無音フェードアウトで構成。
- **縦動画・横動画の両対応 (`portrait` / `landscape` / `auto`)**  
  縦 `1080×1920`（9:16）だけでなく横 `1920×1080`（16:9）にも対応。`orientation: "auto"` にすると入力写真の縦横比から自動で向きを判定します。
- **フル解像度カード静止画 (`card.png`) の自動同時出力**  
  動画書き出し時に、終盤カードと同一品質・透過角丸の静止画（縦 `900×1590` / 横 `1480×860`）を `.card.png` として同時生成します。カード単体の高速出力も可能です。
- **スマート・プリフライト (`npm run render`)**  
  [`card-config.js`](./card-config.js) や `--variables` の変更差分を検知し、レンダリング直前に必要なタイポグラフィ PNG やレイアウト連動アセットのみを自動再生成します。
- **音響・映像の自動定量 QA (`npm run qa`)**  
  書き出した MP4 に対し、尺・解像度・冒頭/末尾の黒フェード・終盤の静止固定・音声ラウドネス（`-14.0 LUFS` 基準）を自動検査します。

<details>
<summary><b>内部パイプラインを見る</b></summary>

```text
[card-config.js / --variables]
        │
        ├──► scripts/render_typography.py  ──► 物理箔・縁取りタイポ PNG + typo-manifest.js
        ├──► scripts/render_optics.py      ──► 多重 PSF ハレーション・魔法陣・星屑 PNG
        ├──► scripts/render_material.py    ──► 虹金属箔フレーム・ヘアライン・ホログラム PNG
        └──► scripts/generate_se.py        ──► 3 トラック効果音 WAV (se_summon / upgrade / fanfare)
                │
                ├──► scripts/render_card_png.py ──► renders/SSR_{preset}_{YYYYMMDD}.card.png
                └──► HyperFrames (index.html)   ──► renders/SSR_{preset}_{YYYYMMDD}.mp4
                                                            │
                                                            ▼
                                                    scripts/qa_video.py (映像・音響定量 QA)
```

</details>

---

## 動作環境

- **Node.js / npm**（`npx` 経由で `hyperframes@0.9.72` を使用）
- **Python 3.10+**（[`requirements.txt`](./requirements.txt) の依存ライブラリ：`numpy`, `scipy`, `Pillow`, `soundfile`）
- **FFmpeg**（動画書き出しおよび `npm run qa` の映像・音響解析で使用）

---

## クイックスタート

### 1. Python 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 写真の配置

`assets/photo.jpg` として任意の画像を配置します（別名・別パスの場合は [`card-config.js`](./card-config.js) の `photo` を変更、または CLI の `--variables` で指定できます）。

### 3. アセットの一括生成

```bash
npm run build:assets
```

タイポグラフィ、光学エフェクト、虹フレーム／マテリアル、効果音 WAV が `assets/generated/` および `assets/` に一括生成されます。

### 4. プレビューと検証

```bash
npm run dev     # ブラウザプレビュー (HyperFrames Studio) を起動
npm run check   # コンポジションの静的・ランタイム・レイアウト検証
```

### 5. MP4 ＆ カード静止画の書き出し

```bash
npm run render
```

[`card-config.js`](./card-config.js) のプリセットに応じたファイル名で、動画とカード静止画が同時に書き出されます。

- **動画**: `renders/SSR_{preset}_{YYYYMMDD}.mp4`（同日重複時は `_2`, `_3` ... と自動連番）
- **カード静止画**: `renders/SSR_{preset}_{YYYYMMDD}.card.png`

書き出し後、以下のコマンドで映像・音響の自動定量 QA を実行できます。

```bash
npm run qa -- renders/SSR_cute-pastel_20261123.mp4 --check-audio
```

---

## カード静止画生成 (`card.png`)

動画レンダリングを行わずに、**カード単体のフル解像度透過 PNG** だけを高速（数秒）に出力することもできます。サムネイル作成、SNS 投稿、印刷用素材などに活用できます。

### 出力仕様

| 向き (`orientation`) | カード全体サイズ | 内窓サイズ | 枠幅 / 角丸 | 背景 |
| :--- | :--- | :--- | :--- | :--- |
| **縦 (`portrait`)** | `900 × 1590 px` | `860 × 1550 px` | 枠 `20px` / 外 `40px` / 内 `24px` | 外周透過 RGBA PNG |
| **横 (`landscape`)** | `1480 × 860 px` | `1440 × 820 px` | 枠 `20px` / 外 `40px` / 内 `24px` | 外周透過 RGBA PNG |

### カード単体で書き出す

```bash
# 基本（renders/card.png に出力）
npm run render:card

# 出力先や設定を上書きして出力
python scripts/render_card_png.py -o renders/my_card.png --overrides '{"title":"伝説の勇者","typography":{"preset":"royal-foil"}}'
```

### 動画書き出し時のオプション制御 (`npm run render`)

`npm run render` は既定で `.mp4` と `.card.png` を同時出力しますが、以下のフラグで挙動を制御できます。

```bash
# カード静止画を別パスに出力する
npm run render -- --card-output renders/custom_card.png

# 動画のみ出力し、card.png の同時生成をスキップする
npm run render -- --no-card-png

# 設定をその場で上書きしつつ動画・カード両方を生成する（事前に typo-sync も自動実行）
npm run render -- --variables '{"photo":"assets/other.jpg","orientation":"auto","title":"新しいタイトル"}'
```

> [!TIP]
> `npm run render -- --dry-run` を実行すると、レンダリングを実行せずにプリセット名・出力ファイル名・`typo-sync` の要否・実行コマンドを事前確認できます。

---

## カスタマイズ

[`card-config.js`](./card-config.js) を編集（または `--variables` / `--variables-file` で上書き）することで、以下の項目を調整できます。

| カテゴリ | 主な設定キー | 説明 |
| :--- | :--- | :--- |
| **向き** | `orientation` | `"portrait"` (縦 9:16) / `"landscape"` (横 16:9) / `"auto"` (写真の縦横比で自動判定) |
| **写真** | `photo`, `photoFit`, `photoPosition`, `photoZoom` | 入力写真パス・表示フィット（`cover` / `contain`）・位置・ズーム倍率 |
| **カード情報** | `rarity`, `stars`, `attributeBadge`, `attributeLabel`, `subtitle`, `title`, `flavor`, `cardNo` | レアリティ・星の数（`0`〜`5`）・属性メダリオン・タイトル・フレーバー・シリアル番号 |
| **タイポグラフィ** | `typography.preset` | `"cute-pastel"`（ポップ水平・ローズプラム縁取り）/ `"royal-foil"`（王道ロイヤル・金箔）/ レガシー互換（`foil-brush`, `handwritten-sign`, `crisp-emboss`） |
| **物理光学** | `optics.halation`, `coreGlow`, `irregularity` | 多重 PSF ハレーション、中心白飛び、3 階層有機ゆらぎ強度 |
| **マテリアル** | `material.frameFoilGlitter`, `frameBrushStrength`, `windowDepthOpacity`, `chromaShockPx` | 虹フレームのラメ・ヘアライン・内窓落ち影・瞬間 RGB 色収差量 |
| **召喚・背景** | `summon.*`, `resultRingMode`, `seed` | 魔法陣速度カーブ（`dramatic` / `steady` / `overdrive`）・リザルト配色（`rainbow` / `cooldown` / `gold`）・決定論シード |

> [!NOTE]
> `npm run render` を使う場合は、`card-config.js` を変更した後に手動で `npm run build:typo` を実行し忘れても、差分検知によって自動で再生成されます。

---

## コマンド一覧

| コマンド | 用途 |
| :--- | :--- |
| `npm run build:assets` | すべての生成アセット（タイポ・光学・マテリアル・効果音）を一括再生成 |
| `npm run build:typo` | [`card-config.js`](./card-config.js) のテキスト・タイポ設定に基づき透過タイポ PNG を再生成 |
| `npm run build:optics` | 物理光学発光アセット（魔法陣・オーブ・星屑など）を再生成 |
| `npm run build:material` | 虹フレーム・カード裏面・ホログラム・フィルムグレインを再生成 |
| `npm run build:se` | 効果音 WAV 3 種を再生成（`assets/se_custom/` のローカル差し替え統合に対応） |
| `npm run dev` | ブラウザプレビュー（HyperFrames Studio）を起動 |
| `npm run check` | コンポジションの静的・ランタイム・レイアウト検証を実行 |
| `npm run render` | スマート・プリフライト付きで MP4 と `.card.png` を同時書き出し |
| `npm run render:card` | フル解像度 `card.png` のみを単体書き出し |
| `npm run qa -- <mp4> --check-audio` | 書き出した MP4 の映像・音響を自動定量検査 |

---

## カスタム素材（ローカル専用）

商用・個人所有のフォントや効果音を使用したい場合は、Git 管理対象外のローカル専用スロットを利用できます。

- **カスタム効果音**: [`assets/se_custom/README.md`](./assets/se_custom/README.md) を参照
- **カスタムフォント**: [`assets/fonts_custom/README.md`](./assets/fonts_custom/README.md) を参照

---

## ドキュメント

- [`SPEC.md`](./SPEC.md) — 確定仕様書（詳細タイムライン・ファイル構成・設定スキーマ・QA 基準）
- [`ROADMAP.md`](./ROADMAP.md) — 開発フェーズ計画・進捗
- [`AGENTS.md`](./AGENTS.md) — AI エージェント向け作業規約・HyperFrames 実装ルール

---

## ライセンス

本プロジェクトは [MIT License](./LICENSE) のもとで公開されています。同梱フォントのライセンスは [`assets/fonts/LICENSE-OFL.txt`](./assets/fonts/LICENSE-OFL.txt) および [`assets/fonts/LICENSE-cinecaption.txt`](./assets/fonts/LICENSE-cinecaption.txt) をご確認ください。
