const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function findPython(apiRoot) {
  const candidates = [
    path.join(apiRoot, ".venv", "Scripts", "python.exe"),
    path.join(apiRoot, ".venv", "bin", "python"),
    process.platform === "win32" ? "py" : null,
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (["py", "python3", "python"].includes(candidate)) {
      return candidate;
    }
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error("python_runtime_not_found");
}

function run(cmd, args, options = {}) {
  const result = spawnSync(cmd, args, {
    stdio: "inherit",
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`command_failed:${cmd}`);
  }
}

function ensurePackagingDeps(python, apiRoot) {
  const probeArgs = python === "py" ? ["-3", "-c", "import PyInstaller"] : ["-c", "import PyInstaller"];
  const probe = spawnSync(python, probeArgs, { stdio: "ignore", cwd: apiRoot });
  if (probe.status === 0) {
    return;
  }
  const pipArgs = python === "py" ? ["-3", "-m", "pip", "install", "-q", "-r", "requirements.txt"] : ["-m", "pip", "install", "-q", "-r", "requirements.txt"];
  run(python, pipArgs, { cwd: apiRoot });
}

function targetArgs(target) {
  const arch = process.env.LAWCOPILOT_BACKEND_ARCH || (process.arch === "x64" ? "x64" : process.arch === "arm64" ? "arm64" : process.arch);
  if (target === "windows") {
    return ["--target-platform", "win32", "--target-arch", "x64", "--clean"];
  }
  if (target === "macos") {
    return ["--target-platform", "darwin", "--target-arch", arch, "--clean"];
  }
  return [
    "--target-platform",
    process.platform === "win32" ? "win32" : process.platform === "darwin" ? "darwin" : "linux",
    "--target-arch",
    arch,
    "--clean",
  ];
}

function main() {
  const target = process.argv[2] || "local";
  const desktopRoot = path.resolve(__dirname, "..");
  const apiRoot = path.resolve(desktopRoot, "..", "api");
  const python = findPython(apiRoot);
  ensurePackagingDeps(python, apiRoot);
  const script = path.join(apiRoot, "packaging", "build_backend.py");
  const args = python === "py" ? ["-3", script, ...targetArgs(target)] : [script, ...targetArgs(target)];
  run(python, args, { cwd: apiRoot });
}

main();
