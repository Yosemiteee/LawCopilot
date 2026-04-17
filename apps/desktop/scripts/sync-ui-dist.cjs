const fs = require("fs");
const path = require("path");

const desktopRoot = path.resolve(__dirname, "..");
const workspaceRoot = path.resolve(desktopRoot, "..");
const uiDist = path.resolve(workspaceRoot, "ui", "dist");
const desktopDistRoot = path.resolve(desktopRoot, "dist");

function ensureSource() {
  if (!fs.existsSync(uiDist)) {
    throw new Error(`UI dist not found: ${uiDist}`);
  }
}

function collectTargets() {
  const targets = [];
  if (!fs.existsSync(desktopDistRoot)) {
    return targets;
  }

  for (const entry of fs.readdirSync(desktopDistRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) {
      continue;
    }
    const candidate = path.join(desktopDistRoot, entry.name, "resources", "ui-dist");
    if (fs.existsSync(path.dirname(candidate))) {
      targets.push(candidate);
    }
  }

  return targets;
}

function syncTarget(targetDir) {
  fs.rmSync(targetDir, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(targetDir), { recursive: true });
  fs.cpSync(uiDist, targetDir, { recursive: true });
}

function main() {
  ensureSource();
  const targets = collectTargets();
  if (targets.length === 0) {
    console.log("No packaged desktop ui-dist targets found. UI dist is still updated for dev mode.");
    return;
  }

  for (const target of targets) {
    syncTarget(target);
    console.log(`Synced UI dist -> ${target}`);
  }
}

main();
