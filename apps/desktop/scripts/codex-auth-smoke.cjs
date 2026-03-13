const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { cancelCodexOAuth, parseAuthUrl, startCodexOAuth } = require("../lib/codex-oauth.cjs");

async function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-codex-oauth-"));
  try {
    assert.equal(
      parseAuthUrl("Open this URL in your LOCAL browser:\nhttps://auth.openai.com/oauth/authorize?state=test"),
      "https://auth.openai.com/oauth/authorize?state=test",
    );

    const status = await startCodexOAuth({ storagePath: tempRoot, provider: {} }, async () => "test-browser");
    assert.equal(status.authStatus, "callback_bekleniyor");
    assert.equal(Boolean(status.authUrl), true);
    assert.equal(status.browserTarget, "test-browser");
    const workspaceRoot = path.join(tempRoot, "openclaw-state", "workspace");
    assert.equal(fs.existsSync(path.join(workspaceRoot, "AGENTS.md")), true);
    assert.equal(fs.existsSync(path.join(workspaceRoot, "BOOTSTRAP.md")), true);
    assert.equal(fs.existsSync(path.join(workspaceRoot, "memory", "daily-logs")), true);
    assert.equal(fs.existsSync(path.join(workspaceRoot, "skills", "manifest.json")), true);

    const cancelled = cancelCodexOAuth();
    assert.equal(cancelled.authStatus, "iptal_edildi");
    console.log("codex-auth-smoke-ok");
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  if (
    process.platform === "win32"
    || message.includes("Docker bulunamadı")
    || message.includes("OpenClaw imajı bulunamadı")
    || message.includes("TTY köprüsü bulunamadı")
    || message.includes("Windows masaüstü kabuğunda gömülü değil")
  ) {
    console.log("codex-auth-smoke-skipped");
    return;
  }
  console.error(error);
  process.exitCode = 1;
});
