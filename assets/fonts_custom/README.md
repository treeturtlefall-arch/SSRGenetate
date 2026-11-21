# ローカル専用カスタムフォント配置フォルダ (`assets/fonts_custom/`)

商用利用可能・再配布不可のフリーフォントや有料購入フォントを、リポジトリへコミットせずにローカル環境だけで利用するための隔離フォルダです（`.gitignore` 対象）。

## 使い方

1. このフォルダに `.ttf` / `.otf` ファイルを配置します。
2. 任意で `fonts.json` を作成してスロット別の上書きや視覚サイズ補正係数（`norm_factor`）を指定できます：

```json
{
  "slots": {
    "title": "MyCustomFont.ttf",
    "subtitle": "MySubFont.ttf"
  },
  "norm_factors": {
    "MyCustomFont.ttf": 1.0
  }
}
```

3. `card-config.js` の `typography.font.slots.title.family` に直接ファイル名を指定しても、`assets/fonts_custom/` が最優先で探索されます。
4. フォント未配置・ファイル不在時は、自動的に同梱の `assets/fonts/` へフォールバックしてビルドが継続されます。
