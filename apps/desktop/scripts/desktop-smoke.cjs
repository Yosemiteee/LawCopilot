const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { defaultDesktopConfig, loadDesktopConfig, resolveRuntimePaths, saveDesktopConfig } = require("../lib/config.cjs");
const { startBackend, stopBackend, waitForBackend } = require("../lib/backend.cjs");

let backendLogPath = "";

async function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-desktop-"));
  const storagePath = path.join(tempRoot, "artifacts");
  const apiPort = 19000 + Math.floor(Math.random() * 1000);
  process.env.LAWCOPILOT_DESKTOP_CONFIG_DIR = tempRoot;

  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const runtimePaths = resolveRuntimePaths({ repoRoot, isPackaged: false });
  const defaults = defaultDesktopConfig(repoRoot);
  assert.equal(defaults.deploymentMode, "local-only");
  assert.equal(defaults.locale, "tr");

  const saved = saveDesktopConfig(
    {
      deploymentMode: "local-only",
      officeId: "pilot-office",
      apiPort,
      apiBaseUrl: `http://127.0.0.1:${apiPort}`,
      storagePath,
      envFile: path.join(storagePath, "runtime", "pilot.env"),
    },
    { repoRoot, overrideDir: tempRoot, storagePath },
  );
  assert.equal(saved.deploymentMode, "local-only");
  const loaded = loadDesktopConfig({ repoRoot, overrideDir: tempRoot, storagePath });
  assert.equal(loaded.deploymentMode, "local-only");
  assert.equal(loaded.officeId, "pilot-office");

  const handle = startBackend(loaded, runtimePaths);
  backendLogPath = handle.outFile || "";
  try {
    const health = await waitForBackend(loaded.apiBaseUrl);
    assert.equal(health.ok, true);
    assert.equal(health.office_id, "pilot-office");
    const telemetry = await fetch(`${loaded.apiBaseUrl}/telemetry/health`, {
      headers: {
        Authorization: `Bearer ${(await createLawyerToken(loaded.apiBaseUrl)).access_token}`
      }
    }).then((response) => response.json());
    assert.equal(telemetry.ok, true);
    console.log("desktop-smoke-ok");
  } finally {
    stopBackend(handle);
  }
}

async function createLawyerToken(apiBaseUrl) {
  const response = await fetch(`${apiBaseUrl}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject: "desktop-smoke", role: "lawyer" })
  });
  if (!response.ok) {
    throw new Error(`token_bootstrap_failed:${response.status}`);
  }
  return response.json();
}

main().catch((error) => {
  console.error(error);
  if (error?.message === "backend_boot_timeout") {
    try {
      if (backendLogPath && fs.existsSync(backendLogPath)) {
        const lines = fs.readFileSync(backendLogPath, "utf-8").trim().split(/\r?\n/).slice(-80);
        console.error("--- backend log tail ---");
        console.error(lines.join("\n"));
      }
    } catch {}
  }
  process.exitCode = 1;
});
