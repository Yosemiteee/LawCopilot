const assert = require("assert");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const {
  cancelCodexOAuth,
  getCodexAuthStatus,
  normalizeCodexCallbackInput,
  parseAuthUrl,
  startCodexOAuth,
  submitCodexOAuthCallback,
} = require("../lib/codex-oauth.cjs");
const { waitForLoopbackCallback } = require("../lib/oauth-loopback.cjs");
const { providerSuggestedModels } = require("../lib/provider-model-catalog.cjs");

async function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-codex-oauth-"));
  let occupiedServer = null;
  try {
    const codexModels = providerSuggestedModels("openai-codex");
    assert.ok(codexModels.includes("openai-codex/gpt-5.4"));
    assert.ok(codexModels.includes("openai-codex/gpt-5.4-mini"));

    const geminiModels = providerSuggestedModels("gemini");
    assert.ok(geminiModels.includes("gemini-3.1-pro-preview"));
    assert.ok(geminiModels.includes("gemini-3.1-flash-lite-preview"));

    assert.equal(
      parseAuthUrl("Open this URL in your LOCAL browser:\nhttps://auth.openai.com/oauth/authorize?state=test"),
      "https://auth.openai.com/oauth/authorize?state=test",
    );
    assert.deepEqual(
      normalizeCodexCallbackInput("http://localhost:1455/auth/callback?code=ac_test_code&scope=openid&state=test"),
      {
        raw: "http://localhost:1455/auth/callback?code=ac_test_code&scope=openid&state=test",
        submitValue: "ac_test_code",
        code: "ac_test_code",
      },
    );
    assert.deepEqual(
      normalizeCodexCallbackInput("ac_manual_code"),
      {
        raw: "ac_manual_code",
        submitValue: "ac_manual_code",
        code: "ac_manual_code",
      },
    );

    occupiedServer = http.createServer((_req, res) => {
      res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("occupied");
    });
    await new Promise((resolve, reject) => {
      const handleError = (error) => {
        occupiedServer.off("listening", handleListening);
        reject(error);
      };
      const handleListening = () => {
        occupiedServer.off("error", handleError);
        resolve();
      };
      occupiedServer.once("error", handleError);
      occupiedServer.once("listening", handleListening);
      occupiedServer.listen(0, "127.0.0.1");
    });
    const occupiedPort = occupiedServer.address().port;
    await assert.rejects(
      () => waitForLoopbackCallback(`http://127.0.0.1:${occupiedPort}/auth/callback`, { timeoutMs: 15_000 }),
      /Yerel OAuth yönlendirme portu açılamadı/,
    );
    occupiedServer.close();
    occupiedServer = null;

    const status = await startCodexOAuth({ storagePath: tempRoot, provider: {} }, async () => "test-browser");
    assert.equal(status.authStatus, "callback_bekleniyor");
    assert.equal(Boolean(status.authUrl), true);
    assert.equal(typeof status.browserTarget, "string");
    const state = new URL(status.authUrl).searchParams.get("state");
    assert.equal(Boolean(state), true);
    const workspaceRoot = path.join(tempRoot, "openclaw-state", "workspace");
    assert.equal(fs.existsSync(path.join(workspaceRoot, "AGENTS.md")), true);
    assert.equal(fs.existsSync(path.join(workspaceRoot, "BOOTSTRAP.md")), true);
    assert.equal(fs.existsSync(path.join(workspaceRoot, "memory", "daily-logs")), true);
    assert.equal(fs.existsSync(path.join(workspaceRoot, "skills", "manifest.json")), true);

    const originalFetch = global.fetch;
    try {
      global.fetch = async () => ({
        ok: true,
        text: async () => JSON.stringify({
          access_token: "eyJhbGciOiJIUzI1NiJ9.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOnsiY2hhdGdwdF9hY2NvdW50X2lkIjoiYWNjdF9zbW9rZSJ9fQ.sig",
          refresh_token: "refresh_smoke",
          expires_in: 3600,
          email: "smoke@example.com",
        }),
      });
      const completed = await submitCodexOAuthCallback(
        { storagePath: tempRoot, provider: {} },
        `http://localhost:1455/auth/callback?code=ac_smoke_code&state=${state}`,
      );
      assert.equal(completed.configured, true);
      const persisted = await getCodexAuthStatus({ storagePath: tempRoot, provider: {} });
      assert.equal(persisted.configured, true);
      assert.equal(persisted.authStatus, "bagli");
      const openclawConfigPath = path.join(tempRoot, "openclaw-state", "openclaw.json");
      const openclawConfig = JSON.parse(fs.readFileSync(openclawConfigPath, "utf-8"));
      assert.equal(openclawConfig?.agents?.defaults?.model?.primary, "openai-codex/gpt-5.4");
      const modelsPath = path.join(tempRoot, "openclaw-state", "agents", "main", "agent", "models.json");
      const modelsPayload = JSON.parse(fs.readFileSync(modelsPath, "utf-8"));
      assert.ok((modelsPayload?.providers?.["openai-codex"]?.models || []).includes("openai-codex/gpt-5.4"));
    } finally {
      global.fetch = originalFetch;
    }

    const cancelled = cancelCodexOAuth();
    assert.equal(cancelled.authStatus, "iptal_edildi");
    console.log("codex-auth-smoke-ok");
  } finally {
    if (occupiedServer) {
      occupiedServer.close();
    }
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  if (
    process.platform === "win32"
    || ((error && typeof error === "object" && "code" in error && error.code === "EPERM") && message.includes("listen"))
    || message.includes("listen EPERM")
    || message.includes("operation not permitted 127.0.0.1")
    || message.includes("Docker bulunamadı")
    || message.includes("OpenClaw imajı bulunamadı")
    || message.includes("OpenClaw çalışma ortamı bulunamadı")
    || message.includes("TTY köprüsü bulunamadı")
    || message.includes("Tarayıcı giriş bağlantısı zamanında üretilemedi")
    || message.includes("Tarayıcı giriş bağlantısı hazırlanırken zaman aşımı oluştu")
    || message.includes("Windows masaüstü kabuğunda gömülü değil")
  ) {
    console.log("codex-auth-smoke-skipped");
    return;
  }
  console.error(error);
  process.exitCode = 1;
});
