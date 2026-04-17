const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const { loadDesktopConfig, resolveRuntimePaths, saveDesktopConfig } = require("../lib/config.cjs");
const { waitForBackend } = require("../lib/backend.cjs");

const DEFAULT_SMOKE_TIMEOUT_MS = Number(process.env.LAWCOPILOT_PACKAGED_SMOKE_TIMEOUT_MS || 30000);
const DEFAULT_SMOKE_HOLD_MS = Number(process.env.LAWCOPILOT_DESKTOP_SMOKE_HOLD_MS || 20000);

function syntheticPackagedPathSmoke() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-packaged-paths-"));
  const resourcesPath = path.join(tempRoot, "resources");
  const userDataPath = path.join(tempRoot, "user-data");
  const configDir = path.join(tempRoot, "config");
  fs.mkdirSync(path.join(resourcesPath, "ui-dist"), { recursive: true });
  fs.mkdirSync(path.join(resourcesPath, "api-bin"), { recursive: true });
  fs.mkdirSync(path.join(resourcesPath, "browser-worker", "dist"), { recursive: true });

  const runtimePaths = resolveRuntimePaths({
    repoRoot: path.resolve(__dirname, "..", "..", ".."),
    isPackaged: true,
    resourcesPath,
    userDataPath,
  });

  assert.equal(runtimePaths.uiDist, path.join(resourcesPath, "ui-dist"));
  assert.equal(runtimePaths.apiRoot, path.join(resourcesPath, "api-bin"));
  assert.equal(runtimePaths.backendBinRoot, path.join(resourcesPath, "api-bin"));
  assert.equal(runtimePaths.browserWorkerRoot, path.join(resourcesPath, "browser-worker"));
  assert.equal(runtimePaths.artifactsRoot, path.join(userDataPath, "artifacts"));

  const saved = saveDesktopConfig(
    {
      deploymentMode: "local-only",
      workspaceRootPath: path.join(tempRoot, "davalar"),
      workspaceRootName: "davalar",
      workspaceRootHash: "deneme-hash",
      storagePath: runtimePaths.artifactsRoot,
      scanOnStartup: true,
    },
    {
      repoRoot: runtimePaths.repoRoot,
      overrideDir: configDir,
      storagePath: runtimePaths.artifactsRoot,
    },
  );

  const loaded = loadDesktopConfig({
    repoRoot: runtimePaths.repoRoot,
    overrideDir: configDir,
    storagePath: runtimePaths.artifactsRoot,
  });

  assert.equal(saved.storagePath, runtimePaths.artifactsRoot);
  assert.equal(saved.envFile, path.join(runtimePaths.artifactsRoot, "runtime", "pilot.env"));
  assert.equal(loaded.workspaceRootName, "davalar");
  assert.equal(loaded.workspaceRootHash, "deneme-hash");
  assert.equal(loaded.storagePath, runtimePaths.artifactsRoot);
}

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

function readTextIfExists(filePath) {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return "";
  }
}

function isSkippablePackagedSandboxFailure(error, smokeLog) {
  const message = error instanceof Error ? error.message : String(error || "");
  if (!message.includes("packaged_app_exited:null:SIGTRAP")) {
    return false;
  }
  const logText = readTextIfExists(smokeLog);
  return logText.includes("sandbox_host_linux.cc:41") && logText.includes("Operation not permitted");
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

async function createLawyerToken(apiBaseUrl, bootstrapKey = "") {
  const payload = { subject: "packaged-smoke", role: "lawyer" };
  if (bootstrapKey) {
    payload.bootstrap_key = bootstrapKey;
  }
  const response = await fetch(`${apiBaseUrl}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`token_bootstrap_failed:${response.status}`);
  }
  return response.json();
}

async function apiRequest(apiBaseUrl, token, pathname, options = {}) {
  const headers = {
    Authorization: `Bearer ${token}`,
    ...(options.headers || {}),
  };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${apiBaseUrl}${pathname}`, {
    method: options.method || "GET",
    headers,
    body: options.body,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`${pathname}:${response.status}:${JSON.stringify(payload)}`);
  }
  return payload;
}

function waitForChildExit(child, timeoutMs = 5000) {
  return new Promise((resolve) => {
    if (!child || child.exitCode !== null) {
      resolve();
      return;
    }
    let settled = false;
    const finish = () => {
      if (settled) {
        return;
      }
      settled = true;
      resolve();
    };
    child.once("exit", finish);
    setTimeout(finish, timeoutMs);
  });
}

function waitForChildUnexpectedExit(child) {
  let active = true;
  let settled = false;
  let rejectPromise = () => {};
  const onExit = (code, signal) => {
    if (!active || settled) {
      return;
    }
    settled = true;
    rejectPromise(new Error(`packaged_app_exited:${String(code ?? "null")}:${String(signal ?? "")}`));
  };
  const onError = (error) => {
    if (!active || settled) {
      return;
    }
    settled = true;
    rejectPromise(error instanceof Error ? error : new Error(String(error || "packaged_app_spawn_failed")));
  };
  const promise = new Promise((_, reject) => {
    if (!child) {
      settled = true;
      reject(new Error("packaged_app_missing"));
      return;
    }
    rejectPromise = reject;
    child.once("exit", onExit);
    child.once("error", onError);
  });
  return {
    promise,
    cancel() {
      active = false;
      if (!child) {
        return;
      }
      child.removeListener("exit", onExit);
      child.removeListener("error", onError);
    },
  };
}

async function guardWithUnexpectedExit(promise, exitWatcher) {
  return Promise.race([promise, exitWatcher.promise]);
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) {
    return;
  }
  child.kill("SIGTERM");
  await waitForChildExit(child, 4000);
  if (child.exitCode === null) {
    child.kill("SIGKILL");
    await waitForChildExit(child, 2000);
  }
}

