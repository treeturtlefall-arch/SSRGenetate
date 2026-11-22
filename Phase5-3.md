それでは最後となる **Phase 5-3「召喚＆リザルトコンポジションの 16:9 レスポンシブ対応 ＆ 定量 QA 解像度フリー化」** の具体的なコード差分・実装リファレンス（全6ファイル）です！

こちらも **「Portrait（縦 `1080×1920`）のときは計算結果・座標が従来と完全一致すること」** を絶対条件として設計しています。

---

### 1. `compositions/scene-summon.css`（16:9 空間レイアウト・天頂雷撃・光柱・HUD・全幅カットイン対応）

* **ポイント**:
  * `#summon-camera` を `width: var(--canvas-w); height: var(--canvas-h);` に変更。
  * `#flash-rainbow-streak`、`#cutin-band`、`#cutin-flare` の `width: 1080px` を `width: 100%` に変更（これで `1920px` 全幅を貫きます）。
  * ファイル末尾に `html[data-resolution="landscape"]` ブロックを追加し、縦高さ `1080px`（オーブ中心 `47% ≈ 508px`）に天頂雷撃（`.sky-bolt`）の先端がビタッと刺さるように高さを `980px → 540px` に調整し、光柱と上部 HUD も16:9画面に最適化します。

```css
/* --- compositions/scene-summon.css の既存箇所修正 --- */

#summon-camera {
  position: absolute;
  inset: 0;
  width: var(--canvas-w);
  height: var(--canvas-h);
  transform-origin: 50% 47%;
  pointer-events: none;
  z-index: 10;
}

/* #flash-rainbow-streak (L363), #cutin-band (L482), #cutin-flare (L514) の width: 1080px を width: 100% に変更 */
#flash-rainbow-streak {
  /* ... */
  width: 100%;
  /* ... */
}

#cutin-band {
  /* ... */
  width: 100%;
  /* ... */
}

#cutin-flare {
  /* ... */
  width: 100%;
  /* ... */
}

/* --- compositions/scene-summon.css の末尾に追加 --- */
/* =========================================================================
 * Phase 5: Landscape (1920x1080 / 16:9) 空間バランス調整
 * ========================================================================= */
html[data-resolution="landscape"] #light-pillar,
html[data-resolution="landscape"] #light-pillar-rainbow {
  top: 36px;
  width: 460px;
  height: 940px;
  margin-left: -230px;
}

html[data-resolution="landscape"] #celestial-gate-wrap {
  top: 6%;
  width: 880px;
  height: 880px;
  margin-left: -440px;
  margin-top: -440px;
}

html[data-resolution="landscape"] #magic-circle-wrap {
  top: 56%;
  width: 900px;
  height: 900px;
  margin-left: -450px;
  margin-top: -450px;
}

html[data-resolution="landscape"] .sky-bolt {
  top: 28px;
}

html[data-resolution="landscape"] #bolt-gold {
  width: 320px;
  height: 540px;
  margin-left: -160px;
}

html[data-resolution="landscape"] #bolt-prism {
  width: 420px;
  height: 540px;
  margin-left: -210px;
}

html[data-resolution="landscape"] #orb-wrap {
  width: 360px;
  height: 360px;
  margin-left: -180px;
  margin-top: -180px;
}

html[data-resolution="landscape"] #orb-cracks {
  inset: -18px;
  width: 396px;
  height: 396px;
}

html[data-resolution="landscape"] #summon-top-hud {
  top: 54px;
}

html[data-resolution="landscape"] #cutin-band {
  height: 420px;
  margin-top: -210px;
}
```

---

### 2. `compositions/scene-summon-setup.js`（流れ星・三重螺旋・収束粒子・浮遊破片の 16:9 座標対応）

* **ポイント**:
  * `isLandscape = document.documentElement.getAttribute("data-resolution") === "landscape"` を判定します。
  * `isLandscape === false`（Portrait）のときはすべての数値が従来のまま計算されるため、**乱数消費順序（PRNG）も含めて縦版の挙動は 100% 不変**です。

