# SSRGenerate 統合ロードマップ (`ROADMAP.md`)

> 写真 1 枚から **16.0 秒（1080×1920）の最新 3D ソシャゲ級 SSR ガチャ演出 MP4** を生成する HyperFrames プロジェクトの開発計画・進捗管理ドキュメントです。  
> 詳細仕様は [`SPEC.md`](./SPEC.md)、エージェント作業規約は [`AGENTS.md`](./AGENTS.md)、Phase 5 詳細設計は [`LANDSCAPE_PLAN.md`](./LANDSCAPE_PLAN.md) を参照してください。

---

## 1. 設計方針と不変の原則（Design Principles & Guardrails）

### 不変の原則（絶対ルール）
- **総尺と余白**: 全体 **16.0 秒**（冒頭 `0.5s` 無音・黒フェードイン ＋ 本編 `15.0s` ＋ 末尾 `0.5s` 無音・黒フェードアウト、音声は `15.3s` で無音着地）。
- **終盤の完全固定**: 本編 `12.0s〜15.0s`（全体 `12.5s〜15.5s`）はカード・文字・星・粒子の位置とサイズを完全固定し、光の微動（ホロシマー・リムグレア・背景ハロー・スパークル/玉ボケ明滅）のみを動かす。
- **写真保護**: 入力写真は 100% クリアなまま無加工で維持する。顔被りは Z 順・軌道設計・中央減衰マスクで回避する。
- **決定論的レンダリング**: `Math.random()`・`Date.now()`・外部ネットワーク取得を禁止し、シード付き疑似乱数（Mulberry32）と登録済み GSAP タイムラインのみで描画する。

### 確定した設計方針
| 項目 | 確定方針 |
| :--- | :--- |
| **ルック方向性** | **最新 3D ソシャゲ寄り**（3D 床パース魔法陣、天蓋アストロラーベ、多面体クリスタル光学オーブ、アナモルフィック光閃、立体ホロ反射カード）。 |
| **サウンド方針** | **標準**: Python（`numpy`/`scipy`）完全プロシージャル合成＋`fftconvolve` 残響による現代ソシャゲ音像（`-14.0 LUFS`）。<br>**任意拡張**: `.gitignore` 隔離の `assets/se_custom/` による 11 スロット差し替え・レイヤー対応（未配置時は完全自動フォールバック）。 |
| **スコープ外** | **AI 被写体セグメンテーション／顔認識マスクは導入しない**（軽量・オフライン・完全決定論構成を維持）。 |
| **横動画対応（Phase 5）** | 横写真向けにキャンバス自体を 16:9（`1920×1080`）にした横型 SSR 演出モードを追加する（縦版 Phase 0〜4 完成後に着手）。 |

---

## 2. フェーズ全体マップ

| Phase | テーマ | 主な対象 | 状態 |
| :--- | :--- | :--- | :---: |
| **Phase 0** | 確定バグ修正 ＆ 光・色基盤の正常化 | `index.html`, `compositions/scene-*`, `scripts/_utils.py` | 完了 |
| **Phase 1** | リザルト画面の「脱 Web UI 化」＆ 光の微動呼吸 | `compositions/scene-result.*`, `scripts/render_typography.py`, `render_material.py` | 完了 |
| **Phase 2A** | タイムライン骨格確定・昇格差別化・定量 QA 導入 | `compositions/scene-summon.html`, `scene-result.*`, `scripts/qa_video.py` | 完了 |
| **Phase 2B** | 召喚〜昇格の「脱 CSS ＆ 3D 空間光学アセット化」 | `scripts/render_optics.py`, `compositions/scene-summon.*` | 完了 |
| **Phase 2.5** | フロントエンド共通化 ＆ ビルド並列高速化・整理 | `compositions/shared-*`, `scripts/_optics_core.py`, `scripts/build_all.py` | 完了 |
| **Phase 3** | 音響「現代ソシャゲ音像化」＆ 映像マイクロポリッシュ | `scripts/_audio_*`, `scripts/generate_se.py`, `compositions/scene-*` | 完了 |
| **Phase 3.5** | カードタイポグラフィ刷新（書体・縁取り・非対称配置） | `assets/fonts/*`, `card-config.js`, `scripts/_typo_modern.py`, `render_video.mjs` | 完了 |
| **Phase 4** | 運用性・量産性強化 ＆ 5 評価軸 / 複数素材検証 | `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js` | **未着手（次期）** |
| **Phase 5** | 横動画（16:9 / 1920×1080）× 横型カード対応 | `card-config.js`, `index.html`, `compositions/*`, `scripts/*` | 未着手（拡張） |

---

## 3. 実装済み基盤サマリー（Phase 0 〜 Phase 3.5：完了）

初期の「Web UI 感・光の濁り・90年代シンセ感」は Phase 0〜3.5 で解消済みです。現在のコードベースには以下の機能が実装・検証済みです。

