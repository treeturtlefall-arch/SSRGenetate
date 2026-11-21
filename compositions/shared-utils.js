/**
 * SSRGenerate — Sub-Composition 共通ユーティリティ
 *
 * - Mulberry32 決定論的疑似乱数生成器 (`createRng`)
 * - サブコンポジションからの相対アセットパス解決 (`resolveAssetPath`)
 * - CLI変数 / card-config.js / フォールバックの優先解決 (`pickConfigValue`)
 * - 瞬間RGB色収差（Chromatic Aberration Shock）のGSAPタイムラインバインド (`addChromaShock`)
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

  function resolveAssetPath(relPath) {
    if (!relPath) return "";
    if (/^(https?:|data:|\/|\.\.\/)/.test(relPath)) return relPath;
    return "../" + relPath.replace(/^\.\//, "");
  }

  function pickConfigValue(varVal, cfgVal, fallback) {
    if (typeof varVal === "string" && varVal.trim() !== "") return varVal;
    if (cfgVal !== undefined && cfgVal !== null && cfgVal !== "") return cfgVal;
    return fallback;
  }

  function ensureChromaShockSvg(rootEl, filterId) {
    const host = rootEl || document.querySelector(".scene-root") || document.body || document.documentElement;
    if (!host) return null;
    const existing = host.querySelector("#" + filterId);
    if (existing) return existing;
    host.insertAdjacentHTML(
      "afterbegin",
      '<svg class="chroma-shock-defs" width="0" height="0" style="position:absolute;pointer-events:none" aria-hidden="true">' +
        "<defs>" +
        '<filter id="' +
        filterId +
        '" x="-4%" y="-2%" width="108%" height="104%" color-interpolation-filters="sRGB">' +
        '<feColorMatrix in="SourceGraphic" type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="r-only" />' +
        '<feOffset id="' +
        filterId +
        '-r" in="r-only" dx="0" dy="0" result="r-shift" />' +
        '<feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="g-only" />' +
        '<feColorMatrix in="SourceGraphic" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="b-only" />' +
        '<feOffset id="' +
        filterId +
        '-b" in="b-only" dx="0" dy="0" result="b-shift" />' +
        '<feBlend in="r-shift" in2="g-only" mode="screen" result="rg" />' +
        '<feBlend in="rg" in2="b-shift" mode="screen" />' +
        "</filter>" +
        "</defs>" +
        "</svg>"
    );
    return host.querySelector("#" + filterId);
  }

  function addChromaShock(tl, targetSel, startAt, peakPx) {
    if (!tl || !peakPx || peakPx <= 0) return;
    const targetEl = document.querySelector(targetSel);
    const rootEl = (targetEl && targetEl.closest(".scene-root")) || document.querySelector(".scene-root");
    const compId = (rootEl && rootEl.getAttribute("data-composition-id")) || "default";
    const filterId = "chroma-shock-" + compId;
    const filterEl = ensureChromaShockSvg(rootEl, filterId);
    const rOff = filterEl ? filterEl.querySelector("#" + filterId + "-r") : null;
    const bOff = filterEl ? filterEl.querySelector("#" + filterId + "-b") : null;
    if (!rOff || !bOff) return;

    tl.set(targetSel, { filter: "url(#" + filterId + ")" }, startAt);
    tl.fromTo(
      rOff,
      { attr: { dx: 0 } },
      { attr: { dx: -peakPx }, duration: 0.04, ease: "power2.out", immediateRender: false },
      startAt
    );
    tl.fromTo(
      bOff,
      { attr: { dx: 0 } },
      { attr: { dx: peakPx }, duration: 0.04, ease: "power2.out", immediateRender: false },
      startAt
    );
    tl.to(
      rOff,
      { attr: { dx: peakPx * 0.45 }, duration: 0.06, ease: "power1.inOut" },
      startAt + 0.04
    );
    tl.to(
      bOff,
      { attr: { dx: -peakPx * 0.45 }, duration: 0.06, ease: "power1.inOut" },
      startAt + 0.04
    );
    tl.to(rOff, { attr: { dx: 0 }, duration: 0.1, ease: "power2.out" }, startAt + 0.1);
    tl.to(bOff, { attr: { dx: 0 }, duration: 0.1, ease: "power2.out" }, startAt + 0.1);
    tl.set(targetSel, { filter: "none" }, startAt + 0.21);
  }

  window.SSR_SHARED = {
    createRng: createRng,
    resolveAssetPath: resolveAssetPath,
    pickConfigValue: pickConfigValue,
    ensureChromaShockSvg: ensureChromaShockSvg,
    addChromaShock: addChromaShock,
  };
})();
