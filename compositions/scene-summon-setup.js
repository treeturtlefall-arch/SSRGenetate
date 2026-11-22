/**
 * SSRGenerate — Scene 1-2 (Summon & Promotion) Deterministic Setup
 *
 * scene-summon.html の行数を300行未満に保ちつつ、決定論的PRNGによる
 * 収束粒子・上空2層パララックス浮遊クリスタル破片・星屑・タイポマニフェスト適用を行う。
 */
(function () {
  const shared = window.SSR_SHARED;
  const createRng = shared.createRng;
  const resolveAssetPath = shared.resolveAssetPath;
  const addChromaShock = shared.addChromaShock;

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
  const isLandscape = document.documentElement.getAttribute("data-resolution") === "landscape";
  const canvasW = isLandscape ? 1920 : 1080;
  const canvasH = isLandscape ? 1080 : 1920;

  // 1. カットイン箔タイポマニフェスト適用
  const typoItems = (window.SSR_TYPO_MANIFEST && window.SSR_TYPO_MANIFEST.items) || {};
  [
    ["cutinMain", "cutin-main-img"],
  ].forEach(function (pair) {
    const entry = typoItems[pair[0]];
    const el = document.getElementById(pair[1]);
    if (entry && el && entry.src) {
      el.style.backgroundImage = 'url("' + resolveAssetPath(entry.src) + '")';
      el.style.width = entry.width + "px";
      el.style.height = entry.height + "px";
    }
  });

  // 1.5 冒頭導入：左から右斜め下へ駆け抜ける物理光学流れ星（Shooting Star）
  const meteorRng = createRng(seed ^ 0x51a7f3);
  const meteorContainer = document.getElementById("intro-shooting-star");
  let introMeteorHead = null;
  let introMeteorStreak = null;
  const introMeteorNodes = [];
  const introMeteorDusts = [];

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

  if (meteorContainer) {
    const headSize = 210;
    const headEl = document.createElement("div");
    headEl.className = "intro-meteor-head";
    headEl.setAttribute("data-layout-allow-overflow", "");
    headEl.setAttribute("data-layout-ignore", "");
    headEl.style.cssText =
      "width:" +
      headSize +
      "px;height:" +
      headSize +
      "px;margin-left:" +
      (-headSize / 2) +
      "px;margin-top:" +
      (-headSize / 2) +
      "px";
    meteorContainer.appendChild(headEl);
    introMeteorHead = headEl;

    const streakW = 440;
    const streakH = 96;
    const streakEl = document.createElement("div");
    streakEl.className = "intro-meteor-streak";
    streakEl.setAttribute("data-layout-allow-overflow", "");
    streakEl.setAttribute("data-layout-ignore", "");
    streakEl.style.cssText =
      "width:" +
      streakW +
      "px;height:" +
      streakH +
      "px;margin-left:" +
      (-streakW / 2) +
      "px;margin-top:" +
      (-streakH / 2) +
      "px";
    meteorContainer.appendChild(streakEl);
    introMeteorStreak = streakEl;

    const nMeteorNodes = 18;
    for (let k = 0; k < nMeteorNodes; k++) {
      const tLag = k / (nMeteorNodes - 1);
      const sz = Math.round(64 - tLag * 46); // 64px -> 18px
      const nodeEl = document.createElement("div");
      nodeEl.className = "intro-meteor-node";
      nodeEl.setAttribute("data-layout-allow-overflow", "");
      nodeEl.setAttribute("data-layout-ignore", "");
      nodeEl.style.cssText =
        "width:" +
        sz +
        "px;height:" +
        sz +
        "px;margin-left:" +
        (-sz / 2) +
        "px;margin-top:" +
        (-sz / 2) +
        "px";
      meteorContainer.appendChild(nodeEl);
      introMeteorNodes.push({
        el: nodeEl,
        delay: +(k * 0.008).toFixed(4),
        peakAlpha: +(0.86 * Math.pow(1 - tLag, 0.92)).toFixed(3),
      });
    }

    const nMeteorDusts = 16;
    for (let i = 0; i < nMeteorDusts; i++) {
      const pDust = 0.12 + (i / (nMeteorDusts - 1)) * 0.74;
      const pt = evalIntroMeteor(pDust);
      const sz = 22 + Math.floor(meteorRng() * 25); // 22..46px
      const col = i % 2 === 0 ? "white" : "cyan";
      const dEl = document.createElement("div");
      dEl.className = "intro-meteor-dust";
      dEl.setAttribute("data-layout-allow-overflow", "");
      dEl.setAttribute("data-layout-ignore", "");
      dEl.style.cssText =
        "width:" +
        sz +
        "px;height:" +
        sz +
        "px;margin-left:" +
        (-sz / 2) +
        "px;margin-top:" +
        (-sz / 2) +
        'px;background-image:url("../assets/generated/opt_sparkle_' +
        col +
        '.png")';
      meteorContainer.appendChild(dEl);
      introMeteorDusts.push({
        el: dEl,
        x0: +(pt.x + (meteorRng() - 0.5) * 24).toFixed(1),
        y0: +(pt.y + (meteorRng() - 0.5) * 24).toFixed(1),
        dx: +(22 + meteorRng() * 38).toFixed(1),
        dy: +(26 + meteorRng() * 48).toFixed(1),
        rot0: +((meteorRng() - 0.5) * 60).toFixed(1),
        drot: +((meteorRng() - 0.5) * 90).toFixed(1),
        appearAt: +(pDust * 0.58 + 0.02).toFixed(3),
        dur: +(0.48 + meteorRng() * 0.30).toFixed(3),
        peakAlpha: +(0.55 + meteorRng() * 0.35).toFixed(3),
      });
    }
  }

  // 2. [C] 冒頭降臨の光の三原色（RGB）3D円錐三重螺旋ウィスプ (3筋 × 星核ヘッド + 42尾ノード + 余韻スターダスト30粒)
  const wispContainer = document.getElementById("wisp-streams");
  const wispHeads = [];
  const wispNodes = [];
  const wispDusts = [];

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

  function evalHelixTangentDeg(sd, p, spread) {
    const p1 = Math.max(0, p - 0.004);
    const p2 = Math.min(1, p + 0.004);
    const pt1 = evalHelixPoint(sd, p1, spread);
    const pt2 = evalHelixPoint(sd, p2, spread);
    const dx = pt2.x - pt1.x;
    const dy = pt2.y - pt1.y;
    if (dx * dx + dy * dy < 1e-6) return 0;
    return (Math.atan2(dy, dx) * 180) / Math.PI;
  }

  if (wispContainer) {
    const streamDefs = [
      {
        color: "blue",
        delay: 0.04,
        dur: 1.34,
        theta0: -Math.PI / 6,
        turns: 1.65,
        headSize: 196,
        tailScale: 1.22,
        dustCols: ["cyan", "white"],
      },
      {
        color: "red",
        delay: 0.08,
        dur: 1.32,
        theta0: -Math.PI / 6 + (Math.PI * 2) / 3,
        turns: 1.65,
        headSize: 146,
        tailScale: 0.94,
        dustCols: ["pink", "white"],
      },
      {
        color: "green",
        delay: 0.12,
        dur: 1.30,
        theta0: -Math.PI / 6 + (Math.PI * 4) / 3,
        turns: 1.65,
        headSize: 142,
        tailScale: 0.90,
        dustCols: ["cyan", "white"],
      },
    ];
    const nPerStream = 42;
    streamDefs.forEach(function (sd) {
      // 各ストリーム先頭の星核ヘッド
      const headEl = document.createElement("div");
      headEl.className = "wisp-head wisp-head-" + sd.color;
      headEl.setAttribute("data-layout-allow-overflow", "");
      headEl.setAttribute("data-layout-ignore", "");
      headEl.style.cssText =
        "width:" +
        sd.headSize +
        "px;height:" +
        sd.headSize +
        "px;margin-left:" +
        (-sd.headSize / 2).toFixed(1) +
        "px;margin-top:" +
        (-sd.headSize / 2).toFixed(1) +
        "px";
      wispContainer.appendChild(headEl);
      wispHeads.push({ el: headEl, sd: sd });

      for (let k = 0; k < nPerStream; k++) {
        const tLag = k / (nPerStream - 1);
        const isVeil = k > 0 && k % 5 === 0;
        const el = document.createElement("div");
        el.className = "wisp-node wisp-node-" + sd.color;
        el.setAttribute("data-layout-allow-overflow", "");
        el.setAttribute("data-layout-ignore", "");
        // 針状白芯＋広大宝石色オーラで、綿棒感を排除したまま堂々たる大スケールを描く
        const size = isVeil
          ? Math.round((152 + tLag * 32) * sd.tailScale)
          : Math.round(58 * sd.tailScale * Math.pow(1 - tLag * 0.78, 1.12));
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

        const spread = (rng() - 0.5) * tLag * 12;
        const peakAlpha =
          k === 0
            ? 0.95
            : isVeil
              ? +(0.17 * (1 - tLag * 0.45)).toFixed(3)
              : +(0.86 * Math.pow(1 - tLag, 1.05)).toFixed(3);

        wispNodes.push({
          el: el,
          sd: sd,
          k: k,
          tLag: tLag,
          isVeil: isVeil,
          startAt: +(sd.delay + k * 0.0105).toFixed(3),
          dur: sd.dur,
          spread: spread,
          peakAlpha: peakAlpha,
        });
      }

      // 軌道からこぼれ落ちて漂う微細スターダスト (各ストリーム10粒)
      for (let d = 0; d < 10; d++) {
        const p = 0.14 + (d / 10) * 0.74;
        const el = document.createElement("div");
        el.className = "sky-star";
        el.setAttribute("data-layout-allow-overflow", "");
        el.setAttribute("data-layout-ignore", "");
        const dSize = 18 + Math.floor(rng() * 24);
        const spCol = sd.dustCols[d % 2];
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
        const pt = evalHelixPoint(sd, p, 0);
        wispDusts.push({
          el: el,
          x0: +(pt.x + (rng() - 0.5) * 32).toFixed(1),
          y0: +pt.y.toFixed(1),
          dx: +((rng() - 0.5) * 62).toFixed(1),
          dy: +(-20 + rng() * 48).toFixed(1),
          appearAt: +(sd.delay + p * sd.dur + 0.04).toFixed(3),
          dur: +(0.40 + rng() * 0.24).toFixed(3),
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
      const sxMul = isLandscape ? 1.35 : 1.0;
      const syMul = isLandscape ? 0.78 : 1.0;
      convergeData.push({
        el: el,
        startX: Math.cos(angle) * dist * sxMul,
        startY: Math.sin(angle) * dist * syMul,
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
      const x0 = 55 + rng() * (canvasW - 110);
      const y0 = isLandscape
        ? Math.max(50, Math.min(canvasH - 50, 60 + (i / 36) * (canvasH - 120) + (rng() - 0.5) * 55))
        : Math.max(80, Math.min(1840, 100 + (i / 36) * 1680 + (rng() - 0.5) * 90));
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
      const x0 = 65 + rng() * (canvasW - 130);
      const y0 = isLandscape
        ? Math.max(45, Math.min(canvasH - 70, 55 + (i / 20) * (canvasH - 140) + (rng() - 0.5) * 55))
        : Math.max(70, Math.min(1780, 80 + (i / 20) * 1620 + (rng() - 0.5) * 90));
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
      const rightLaneStart = canvasW - 245;
      const x0 = isLeft ? 50 + rng() * 195 : rightLaneStart + rng() * 195;
      const y0 = isLandscape
        ? 85 + (i >> 1) * 135 + rng() * 65
        : 150 + (i >> 1) * 245 + rng() * 110;
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
      {
        count: 8,
        baseTime: 3.78,
        spreadT: 0.28,
        nearRatio: 3,
        kindPool: [1, 2, 1],
        yMin: isLandscape ? 700 : 1280,
        yMax: isLandscape ? 1100 : 1940,
      },
      // 虹昇格ウェーブ (12個: 遠景8 + 近景4)
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
        const rightWaveStart = canvasW - 265;
        const x0 = isNear
          ? (isLeft ? 55 + rng() * 210 : rightWaveStart + rng() * 210)
          : 65 + rng() * (canvasW - 130);
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

    const STEPS = 28;

    // 冒頭導入：左上→右斜め下へ駆け抜ける流れ星タイムライン
    if (introMeteorHead && introMeteorStreak) {
      const M_STEPS = 20;
      const mDur = 0.58;
      const p0 = evalIntroMeteor(0);
      tl.set(introMeteorHead, { x: p0.x, y: p0.y, scale: 0.45, rotation: p0.deg, opacity: 0 }, 0);
      tl.set(
        introMeteorStreak,
        {
          x: +(p0.x - 115 * Math.cos(p0.rad)).toFixed(1),
          y: +(p0.y - 115 * Math.sin(p0.rad)).toFixed(1),
          scaleX: 0.55,
          scaleY: 0.65,
          rotation: p0.deg,
          opacity: 0,
        },
        0
      );

      const headFrames = [];
      const streakFrames = [];
      for (let i = 1; i <= M_STEPS; i++) {
        const p = i / M_STEPS;
        const pt = evalIntroMeteor(p);
        const envIn = p < 0.16 ? p / 0.16 : 1.0;
        const envOut = p > 0.72 ? Math.max(0, (1 - p) / 0.28) : 1.0;
        const bell = Math.sin(Math.PI * p);
        const alpha = envIn * envOut;
        const sc = 0.65 + 0.55 * bell;
        headFrames.push({
          x: pt.x,
          y: pt.y,
          scale: +sc.toFixed(3),
          rotation: +(pt.deg + p * 22).toFixed(2),
          opacity: +(alpha * 0.96).toFixed(3),
        });
        streakFrames.push({
          x: +(pt.x - 115 * Math.cos(pt.rad)).toFixed(1),
          y: +(pt.y - 115 * Math.sin(pt.rad)).toFixed(1),
          scaleX: +(0.65 + 0.55 * bell).toFixed(3),
          scaleY: +(0.72 + 0.35 * bell).toFixed(3),
          rotation: pt.deg,
          opacity: +(alpha * 0.88).toFixed(3),
        });
      }
      tl.to(introMeteorHead, { keyframes: headFrames, duration: mDur, ease: "power1.inOut" }, 0);
      tl.to(introMeteorStreak, { keyframes: streakFrames, duration: mDur, ease: "power1.inOut" }, 0);

      introMeteorNodes.forEach(function (mn) {
        tl.set(mn.el, { x: p0.x, y: p0.y, scaleX: 1.0, scaleY: 0.35, rotation: p0.deg, opacity: 0 }, 0);
        const nFrames = [];
        for (let i = 1; i <= M_STEPS; i++) {
          const p = i / M_STEPS;
          const pt = evalIntroMeteor(p);
          const envIn = p < 0.14 ? p / 0.14 : 1.0;
          const envOut = p > 0.70 ? Math.max(0, (1 - p) / 0.30) : 1.0;
          const baseSc = 0.75 + 0.35 * Math.sin(Math.PI * p);
          nFrames.push({
            x: pt.x,
            y: pt.y,
            scaleX: +(baseSc * 2.15).toFixed(3),
            scaleY: +(baseSc * 0.46).toFixed(3),
            rotation: pt.deg,
            opacity: i === M_STEPS ? 0 : +(mn.peakAlpha * envIn * envOut).toFixed(3),
          });
        }
        tl.to(mn.el, { keyframes: nFrames, duration: 0.54, ease: "power1.inOut" }, mn.delay);
      });

      introMeteorDusts.forEach(function (md) {
        tl.set(md.el, { x: md.x0, y: md.y0, scale: 0.35, rotation: md.rot0, opacity: 0 }, 0);
        tl.to(md.el, { opacity: md.peakAlpha, scale: 1.0, duration: 0.08, ease: "power2.out" }, md.appearAt);
        tl.to(
          md.el,
          { x: +(md.x0 + md.dx).toFixed(1), y: +(md.y0 + md.dy).toFixed(1), rotation: +(md.rot0 + md.drot).toFixed(1), duration: md.dur, ease: "sine.out" },
          md.appearAt
        );
        tl.to(
          md.el,
          { opacity: 0, scale: 0.25, duration: +(md.dur * 0.72).toFixed(3), ease: "sine.in" },
          +(md.appearAt + md.dur * 0.28).toFixed(3)
        );
      });
    }

    // 先頭星核ヘッド: 120°位相差の3D円錐三重螺旋を描きながら中央へ収束してオーブを生む
    wispHeads.forEach(function (wh) {
      const sd = wh.sd;
      const p0 = evalHelixPoint(sd, 0, 0);
      tl.set(
        wh.el,
        { x: p0.x, y: p0.y, scale: +(0.42 * p0.depthScale).toFixed(3), rotation: -14, opacity: 0 },
        0
      );
      const frames = [];
      for (let i = 1; i <= STEPS; i++) {
        const p = i / STEPS;
        const pt = evalHelixPoint(sd, p, 0);
        const inEnv = p < 0.12 ? p / 0.12 : 1.0;
        let baseScale;
        let alphaEnv;
        if (p < 0.12) {
          baseScale = 0.42 + 0.64 * inEnv;
          alphaEnv = inEnv;
        } else if (p <= 0.90) {
          baseScale = 1.06;
          alphaEnv = 1.0;
        } else {
          const outT = (p - 0.90) / 0.10;
          baseScale = outT < 0.35 ? 1.06 + 0.26 * (outT / 0.35) : 1.32 - 1.10 * ((outT - 0.35) / 0.65);
          alphaEnv = Math.max(0, 1.0 - Math.pow(outT, 1.4));
        }
        frames.push({
          x: pt.x,
          y: pt.y,
          scale: +(baseScale * pt.depthScale).toFixed(3),
          opacity: +(alphaEnv * pt.depthAlpha).toFixed(3),
        });
      }
      tl.to(wh.el, { keyframes: frames, duration: sd.dur, ease: "none" }, sd.delay);
      tl.to(wh.el, { rotation: 36, duration: sd.dur, ease: "none" }, sd.delay);
    });

    // 3D円錐三重螺旋・尾ノード: keyframes による競合ゼロの単一軌道トゥイーン
    wispNodes.forEach(function (wn) {
      const sd = wn.sd;
      const t0 = wn.startAt;
      const p0 = evalHelixPoint(sd, 0, wn.spread);
      let prevDeg = evalHelixTangentDeg(sd, 0, wn.spread);
      let unwrappedDeg = prevDeg;
      const initSc = +(0.65 * p0.depthScale).toFixed(3);
      if (wn.isVeil) {
        tl.set(wn.el, { x: p0.x, y: p0.y, scaleX: initSc, scaleY: initSc, rotation: 0, opacity: 0 }, 0);
      } else {
        tl.set(
          wn.el,
          { x: p0.x, y: p0.y, scaleX: +(initSc * 2.05).toFixed(3), scaleY: +(initSc * 0.46).toFixed(3), rotation: +unwrappedDeg.toFixed(2), opacity: 0 },
          0
        );
      }
      const frames = [];
      for (let i = 1; i <= STEPS; i++) {
        const p = i / STEPS;
        const pt = evalHelixPoint(sd, p, wn.spread);
        const inEnv = p < 0.12 ? p / 0.12 : 1.0;
        const outEnv = p > 0.88 ? Math.max(0, (1 - p) / 0.12) : 1.0;
        const scaleBoost = 1 + (wn.isVeil ? 0.35 : 0.18) * (1 - outEnv);
        const sc = (0.65 + 0.35 * Math.min(1, inEnv)) * scaleBoost * pt.depthScale;
        const op = wn.peakAlpha * Math.min(1, inEnv) * outEnv * pt.depthAlpha;
        if (wn.isVeil) {
          frames.push({
            x: pt.x,
            y: pt.y,
            scaleX: +sc.toFixed(3),
            scaleY: +sc.toFixed(3),
            rotation: 0,
            opacity: i === STEPS ? 0 : +op.toFixed(3),
          });
        } else {
          const curDeg = evalHelixTangentDeg(sd, p, wn.spread);
          let delta = curDeg - prevDeg;
          while (delta > 180) delta -= 360;
          while (delta < -180) delta += 360;
          unwrappedDeg += delta;
          prevDeg = curDeg;
          const stretch = 2.05 - 0.55 * Math.pow(p, 2.2);
          const squash = 0.46 + 0.16 * Math.pow(p, 2.2);
          frames.push({
            x: pt.x,
            y: pt.y,
            scaleX: +(sc * stretch).toFixed(3),
            scaleY: +(sc * squash).toFixed(3),
            rotation: +unwrappedDeg.toFixed(2),
            opacity: i === STEPS ? 0 : +op.toFixed(3),
          });
        }
      }
      tl.to(wn.el, { keyframes: frames, duration: wn.dur, ease: "none" }, t0);
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

  window.SSR_SUMMON_STATE = {
    seed: seed,
    chromaShockPx: chromaShockPx,
    bindLoopsAndHelpers: bindLoopsAndHelpers,
    addChromaShock: addChromaShock,
  };
})();
