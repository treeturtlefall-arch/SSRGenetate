/**
 * SSRGenerate — カード設定ファイル
 *
 * 写真やカード上のテキスト・ステータスを差し替える場合は、このファイルを編集してください。
 * 写真は `assets/` フォルダに配置し、`photo` に相対パスを指定します。
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
  photoZoom: 1.04,

  // レアリティ・星の数
  rarity: "SSR",
  stars: 5,

  // カード情報（日本語対応）
  badgeText: "NEW ARRIVAL",
  summonLabel: "LEGENDARY SUMMON",
  attribute: "光属性 / SMILE",
  subtitle: "【奇跡のテーブル55】",
  title: "ちいさな美食家",
  flavor: "黄金のたまご焼きを前に、世界一の幸せを召喚する。",

  // カード下部ステータス（最大3項目）
  stats: [
    { label: "HP", value: "9999" },
    { label: "CUTE", value: "MAX" },
    { label: "LUCK", value: "★★★★★" },
  ],

  // シリアル番号風フッター表記
  cardNo: "NO.055-SSR",

  // パーティクル配置用の決定論シード値（数値を変えると星屑や紙吹雪の配置パターンが変化）
  seed: 20261120,
};
