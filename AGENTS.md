# SSRGenerate — エージェント作業規約

写真 1 枚から **16.0 秒（1080×1920）の SSR ガチャ当選演出 MP4** を生成する HyperFrames プロジェクト。
詳細仕様は [`SPEC.md`](./SPEC.md) を参照してください。

## 絶対ルール

1. **総尺と余白**: 全体 **16.0 秒**（冒頭 `0.5s` 無音・黒フェードイン ＋ 本編 `15.0s` ＋ 末尾 `0.5s` 無音・黒フェードアウト、音声は `15.3s` で無音着地）。
2. **終盤の固定ルール**: 本編 `12.0s 〜 15.0s`（全体 `12.5s 〜 15.5s`）はカード・文字・星・粒子の位置とサイズを完全固定し、光の微動（ホロシマー・リムグレア・背景ハロー・スパークル/玉ボケ明滅）のみ動かす。
3. **写真保護**: 入力写真（`assets/photo.jpg` 等）は 100% クリアなまま無加工で維持する。顔被りは Z 順・軌道・中央減衰マスクで回避する。
4. **決定論的レンダリング**: `Math.random()`・`Date.now()`・実行時ネットワーク `fetch()` を禁止する。Mulberry32 疑似乱数と登録済み GSAP タイムラインのみで描画する。
5. **物理寸法の同期**: カード寸法（`900×1590`, border `20`, radius `40/24`）を変更する場合は `scripts/_utils.py` と `compositions/shared-base.css` を必ず同時に揃える。

## プロジェクト地図 ＆ ドキュメント

- `card-config.js` / `index.html` — カード設定（`--variables` 上書き対応）と 16.0s ルートコンポジション
- `compositions/` — サブコンポジション（`scene-summon.*`, `scene-result.*`）および共通基盤（`shared-base.css`, `shared-utils.js`）
- `scripts/` — Python 決定論的アセット生成（`build_all.py`, `render_*.py`, `generate_se.py`）と自動定量 QA（`qa_video.py`）
- `assets/` — 入力写真・フォント・生成アセット（`generated/`）・ローカル専用カスタム SE（`se_custom/`）
- `renders/` — 出力 MP4（`renders/ssr_gacha.mp4`）

**詳細ドキュメント**:
- [`SPEC.md`](./SPEC.md) — 確定仕様（詳細タイムライン・全ファイル一覧・設定スキーマ・音響/QA 基準）※仕様確認や構造変更時は必ず参照
- [`ROADMAP.md`](./ROADMAP.md) — 開発フェーズ計画・進捗（Phase 0〜5）
- [`LANDSCAPE_PLAN.md`](./LANDSCAPE_PLAN.md) — Phase 5 横動画（16:9）拡張設計
- [`assets/se_custom/README.md`](./assets/se_custom/README.md) — ローカル専用カスタム SE スロット運用ガイド

## コマンド

```bash
npm run build:assets   # 全ての生成アセット（タイポ・光学・フレーム・効果音）を一括再生成
npm run build:typo     # card-config.js のテキスト/typography 変更時に透過タイポ PNG を再生成
npm run build:optics   # 物理光学発光アセット PNG を再生成
npm run build:material # 虹フレーム・カード裏面・ホロ・フィルムグレイン PNG を再生成
npm run build:se       # 効果音 WAV（assets/se_custom/ 統合含む）を再生成
npm run check          # lint + runtime + layout + motion + contrast を一括検証
npx hyperframes snapshot --at 1,3,5   # 指定秒数のフレーム PNG を出力して目視確認
npm run render         # MP4 書き出し (renders/ssr_gacha.mp4)
npm run qa -- renders/ssr_gacha.mp4 --check-audio  # 出力 MP4 の定量 QA（映像・音響）
npx hyperframes preview --background  # エージェント用の永続 Studio プレビュー起動
npx hyperframes preview --status      # プレビュー稼働確認
npx hyperframes preview --stop        # レビュー完了後の停止
npx hyperframes docs <topic>          # ローカルリファレンス (data-attributes / gsap / compositions / rendering / examples / troubleshooting)
```

> Studio プレビューをエージェントから起動する場合は、`npm run dev`（フォアグラウンド）ではなく必ず `npx hyperframes preview --background` を使い、完了後に `--stop` で終了すること。

## 変更後の検証（必須）

1. **`.html` / `.css` / `.js` コンポジションを変更した後**: 必ず `npm run check` を実行してエラー 0 を確認し、変更時刻のフレームを `npx hyperframes snapshot --at <seconds>` で視覚確認する。
2. **Python 生成スクリプトを変更した後**: 対応する `npm run build:*` を実行して生成物を確認する。
3. **MP4 レンダリング後**: `npm run qa -- renders/ssr_gacha.mp4 --check-audio` で定量基準への適合を確認する。

## HyperFrames 実装規約

1. すべての時間制御要素に `data-start` と `data-duration` を指定する（`data-track-index` は Studio 表示用の任意属性）。
2. 時間制御する視覚要素には `class="clip"` を付与する。
3. コンポジションごとに一時停止状態のルートタイムラインを `window.__timelines` に登録する（手動追加する子タイムラインは `paused` にしない）：
   ```js
   window.__timelines = window.__timelines || {};
   window.__timelines["composition-id"] = gsap.timeline({ paused: true });
   ```
4. 音声付き `<video>` は `muted` にせず `data-has-audio="true"` を付け、BGM や差し替え音声は独立した `<audio>` を使用する（無音映像は `muted`）。
5. サブコンポジションは `data-composition-src="compositions/file.html"` で参照する。
