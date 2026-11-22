# SSRGenerate

写真 1 枚から **16.0 秒（1080×1920 / 縦 9:16）のソシャゲ風 SSR ガチャ当選演出 MP4** を生成する HyperFrames + Python プロジェクトです。

## 主な特徴

- **16.0 秒の一貫したガチャ演出**  
  冒頭 `0.5s` フェードイン ＋ 召喚・オーブ・金→虹昇格カットイン・3D カード回転着地・リザルト余韻（`15.0s`）＋ 末尾 `0.5s` フェードアウトで構成。
- **入力写真を 100% クリアに維持**  
  元の写真自体は加工せず、Z 順・パーティクル軌道・中央減衰ホロマスクによって被写体への被りを抑えます。
- **決定論的レンダリング**  
  シード付き疑似乱数（Mulberry32 / NumPy）と GSAP タイムラインにより、同じ設定から毎回同一の映像・音声を再現します。
- **物理光学・タイポグラフィ・音響の自動生成**  
  Python（`numpy` / `scipy` / `Pillow`）を用いて、光学発光アセット・箔押し風タイポグラフィ・効果音（`-14.0 LUFS` 基準のステレオ WAV）を一括生成します。

---

## 動作環境

- **Node.js / npm**（`npx` 経由で `hyperframes@0.9.72` を使用）
- **Python 3.10+**（`requirements.txt` の依存ライブラリ）
- **FFmpeg**（動画書き出し・定量 QA で使用）

---

## クイックスタート

### 1. Python 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 写真の配置

`assets/photo.jpg` として任意の画像を配置します（別名・別パスの場合は `card-config.js` の `photo` を変更）。

### 3. アセットの生成

```bash
npm run build:assets
```

タイポグラフィ、光学エフェクト、カードフレーム／マテリアル、効果音が一括生成されます。

### 4. プレビュー・検証

```bash
npm run dev     # ブラウザプレビューを起動
npm run check   # コンポジションの静的・ランタイム検証
```

### 5. MP4 書き出し

```bash
npm run render
```

設定に応じたファイル名（`renders/SSR_{preset}_{YYYYMMDD}.mp4`）で書き出されます。  
書き出し後、以下のコマンドで映像・音響の自動定量 QA を実行できます。

```bash
npm run qa -- renders/SSR_xxxx_YYYYMMDD.mp4 --check-audio
```

---

## カスタマイズ

[`card-config.js`](./card-config.js) を編集することで、以下の項目をカスタマイズできます。

- **写真・表示調整**: `photo`, `photoFit`, `photoPosition`, `photoZoom`
- **カード情報**: `rarity`, `stars`（`0`〜`5`）, `attributeBadge`, `attributeLabel`, `subtitle`, `title`, `flavor`, `cardNo`
- **タイポグラフィ**: `typography.preset`（`cute-pastel` / `royal-foil` など）
- **光学・マテリアル・魔法陣**: `optics`, `material`, `summon`, `resultRingMode`, `seed`

`npm run render` 実行時には `card-config.js` や CLI 引数（`--variables`）の変更を自動検知し、必要に応じてタイポグラフィ PNG を自動再生成します。

---

## ドキュメント

- [`SPEC.md`](./SPEC.md) — 確定仕様書（タイムライン・ファイル構成・設定スキーマ）
- [`ROADMAP.md`](./ROADMAP.md) — 開発フェーズ計画・進捗（Phase 0〜5）
- [`LANDSCAPE_PLAN.md`](./LANDSCAPE_PLAN.md) — Phase 5 横動画（16:9）拡張設計
- [`AGENTS.md`](./AGENTS.md) — 開発コマンド・実装規約