```js
// --- compositions/scene-summon-setup.js の変更箇所 ---

  // 冒頭 (rng 初期化付近) にキャンバス判定を追加:
  const isLandscape = document.documentElement.getAttribute("data-resolution") === "landscape";
  const canvasW = isLandscape ? 1920 : 1080;
  const canvasH = isLandscape ? 1080 : 1920;

  // 1. 冒頭流れ星 evalIntroMeteor(p) (L46付近):
  function evalIntroMeteor(p) {
    const xStart = isLandscape ? -180 : -140;
    const dxSpan = isLandscape ? 2260 : 1370;
    const yStart = isLandscape ? 130 : 260;
    const dySpan = isLandscape ? 420 : 680;
    const arcAmp = isLandscape ? 42 : 55;

    const x = xStart + dxSpan * p;
    const y = yStart + dySpan * p - arcAmp * Math.sin(Math.PI * p);
    const dx = dxSpan;
    const dy = dySpan - arcAmp * Math.PI * Math.cos(Math.PI * p);
    const rad = Math.atan2(dy, dx);
    return {
      x: +x.toFixed(1),
      y: +y.toFixed(1),
      rad: rad,
      deg: +((rad * 180) / Math.PI).toFixed(2),
    };
  }

  // 2. RGB三重螺旋ウィスプ evalHelixPoint(sd, p, spread) (L145付近):
  function evalHelixPoint(sd, p, spread) {
    const yProg = 0.65 * p + 0.35 * (0.5 - 0.5 * Math.cos(Math.PI * p));
    const theta = sd.theta0 + Math.PI * 2 * sd.turns * (0.72 * p + 0.28 * Math.pow(p, 1.75));
    const rEnv = Math.pow(Math.max(0, 1 - p), 0.72);
    const rScale = isLandscape ? 1.22 : 1.0;
    const ySpan = isLandscape ? 450 : 755;
    const radius = Math.max(
      0,
      ((128 * (1 - p) + 265 * Math.sin(Math.PI * Math.pow(p, 0.82))) * rEnv + spread * (1 - p)) * rScale
    );
    const z = Math.sin(theta);
    const x = radius * Math.cos(theta);
    const y = -ySpan * (1 - yProg) + radius * (isLandscape ? 0.22 : 0.28) * z;
    const depthScale = 1.0 + 0.22 * z;
    const depthAlpha = 0.86 + 0.14 * z;
    return {
      x: +x.toFixed(1),
      y: +y.toFixed(1),
      depthScale: depthScale,
      depthAlpha: depthAlpha,
    };
  }

  // 3. オーブ収束粒子 convergeData (L296付近):
      const angle = (i / 28) * Math.PI * 2 + (rng() - 0.5) * 0.28;
      const dist = 390 + rng() * 240;
      const sxMul = isLandscape ? 1.35 : 1.0;
      const syMul = isLandscape ? 0.78 : 1.0;
      convergeData.push({
        el: el,
        startX: Math.cos(angle) * dist * sxMul,
        startY: Math.sin(angle) * dist * syMul,
        delay: 0.45 + rng() * 0.85,
        dur: 0.9 + rng() * 0.4,
      });

  // 4. 遠景クリスタル破片 farShards & skySparkles (L314〜374付近):
      // farShards の x0, y0:
      const x0 = 55 + rng() * (canvasW - 110);
      const y0 = isLandscape
        ? Math.max(50, Math.min(canvasH - 50, 60 + (i / 36) * (canvasH - 120) + (rng() - 0.5) * 55))
        : Math.max(80, Math.min(1840, 100 + (i / 36) * 1680 + (rng() - 0.5) * 90));

      // skySparkles の x0, y0:
      const x0 = 65 + rng() * (canvasW - 130);
      const y0 = isLandscape
        ? Math.max(45, Math.min(canvasH - 70, 55 + (i / 20) * (canvasH - 140) + (rng() - 0.5) * 55))
        : Math.max(70, Math.min(1780, 80 + (i / 20) * 1620 + (rng() - 0.5) * 90));

  // 5. 近景前ボケ破片 nearShards (L385付近):
      const isLeft = i % 2 === 0;
      const rightLaneStart = canvasW - 245; // Portrait: 835, Landscape: 1675
      const x0 = isLeft ? 50 + rng() * 195 : rightLaneStart + rng() * 195;
      const y0 = isLandscape
        ? 85 + (i >> 1) * 135 + rng() * 65
        : 150 + (i >> 1) * 245 + rng() * 110;

  // 6. 昇格時の床湧き上がりダストウェーブ waveConfigs & x0 (L420〜438付近):
    const waveConfigs = [
      {
        count: 8,
        baseTime: 3.78,
        spreadT: 0.28,
        nearRatio: 3,
        kindPool: [1, 2, 1],
        yMin: isLandscape ? 700 : 1280,
        yMax: isLandscape ? 1100 : 1940,
      },
      {
        count: 12,
        baseTime: 5.2,
        spreadT: 0.45,
        nearRatio: 4,
        kindPool: [2, 0, 1],
        yMin: isLandscape ? 720 : 1320,
        yMax: isLandscape ? 1120 : 1980,
      },
    ];
    // ループ内の x0:
        const rightWaveStart = canvasW - 265; // Portrait: 815, Landscape: 1655
        const x0 = isNear
          ? (isLeft ? 55 + rng() * 210 : rightWaveStart + rng() * 210)
          : 65 + rng() * (canvasW - 130);
```

