const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const { resolveRuntimePaths, saveDesktopConfig } = require("../lib/config.cjs");
const { waitForBackend } = require("../lib/backend.cjs");

const DEFAULT_TIMEOUT_MS = Number(process.env.LAWCOPILOT_PACKAGED_LIFECYCLE_TIMEOUT_MS || 45000);
const DEFAULT_HOLD_MS = Number(process.env.LAWCOPILOT_PACKAGED_LIFECYCLE_HOLD_MS || 180000);

function packagedExecutablePath() {
  const explicit = String(process.env.LAWCOPILOT_PACKAGED_APP_PATH || process.argv[2] || "").trim();
  if (explicit) {
    return path.resolve(explicit);
  }
  const appRoot = path.resolve(__dirname, "..");
  const candidates = [
    path.join(appRoot, "dist", "linux-unpacked", "lawcopilot-desktop"),
    path.join(appRoot, "dist", "linux-unpacked", "LawCopilot"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function withTempHome(tempRoot) {
  const home = path.join(tempRoot, "home");
  const xdgConfig = path.join(tempRoot, "xdg-config");
  const xdgData = path.join(tempRoot, "xdg-data");
  fs.mkdirSync(home, { recursive: true });
  fs.mkdirSync(xdgConfig, { recursive: true });
  fs.mkdirSync(xdgData, { recursive: true });
  return { home, xdgConfig, xdgData };
}

function runtimeFiles(storagePath) {
  const runtimeDir = path.join(storagePath, "runtime");
  return {
    runtimeDir,
    desktopPidFile: path.join(runtimeDir, "desktop-main.pid"),
    backendPidFile: path.join(runtimeDir, "desktop-backend.pid"),
  };
}

function readPidFile(filePath) {
  if (!filePath || !fs.existsSync(filePath)) {
    return null;
  }
  try {
    const payload = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const pid = Number(payload?.pid || 0);
    return Number.isFinite(pid) && pid > 0 ? { ...payload, pid } : null;
  } catch {
    return null;
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForCondition(label, predicate, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const result = await Promise.resolve().then(() => predicate());
    if (result) {
      return result;
    }
    await wait(300);
  }
  throw new Error(`condition_timeout:${label}`);
}

async function createLawyerToken(apiBaseUrl, bootstrapKey) {
  const response = await fetch(`${apiBaseUrl}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject: "packaged-lifecycle", role: "lawyer", bootstrap_key: bootstrapKey }),
  });
  if (!response.ok) {
    throw new Error(`token_bootstrap_failed:${response.status}`);
  }
  return response.json();
}

async function apiGet(apiBaseUrl, token, pathname) {
  const response = await fetch(`${apiBaseUrl}${pathname}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    throw new Error(`api_failed:${pathname}:${response.status}`);
  }
  return response.json();
}

function spawnDesktop(executablePath, childEnv, logFile) {
  return spawn(executablePath, ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"], {
    cwd: path.dirname(executablePath),
    env: childEnv,
    stdio: ["ignore", fs.openSync(logFile, "a", 0o600), fs.openSync(logFile, "a", 0o600)],
  });
}

function waitForExit(child, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    if (!child || child.exitCode !== null) {
      resolve({ code: child?.exitCode ?? 0, signal: null });
      return;
    }
    const timer = setTimeout(() => {
      child.removeListener("exit", onExit);
      reject(new Error("child_exit_timeout"));
    }, timeoutMs);
    const onExit = (code, signal) => {
      clearTimeout(timer);
      resolve({ code, signal });
    };
    child.once("exit", onExit);
  });
}

async function stopChild(child, signal = "SIGTERM") {
  if (!child || child.exitCode !== null) {
    return;
  }
  child.kill(signal);
  try {
    await waitForExit(child, 12000);
  } catch {
    if (child.exitCode === null) {
      child.kill("SIGKILL");
      await waitForExit(child, 5000).catch(() => null);
    }
  }
}

async function runScenario(label, task) {
  await Promise.resolve().then(task);
  console.log(`scenario_ok:${label}`);
}

async function main() {
  const executablePath = packagedExecutablePath();
  if (!executablePath) {
    throw new Error("packaged_app_missing");
  }

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-packaged-lifecycle-"));
  const { home, xdgConfig, xdgData } = withTempHome(tempRoot);
  const configDir = path.join(tempRoot, "config");
  const storagePath = path.join(tempRoot, "artifacts");
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const apiPort = 19400 + Math.floor(Math.random() * 400);
  const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
  const bootstrapKey = crypto.randomBytes(24).toString("hex");
  const paths = runtimeFiles(storagePath);

  saveDesktopConfig(
    {
      deploymentMode: "local-only",
      officeId: "packaged-lifecycle-office",
      apiPort,
      apiBaseUrl,
      storagePath,
      runtimeBootstrapKey: bootstrapKey,
      envFile: path.join(storagePath, "runtime", "pilot.env"),
      workspaceRootPath: path.join(tempRoot, "workspace"),
      workspaceRootName: "workspace",
    },
    { repoRoot, overrideDir: configDir, storagePath },
  );

  const childEnv = {
    ...process.env,
    ELECTRON_DISABLE_SANDBOX: "1",
    HOME: home,
    XDG_CONFIG_HOME: xdgConfig,
    XDG_DATA_HOME: xdgData,
    LAWCOPILOT_DESKTOP_CONFIG_DIR: configDir,
    LAWCOPILOT_DISABLE_GPU: "1",
    LAWCOPILOT_DESKTOP_SMOKE: "1",
    LAWCOPILOT_DESKTOP_SMOKE_HOLD_MS: String(Math.max(DEFAULT_HOLD_MS, 60000)),
    LAWCOPILOT_DESKTOP_MAIN_LOG: path.join(tempRoot, "startup-main.log"),
    LAWCOPILOT_BOOTSTRAP_ADMIN_KEY: bootstrapKey,
  };
  delete childEnv.ELECTRON_RUN_AS_NODE;

  let child = spawnDesktop(executablePath, childEnv, path.join(tempRoot, "main-smoke.log"));
  try {
    await runScenario("fresh_launch", async () => {
      const health = await waitForBackend(apiBaseUrl, { timeoutMs: DEFAULT_TIMEOUT_MS });
      assert.equal(health.ok, true);
      const desktopPid = await waitForCondition("desktop_pid_file", () => readPidFile(paths.desktopPidFile));
      const backendPid = await waitForCondition("backend_pid_file", () => readPidFile(paths.backendPidFile));
      assert.equal(desktopPid.pid, child.pid);
      assert.ok(backendPid.pid > 0);
    });

    const token = (await createLawyerToken(apiBaseUrl, bootstrapKey)).access_token;
    await apiGet(apiBaseUrl, token, "/assistant/home");

    await runScenario("long_running_health", async () => {
      for (let index = 0; index < 5; index += 1) {
        const health = await waitForBackend(apiBaseUrl, { timeoutMs: 12000 });
        assert.equal(health.ok, true);
        await wait(1500);
      }
    });

    await runScenario("backend_crash_recovery", async () => {
      const before = await waitForCondition("backend_pid_before_kill", () => readPidFile(paths.backendPidFile));
      process.kill(before.pid, "SIGTERM");
      const recovered = await waitForCondition("backend_pid_after_recovery", async () => {
        const next = readPidFile(paths.backendPidFile);
        if (!next || next.pid === before.pid) {
          return null;
        }
        const health = await waitForBackend(apiBaseUrl, { timeoutMs: 10000 }).catch(() => null);
        return health?.ok ? next : null;
      }, DEFAULT_TIMEOUT_MS);
      assert.notEqual(recovered.pid, before.pid);
    });

    await runScenario("duplicate_launch_guard", async () => {
      const secondStartupLog = path.join(tempRoot, "startup-second.log");
      const second = spawnDesktop(
        executablePath,
        {
          ...childEnv,
          LAWCOPILOT_DESKTOP_MAIN_LOG: secondStartupLog,
        },
        path.join(tempRoot, "second-instance.log"),
      );
      const exit = await waitForExit(second, 12000);
      assert.ok(exit.code === 0 || exit.signal === null);
      const health = await waitForBackend(apiBaseUrl, { timeoutMs: 15000 });
      assert.equal(health.ok, true);
      const secondLog = fs.existsSync(secondStartupLog) ? fs.readFileSync(secondStartupLog, "utf-8") : "";
      assert.match(secondLog, /desktop_quit single_instance_lock_denied/);
      assert.doesNotMatch(secondLog, /backend_boot_begin/);
      assert.doesNotMatch(secondLog, /window_created/);
    });

    await runScenario("graceful_restart", async () => {
      await stopChild(child, "SIGTERM");
      child = spawnDesktop(executablePath, childEnv, path.join(tempRoot, "graceful-restart.log"));
      const health = await waitForBackend(apiBaseUrl, { timeoutMs: DEFAULT_TIMEOUT_MS });
      assert.equal(health.ok, true);
      const desktopPid = await waitForCondition("desktop_pid_after_restart", () => readPidFile(paths.desktopPidFile));
      assert.equal(desktopPid.pid, child.pid);
    });

    await runScenario("crash_relaunch", async () => {
      await stopChild(child, "SIGKILL");
      child = spawnDesktop(executablePath, childEnv, path.join(tempRoot, "crash-relaunch.log"));
      const health = await waitForBackend(apiBaseUrl, { timeoutMs: DEFAULT_TIMEOUT_MS });
      assert.equal(health.ok, true);
      const tokenAfterCrash = (await createLawyerToken(apiBaseUrl, bootstrapKey)).access_token;
      const home = await apiGet(apiBaseUrl, tokenAfterCrash, "/assistant/home");
      assert.ok(Array.isArray(home.proactive_suggestions || []));
    });

    console.log("packaged-lifecycle-smoke-ok");
  } finally {
    await stopChild(child, "SIGTERM").catch(() => null);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
