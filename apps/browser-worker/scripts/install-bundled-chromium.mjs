import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const workerRoot = path.resolve(scriptDir, "..");
const bundledBrowsersPath = path.join(workerRoot, ".bundled-browsers");

function copyCacheDirIfPresent(fromPath, toPath) {
  if (!existsSync(fromPath)) {
    return false;
  }
  cpSync(fromPath, toPath, { recursive: true });
  return true;
}

function seedBundledBrowsersFromCache() {
  const cacheRoot = process.env.PLAYWRIGHT_CACHE_DIR || path.join(os.homedir(), ".cache", "ms-playwright");
  if (!existsSync(cacheRoot)) {
    return false;
  }
  let copiedAny = false;
  for (const entry of readdirSync(cacheRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
      continue;
    }
    if (!/^chromium(?:_headless_shell)?-\d+$/.test(entry.name) && entry.name !== ".links") {
      continue;
    }
    copiedAny = copyCacheDirIfPresent(path.join(cacheRoot, entry.name), path.join(bundledBrowsersPath, entry.name)) || copiedAny;
  }
  return copiedAny;
}

rmSync(bundledBrowsersPath, { recursive: true, force: true });
mkdirSync(bundledBrowsersPath, { recursive: true });

if (seedBundledBrowsersFromCache()) {
  process.stdout.write(
    `Seeded bundled Chromium from ${process.env.PLAYWRIGHT_CACHE_DIR || path.join(os.homedir(), ".cache", "ms-playwright")}\n`,
  );
  process.exit(0);
}

const command = process.platform === "win32" ? "npx.cmd" : "npx";
const completed = spawnSync(command, ["playwright", "install", "chromium"], {
  cwd: workerRoot,
  stdio: "inherit",
  env: {
    ...process.env,
    PLAYWRIGHT_BROWSERS_PATH: bundledBrowsersPath,
  },
});

if (completed.error) {
  throw completed.error;
}
if ((completed.status ?? 1) !== 0) {
  if (seedBundledBrowsersFromCache()) {
    process.stdout.write(
      `Falling back to cached Playwright Chromium from ${process.env.PLAYWRIGHT_CACHE_DIR || path.join(os.homedir(), ".cache", "ms-playwright")}\n`,
    );
    process.exit(0);
  }
  process.exit(completed.status ?? 1);
}
