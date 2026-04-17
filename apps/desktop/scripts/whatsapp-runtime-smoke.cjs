const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

async function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-whatsapp-"));
  process.env.LAWCOPILOT_DESKTOP_CONFIG_DIR = tempRoot;

  const { __internal } = require("../lib/whatsapp-web-bridge.cjs");
  const config = {
    whatsapp: {
      enabled: true,
      mode: "web",
      webSessionName: "smoke-session",
    },
  };

  const userDataDir = __internal.resolveSessionUserDataDir(config);
  assert.equal(userDataDir, path.join(tempRoot, "whatsapp-web-auth", "session-smoke-session"));

  fs.mkdirSync(userDataDir, { recursive: true });
  const child = spawn(
    process.execPath,
    ["-e", "setTimeout(() => process.exit(0), 5000)", "--", `--user-data-dir=${userDataDir}`],
    {
      stdio: "ignore",
      detached: false,
    },
  );

  try {
    await new Promise((resolve) => setTimeout(resolve, 200));
    const conflicts = __internal.sessionConflictProcesses(config);
    assert(conflicts.some((item) => Number(item.pid) === child.pid));
    const busyError = __internal.createSessionBusyError(config);
    assert.equal(busyError.code, "WHATSAPP_WEB_SESSION_BUSY");
    assert.equal(busyError.userDataDir, userDataDir);
    assert(__internal.isSessionConflictError(new Error(`The browser is already running for ${userDataDir}`)));
    console.log("whatsapp-runtime-smoke-ok");
  } finally {
    child.kill("SIGTERM");
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