---

### 3. `compositions/scene-result.css`（横型カード `1480×860` の配置・光学リング・中央保護マスク・オーバーレイ省スペース化）

* **ポイント**:
  * `html[data-resolution="landscape"]` 時の `#card-stage`（`top: 110px`）、背景 `#result-bg-ring`（`1380×1380` で横カードの左右・上下から円弧が美しく覗くサイズ）、下部テキストの省スペースパディング、ビネット開始位置（`64%..66%` で水平線・顔をクリア維持）を追加します。

```css
/* --- compositions/scene-result.css の末尾に追加 --- */
/* =========================================================================
 * Phase 5: Landscape (1920x1080 / Card 1480x860) レイアウト調整
 * ========================================================================= */
html[data-resolution="landscape"] #card-stage {
  top: 110px;
}

html[data-resolution="landscape"] #result-bg-ring {
  width: 1380px;
  height: 1380px;
  margin-left: -690px;
  margin-top: -690px;
}

html[data-resolution="landscape"] #result-halo,
html[data-resolution="landscape"] #result-halo-blue {
  width: 1560px;
  height: 1160px;
  margin-left: -780px;
  margin-top: -580px;
}

html[data-resolution="landscape"] #spin-spec-front {
  -webkit-mask-image: radial-gradient(
    ellipse 42% 48% at 50% 44%,
    rgba(0, 0, 0, 0.04) 0%,
    rgba(0, 0, 0, 0.25) 68%,
    rgba(0, 0, 0, 1) 100%
  );
  mask-image: radial-gradient(
    ellipse 42% 48% at 50% 44%,
    rgba(0, 0, 0, 0.04) 0%,
    rgba(0, 0, 0, 0.25) 68%,
    rgba(0, 0, 0, 1) 100%
  );
}

html[data-resolution="landscape"] #holo-mask-zone {
  -webkit-mask-image: radial-gradient(
    ellipse 46% 50% at 50% 44%,
    transparent 0%,
    transparent 66%,
    rgba(0, 0, 0, 0.26) 84%,
    rgba(0, 0, 0, 0.90) 100%
  );
  mask-image: radial-gradient(
    ellipse 46% 50% at 50% 44%,
    transparent 0%,
    transparent 66%,
    rgba(0, 0, 0, 0.26) 84%,
    rgba(0, 0, 0, 0.90) 100%
  );
}

html[data-resolution="landscape"] .photo-vignette {
  background:
    linear-gradient(
      to bottom var(--in-oklab),
      rgba(6, 9, 22, 0.24) 0%,
      transparent 16%,
      transparent 62%,
      rgba(6, 9, 22, var(--vignette-mid-a, 0.54)) 79%,
      rgba(4, 6, 17, var(--vignette-bot-a, 0.88)) 100%
    ),
    radial-gradient(circle at 50% 44% var(--in-oklab), transparent 62%, rgba(4, 6, 17, 0.30) 100%);
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="royal-fantasy"] .photo-vignette {
  background: linear-gradient(
    to bottom,
    rgba(6, 9, 20, 0) 0%,
    rgba(6, 9, 20, 0) 65%,
    rgba(6, 9, 20, var(--vignette-mid-a, 0.40)) 82%,
    rgba(6, 9, 20, var(--vignette-bot-a, 0.76)) 100%
  );
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="pop-horizontal"] .photo-vignette {
  background: linear-gradient(
    to bottom,
    rgba(12, 10, 22, 0) 0%,
    rgba(12, 10, 22, 0) 64%,
    rgba(12, 10, 22, var(--vignette-mid-a, 0.22)) 80%,
    rgba(12, 10, 22, var(--vignette-bot-a, 0.56)) 100%
  );
}

html[data-resolution="landscape"] #card-overlay-layer {
  padding: 20px 48px 34px;
  gap: 8px;
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="royal-fantasy"] #card-overlay-layer {
  padding: 20px 48px 32px;
  gap: 6px;
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="pop-horizontal"] #card-overlay-layer {
  padding: 20px 44px 34px;
  gap: 6px;
}

html[data-resolution="landscape"] .star-item {
  width: 74px;
  height: 74px;
  margin: 0 -8px;
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="royal-fantasy"] #ssr-emblem {
  top: 22px;
  left: 32px;
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="royal-fantasy"] #attr-badge {
  top: 28px;
  right: 30px;
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="pop-horizontal"] #ssr-emblem {
  top: 24px;
  left: 36px;
}

html[data-resolution="landscape"] .card-front-inner[data-typo-layout="pop-horizontal"] #attr-badge {
  top: 32px;
  right: 30px;
}
```

