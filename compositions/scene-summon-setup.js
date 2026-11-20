/**
 * SSRGenerate — Scene 1-2 (Summon & Promotion) Deterministic Setup
 *
 * scene-summon.html の行数を300行未満に保ちつつ、決定論的PRNGによる
 * 収束粒子・上空2層パララックス浮遊クリスタル破片・星屑・タイポマニフェスト適用を行う。
 */
(function () {
  function createRng(seed) {
    let s = seed >>> 0;
    return function () {
      s = (s + 0x6d2b79f5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const baseCfg = window.SSR_CARD_CONFIG || {};
  const seed = typeof baseCfg.seed === "number" ? baseCfg.seed : 20261120;
  const chromaShockPx =
    typeof (baseCfg.material || {}).chromaShockPx === "number"
      ? baseCfg.material.chromaShockPx
      : 9;
  const sumCfg = baseCfg.summon || {};
  const mcSpeed =
    typeof sumCfg.magicCircleSpeed === "number" && Number.isFinite(sumCfg.magicCircleSpeed)
      ? sumCfg.magicCircleSpeed
      : 1.0;
  const mcCurve = typeof sumCfg.magicCircleCurve === "string" ? sumCfg.magicCircleCurve : "dramatic";
  const mcRatios =
    Array.isArray(sumCfg.magicCircleRingRatios) && sumCfg.magicCircleRingRatios.length === 3
      ? sumCfg.magicCircleRingRatios
      : [1.0, -1.3, 1.7];

  const rng = createRng(seed);

  // 1. カットイン箔タイポマニフェスト適用
  const typoItems = (window.SSR_TYPO_MANIFEST && window.SSR_TYPO_MANIFEST.items) || {};
  [
    ["cutinSub", "cutin-sub-img"],
    ["cutinMain", "cutin-main-img"],
  ].forEach(function (pair) {
    const entry = typoItems[pair[0]];
    const el = document.getElementById(pair[1]);
    if (entry && el && entry.src) {
      el.style.backgroundImage = 'url("../' + entry.src.replace(/^\.\//, "") + '")';
      el.style.width = entry.width + "px";
      el.style.height = entry.height + "px";
    }
  });

  // 2. [C] 冒頭降臨の流体シルクリボン・ウィスプ (3筋 × 18ノード + 余韻スターダスト18粒)
  const wispContainer = document.getElementById("wisp-streams");
  const wispNodes = [];
  const wispDusts = [];
  if (wispContainer) {
    const streamDefs = [
      { delay: 0.05, dur: 1.32, startX: -18, startY: -745, sway1: 135, sway2: -95 },
      { delay: 0.12, dur: 1.26, startX: -105, startY: -735, sway1: -185, sway2: 130 },
      { delay: 0.19, dur: 1.22, startX: 105, startY: -735, sway1: 180, sway2: -125 },
    ];
    const nPerStream = 18;
    streamDefs.forEach(function (sd, sIdx) {
      for (let k = 0; k < nPerStream; k++) {
        const tLag = k / (nPerStream - 1);
        const isVeil = k > 0 && k % 4 === 0;
        const el = document.createElement("div");
        el.className = "wisp-node";
        el.setAttribute("data-layout-allow-overflow", "");
        // 存在感のある力強い光核から後方へしなやかに先細りさせ、オーロラ霞で豊かに包む
        const size = isVeil ? Math.round(168 + tLag * 48) : Math.round(124 * (1 - tLag * 0.52));
        el.style.cssText =
          "width:" +
          size +
          "px;height:" +
          size +
          "px;margin-left:" +
          (-size / 2).toFixed(1) +
          "px;margin-top:" +
          (-size / 2).toFixed(1) +
          "px";
        wispContainer.appendChild(el);

        const spread = (rng() - 0.5) * tLag * 26;
        const peakAlpha =
          k === 0
            ? 1.0
            : isVeil
              ? +(0.26 * (1 - tLag * 0.45)).toFixed(3)
              : +(0.72 * Math.pow(1 - tLag, 1.25)).toFixed(3);

        wispNodes.push({
          el: el,
          sd: sd,
          k: k,
          tLag: tLag,
          isVeil: isVeil,
          startAt: +(sd.delay + k * 0.015).toFixed(3),
          dur: sd.dur,
          spread: spread,
          peakAlpha: peakAlpha,
        });
      }

      // 軌道からふわっとこぼれ落ちて漂う微細スターダスト (各ストリーム6粒)
      for (let d = 0; d < 6; d++) {
        const p = 0.18 + (d / 6) * 0.68;
        const el = document.createElement("div");
        el.className = "sky-star";
        el.setAttribute("data-layout-allow-overflow", "");
        const dSize = 26 + Math.floor(rng() * 20);
        const spCol = (sIdx + d) % 2 === 0 ? "cyan" : "white";
        el.style.cssText =
          "left:50%;top:47%;width:" +
          dSize +
          "px;height:" +
          dSize +
          "px;margin-left:" +
          (-dSize / 2).toFixed(1) +
          "px;margin-top:" +
          (-dSize / 2).toFixed(1) +
          'px;background-image:url("../assets/generated/opt_sparkle_' +
          spCol +
          '.png")';
        wispContainer.appendChild(el);
        const yAt = sd.startY * (1 - p);
        const xAt = p < 0.5 ? sd.sway1 * Math.sin(p * Math.PI * 2) : sd.sway2 * Math.sin((p - 0.5) * Math.PI * 2);
        wispDusts.push({
          el: el,
          x0: +(xAt + (rng() - 0.5) * 28).toFixed(1),
          y0: +yAt.toFixed(1),
          dx: +((rng() - 0.5) * 56).toFixed(1),
          dy: +(-18 + rng() * 44).toFixed(1),
          appearAt: +(sd.delay + p * sd.dur + 0.04).toFixed(3),
          dur: +(0.38 + rng() * 0.24).toFixed(3),
        });
      }
    });
  }

  // 3. オーブ収束粒子 (28個)
  const convergeContainer = document.getElementById("converge-particles");
  const convergeData = [];
  const convergeColors = ["#a4d4f7", "#5aa8eb", "#f4f9ff", "#f2dfb3", "#e88db4"];
  if (convergeContainer) {
    for (let i = 0; i < 28; i++) {
      const el = document.createElement("div");
      el.className = "c-particle";
      el.setAttribute("data-layout-allow-overflow", "");
      const size = 8 + Math.floor(rng() * 14);
      const color = convergeColors[i % convergeColors.length];
      el.style.cssText =
        "width:" +
        size +
        "px;height:" +
        size +
        "px;margin-left:" +
        -size / 2 +
        "px;margin-top:" +
        -size / 2 +
        "px;background:" +
        color +
        ";box-shadow:0 0 " +
        size * 2 +
        "px " +
        color;
      convergeContainer.appendChild(el);
      const angle = (i / 28) * Math.PI * 2 + (rng() - 0.5) * 0.28;
      const dist = 390 + rng() * 240;
      convergeData.push({
        el: el,
        startX: Math.cos(angle) * dist,
        startY: Math.sin(angle) * dist,
        delay: 0.45 + rng() * 0.85,
        dur: 0.9 + rng() * 0.4,
      });
    }
  }

  // 3. [D] 全画面縦フルレンジ 2層パララックス浮遊クリスタル破片・星屑 & 昇格時の床湧き上がりダストウェーブ
  const farContainer = document.getElementById("sky-shards-far");
  const nearContainer = document.getElementById("sky-shards-near");
  const farShards = [];
  const nearShards = [];
  const waveShards = [];
  const skySparkles = [];

  if (farContainer) {
    // 遠景クリスタル破片 (36個: 縦フルレンジ y=100..1780px を層別サンプリング、遠景は控えめ上昇で視差強調)
    for (let i = 0; i < 36; i++) {
      const el = document.createElement("div");
      const kind = i % 3;
      el.className = "sky-shard sky-shard-far";
      el.setAttribute("data-layout-allow-overflow", "");
      const size = 22 + Math.floor(rng() * 32);
      const x0 = 55 + rng() * 970;
      const y0 = Math.max(80, Math.min(1840, 100 + (i / 36) * 1680 + (rng() - 0.5) * 90));
      el.style.cssText =
        "width:" +
        size +
        "px;height:" +
        size +
        "px;left:" +
        x0.toFixed(1) +
        "px;top:" +
        y0.toFixed(1) +
        "px;margin-left:" +
        (-size / 2).toFixed(1) +
        "px;margin-top:" +
        (-size / 2).toFixed(1) +
        'px;background-image:url("../assets/generated/opt_shard_far_' +
        kind +
        '.png")';
      farContainer.appendChild(el);
      farShards.push({
        el: el,
        rot0: -45 + rng() * 90,
        drot1: (rng() < 0.5 ? -1 : 1) * (24 + rng() * 40),
        drot2: (rng() < 0.5 ? -1 : 1) * (55 + rng() * 85),
        dx1: (rng() - 0.5) * 42,
        dy1: -(35 + rng() * 48),
        dy2: -(85 + rng() * 80),
        dy3: -(170 + rng() * 130),
        baseAlpha: 0.36 + rng() * 0.36,
        scale0: 0.68 + rng() * 0.44,
      });
    }

    // 縦全域の微細星屑スパークル (20個: y=80..1700px)
    const spColors = ["cyan", "white", "gold", "pink"];
    for (let i = 0; i < 20; i++) {
      const el = document.createElement("div");
      const cname = spColors[i % spColors.length];
      el.className = "sky-star sky-star-g" + (i % 3);
      el.setAttribute("data-layout-allow-overflow", "");
      const size = 18 + Math.floor(rng() * 20);
      const x0 = 65 + rng() * 950;
      const y0 = Math.max(70, Math.min(1780, 80 + (i / 20) * 1620 + (rng() - 0.5) * 90));
      el.style.cssText =
        "width:" +
        size +
        "px;height:" +
        size +
        "px;left:" +
        x0.toFixed(1) +
        "px;top:" +
        y0.toFixed(1) +
        "px;margin-left:" +
        (-size / 2).toFixed(1) +
        "px;margin-top:" +
        (-size / 2).toFixed(1) +
        'px;background-image:url("../assets/generated/opt_sparkle_' +
        cname +
        '.png")';
      farContainer.appendChild(el);
      skySparkles.push({ el: el, group: i % 3 });
    }
  }

  if (nearContainer) {
    // 近景前ボケ大粒クリスタル破片 (14個: 左右端寄り・縦フルレンジ y=150..1860px で中央オーブ/カットインを避ける)
    for (let i = 0; i < 14; i++) {
      const el = document.createElement("div");
      const kind = (i + 1) % 3;
      el.className = "sky-shard sky-shard-near";
      el.setAttribute("data-layout-allow-overflow", "");
      const size = 78 + Math.floor(rng() * 46);
      const isLeft = i % 2 === 0;
      const x0 = isLeft ? 50 + rng() * 195 : 835 + rng() * 195;
      const y0 = 150 + (i >> 1) * 245 + rng() * 110;
      el.style.cssText =
        "width:" +
        size +
        "px;height:" +
        size +
        "px;left:" +
        x0.toFixed(1) +
        "px;top:" +
        y0.toFixed(1) +
        "px;margin-left:" +
        (-size / 2).toFixed(1) +
        "px;margin-top:" +
        (-size / 2).toFixed(1) +
        'px;background-image:url("../assets/generated/opt_shard_near_' +
        kind +
        '.png")';
      nearContainer.appendChild(el);
      nearShards.push({
        el: el,
        rot0: -60 + rng() * 120,
        drot1: (isLeft ? 1 : -1) * (38 + rng() * 48),
        drot2: (isLeft ? 1 : -1) * (85 + rng() * 105),
        dx1: (isLeft ? 1 : -1) * (18 + rng() * 28),
        dy1: -(90 + rng() * 70),
        dy2: -(195 + rng() * 115),
        dy3: -(360 + rng() * 180),
        baseAlpha: 0.34 + rng() * 0.24,
        scale0: 0.85 + rng() * 0.3,
      });
    }
  }

  // 昇格時の「床魔法陣からの後発ダストウェーブ」(金8個 @3.78s + 虹12個 @5.20s = 計20個)
  if (farContainer && nearContainer) {
    const waveConfigs = [
      // 金昇格ウェーブ (8個: 遠景5 + 近景3)
      { count: 8, baseTime: 3.78, spreadT: 0.28, nearRatio: 3, kindPool: [1, 2, 1], yMin: 1280, yMax: 1940 },
      // 虹昇格ウェーブ (12個: 遠景8 + 近景4)
      { count: 12, baseTime: 5.2, spreadT: 0.45, nearRatio: 4, kindPool: [2, 0, 1], yMin: 1320, yMax: 1980 },
    ];
    waveConfigs.forEach(function (wc) {
      for (let i = 0; i < wc.count; i++) {
        const isNear = i < wc.nearRatio;
        const container = isNear ? nearContainer : farContainer;
        const el = document.createElement("div");
        const kind = wc.kindPool[i % wc.kindPool.length];
        el.className = "sky-shard " + (isNear ? "sky-shard-near" : "sky-shard-far");
        el.setAttribute("data-layout-allow-overflow", "");
        const size = isNear ? 76 + Math.floor(rng() * 44) : 20 + Math.floor(rng() * 26);
        const isLeft = i % 2 === 0;
        const x0 = isNear ? (isLeft ? 55 + rng() * 210 : 815 + rng() * 210) : 65 + rng() * 950;
        const y0 = wc.yMin + rng() * (wc.yMax - wc.yMin);
        el.style.cssText =
          "width:" +
          size +
          "px;height:" +
          size +
          "px;left:" +
          x0.toFixed(1) +
          "px;top:" +
          y0.toFixed(1) +
          "px;margin-left:" +
          (-size / 2).toFixed(1) +
          "px;margin-top:" +
          (-size / 2).toFixed(1) +
          'px;background-image:url("../assets/generated/opt_shard_' +
          (isNear ? "near" : "far") +
          "_" +
          kind +
          '.png")';
        container.appendChild(el);
        waveShards.push({
          el: el,
          isNear: isNear,
          isGoldWave: wc.baseTime < 4.5,
          spawnAt: +(wc.baseTime + rng() * wc.spreadT).toFixed(3),
          rot0: -50 + rng() * 100,
          drot: (rng() < 0.5 ? -1 : 1) * (65 + rng() * 95),
          dx: (rng() - 0.5) * (isNear ? 70 : 54),
          riseY: -(isNear ? 340 + rng() * 260 : 210 + rng() * 190),
          peakAlpha: isNear ? 0.36 + rng() * 0.24 : 0.44 + rng() * 0.36,
          scale0: 0.72 + rng() * 0.42,
        });
      }
    });
  }

  function bindLoopsAndHelpers(tl) {
    const dramaticSegs = [
      [0, 1.45, 32, "power2.out"],
      [1.45, 2.68, 26, "none"],
      [2.68, 3.1, 28, "power2.out"],
      [3.1, 3.78, 14, "power2.inOut"],
      [3.78, 4.3, 72, "power2.out"],
      [4.3, 4.56, 12, "power3.out"],
      [4.56, 4.86, 0, "none"],
      [4.86, 7.06, 580, "power2.in"],
    ];
    const mcSegs =
      mcCurve === "steady"
        ? [[0.15, 7.15, 210, "power1.in"]]
        : mcCurve === "overdrive"
          ? dramaticSegs.map(function (s) {
              return [s[0], s[1], s[2] * 1.45, s[3]];
            })
          : dramaticSegs;
    [
      ["#mc-ring-outer, #mc-gold-outer, #mc-rb-outer", mcRatios[0]],
      ["#mc-ring-mid, #mc-gold-mid, #mc-rb-mid", mcRatios[1]],
      ["#mc-ring-inner, #mc-gold-inner, #mc-rb-inner", mcRatios[2]],
      ["#gate-blue-outer, #gate-gold-outer, #gate-rb-outer", -0.75],
      ["#gate-blue-inner, #gate-gold-inner, #gate-rb-inner", 1.25],
    ].forEach(function (grp) {
      const sel = grp[0];
      const mult = mcSpeed * (typeof grp[1] === "number" ? grp[1] : 1);
      let acc = 0;
      tl.set(sel, { rotation: 0 }, 0);
      mcSegs.forEach(function (seg) {
        acc += seg[2] * mult;
        tl.to(sel, { rotation: acc, duration: +(seg[1] - seg[0]).toFixed(4), ease: seg[3] }, seg[0]);
      });
    });

    convergeData.forEach(function (p) {
      tl.fromTo(
        p.el,
        { x: p.startX, y: p.startY, opacity: 0, scale: 1.2 },
        { x: 0, y: 0, opacity: 0.95, scale: 0.25, duration: p.dur, ease: "power2.in" },
        p.delay
      );
      tl.to(p.el, { opacity: 0, duration: 0.1 }, p.delay + p.dur);
    });

    // 流体シルクリボン・ウィスプ: Y軸(連続sine/power降下) × X軸(3セグメント連続sine.inOutしなり) による完全スムーズ曲線
    wispNodes.forEach(function (wn) {
      const sd = wn.sd;
      const t0 = wn.startAt;
      const d1 = +(wn.dur * 0.36).toFixed(4);
      const d2 = +(wn.dur * 0.36).toFixed(4);
      const d3 = +(wn.dur - d1 - d2).toFixed(4);

      tl.set(
        wn.el,
        { x: sd.startX, y: sd.startY, scale: wn.k === 0 ? 0.85 : 0.65, opacity: 0 },
        0
      );
      // 立ち上がりフェード
      tl.to(wn.el, { opacity: wn.peakAlpha, scale: 1.0, duration: 0.16, ease: "sine.out" }, t0);
      // Y軸: 1本の滑らかな連続曲線で天蓋の穴からオーブ中心へ吸い込まれる
      tl.to(wn.el, { y: 0, duration: wn.dur, ease: "sine.inOut" }, t0);
      // X軸: sine.inOut の連続S字しなりで流体のように柔らかく蛇行して中央(0)へ収束
      tl.to(wn.el, { x: +(sd.sway1 + wn.spread).toFixed(1), duration: d1, ease: "sine.inOut" }, t0);
      tl.to(wn.el, { x: +(sd.sway2 - wn.spread * 0.7).toFixed(1), duration: d2, ease: "sine.inOut" }, +(t0 + d1).toFixed(4));
      tl.to(wn.el, { x: 0, duration: d3, ease: "sine.inOut" }, +(t0 + d1 + d2).toFixed(4));
      // 着弾時: 柔らかい余韻としてふわっと膨らみながら溶ける
      tl.to(
        wn.el,
        {
          scale: wn.isVeil ? 2.1 : 1.55,
          opacity: 0,
          duration: +(0.24 + (1 - wn.tLag) * 0.14).toFixed(3),
          ease: "sine.out",
        },
        +(t0 + wn.dur - 0.06).toFixed(4)
      );
    });

    wispDusts.forEach(function (wd) {
      tl.set(wd.el, { x: wd.x0, y: wd.y0, scale: 0.4, opacity: 0 }, 0);
      tl.to(wd.el, { opacity: 0.82, scale: 1.08, duration: 0.12, ease: "sine.out" }, wd.appearAt);
      tl.to(wd.el, { x: wd.x0 + wd.dx, y: wd.y0 + wd.dy, duration: wd.dur, ease: "sine.out" }, wd.appearAt);
      tl.to(wd.el, { opacity: 0, scale: 0.35, duration: +(wd.dur * 0.72).toFixed(3), ease: "sine.in" }, +(wd.appearAt + wd.dur * 0.28).toFixed(3));
    });

    farShards.concat(nearShards).forEach(function (s) {
      tl.fromTo(
        s.el,
        { x: 0, y: 0, rotation: s.rot0, opacity: 0, scale: s.scale0 * 0.72 },
        { x: s.dx1, y: s.dy1, rotation: s.rot0 + s.drot1, opacity: s.baseAlpha, scale: s.scale0, duration: 3.78, ease: "sine.out" },
        0.05
      );
      tl.to(
        s.el,
        { y: s.dy2, rotation: s.rot0 + s.drot1 * 1.85, opacity: Math.min(0.95, s.baseAlpha * 1.28), duration: 1.28, ease: "power1.inOut" },
        3.78
      );
      tl.to(
        s.el,
        { y: s.dy3, rotation: s.rot0 + s.drot1 * 1.85 + s.drot2, scale: s.scale0 * 1.24, opacity: +(s.baseAlpha * 0.85).toFixed(3), duration: 1.8, ease: "power2.out" },
        5.2
      );
    });

    // 昇格時の床魔法陣からの後発ダストウェーブ（親コンテナの真空暗転 5.06-5.18s と自動同期）
    waveShards.forEach(function (ws) {
      const endT = 7.0;
      const moveDur = Math.max(0.5, +(endT - ws.spawnAt).toFixed(3));
      tl.set(ws.el, { x: 0, y: 0, rotation: ws.rot0, opacity: 0, scale: ws.scale0 * 0.65 }, 0);
      tl.to(ws.el, { opacity: ws.peakAlpha, scale: ws.scale0, duration: 0.34, ease: "sine.out" }, ws.spawnAt);
      tl.to(
        ws.el,
        {
          x: +ws.dx.toFixed(1),
          y: +ws.riseY.toFixed(1),
          rotation: +(ws.rot0 + ws.drot).toFixed(1),
          scale: +(ws.scale0 * 1.18).toFixed(2),
          duration: moveDur,
          ease: ws.isGoldWave ? "power1.inOut" : "power2.out",
        },
        ws.spawnAt
      );
    });

    [0, 1, 2].forEach(function (g) {
      tl.fromTo(
        ".sky-star-g" + g,
        { opacity: 0.18, scale: 0.68 },
        { opacity: 0.82, scale: 1.12, duration: 0.62, ease: "sine.inOut", yoyo: true, repeat: 9 },
        0.1 + g * 0.21
      );
    });
  }

  function addChromaShock(tl, targetSel, startAt, peakPx) {
    if (!peakPx || peakPx <= 0) return;
    tl.set(targetSel, { filter: "url(#chroma-shock)" }, startAt);
    tl.fromTo("#chroma-r-off", { attr: { dx: 0 } }, { attr: { dx: -peakPx }, duration: 0.04, ease: "power2.out", immediateRender: false }, startAt);
    tl.fromTo("#chroma-b-off", { attr: { dx: 0 } }, { attr: { dx: peakPx }, duration: 0.04, ease: "power2.out", immediateRender: false }, startAt);
    tl.to("#chroma-r-off", { attr: { dx: peakPx * 0.45 }, duration: 0.06, ease: "power1.inOut" }, startAt + 0.04);
    tl.to("#chroma-b-off", { attr: { dx: -peakPx * 0.45 }, duration: 0.06, ease: "power1.inOut" }, startAt + 0.04);
    tl.to("#chroma-r-off", { attr: { dx: 0 }, duration: 0.1, ease: "power2.out" }, startAt + 0.1);
    tl.to("#chroma-b-off", { attr: { dx: 0 }, duration: 0.1, ease: "power2.out" }, startAt + 0.1);
    tl.set(targetSel, { filter: "none" }, startAt + 0.21);
  }

  window.SSR_SUMMON_STATE = {
    seed: seed,
    chromaShockPx: chromaShockPx,
    bindLoopsAndHelpers: bindLoopsAndHelpers,
    addChromaShock: addChromaShock,
  };
})();
