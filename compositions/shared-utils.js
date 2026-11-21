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

  function addChromaShock(tl, targetSel, startAt, peakPx) {
    if (!tl || !peakPx || peakPx <= 0) return;
    tl.set(targetSel, { filter: "url(#chroma-shock)" }, startAt);
    tl.fromTo(
      "#chroma-r-off",
      { attr: { dx: 0 } },
      { attr: { dx: -peakPx }, duration: 0.04, ease: "power2.out", immediateRender: false },
      startAt
    );
    tl.fromTo(
      "#chroma-b-off",
      { attr: { dx: 0 } },
      { attr: { dx: peakPx }, duration: 0.04, ease: "power2.out", immediateRender: false },
      startAt
    );
    tl.to(
      "#chroma-r-off",
      { attr: { dx: peakPx * 0.45 }, duration: 0.06, ease: "power1.inOut" },
      startAt + 0.04
    );
    tl.to(
      "#chroma-b-off",
      { attr: { dx: -peakPx * 0.45 }, duration: 0.06, ease: "power1.inOut" },
      startAt + 0.04
    );
    tl.to("#chroma-r-off", { attr: { dx: 0 }, duration: 0.1, ease: "power2.out" }, startAt + 0.1);
    tl.to("#chroma-b-off", { attr: { dx: 0 }, duration: 0.1, ease: "power2.out" }, startAt + 0.1);
    tl.set(targetSel, { filter: "none" }, startAt + 0.21);
  }

  window.SSR_SHARED = {
    createRng: createRng,
    resolveAssetPath: resolveAssetPath,
    pickConfigValue: pickConfigValue,
    addChromaShock: addChromaShock,
  };
})();