async function runLivePackagedSmoke(executablePath) {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-packaged-live-"));
  const { home, xdgConfig, xdgData } = withTempHome(tempRoot);
  const configDir = path.join(tempRoot, "config");
  const storagePath = path.join(tempRoot, "artifacts");
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const apiPort = 19200 + Math.floor(Math.random() * 600);
  const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
  const smokeLog = path.join(tempRoot, "packaged-smoke.log");
  const bootstrapKey = crypto.randomBytes(24).toString("hex");

  saveDesktopConfig(
    {
      deploymentMode: "local-only",
      officeId: "packaged-smoke-office",
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
    LAWCOPILOT_DESKTOP_SMOKE_HOLD_MS: String(Math.max(5000, DEFAULT_SMOKE_HOLD_MS)),
    LAWCOPILOT_BOOTSTRAP_ADMIN_KEY: bootstrapKey,
  };
  delete childEnv.ELECTRON_RUN_AS_NODE;

  const child = spawn(executablePath, ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"], {
    cwd: path.dirname(executablePath),
    env: childEnv,
    stdio: ["ignore", fs.openSync(smokeLog, "a", 0o600), fs.openSync(smokeLog, "a", 0o600)],
  });
  const exitWatcher = waitForChildUnexpectedExit(child);

  try {
    const health = await guardWithUnexpectedExit(waitForBackend(apiBaseUrl, DEFAULT_SMOKE_TIMEOUT_MS), exitWatcher);
    assert.equal(health.ok, true);
    assert.equal(health.office_id, "packaged-smoke-office");

    const token = (await guardWithUnexpectedExit(createLawyerToken(apiBaseUrl, bootstrapKey), exitWatcher)).access_token;

    const emptyHome = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/home"), exitWatcher);
    assert.ok(emptyHome);
    assert.ok(Array.isArray(emptyHome.proactive_suggestions || []));

    await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/knowledge-base/ingest", {
      method: "POST",
      body: JSON.stringify({
        source_type: "user_preferences",
        title: "Iletisim tarzi",
        content: "E-posta yanitlari kisa, nazik ve acik olmali.",
        metadata: { field: "communication_style", scope: "personal" },
        tags: ["preferences", "email"],
      }),
    }), exitWatcher);
    await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/knowledge-base/ingest", {
      method: "POST",
      body: JSON.stringify({
        source_type: "assistant_file_back",
        title: "Konum tercihleri",
        content: "Yakin cevrede hafif yemek ve toplu tasima onerileri kullanisli olur.",
        metadata: { page_key: "places", record_type: "location_note", scope: "personal" },
        tags: ["location", "preferences"],
      }),
    }), exitWatcher);

    const search = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/knowledge-base/search", {
      method: "POST",
      body: JSON.stringify({ query: "mail tarzim neydi", scopes: ["personal"], limit: 5 }),
    }), exitWatcher);
    assert.equal(search.backend, "sqlite_hybrid_fts_v1");
    assert.ok(Array.isArray(search.items));
    assert.ok(search.items.length > 0);

    const locationSuccess = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/location/context", {
      method: "POST",
      body: JSON.stringify({
        current_place: {
          place_id: "device-1",
          label: "Cihaz konumu",
          category: "device_location",
          area: "Kadikoy",
          latitude: 40.991,
          longitude: 29.026,
          accuracy_meters: 42,
          started_at: "2026-04-08T12:36:00+00:00",
          tags: ["device_capture"],
        },
        recent_places: [],
        nearby_categories: ["cafe", "transit"],
        observed_at: "2026-04-08T12:36:00+00:00",
        source: "browser_geolocation",
        provider: "desktop_browser_capture_v1",
        provider_mode: "desktop_renderer_geolocation",
        provider_status: "fresh",
        capture_mode: "device_capture",
        permission_state: "granted",
        persist_raw: true,
      }),
    }), exitWatcher);
    assert.equal(locationSuccess.location_context.provider_status, "fresh");

    const locationDenied = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/location/context", {
      method: "POST",
      body: JSON.stringify({
        current_place: {},
        recent_places: [],
        nearby_categories: ["cafe", "transit"],
        observed_at: "2026-04-08T12:40:00+00:00",
        source: "browser_geolocation",
        provider: "desktop_browser_capture_v1",
        provider_mode: "desktop_renderer_geolocation",
        provider_status: "permission_denied",
        capture_mode: "device_capture",
        permission_state: "denied",
        capture_failure_reason: "Konum izni reddedildi.",
        persist_raw: false,
      }),
    }), exitWatcher);
    assert.equal(locationDenied.location_context.provider_status, "permission_denied");
    assert.equal(locationDenied.location_context.current_place, null);

    const googleSync = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/integrations/google/sync", {
      method: "POST",
      body: JSON.stringify({
        account_label: "Smoke Google",
        email_threads: [
          {
            provider: "google",
            thread_ref: "thread-1",
            subject: "Akşam planı",
            snippet: "Akşam planını hafifletelim.",
            sender: "ayse@example.com",
            unread_count: 1,
            reply_needed: true,
          },
        ],
      }),
    }), exitWatcher);
    assert.ok((googleSync.knowledge_base_sync?.result?.synced_record_count || 0) >= 0);
    assert.deepEqual(googleSync.knowledge_base_sync?.result?.failed_connectors || [], []);

    const connectorStatus = await guardWithUnexpectedExit(
      apiRequest(apiBaseUrl, token, "/assistant/connectors/sync-status"),
      exitWatcher,
    );
    assert.ok(Array.isArray(connectorStatus.items));
    assert.ok(connectorStatus.items.some((item) => item.connector === "email_threads"));

    const orchestration = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/orchestration/run", {
      method: "POST",
      body: JSON.stringify({
        job_names: ["connector_sync", "trigger_evaluation", "suppression_cleanup"],
        reason: "packaged_smoke",
        force: true,
      }),
    }), exitWatcher);
    assert.ok(Array.isArray(orchestration.results));
    assert.ok(orchestration.results.some((item) => item.job === "trigger_evaluation"));

    const recommendations = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/recommendations", {
      method: "POST",
      body: JSON.stringify({
        current_context: "Yogun gun icin ne onermelisin?",
        location_context: "Kadikoy",
        limit: 2,
        persist: true,
      }),
    }), exitWatcher);
    assert.ok(Array.isArray(recommendations.items));
    assert.ok(recommendations.items.length > 0);

    const actionPreview = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/actions/generate", {
      method: "POST",
      body: JSON.stringify({
        action_type: "create_task",
        target_channel: "task",
        title: "Smoke gorevi",
        instructions: "Yarin sabah icin kisa bir gorev taslagi hazirla.",
        source_refs: [],
      }),
    }), exitWatcher);
    assert.equal(actionPreview.action_ladder.preview_required_before_execute, true);
    assert.equal(actionPreview.action_ladder.execution_policy, "preview_then_confirm");

    const systemStatus = await guardWithUnexpectedExit(
      apiRequest(apiBaseUrl, token, "/assistant/system/status"),
      exitWatcher,
    );
    assert.equal(systemStatus.execution_policy?.draft_first_external_actions, true);
    assert.ok(Array.isArray(systemStatus.canonical_sources));
    assert.ok(systemStatus.canonical_sources.some((item) => item?.key === "system_contract"));

    const finalHome = await guardWithUnexpectedExit(apiRequest(apiBaseUrl, token, "/assistant/home"), exitWatcher);
    assert.ok(Array.isArray(finalHome.proactive_suggestions || []));
    assert.ok(finalHome.location_context);
    assert.ok(finalHome.connector_sync_status);
    assert.ok(finalHome.orchestration_status);

    return {
      apiBaseUrl,
      smokeLog,
      storagePath,
    };
  } catch (error) {
    if (isSkippablePackagedSandboxFailure(error, smokeLog)) {
      return {
        apiBaseUrl,
        smokeLog,
        storagePath,
        skipped: true,
      };
    }
    throw error;
  } finally {
    exitWatcher.cancel();
    await stopChild(child);
  }
}

async function main() {
  syntheticPackagedPathSmoke();

  const executablePath = packagedExecutablePath();
  if (!executablePath) {
    console.log("packaged-runtime-smoke-ok (path-only)");
    return;
  }

  const result = await runLivePackagedSmoke(executablePath);
  assert.ok(fs.existsSync(result.smokeLog));
  if (result.skipped) {
    console.log("packaged-runtime-smoke-skipped");
    return;
  }
  console.log("packaged-runtime-smoke-ok");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
