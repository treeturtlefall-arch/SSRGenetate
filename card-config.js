/**
 * SSRGenerate — カード設定ファイル
 *
 * 写真やカード上のテキストを差し替える場合は、このファイルを編集してください。
 * 写真は `assets/` フォルダに配置し、`photo` に相対パスを指定します。
 * テキストや typography 設定を変更した場合は `npm run build:typo` で透過PNGを再生成してください。
 *
 * CLI から一時的に上書きしたい場合は以下でも可能です:
 *   npx hyperframes render --variables '{"title":"新しいタイトル","photo":"assets/other.jpg"}'
 */
window.SSR_CARD_CONFIG = {
  // 入力写真のパス（index.html からの相対パス）
  photo: "assets/photo.jpg",

  // 写真の表示調整（cover / contain、および object-position）
  photoFit: "cover",
  photoPosition: "50% 35%",
  photoZoom: 1.05,

  // レアリティ・星の数（stars: 0 で非表示、1..5 で柔軟に表示可能）
  rarity: "SSR",
  stars: 0,

  // カード属性（右上メダリオン＋帯ラベル。両方空にすると非表示、badgeのみ空にすると素アイコン表示）
  attributeBadge: "愛",     // メダリオン内の1文字（例: "光", "愛", ""）
  attributeLabel: "ANGEL",  // 帯ラベル（目安: 英字3〜8文字 / 日本語2〜5文字。例: "BABY", "ANGEL"）
  subtitle: "【満開の笑顔】",
  title: "えがおの天使",
  flavor: "", // デフォルト非表示（subtitle + title の 2 段構成）。文言を入れると表示されます。

  // シリアル番号風フッター表記（カード右下隅へ控えめに極小刻印）
  cardNo: "NO.777-SSR",

  // タイポグラフィ設定（scripts/render_typography.py が参照）
  //   preset: "royal-foil"  (男の子・王道ロイヤル / A-1)
  //         | "cute-pastel" (女の子・可愛いポップ / B-2 水平 + 2x SSAA ローズプラム外縁)
  //         | "foil-brush" | "handwritten-sign" | "crisp-emboss" (レガシー互換)
  //   ※ 昇格カットイン文字 (5.6s付近) はカード側設定とは完全分離され、王道金箔のまま固定されます。
  typography: {
    preset: "cute-pastel",
    wobble: 28,           // 0..100（レガシー互換プリセット用）
    foilGlitter: 0.42,    // 0.0..1.0（レガシー互換プリセット用）
    paperGrain: 0.35,     // 0.0..1.0（レガシー互換プリセット用）
    seed: 20261120,
  },

  // 物理光学発光設定（scripts/render_optics.py が参照：FilmDateStamp 由来 H&D 分光モデル）
  optics: {
    halation: 1.05,       // 多重 PSF ハレーションの広がり（0.5..2.0）
    coreGlow: 1.15,       // 中心尾根の白飛び（Core Bleach）強度（0.5..2.0）
    irregularity: 0.85,   // 3階層有機ゆらぎ（光量差・波打ち・裾野ちぎれ）
    seed: 20261120,
  },

  // 虹フレーム物理マテリアル・内窓深度・瞬間RGB色収差設定（写真は100%クリア維持）
  material: {
    frameFoilGlitter: 0.45,   // 虹フレーム表面のマイクロホログラムラメ強度（0.0..1.0）
    frameBrushStrength: 0.85, // 虹フレームの金属ヘアライン研磨・圧着反射ムラ強度（0.0..1.5）
    windowDepthOpacity: 0.92, // 内窓落ち影＆右下断面ハイライト（0.0..1.0）
    chromaShockPx: 9,         // 昇格・着地インパクトの瞬間RGB色収差量（px, 0でOFF）
    seed: 20261120,
  },

  // 召喚フェーズの魔法陣回転設定（compositions/scene-summon.html が参照）
  summon: {
    magicCircleSpeed: 1.0,                 // 全体速度倍率（0.5=重厚低速, 1.0=標準, 1.5=高速）
    magicCircleCurve: "dramatic",          // "dramatic"（昇格ギアチェンジ＆真空急停止）| "steady" | "overdrive"
    magicCircleRingRatios: [1.0, -1.3, 1.7], // [外周, 中段, 内周] の相対倍率（負値で逆回転）
  },

  // リザルト背景魔法陣の配色モード（"rainbow" = 虹色維持[既定] | "cooldown" = 虹→赤金→青系クールダウン | "gold" = 従来赤金）
  resultRingMode: "rainbow",

  // パーティクル配置用の決定論シード値（数値を変えると星屑や紙吹雪の配置パターンが変化）
  seed: 20261120,
};
