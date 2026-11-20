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
  photoPosition: "50% 42%",
  photoZoom: 1.02,

  // レアリティ・星の数
  rarity: "SSR",
  stars: 5,

  // カード情報（空文字・空配列にすると非表示になります）
  attribute: "", // 例: "光属性 / SMILE"（デフォルトはミニマル・写真主役のため非表示）
  subtitle: "【奇跡のテーブル55】",
  title: "ちいさな美食家",
  flavor: "黄金のたまご焼きを前に、世界一の幸せを召喚する。",

  // カード下部ステータス（デフォルトは写真主役のため非表示。最大3項目まで任意表示可）
  stats: [],

  // シリアル番号風フッター表記（カード右下隅へ控えめに刻印）
  cardNo: "NO.055-SSR",

  // 文字ヒューマナイズ＆箔物理設定（scripts/render_typography.py が参照）
  typography: {
    preset: "foil-brush", // "foil-brush" | "handwritten-sign" | "crisp-emboss"
    wobble: 28,           // 0..100（0=完全整列, 28=品のある人間味, 50=手書き感）
    foilGlitter: 0.42,    // 0.0..1.0（金箔・銀箔の微細ラメ反射強度）
    paperGrain: 0.35,     // 0.0..1.0（下地シボによるインク/箔の乗り変調）
    seed: 20261120,
  },

  // パーティクル配置用の決定論シード値（数値を変えると星屑や紙吹雪の配置パターンが変化）
  seed: 20261120,
};
