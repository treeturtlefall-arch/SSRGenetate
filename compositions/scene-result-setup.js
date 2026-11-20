(function () {
  const T0 = 6.9;
  function at(globalSec) {
    return Math.max(0, Number((globalSec - T0).toFixed(4)));
  }

  function resolveAssetPath(relPath) {
    if (!relPath) return "";
    if (/^(https?:|data:|\/|\.\.\/)/.test(relPath)) return relPath;
    return "../" + relPath.replace(/^\.\//, "");
  }

  function createRng(seed) {
    let s = seed >>> 0;
    return function () {
      s |= 0;
      s = (s + 0x6d2b79f5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const baseCfg = window.SSR_CARD_CONFIG || {};
  const hfVars =
    window.__hyperframes && typeof window.__hyperframes.getVariables === "function"
      ? window.__hyperframes.getVariables()
      : {};

  function pick(varVal, cfgVal, fallback) {
    if (typeof varVal === "string" && varVal.trim() !== "") return varVal;
    if (cfgVal !== undefined && cfgVal !== null && cfgVal !== "") return cfgVal;
    return fallback;
  }

  const cfg = {
    photo: pick(hfVars.photo, baseCfg.photo, "assets/photo.jpg"),
    photoFit: baseCfg.photoFit || "cover",
    photoPosition: baseCfg.photoPosition || "50% 42%",
    photoZoom: typeof baseCfg.photoZoom === "number" ? baseCfg.photoZoom : 1.02,
    rarity: pick(hfVars.rarity, baseCfg.rarity, "SSR"),
    stars: typeof baseCfg.stars === "number" ? baseCfg.stars : 5,
    attribute: typeof baseCfg.attribute === "string" ? baseCfg.attribute.trim() : "",
    subtitle: pick(hfVars.subtitle, baseCfg.subtitle, "【奇跡のテーブル55】"),
    title: pick(hfVars.title, baseCfg.title, "ちいさな美食家"),
    flavor: pick(hfVars.flavor, baseCfg.flavor, "黄金のたまご焼きを前に、世界一の幸せを召喚する。"),
    stats: Array.isArray(baseCfg.stats) && baseCfg.stats.length > 0 ? baseCfg.stats.slice(0, 3) : [],
    cardNo: baseCfg.cardNo || "NO.055-SSR",
    material: baseCfg.material || {},
    seed: typeof baseCfg.seed === "number" ? baseCfg.seed : 20261120,
  };

  const matCfg = cfg.material;
  const depthEl = document.getElementById("mat-window-depth");
  if (depthEl && typeof matCfg.windowDepthOpacity === "number") {
    depthEl.style.opacity = String(matCfg.windowDepthOpacity);
  }
  const chromaShockPx = typeof matCfg.chromaShockPx === "number" ? matCfg.chromaShockPx : 9;

  const photoEl = document.getElementById("card-photo");
  photoEl.src = resolveAssetPath(cfg.photo);
  photoEl.style.objectFit = cfg.photoFit;
  photoEl.style.objectPosition = cfg.photoPosition;
  photoEl.style.transform = "scale(" + cfg.photoZoom + ")";

  const typoManifest = (window.SSR_TYPO_MANIFEST && window.SSR_TYPO_MANIFEST.items) || {};

  function bindTypoSlot(key, text, imgId, textId, wrapId, fixedHeight) {
    const cleanText = (text || "").trim();
    const imgEl = document.getElementById(imgId);
    const txtEl = document.getElementById(textId);
    const wrapEl = wrapId ? document.getElementById(wrapId) : null;

    if (!cleanText) {
      if (wrapEl) wrapEl.style.display = "none";
      return;
    }

    const entry = typoManifest[key];
    if (entry && entry.text === cleanText && entry.src) {
      imgEl.style.backgroundImage = 'url("' + resolveAssetPath(entry.src) + '")';
      if (fixedHeight) {
        imgEl.style.height = fixedHeight + "px";
        imgEl.style.width = Math.round((entry.width / Math.max(1, entry.height)) * fixedHeight) + "px";
      } else {
        imgEl.style.width = entry.width + "px";
        imgEl.style.height = entry.height + "px";
      }
      imgEl.style.display = "block";
      txtEl.style.display = "none";
    } else {
      imgEl.style.display = "none";
      txtEl.textContent = cleanText;
      txtEl.style.display = "block";
    }
  }

  bindTypoSlot("ssr", cfg.rarity, "ssr-emblem-img", "ssr-emblem-text", "ssr-emblem", 94);
  bindTypoSlot("attribute", cfg.attribute, "attr-badge-img", "attr-badge-text", "attr-badge", 70);
  bindTypoSlot("subtitle", cfg.subtitle, "card-subtitle-img", "card-subtitle", "card-subtitle-wrap", 0);
  bindTypoSlot("title", cfg.title, "card-title-img", "card-title", "card-title-wrap", 0);
  bindTypoSlot("flavor", cfg.flavor, "card-flavor-img", "card-flavor", "card-flavor-wrap", 0);
  bindTypoSlot("cardNo", cfg.cardNo, "card-no-img", "card-no-text", "card-no-corner", 0);

  const starsRow = document.getElementById("stars-row");
  const starCount = Math.max(1, Math.min(6, cfg.stars));
  const starEls = [];
  for (let i = 0; i < starCount; i++) {
    const star = document.createElement("div");
    star.className = "star-item";
    starsRow.appendChild(star);
    starEls.push(star);
  }

  const statsEl = document.getElementById("card-stats");
  if (cfg.stats.length > 0) {
    statsEl.style.display = "grid";
    cfg.stats.forEach(function (st) {
      const box = document.createElement("div");
      box.className = "stat-box";
      const lbl = document.createElement("div");
      lbl.className = "stat-label";
      lbl.setAttribute("data-layout-allow-safe-zone", "");
      lbl.textContent = st.label;
      const val = document.createElement("div");
      val.className = "stat-value";
      val.setAttribute("data-layout-allow-safe-zone", "");
      val.textContent = st.value;
      box.appendChild(lbl);
      box.appendChild(val);
      statsEl.appendChild(box);
    });
  }

  const rng = createRng(cfg.seed);
  for (let i = 0; i < 28 * 3; i++) {
    rng();
  }

  const celebLayer = document.getElementById("celebration-layer");
  const bokehBackLayer = document.getElementById("bokeh-back-layer");

  // =========================================================================
  // 1-4a. スパークル疎密クラスター配置（極端なサイズ差：特大3・中5・極小14）
  // 対角線上（左上・右下を主軸、右上・左下を副軸）のクラスターへ配置し、等間隔感を排除
  // =========================================================================
  const sparkleClusters = [
    // 主クラスター A: 左上コーナー外縁（特大1 + 中1 + 極小3）
    { x: -468, y: -790, tier: "hero",  color: "gold",  group: 0 },
    { x: -492, y: -670, tier: "mid",   color: "white", group: 1 },
    { x: -395, y: -832, tier: "micro", color: "pink",  group: 2 },
    { x: -504, y: -740, tier: "micro", color: "gold",  group: 0 },
    { x: -445, y: -595, tier: "micro", color: "cyan",  group: 3 },
    // 主クラスター B: 右下コーナー外縁（特大1 + 中2 + 極小4）
    { x: 472,  y: 735,  tier: "hero",  color: "white", group: 1 },
    { x: 492,  y: 610,  tier: "mid",   color: "gold",  group: 2 },
    { x: 388,  y: 825,  tier: "mid",   color: "pink",  group: 3 },
    { x: 504,  y: 685,  tier: "micro", color: "cyan",  group: 0 },
    { x: 448,  y: 810,  tier: "micro", color: "gold",  group: 1 },
    { x: 496,  y: 525,  tier: "micro", color: "white", group: 2 },
    { x: 315,  y: 838,  tier: "micro", color: "gold",  group: 3 },
    // 副クラスター C: 右上〜右中段（特大1 + 中1 + 極小4）
    { x: 478,  y: -510, tier: "hero",  color: "pink",  group: 2 },
    { x: 465,  y: -785, tier: "mid",   color: "cyan",  group: 0 },
    { x: 500,  y: -435, tier: "micro", color: "white", group: 1 },
    { x: 490,  y: -600, tier: "micro", color: "gold",  group: 3 },
    { x: 405,  y: -832, tier: "micro", color: "white", group: 2 },
    { x: 498,  y: -150, tier: "micro", color: "cyan",  group: 0 },
    // 副クラスター D: 左下段（中1 + 極小3）
    { x: -478, y: 555,  tier: "mid",   color: "cyan",  group: 3 },
    { x: -498, y: 475,  tier: "micro", color: "gold",  group: 1 },
    { x: -465, y: 775,  tier: "micro", color: "pink",  group: 2 },
    { x: -498, y: 185,  tier: "micro", color: "white", group: 0 },
  ];

  const sparkleData = [];
  for (let i = 0; i < sparkleClusters.length; i++) {
    const spec = sparkleClusters[i];
    let size;
    let baseAlpha;
    if (spec.tier === "hero") {
      size = 138 + Math.floor(rng() * 24); // 138..162px
      baseAlpha = 0.96;
    } else if (spec.tier === "mid") {
      size = 76 + Math.floor(rng() * 20);  // 76..96px
      baseAlpha = 0.90;
    } else {
      size = 32 + Math.floor(rng() * 18);  // 32..50px
      baseAlpha = 0.80;
    }

    const sp = document.createElement("div");
    sp.className = "sparkle-star sp-group-" + spec.group;
    sp.setAttribute("data-layout-allow-overflow", "");
    sp.style.backgroundImage = 'url("../assets/generated/opt_sparkle_' + spec.color + '.png")';
    sp.style.width = size + "px";
    sp.style.height = size + "px";
    sp.style.marginLeft = -size / 2 + "px";
    sp.style.marginTop = -size / 2 + "px";
    celebLayer.appendChild(sp);

    const jitter = spec.tier === "micro" ? 18 : 10;
    sparkleData.push({
      el: sp,
      tier: spec.tier,
      group: spec.group,
      endX: spec.x + (rng() - 0.5) * jitter,
      endY: spec.y + (rng() - 0.5) * jitter,
      rot: (rng() - 0.5) * 44,
      finalScale: 0.90 + rng() * 0.20,
      baseAlpha: baseAlpha,
      startAt: at(8.68 + (i % 7) * 0.09),
    });
  }

  // =========================================================================
  // 1-4b. 3D 金箔・プリズム結晶片（rotateX / rotateY で光を反射しながらカード外縁へ舞う）
  // 中央の顔エリア（|x| < 380, |y| < 620）を避け、カードの左右外縁で輝く軌道に制御
  // =========================================================================
  const flakeData = [];
  for (let i = 0; i < 18; i++) {
    const el = document.createElement("div");
    el.className = "foil-flake";
    el.setAttribute("data-layout-allow-overflow", "");
    const size = 28 + Math.floor(rng() * 24);
    el.style.width = size + "px";
    el.style.height = size + "px";
    el.style.marginLeft = -size / 2 + "px";
    el.style.marginTop = -size / 2 + "px";
    el.style.backgroundImage = 'url("../assets/generated/mat_flake_' + (i % 6) + '.png")';
    celebLayer.appendChild(el);

    const side = i % 2 === 0 ? -1 : 1;
    // カード外周縁から外側へ飛び出し、写真中央を横切らない
    const startX = side * (360 + rng() * 85);
    const startY = (rng() - 0.5) * 1180;
    const midX = startX + side * (55 + rng() * 95);
    const midY = startY - (70 + rng() * 90);
    const endX = midX + side * (20 + rng() * 55);
    const endY = midY + 190 + rng() * 140;

    flakeData.push({
      el: el,
      startX: startX,
      startY: startY,
      midX: midX,
      midY: midY,
      endX: endX,
      endY: endY,
      rotX: (rng() > 0.5 ? 1 : -1) * (320 + rng() * 280),
      rotY: (rng() > 0.5 ? 1 : -1) * (360 + rng() * 320),
      rotZ: (rng() - 0.5) * 220,
      startAt: at(8.70 + (i % 6) * 0.045),
    });
  }

  // =========================================================================
  // 1-4c. 玉ボケ光粒（bokeh_flow.hlsl 由来：sizeRand^4 の疎密分布＋遠近2層のDOF）
  // 12.0s で位置は完全固定し、12.0s〜15.0s はわずかな明滅呼吸のみ行う
  // =========================================================================
  const bokehColors = ["gold", "rose", "aqua", "white"];
  const bokehData = [];
  for (let i = 0; i < 16; i++) {
    const isNear = i < 5; // 5個は近景大ボケ、11個は遠景シャープボケ
    const sizeRand = rng();
    const size = isNear
      ? Math.round(92 + Math.pow(sizeRand, 2.2) * 88)  // 92..180px
      : Math.round(34 + Math.pow(sizeRand, 4.0) * 76); // 34..110px (極小多数)
    const cname = bokehColors[i % bokehColors.length];
    const depthTag = isNear ? "near" : "far";

    const el = document.createElement("div");
    el.className = "bokeh-orb bk-group-" + (i % 3);
    el.setAttribute("data-layout-allow-overflow", "");
    el.style.width = size + "px";
    el.style.height = size + "px";
    el.style.marginLeft = -size / 2 + "px";
    el.style.marginTop = -size / 2 + "px";
    el.style.backgroundImage = 'url("../assets/generated/opt_bokeh_' + cname + "_" + depthTag + '.png")';
    (isNear ? celebLayer : bokehBackLayer).appendChild(el);

    // 画面四隅・上下左右の余白フレーム領域へ配置（中央の写真は完全に避ける）
    const side = i % 2 === 0 ? -1 : 1;
    let endX;
    let endY;
    if (i % 4 < 2) {
      // 左右の外縁レーン
      endX = side * (435 + rng() * 90);
      endY = (rng() - 0.5) * 1580;
    } else {
      // 上下の外縁レーン
      endX = (rng() - 0.5) * 920;
      endY = (i % 4 === 2 ? -1 : 1) * (775 + rng() * 145);
    }

    bokehData.push({
      el: el,
      isNear: isNear,
      group: i % 3,
      startX: endX * 0.86,
      startY: endY + 55,
      endX: endX,
      endY: endY,
      peakAlpha: isNear ? 0.34 : 0.52,
      holdAlpha: isNear ? 0.22 : 0.38,
      startAt: at(8.66 + (i % 5) * 0.08),
    });
  }

  window.SSR_RESULT_STATE = {
    at: at,
    cfg: cfg,
    chromaShockPx: chromaShockPx,
    starEls: starEls,
    sparkleData: sparkleData,
    flakeData: flakeData,
    bokehData: bokehData,
  };
})();