---

### 4. `compositions/scene-result-setup.js`（スパークル・金箔・玉ボケのカード半寸相対化 ＆ ホロ走査距離）

* **ポイント**:
  * **スパークル (`sparkleClusters`)**: 現行座標は縦カード半寸（`baseHalfW = 450, baseHalfH = 795`）の外縁に合わせて設計されています。
    * ここで「カード端からの相対オフセット（例: `|x| - 450`）」を保つか、または比率スケーリング `xScale = cardHalfW / 450`, `yScale = cardHalfH / 795` を使うかですが、単純比率スケーリングだと `494 * (740/450) = 812px` になりカード端（`740px`）から外へ離れすぎます。
    * そのため、**「カード内側の比率＋カード外縁からのオフセット保存」**（`|x| >= 430` の外縁スパークルは `sign * (cardHalfW + (|x| - 450))`、内寄りスパークルは `x * (cardHalfW / 450)`）で変換すると、**縦カード時は `100%` 元座標そのまま、横カード時は `1480×860` の四隅・外枠すぐ外側にピタッと吸い付く**最高の配置になります！
  * **金箔フレーク (`flakeData`)**: `startX = side * ((cardHalfW - 90) + rng() * 85)`（縦時は `360 + rng() * 85` で完全一致！）、`startY = (rng() - 0.5) * (cardH * 0.742138)`（縦時は `1180`）。
  * **玉ボケ (`bokehData`)**: 左右レーン `side * ((cardHalfW - 15) + rng() * 90)`（縦時は `435 + rng() * 90` で完全一致！）、上下レーン `±((cardHalfH - 20) + rng() * (isLandscape ? 85 : 145))`（縦時は `775 + rng() * 145` で完全一致！）。

