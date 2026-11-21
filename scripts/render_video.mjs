/**
 * SSRGenerate — レンダリングラッパー (renders/SSR_{preset}_{YYYYMMDD}.mp4)
 *
 * - card-config.js (typography.preset) からプリセット名を取得し、
 *   renders/SSR_{preset}_{YYYYMMDD}.mp4 形式で出力パスを自動決定する。
 * - 同日に同名ファイルが既に存在する場合は _2, _3 ... と自動連番して上書きを防止する。
 * - 追加引数（例: --variables '{...}' や明示的な -o / --output）はそのまま hyperframes render へ転送する。
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..");
const RENDERS_DIR = path.join(PROJECT_ROOT, "renders");

function readPresetName() {
  // 1. card-config.js から取得
  const cfgPath = path.join(PROJECT_ROOT, "card-config.js");
  if (fs.existsSync(cfgPath)) {
    try {
      const ctx = { window: {} };
      vm.runInNewContext(fs.readFileSync(cfgPath, "utf8"), ctx);
      const p = ctx.window?.SSR_CARD_CONFIG?.typography?.preset;
      if (typeof p === "string" && p.trim()) return p.trim();
    } catch {
      // fallback below
    }
  }
  // 2. typo-manifest.js からフォールバック取得
  const mfPath = path.join(PROJECT_ROOT, "assets", "generated", "typo-manifest.js");
  if (fs.existsSync(mfPath)) {
    try {
      const ctx = { window: {} };
      vm.runInNewContext(fs.readFileSync(mfPath, "utf8"), ctx);
      const p = ctx.window?.SSR_TYPO_MANIFEST?.preset;
      if (typeof p === "string" && p.trim()) return p.trim();
    } catch {
      // fallback below
    }
  }
  return "royal-foil";
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

const extraArgs = process.argv.slice(2);
const hasExplicitOutput = extraArgs.some((a) => a === "-o" || a === "--output" || a.startsWith("--output="));
const dryRun = extraArgs.includes("--dry-run");
const passthroughArgs = extraArgs.filter((a) => a !== "--dry-run");

const preset = readPresetName();
const autoOutput = resolveOutputPath(preset);

const cmdArgs = ["--yes", "hyperframes@0.9.72", "render", "-q", "delivery", "--crf", "12"];
if (!hasExplicitOutput) {
  cmdArgs.push("-o", autoOutput);
}
cmdArgs.push(...passthroughArgs);

if (dryRun) {
  console.log(`[dry-run] preset=${preset}`);
  console.log(`[dry-run] command: npx ${cmdArgs.join(" ")}`);
  process.exit(0);
}

console.log(`[render] preset=${preset} -> ${hasExplicitOutput ? "(custom -o)" : autoOutput}`);

const isWin = process.platform === "win32";
const res = spawnSync(isWin ? "npx.cmd" : "npx", cmdArgs, {
  cwd: PROJECT_ROOT,
  stdio: "inherit",
  shell: isWin,
});

process.exit(res.status ?? 1);
