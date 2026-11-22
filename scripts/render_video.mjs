/**
 * SSRGenerate — スマート・プリフライト＆レンダリングラッパー (renders/SSR_{preset}_{YYYYMMDD}.mp4)
 *
 * - card-config.js と CLI 引数 (--variables '{...}') をマージし、
 *   assets/generated/typo-manifest.js の source スナップショットと差分を比較する。
 * - テキスト・プリセット・4軸上書き・写真/シード変更がある場合は、レンダリング直前に
 *   python scripts/render_typography.py --overrides-stdin を自動実行して物理箔 PNG とビネットを更新する。
 * - 出力ファイル名 renders/SSR_{preset}_{YYYYMMDD}.mp4 も上書き後のプリセット名に同期させる。
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..");
const RENDERS_DIR = path.join(PROJECT_ROOT, "renders");
const CONFIG_PATH = path.join(PROJECT_ROOT, "card-config.js");
const MANIFEST_PATH = path.join(PROJECT_ROOT, "assets", "generated", "typo-manifest.js");

const VALID_PRESETS = new Set([
  "royal-foil",
  "cute-pastel",
  "foil-brush",
  "handwritten-sign",
  "crisp-emboss",
]);

function roundTo(val, digits) {
  const m = 10 ** digits;
  return Math.round(val * m) / m;
}

function stableNormalize(val) {
  if (Array.isArray(val)) return val.map(stableNormalize);
  if (val && typeof val === "object") {
    const out = {};
    for (const k of Object.keys(val).sort()) {
      out[k] = stableNormalize(val[k]);
    }
    return out;
  }
  return val;
}

function deepEqual(a, b) {
  return JSON.stringify(stableNormalize(a)) === JSON.stringify(stableNormalize(b));
}

function loadCardConfig() {
  if (!fs.existsSync(CONFIG_PATH)) return {};
  try {
    const ctx = { window: {} };
    vm.runInNewContext(fs.readFileSync(CONFIG_PATH, "utf8"), ctx);
    return ctx.window?.SSR_CARD_CONFIG && typeof ctx.window.SSR_CARD_CONFIG === "object"
      ? ctx.window.SSR_CARD_CONFIG
      : {};
  } catch {
    return {};
  }
}

function loadTypoManifest() {
  if (!fs.existsSync(MANIFEST_PATH)) return null;
  try {
    const ctx = { window: {} };
    vm.runInNewContext(fs.readFileSync(MANIFEST_PATH, "utf8"), ctx);
    return ctx.window?.SSR_TYPO_MANIFEST || null;
  } catch {
    return null;
  }
}

function loadVariablesPayload(rawArg, label) {
  let text = rawArg;
  const trimmed = rawArg.trim();
  if (!trimmed.startsWith("{")) {
    const filePath = path.isAbsolute(trimmed) ? trimmed : path.resolve(PROJECT_ROOT, trimmed);
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      text = fs.readFileSync(filePath, "utf8");
    }
  }
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("must be a JSON object");
    }
    return parsed;
  } catch (err) {
    console.error(`[error] Invalid ${label} JSON: ${err.message}`);
    process.exit(1);
  }
}

function parseCliArgs(argv) {
  let cliVars = {};
  let dryRun = false;
  let forceTypo = false;
  let noAutoTypo = false;
  let hasExplicitOutput = false;
  const passthroughArgs = [];

  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--dry-run") {
      dryRun = true;
      continue;
    }
    if (a === "--force-typo") {
      forceTypo = true;
      continue;
    }
    if (a === "--no-auto-typo") {
      noAutoTypo = true;
      continue;
    }
    if (a === "-o" || a === "--output" || a.startsWith("--output=")) {
      hasExplicitOutput = true;
    }
    if (a === "--variables" || a.startsWith("--variables=") || a === "--variables-file" || a.startsWith("--variables-file=")) {
      const isFileFlag = a === "--variables-file" || a.startsWith("--variables-file=");
      const flagName = isFileFlag ? "--variables-file" : "--variables";
      let rawVal = "";
      if (a === flagName) {
        if (i + 1 >= argv.length) {
          console.error(`[error] ${flagName} requires an argument.`);
          process.exit(1);
        }
        rawVal = argv[i + 1];
        i += 1;
      } else {
        rawVal = a.slice(`${flagName}=`.length);
      }
      const parsed = loadVariablesPayload(rawVal, flagName);
      cliVars = { ...cliVars, ...parsed };
      continue;
    }
    passthroughArgs.push(a);
  }

  return { cliVars, dryRun, forceTypo, noAutoTypo, hasExplicitOutput, passthroughArgs };
}

function applyCliOverrides(baseCfg, overrides) {
  if (!overrides || typeof overrides !== "object") return baseCfg;
  const out = { ...baseCfg };
  const typo = baseCfg.typography && typeof baseCfg.typography === "object" ? { ...baseCfg.typography } : {};

  const strKeys = [
    "photo",
    "photoFit",
    "photoPosition",
    "rarity",
    "attribute",
    "attributeBadge",
    "attributeLabel",
    "subtitle",
    "title",
    "flavor",
    "cardNo",
    "resultRingMode",
  ];
  for (const k of strKeys) {
    if (Object.prototype.hasOwnProperty.call(overrides, k) && overrides[k] !== null && overrides[k] !== undefined) {
      out[k] = String(overrides[k]);
    }
  }

  if (Object.prototype.hasOwnProperty.call(overrides, "photoZoom") && overrides.photoZoom !== null && String(overrides.photoZoom).trim() !== "") {
    const n = Number(overrides.photoZoom);
    if (Number.isFinite(n)) out.photoZoom = n;
  }
  for (const ik of ["stars", "seed"]) {
    if (Object.prototype.hasOwnProperty.call(overrides, ik) && overrides[ik] !== null && String(overrides[ik]).trim() !== "") {
      const n = Number.parseInt(String(overrides[ik]), 10);
      if (Number.isFinite(n)) out[ik] = n;
    }
  }

  if (typeof overrides.preset === "string" && overrides.preset.trim() !== "") {
    typo.preset = overrides.preset.trim();
  }
  if (overrides.typography && typeof overrides.typography === "object" && !Array.isArray(overrides.typography)) {
    for (const [tk, tv] of Object.entries(overrides.typography)) {
      if (tv !== null && tv !== undefined) {
        typo[tk] = tv;
      }
    }
  }

  out.typography = typo;
  return out;
}

function parseAttributeParts(cfg) {
  const hasSplit = Object.prototype.hasOwnProperty.call(cfg, "attributeBadge") || Object.prototype.hasOwnProperty.call(cfg, "attributeLabel");
  if (hasSplit) {
    const b = Array.from(String(cfg.attributeBadge ?? "").trim())[0] || "";
    const l = String(cfg.attributeLabel ?? "").trim();
    if (!b && !l) return "";
    return b && l ? `${b} / ${l}` : l || b;
  }

  const clean = String(cfg.attribute ?? "").trim();
  if (!clean) return "";
  const parts = clean.replace(/／/g, "/").split("/").map((p) => p.trim()).filter(Boolean);
  if (parts.length >= 2) {
    const stripped = parts[0].replace(/属性/g, "").trim();
    const b = Array.from(stripped || parts[0])[0] || Array.from(parts[0])[0] || "";
    return b ? `${b} / ${parts[1]}` : parts[1];
  }
  const stripped = clean.replace(/属性/g, "").trim();
  const b = Array.from(stripped || clean)[0] || Array.from(clean)[0] || "";
  return b ? `${b} / ${clean}` : clean;
}

function resolvePhotoPath(photoRel) {
  const raw = String(photoRel || "assets/photo.jpg").trim();
  if (path.isAbsolute(raw)) return raw;
  return path.join(PROJECT_ROOT, raw.replace(/^[./\\]+/, ""));
}

function buildExpectedSource(cfg) {
  const typo = cfg.typography && typeof cfg.typography === "object" ? cfg.typography : {};
  let presetName = typeof typo.preset === "string" && typo.preset.trim() ? typo.preset.trim() : "royal-foil";
  if (!VALID_PRESETS.has(presetName)) presetName = "royal-foil";

  const wobbleVal = typo.wobble !== undefined && typo.wobble !== null ? Number(typo.wobble) : 28;
  const foilGlitter = typo.foilGlitter !== undefined && typo.foilGlitter !== null ? Number(typo.foilGlitter) : 0.42;
  const paperGrain = typo.paperGrain !== undefined && typo.paperGrain !== null ? Number(typo.paperGrain) : 0.35;
  const seed = typo.seed !== undefined && typo.seed !== null
    ? Number.parseInt(String(typo.seed), 10)
    : cfg.seed !== undefined && cfg.seed !== null
      ? Number.parseInt(String(cfg.seed), 10)
      : 20261120;

  const photoRel = String(cfg.photo ?? "assets/photo.jpg").trim().replace(/\\/g, "/") || "assets/photo.jpg";
  const photoAbs = resolvePhotoPath(photoRel);
  let photoSize = -1;
  let photoMtimeSec = -1;
  if (fs.existsSync(photoAbs)) {
    try {
      const st = fs.statSync(photoAbs);
      if (st.isFile()) {
        photoSize = Number(st.size);
        photoMtimeSec = Math.floor(st.mtimeMs / 1000);
      }
    } catch {
      // keep -1
    }
  }

  const rawZoom = cfg.photoZoom !== undefined && cfg.photoZoom !== null ? Number(cfg.photoZoom) : 1.05;
  const zoomVal = Number.isFinite(rawZoom) ? roundTo(rawZoom, 4) : 1.05;

  return {
    preset: presetName,
    seed,
    texts: {
      ssr: String(cfg.rarity ?? "SSR").trim(),
      attribute: parseAttributeParts(cfg).trim(),
      subtitle: String(cfg.subtitle ?? "").trim(),
      title: String(cfg.title ?? "").trim(),
      flavor: String(cfg.flavor ?? "").trim(),
      cardNo: String(cfg.cardNo ?? "").trim(),
    },
    typography: {
      layout: typo.layout ?? null,
      palette: typo.palette ?? null,
      font: typo.font ?? null,
      style: typo.style ?? null,
      wobble: roundTo(wobbleVal, 3),
      foilGlitter: roundTo(foilGlitter, 3),
      paperGrain: roundTo(paperGrain, 3),
    },
    photo: {
      path: photoRel,
      size: photoSize,
      mtimeSec: photoMtimeSec,
      fit: String(cfg.photoFit ?? "cover").trim() || "cover",
      position: String(cfg.photoPosition ?? "50% 35%").trim() || "50% 35%",
      zoom: zoomVal,
    },
  };
}

function checkTypoSyncStatus(expectedSource, manifest) {
  const reasons = [];
  if (!manifest) {
    reasons.push("manifest-missing");
    return { needsSync: true, reasons };
  }
  if (manifest.schemaVersion !== 2 || !manifest.source) {
    reasons.push("manifest-schema-outdated");
    return { needsSync: true, reasons };
  }

  const actual = manifest.source;
  if (expectedSource.preset !== actual.preset) reasons.push(`preset(${actual.preset}->${expectedSource.preset})`);
  if (expectedSource.seed !== actual.seed) reasons.push("seed");

  for (const k of Object.keys(expectedSource.texts)) {
    if (expectedSource.texts[k] !== (actual.texts?.[k] ?? "")) {
      reasons.push(`texts.${k}`);
    }
  }
  if (!deepEqual(expectedSource.typography, actual.typography)) {
    reasons.push("typography");
  }
  if (!deepEqual(expectedSource.photo, actual.photo)) {
    reasons.push("photo");
  }

  const items = manifest.items && typeof manifest.items === "object" ? manifest.items : {};
  for (const [k, entry] of Object.entries(items)) {
    if (entry?.src) {
      const abs = path.join(PROJECT_ROOT, String(entry.src));
      if (!fs.existsSync(abs)) {
        reasons.push(`missing-png:${k}`);
      }
    }
  }

  return { needsSync: reasons.length > 0, reasons };
}

function formatLocalDate(now = new Date()) {
  const y = String(now.getFullYear());
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

function resolveOutputPath(preset) {
  fs.mkdirSync(RENDERS_DIR, { recursive: true });
  const safePreset = preset.replace(/[^a-zA-Z0-9_-]/g, "_");
  const dateStr = formatLocalDate();
  const base = `SSR_${safePreset}_${dateStr}`;
  let candidate = path.join(RENDERS_DIR, `${base}.mp4`);
  let seq = 2;
  while (fs.existsSync(candidate)) {
    candidate = path.join(RENDERS_DIR, `${base}_${seq}.mp4`);
    seq += 1;
  }
  return path.relative(PROJECT_ROOT, candidate).replace(/\\/g, "/");
}

const { cliVars, dryRun, forceTypo, noAutoTypo, hasExplicitOutput, passthroughArgs } = parseCliArgs(process.argv.slice(2));
const baseCfg = loadCardConfig();
const effectiveCfg = applyCliOverrides(baseCfg, cliVars);
const expectedSource = buildExpectedSource(effectiveCfg);
const manifest = loadTypoManifest();
const syncStatus = checkTypoSyncStatus(expectedSource, manifest);

function encodeVariablesForHyperFrames(vars) {
  if (!vars || typeof vars !== "object") return {};
  const out = {};
  for (const [k, v] of Object.entries(vars)) {
    if (typeof v === "string" && v.trim() === "") {
      out[k] = "__EMPTY__";
    } else {
      out[k] = v;
    }
  }
  return out;
}

const preset = expectedSource.preset;
const autoOutput = resolveOutputPath(preset);

const cmdArgs = ["--yes", "hyperframes@0.9.72", "render", "-q", "delivery", "--crf", "12"];
if (!hasExplicitOutput) {
  cmdArgs.push("-o", autoOutput);
}
if (Object.keys(cliVars).length > 0) {
  const encodedVars = encodeVariablesForHyperFrames(cliVars);
  cmdArgs.push("--variables", JSON.stringify(encodedVars));
}
cmdArgs.push(...passthroughArgs);

const shouldSyncTypo = !noAutoTypo && (forceTypo || syncStatus.needsSync);
const syncReasonText = forceTypo ? ["forced", ...syncStatus.reasons] : syncStatus.reasons;

if (dryRun) {
  console.log(`[dry-run] preset=${preset}`);
  console.log(`[dry-run] output=${hasExplicitOutput ? "(custom -o)" : autoOutput}`);
  console.log(
    `[dry-run] typoSync=${shouldSyncTypo ? `needs-sync (${syncReasonText.join(", ")})` : noAutoTypo ? "skipped (--no-auto-typo)" : "up-to-date"}`
  );
  if (shouldSyncTypo) {
    console.log(`[dry-run] preflight: python scripts/render_typography.py --overrides-stdin`);
  }
  console.log(`[dry-run] command: npx ${cmdArgs.join(" ")}`);
  process.exit(0);
}

if (shouldSyncTypo) {
  console.log(`[typo-sync] Regenerating typography (${syncReasonText.join(", ")})...`);
  const pyRes = spawnSync("python", ["scripts/render_typography.py", "--overrides-stdin"], {
    cwd: PROJECT_ROOT,
    input: JSON.stringify(cliVars),
    encoding: "utf8",
    stdio: ["pipe", "inherit", "inherit"],
    shell: false,
  });
  if (pyRes.error) {
    console.error(`[typo-sync] Failed to spawn python: ${pyRes.error.message}`);
    process.exit(1);
  }
  if ((pyRes.status ?? 1) !== 0) {
    console.error(`[typo-sync] render_typography.py exited with status ${pyRes.status}`);
    process.exit(pyRes.status ?? 1);
  }
} else {
  console.log(`[typo-sync] up-to-date (${preset})`);
}

console.log(`[render] preset=${preset} -> ${hasExplicitOutput ? "(custom -o)" : autoOutput}`);

const isWin = process.platform === "win32";
const res = spawnSync(isWin ? "npx.cmd" : "npx", cmdArgs, {
  cwd: PROJECT_ROOT,
  stdio: "inherit",
  shell: isWin,
});

process.exit(res.status ?? 1);