- **Phase 0（光・色・3D 基盤正常化）**: `#card-stage` への opacity 分離による 3D 表裏正常化、着地衝撃波の背面移動（顔被り解消）、発光レイヤーの `screen` / `plus-lighter` 統一、シャンパン金＆連続スペクトル虹パレット刷新、決定論フィルムグレイン導入。
- **Phase 1（リザルト脱 Web UI 化 ＆ 終盤光微動）**: `#ssr-emblem` / `#attr-badge` の物理箔・金属刻印化、素 SVG 廃止、カード占有率調整（余白確保）、スパークル疎密クラスター＆3D 金箔片・玉ボケ導入、回転スペキュラ＋写真中央保護ホロマスク実装、12.0s〜15.0s のレイアウト固定＆光微動実装。
- **Phase 2A（15s 因果骨格 ＆ 自動定量 QA）**: スピンスペキュラのクリップ修正、露出役割分離（`#flash-layer` は 7.0s 純白ホワイトアウト専用）、昇格演出差別化（5.10s〜5.18s「真空の間」暗転）、3 段階 3D 回転→`8.68s` ビタ止め同期、自動定量 QA スクリプト `scripts/qa_video.py`（`npm run qa`）構築。
- **Phase 2B（召喚前半 3D 空間光学化 ＆ 天蓋演出）**: カットインの脱ベタ帯＆アナモルフィック閃光化、0.0s 点火フック、3D 床パース魔法陣＋カメラワーク、多面体クリスタルオーブ＋分岐亀裂、不規則ゴッドレイ（前後半両方）＆縦ストリーク光柱、天蓋アストロラーベゲート・流体ウィスプ・天頂雷撃・全域パララックス星屑・天蓋連動 HUD を実装。
- **Phase 2.5（共通基盤 ＆ ビルド高速化）**: `shared-base.css` / `shared-utils.js` へ共通ロジック集約、`_optics_core.py` 分離と `distance_transform_edt` 化、`ProcessPoolExecutor` + `ThreadPoolExecutor` 並列ビルド化により `npm run build:assets` を **41.1s → 7.5s** へ短縮。
- **Phase 3（現代ソシャゲ音像 ＆ 映像マイクロポリッシュ）**:
  - **音響**: `_audio_dsp.py` によるモダン音像（シマーパッド＋サブ＆ティンパニ＋クラッシュ＋ハープ/チェレスタ＋ホーン）、`fftconvolve` ホールリバーブ、真空ダッキング、終盤 Cmaj9 余韻＋前後 `0.5s` 無音パディング（`-14.1 LUFS` / TruePeak `-2.3 dBFS` 達成）、`assets/se_custom/` の 11 スロットカスタム SE 基盤（`_audio_slots.py`）を実装。
  - **映像**: 表面四隅フィリグリー撤去（裏面へ移植）、星白閃光＆文字光走査ワイプ化、`13.2s` 外枠リムグレア追加、RGB 三重螺旋ウィスプの流体リボン化、青フェイク区間カメラ溜め、カード側面 5 層金属厚み＆裏面タメ光を追加。
- **Phase 3.5（タイポグラフィ刷新 ＆ ヘッダー共通座布団 ＆ 出力自動化）**:
  - **設計分離・書体**: 昇格カットイン（`RAINBOW ASCENSION` 撤去・「昇格 SSR 確定」中央配置）とカード文字を完全分離。ジャンル別フォント・`royal-foil` / `cute-pastel` 等プリセット・4 軸直交スキーマ・`scipy` 二重縁取り（`_typo_modern.py`）・非対称スラントレイアウト（`diagonal-ribbon` 等）・表面中央鋲を追加。
  - **ヘッダー＆命名自動化**: 左上 `SSR`（Pattern A オーバーハング）× 右上 `属性`（Pattern C メダリオン＋`attributeBadge` / `attributeLabel` 分割）の共通 `44px` 座布団ギミックを実装。`scripts/render_video.mjs` により `renders/SSR_{preset}_{YYYYMMDD}.mp4` の自動命名出力に対応。

---

## 4. 今後の開発フェーズ（Phase 4 〜 Phase 5：未着手）

### Phase 4：運用性・量産性の強化 ＆ 品質評価・複数素材検証（仕上げ）

任意の写真・テキストを流し込んで運用する際の品質一貫性を仕上げます。

- [ ] **4-1. 任意テキスト変更時の箔タイポ自動同期 ＆ オートレイアウト・ビネット自動適応強化**
  - **対象**: `package.json`, `scripts/render_typography.py`, `compositions/scene-result-setup.js`
  - **課題**: `compositions/scene-result-setup.js` の `bindTypoSlot` は `typo-manifest.js` 内の文字列と完全一致する場合のみ箔 PNG を使い、`--variables` 等でテキストを変更すると素の HTML テキストへフォールバックしてしまう。また明るい背景写真では下部ビネット濃度が不足する場合がある。
  - **対策**: テキスト変更時に `render_typography.py` を自動連動させて物理箔 PNG を再生成するワンコマンド実行導線（またはレンダリング前フック）を整備する。Phase 3.5 で導入した可変フォント・縁取り・非対称レイアウトプリセットを含め、長文タイトル・フレーバーや多行折り返し時の文字サイズ・配置自動調整（オートレイアウト）を強化し、あわせて入力写真（CLI `--variables photo=...` 差し替え含む）の下部 30% 平均輝度に応じた `.photo-vignette` 濃度の自動適応も実装する。
