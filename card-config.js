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

  // レアリティ・星の数
  rarity: "SSR",
  stars: 5,

  // カード情報（空文字・空配列にすると非表示になります）
  attribute: "光属性 / BABY", // 例: "光属性 / SMILE"
  subtitle: "【覚醒の眼光】",
  title: "ちいさな覇王",
  flavor: "溢れ出す鼻水は強者の証。その鋭き流し目に平伏せよ。",

  // カード下部ステータス（デフォルトは写真主役のため非表示。最大3項目まで任意表示可）
  stats: [],

  // シリアル番号風フッター表記（カード右下隅へ控えめに刻印）
  cardNo: "NO.077-SSR",

  // 文字ヒューマナイズ＆箔物理設定（scripts/render_typography.py が参照）
  typography: {
    preset: "foil-brush", // "foil-brush" | "handwritten-sign" | "crisp-emboss"
    wobble: 28,           // 0..100（0=完全整列, 28=品のある人間味, 50=手書き感）
    foilGlitter: 0.42,    // 0.0..1.0（金箔・銀箔の微細ラメ反射強度）
    paperGrain: 0.35,     // 0.0..1.0（下地シボによるインク/箔の乗り変調）
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

  // パーティクル配置用の決定論シード値（数値を変えると星屑や紙吹雪の配置パターンが変化）
  seed: 20261120,
};
