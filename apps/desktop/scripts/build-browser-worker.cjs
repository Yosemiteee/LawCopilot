const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const workerRoot = path.resolve(__dirname, "..", "..", "browser-worker");
const lockfilePath = path.join(workerRoot, "package-lock.json");
const installStampPath = path.join(workerRoot, "node_modules", ".package-lock.json");
const playwrightPackagePath = path.join(workerRoot, "node_modules", "playwright", "package.json");

function fileMtime(targetPath) {
  try {
    return fs.statSync(targetPath).mtimeMs;
  } catch {
    return 0;
  }
}

function runNpm(args) {
  const npmExecPath = String(process.env.npm_execpath || "").trim();
  const command = npmExecPath && fs.existsSync(npmExecPath)
    ? process.execPath
    : process.platform === "win32"
      ? "npm.cmd"
      : "npm";
  const commandArgs = npmExecPath && fs.existsSync(npmExecPath)
    ? [npmExecPath, ...args]
    : args;
  const result = spawnSync(command, commandArgs, {
    cwd: workerRoot,
    stdio: "inherit",
    env: process.env,
  });
  if (typeof result.status === "number" && result.status !== 0) {
    process.exit(result.status);
  }
  if (result.error) {
    throw result.error;
  }
}

function needsInstall() {
  if (!fs.existsSync(playwrightPackagePath)) {
    return true;
  }
  return fileMtime(lockfilePath) > fileMtime(installStampPath);
}

if (needsInstall()) {
  console.log("[browser-worker] dependencies changed; running npm ci");
  runNpm(["ci"]);
} else {
  console.log("[browser-worker] reusing existing node_modules");
}

runNpm(["run", "build"]);
