const assert = require("assert");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const { loadDesktopConfig, sanitizeDesktopConfig, saveDesktopConfig } = require("../lib/config.cjs");
const { parseAuthUrl } = require("../lib/codex-oauth.cjs");
const { sendTelegramTestMessage, validateProviderConfig, validateTelegramConfig } = require("../lib/integrations.cjs");

async function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-integrations-"));
  const configDir = path.join(tempRoot, "config");
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  const server = await createFakeServer();

  try {
    const baseUrl = `http://127.0.0.1:${server.address().port}`;
    const saved = saveDesktopConfig(
      {
        provider: {
          type: "openai-compatible",
          baseUrl: `${baseUrl}/v1`,
          model: "gpt-test",
          apiKey: "abc123456789xyz",
        },
        telegram: {
          enabled: true,
          botToken: "123456:ABCDEF",
          allowedUserId: "6008898834",
          botUsername: "@Avukatburobot",
        },
      },
      { repoRoot, overrideDir: configDir, storagePath: path.join(tempRoot, "artifacts") },
    );

    const sanitized = sanitizeDesktopConfig(saved);
    assert.equal(Boolean(sanitized.provider.apiKeyConfigured), true);
    assert.equal(Boolean(sanitized.telegram.botTokenConfigured), true);
    assert.ok(String(sanitized.provider.apiKeyMasked).includes("***"));
    assert.ok(String(sanitized.telegram.botTokenMasked).includes("***"));

    const oauthSaved = saveDesktopConfig(
      {
        provider: {
          type: "openai-codex",
          authMode: "oauth",
          model: "openai-codex/gpt-5.3-codex",
          availableModels: ["openai-codex/gpt-5.3-codex", "openai-codex/gpt-5.3-codex-spark"],
          oauthConnected: true,
          validationStatus: "valid",
        },
      },
      { repoRoot, overrideDir: configDir, storagePath: path.join(tempRoot, "artifacts") },
    );
    const oauthSanitized = sanitizeDesktopConfig(oauthSaved);
    assert.equal(oauthSanitized.provider.type, "openai-codex");
    assert.equal(Boolean(oauthSanitized.provider.oauthConnected), true);
    assert.ok(Array.isArray(oauthSanitized.provider.availableModels));
    assert.equal(
      parseAuthUrl("Open this URL in your LOCAL browser:\nhttps://auth.openai.com/oauth/authorize?client_id=test&state=abc"),
      "https://auth.openai.com/oauth/authorize?client_id=test&state=abc",
    );

    const loaded = loadDesktopConfig({ repoRoot, overrideDir: configDir, storagePath: path.join(tempRoot, "artifacts") });
    assert.equal(loaded.provider.type, "openai-codex");
    assert.equal(loaded.telegram.allowedUserId, "6008898834");

    const providerCheck = await validateProviderConfig({
      type: "openai-compatible",
      baseUrl: `${baseUrl}/v1`,
      model: "gpt-test",
      apiKey: "abc123456789xyz",
    });
    assert.equal(providerCheck.ok, true);
    assert.ok(providerCheck.provider.availableModels.includes("gpt-test"));

    const ollamaCheck = await validateProviderConfig({
      type: "ollama",
      baseUrl,
      model: "llama3.1",
    });
    assert.equal(ollamaCheck.ok, true);
    assert.ok(ollamaCheck.provider.availableModels.includes("llama3.1"));

    const telegramCheck = await validateTelegramConfig({
      enabled: true,
      botToken: "123456:ABCDEF",
      allowedUserId: "6008898834",
      apiBaseUrl: baseUrl,
    });
    assert.equal(telegramCheck.ok, true);
    assert.equal(telegramCheck.telegram.botUsername, "@Avukatburobot");

    const testMessage = await sendTelegramTestMessage({
      botToken: "123456:ABCDEF",
      allowedUserId: "6008898834",
      text: "LawCopilot test mesajı",
      apiBaseUrl: baseUrl,
    });
    assert.equal(testMessage.ok, true);
    assert.equal(testMessage.messageId, 42);

    console.log("integration-config-smoke-ok");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

function createFakeServer() {
  const server = http.createServer((req, res) => {
    if (req.url === "/v1/models") {
      if (req.headers.authorization !== "Bearer abc123456789xyz") {
        res.writeHead(401, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { message: "invalid_api_key" } }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ data: [{ id: "gpt-test" }, { id: "gpt-4.1-mini" }] }));
      return;
    }

    if (req.url === "/api/tags") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ models: [{ name: "llama3.1" }, { name: "qwen2.5" }] }));
      return;
    }

    if (req.url === "/bot123456:ABCDEF/getMe") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, result: { id: 1, is_bot: true, username: "Avukatburobot" } }));
      return;
    }

    if (req.url === "/bot123456:ABCDEF/sendMessage" && req.method === "POST") {
      let body = "";
      req.on("data", (chunk) => {
        body += chunk;
      });
      req.on("end", () => {
        const payload = JSON.parse(body || "{}");
        if (payload.chat_id !== "6008898834") {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ ok: false, description: "chat_not_found" }));
          return;
        }
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true, result: { message_id: 42 } }));
      });
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { message: "not_found" } }));
  });

  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