- [ ] **4-2. 5品質評価軸 ＆ 複数入力素材による汎用性検証（＋任意音響アタック強化）**
  - **対象**: 検証チェックリスト、多様な入力画像（顔写真・人物以外の物体写真・風景・イラスト）、`scripts/generate_se.py`, `scripts/_audio_dsp.py`
  - **対策**: 以下の 5 品質評価軸で「足し算だけでなく不要要素を削るレビュー」を実施し、どの種類の画像（および Phase 3.5 のジャンル別タイポプリセットとの組み合わせ）を入れても品質と視認性が破綻しないことを確認する：
    - `Material`（素材ごとの質感一貫性） / `Lighting`（光源と反射・影の整合） / `Depth`（奥行き・カメラ移動） / `Timing`（予兆・溜め・解放・余韻） / `Hierarchy`（主役と脇役の優先順位）
  - （任意）着地〜ファンファーレ頭（`card_land` / Cmaj9 着地）への高域ウィンドチャイム／金属トライアングルの煌めきおよびホーン頭倍音パンチの追加（`-14.0 LUFS` 維持）を検討・適用する。

**Phase 4 完了基準（DoD）**
- `card-config.js` または CLI 変数でタイトル・属性・フレーバーを差し替えても、素 HTML フォールバックにならず物理箔タイポ（選択フォント・縁取り・レイアウト含む）のまま破綻なく MP4 生成できること。
- 人物・物体・風景・イラストの複数素材で 5 評価軸の破綻がないこと。

---

### Phase 5：横動画（16:9 / 1920×1080）× 横型カード対応（拡張）

> **詳細設計書**: HyperFrames 解像度同期の制約、モジュール別の改修箇所（裏面紋章スケーリング・ホロ走査距離・座標のカード半寸相対化など）は **[`LANDSCAPE_PLAN.md`](./LANDSCAPE_PLAN.md)** を参照してください。

縦（9:16）の演出・音響・運用性が Phase 0〜4 で完成した後に着手する、風景・集合写真など横長素材向けのワイドスクリーン対応フェーズです（パターン B）。

- [ ] **5-1. 縦横レイアウト切替アーキテクチャの整備**
  - **対象**: `card-config.js`, `scripts/_utils.py`, `package.json`, `index.html`（または横専用エントリ／設定切替）
  - **対策**: `card-config.js` にレイアウト指定（例：`orientation: "portrait" | "landscape" | "auto"`、`auto` 時は入力写真の縦横比から自動判定）を追加し、`1080×1920`（縦）と `1920×1080`（横）をクリーンに切り替えられる構成にする。
- [ ] **5-2. 横型カード物理アセット生成（虹フレーム・裏面・内窓深度・グレイン）**
  - **対象**: `scripts/_utils.py`, `scripts/render_material.py`, `scripts/render_typography.py`
  - **対策**: `CARD_W / CARD_H` を横型カード比率（例：画面幅の約 75〜80% を占める `1440×860` 付近の 16:10 / 3:2 比率）へ切り替え、虹金属箔フレーム・ギョーシェ裏面・内窓深度・`1920×1080` フィルムグレインおよび横幅に合わせた箔タイポを自動生成する。
- [ ] **5-3. 召喚＆リザルトコンポジションの 16:9 レスポンシブ対応**
  - **対象**: `compositions/scene-summon.html`, `compositions/scene-result.html`, `compositions/scene-result.css`, `compositions/scene-result-setup.js`
  - **対策**: 1920×1080 キャンバスに合わせて 3D 床パース魔法陣・アナモルフィック光閃・カットイン・背景光学リング・疎密スパークル・3D 金箔片・玉ボケの座標および中央写真保護マスクを調整する。タイトル・星・フレーバーはカード下端の薄い暗色グラデ上へコンパクトに配置し、風景の水平線や主要被写体をクリアに保つ。

**Phase 5 完了基準（DoD）**
- 横長写真を指定して `1920×1080`（16:9）の SSR ガチャ演出 MP4 が、縦版と同等の物理質感・写真保護・`12.0s〜15.0s` 光微動を保ったまま出力できること。
- 既存の縦版（`1080×1920`）の品質・出力結果に一切のデグレがないこと。

---

## 5. 各フェーズ共通の検証ワークフロー

変更時は以下の手順でビルド・静的チェック・フレーム目視・動画書き出し・定量 QA を行います。

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

# 4. MP4 本レンダリング（renders/SSR_<preset>_<YYYYMMDD>.mp4）
npm run render

# 5. 定量QAチェック（全映像・音響基準 PASS を確認）
npm run qa -- renders/SSR_<preset>_<YYYYMMDD>.mp4 --check-audio
```