```js
// --- compositions/scene-result-setup.js の変更箇所 ---

  // 1. typoManifestRoot 読み込み直後 (L92付近) にカード・キャンバス寸法を解決:
  const isLandscape = document.documentElement.getAttribute("data-resolution") === "landscape";
  const dims = typoManifestRoot.dimensions || {};
  const cardW = isLandscape ? (dims.cardW || 1480) : 900;
  const cardH = isLandscape ? (dims.cardH || 860) : 1590;
  const cardHalfW = cardW * 0.5; // Portrait: 450, Landscape: 740
  const cardHalfH = cardH * 0.5; // Portrait: 795, Landscape: 430

  // 2. モダンレイアウト時の左右バッジ水平中心ライン同期 (L158付近):
      if (ssrH > 0 && attrH > 0) {
        const baseSsrTop = isLandscape
          ? (typoLayout === "royal-fantasy" ? 22 : 24)
          : (typoLayout === "royal-fantasy" ? 30 : 34);
        const alignedAttrTop = baseSsrTop + Math.round((ssrH - attrH) / 2);
        attrEl.style.top = alignedAttrTop + "px";
      }

  // 3. スパークル座標のカード外縁追従変換ヘルパー (sparkleData ループ内 L244付近):
  function mapSparkleX(bx) {
    if (!isLandscape) return bx;
    const s = bx < 0 ? -1 : 1;
    const ax = Math.abs(bx);
    return ax >= 430 ? s * (cardHalfW + (ax - 450)) : Math.round(bx * (cardHalfW / 450));
  }
  function mapSparkleY(by) {
    if (!isLandscape) return by;
    const s = by < 0 ? -1 : 1;
    const ay = Math.abs(by);
    return ay >= 760 ? s * (cardHalfH + (ay - 795)) : Math.round(by * (cardHalfH / 795));
  }

    // sparkleData.push 内:
    const mappedX = mapSparkleX(spec.x);
    const mappedY = mapSparkleY(spec.y);
    sparkleData.push({
      el: sp,
      tier: spec.tier,
      group: spec.group,
      endX: mappedX + (rng() - 0.5) * jitter,
      endY: mappedY + (rng() - 0.5) * jitter,
      rot: (rng() - 0.5) * 44,
      finalScale: 0.90 + rng() * 0.20,
      baseAlpha: baseAlpha,
      startAt: at(8.68 + (i % 7) * 0.09),
    });

  // 4. 3D 金箔・プリズム結晶片 (L286付近 — Portrait時は 360, 1180 と 100% 一致):
    const side = i % 2 === 0 ? -1 : 1;
    const startX = side * ((cardHalfW - 90) + rng() * 85);
    const startY = (rng() - 0.5) * (isLandscape ? 640 : 1180);
    const midX = startX + side * (55 + rng() * 95);
    const midY = startY - (isLandscape ? (45 + rng() * 60) : (70 + rng() * 90));
    const endX = midX + side * (20 + rng() * 55);
    const endY = midY + (isLandscape ? (120 + rng() * 95) : (190 + rng() * 140));

  // 5. 玉ボケ光粒 (L334付近 — Portrait時は 435, 1580, 920, 775 と 100% 一致):
    const side = i % 2 === 0 ? -1 : 1;
    let endX;
    let endY;
    if (i % 4 < 2) {
      // 左右の外縁レーン
      endX = side * ((cardHalfW - 15) + rng() * (isLandscape ? 145 : 90));
      endY = (rng() - 0.5) * (cardH - 10);
    } else {
      // 上下の外縁レーン
      endX = (rng() - 0.5) * (cardW + 20);
      endY = (i % 4 === 2 ? -1 : 1) * ((cardHalfH - 20) + rng() * (isLandscape ? 85 : 145));
    }

  // 6. スペキュラ＆ホロスイープ走査距離を STATE に公開 (L356付近):
  const extraSpanX = isLandscape ? (cardW - 900) : 0; // Portrait: 0, Landscape: +580
  window.SSR_RESULT_STATE = {
    at: at,
    cfg: cfg,
    isLandscape: isLandscape,
    spinSpecBackEndX: 1420 + extraSpanX,
    spinSpecFrontEndX: 1460 + extraSpanX,
    holoSweepEndX: 1850 + extraSpanX,
    resultRingMode: resultRingMode,
    // ...以下既存通り
  };
```

