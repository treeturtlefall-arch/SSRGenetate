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

  function bindTypoSlot(key, text, imgId, textId, wrapId) {
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
      if (key === "ssr") {
        imgEl.style.height = "58px";
        imgEl.style.width = Math.round((entry.width / Math.max(1, entry.height)) * 58) + "px";
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

  bindTypoSlot("ssr", cfg.rarity, "ssr-emblem-img", "ssr-emblem-text", null);
  bindTypoSlot("subtitle", cfg.subtitle, "card-subtitle-img", "card-subtitle", "card-subtitle-wrap");
  bindTypoSlot("title", cfg.title, "card-title-img", "card-title", "card-title-wrap");
  bindTypoSlot("flavor", cfg.flavor, "card-flavor-img", "card-flavor", "card-flavor-wrap");
  bindTypoSlot("cardNo", cfg.cardNo, "card-no-img", "card-no-text", "card-no-corner");

  const attrBadgeEl = document.getElementById("attr-badge");
  if (cfg.attribute) {
    attrBadgeEl.textContent = cfg.attribute;
  } else {
    attrBadgeEl.style.display = "none";
  }

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
  const sparkleData = [];
  const rimAnchors = [
    { x: -495, y: -620 }, { x: 495, y: -600 },
    { x: -510, y: -280 }, { x: 508, y: -250 },
    { x: -508, y: 120 },  { x: 505, y: 150 },
    { x: -495, y: 520 },  { x: 495, y: 540 },
    { x: -475, y: -855 }, { x: 475, y: -855 },
    { x: -280, y: -885 }, { x: 280, y: -885 },
    { x: -280, y: 890 },  { x: 280, y: 890 },
    { x: -495, y: 790 },  { x: 495, y: 790 },
  ];

  const sparkleSources = [
    "../assets/generated/opt_sparkle_gold.png",
    "../assets/generated/opt_sparkle_white.png",
    "../assets/generated/opt_sparkle_pink.png",
    "../assets/generated/opt_sparkle_cyan.png",
  ];
  for (let i = 0; i < rimAnchors.length; i++) {
    const size = 66 + Math.floor(rng() * 54);
    const sp = document.createElement("div");
    sp.className = "sparkle-star";
    sp.setAttribute("data-layout-allow-overflow", "");
    sp.style.backgroundImage = 'url("' + sparkleSources[i % sparkleSources.length] + '")';
    sp.style.width = size + "px";
    sp.style.height = size + "px";
    sp.style.marginLeft = -size / 2 + "px";
    sp.style.marginTop = -size / 2 + "px";
    celebLayer.appendChild(sp);

    sparkleData.push({
      el: sp,
      endX: rimAnchors[i].x + (rng() - 0.5) * 26,
      endY: rimAnchors[i].y + (rng() - 0.5) * 26,
      rot: (rng() - 0.5) * 60,
      finalScale: 0.78 + rng() * 0.42,
      startAt: at(9.25 + (i % 6) * 0.14),
    });
  }

  const confettiData = [];
  const confettiColors = ["#fde047", "#f472b6", "#38bdf8", "#a855f7", "#34d399", "#ffffff"];
  for (let i = 0; i < 22; i++) {
    const el = document.createElement("div");
    el.className = "confetti-bit";
    el.setAttribute("data-layout-allow-overflow", "");
    const w = 12 + Math.floor(rng() * 14);
    const h = 22 + Math.floor(rng() * 18);
    el.style.width = w + "px";
    el.style.height = h + "px";
    el.style.marginLeft = -w / 2 + "px";
    el.style.marginTop = -h / 2 + "px";
    el.style.background = confettiColors[i % confettiColors.length];
    celebLayer.appendChild(el);

    const angle = (i / 22) * Math.PI * 2 + (rng() - 0.5) * 0.25;
    const dist = 410 + rng() * 220;
    confettiData.push({
      el: el,
      midX: Math.cos(angle) * dist * 0.82,
      midY: Math.sin(angle) * dist * 0.82 - 80,
      endX: Math.cos(angle) * dist * 0.98,
      endY: Math.sin(angle) * dist * 0.82 + 210 + rng() * 140,
      rot: (rng() > 0.5 ? 1 : -1) * (240 + rng() * 320),
    });
  }

  window.SSR_RESULT_STATE = {
    at: at,
    cfg: cfg,
    chromaShockPx: chromaShockPx,
    starEls: starEls,
    sparkleData: sparkleData,
    confettiData: confettiData,
  };
})();