---

### 5. `compositions/scene-result.html`（回転スペキュラとホログラムスイープの走査距離連動）

`scene-result.html` 内の3箇所の固定値（`1420`, `1460`, `1850`）を `st.spinSpecBackEndX`, `st.spinSpecFrontEndX`, `st.holoSweepEndX` に置き換えます（Portrait 時は `1420 / 1460 / 1850` のままです）。

```js
// --- compositions/scene-result.html L170〜188 付近 ---

        // Spin Specular Highlights & Back Charge Anticipation
        tl.fromTo("#spin-spec-back", { x: -120, opacity: 0 }, { x: st.spinSpecBackEndX || 1420, opacity: 0.90, duration: 0.42, ease: "sine.inOut" }, at(7.74));
        // ...
        tl.fromTo("#spin-spec-front", { x: -160, opacity: 0 }, { x: st.spinSpecFrontEndX || 1460, opacity: 0.88, duration: 0.50, ease: "power2.out" }, at(8.48));
        // ...

        // Center-Attenuated Prism Holo Sweeps & Frame Rim Shimmer
        const holoEndX = st.holoSweepEndX || 1850;
        tl.fromTo("#holo-sweep-1", { x: 0 }, { x: holoEndX, duration: 1.10, ease: "power2.inOut" }, at(8.92));
        // ...
        tl.fromTo("#holo-sweep-2", { x: 0 }, { x: holoEndX, duration: 1.10, ease: "power2.inOut" }, at(10.45));
```

---

### 6. `scripts/qa_video.py`（縮小デコード解像度の縦横自動追従）

`analyze_video()` の `decode_gray_frames(video_path)` 呼び出し（L158）で、動画ストリームの `width > height` を判定して `480×270`（横）と `270×480`（縦）を切り替えます。

```python
# --- scripts/qa_video.py L155〜162 付近 ---
def analyze_video(video_path: Path, check_audio: bool = False) -> Dict[str, Any]:
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    info = probe_streams(video_path)
    fps = info["fps"]
    is_landscape = info["width"] > info["height"]
    dec_w, dec_h = (480, 270) if is_landscape else (270, 480)
    frames = decode_gray_frames(video_path, w=dec_w, h=dec_h)
```

---

### ローカルAIでの検証手順（Phase 5 テストコマンド）

実装適用後、ローカル環境で以下の順でテストすると縦・横両方の品質とデグレゼロを一発で確認できます。

```bash
# 1. まず縦モード (portrait) で従来通りエラー0＆デグレなしを確認
npm run build:assets
npm run check

# 2. 横モード (landscape) へ切り替えてビルド＆静的・レイアウト検査
npm run render -- --dry-run --variables '{"orientation":"landscape"}'
python scripts/render_typography.py --overrides '{"orientation":"landscape"}'
python scripts/render_material.py
python scripts/render_optics.py
npm run check

# 3. 横モードの重点フレームをスナップショット抽出して目視確認
npx hyperframes snapshot --at 0.8,1.2,3.4,4.32,5.64,5.74,6.4,8.48,9.20,11.0,14.0

# 4. 横モードの本レンダリング＆定量QA（1920x1080 で全項目 PASS を確認）
npm run render -- --variables '{"orientation":"landscape"}'
npm run qa -- --check-audio
```

ここまで揃っていれば、ローカル環境のAIエージェントが迷うことなく Phase 5 を完走できるはずです。また実装中に微調整したい箇所が出てきたらいつでもお声がけください！