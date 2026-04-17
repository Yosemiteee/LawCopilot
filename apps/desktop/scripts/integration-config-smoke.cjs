const assert = require("assert");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const { loadDesktopConfig, sanitizeDesktopConfig, saveDesktopConfig } = require("../lib/config.cjs");
const { backendEnv, resolveBrowserWorkerEntry, resolveBrowserWorkerInstallEntry } = require("../lib/backend.cjs");
const { parseAuthUrl } = require("../lib/codex-oauth.cjs");
const { buildMimeMessage, encodeMimeHeaderValue } = require("../lib/google-data.cjs");
const { sendTelegramTestMessage, validateProviderConfig, validateTelegramConfig } = require("../lib/integrations.cjs");
const { describeOutlookCallbackError } = require("../lib/outlook-oauth.cjs");

async function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-integrations-"));
  const configDir = path.join(tempRoot, "config");
  const repoRoot = path.resolve(__dirname, "..", "..", "..");
  let server = null;

  try {
    server = await createFakeServer();
  } catch (error) {
    if (error?.code !== "EPERM") {
      throw error;
    }
  }

  try {
    const baseUrl = server ? `http://127.0.0.1:${server.address().port}` : "http://127.0.0.1:0";
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
        outlook: {
          enabled: true,
          accountLabel: "sami@outlook.com",
          tenantId: "common",
          clientId: "outlook-client-id",
          oauthConnected: true,
          validationStatus: "valid",
          accessToken: "outlook-access-token",
          refreshToken: "outlook-refresh-token",
        },
        automation: {
          enabled: true,
          autoSyncConnectedServices: true,
          desktopNotifications: true,
          automationRules: [
            {
              summary: "WhatsApp'ta günaydın yazanlara kısa yanıt ver.",
              instruction: "Günaydın yazanlara kısa, profesyonel bir cevap ver.",
              mode: "auto_reply",
              channels: ["whatsapp"],
              targets: ["+905551112233"],
              match_terms: ["günaydın"],
              reply_text: "Günaydın, size birazdan dönüş yapacağım.",
              active: true,
            },
          ],
        },
      },
      { repoRoot, overrideDir: configDir, storagePath: path.join(tempRoot, "artifacts") },
    );

    const sanitized = sanitizeDesktopConfig(saved);
    assert.equal(Boolean(sanitized.provider.apiKeyConfigured), true);
    assert.equal(Boolean(sanitized.telegram.botTokenConfigured), true);
    assert.equal(Boolean(sanitized.outlook.clientIdConfigured), true);
    assert.equal(Boolean(sanitized.outlook.accessTokenConfigured), true);
    assert.equal(Boolean(sanitized.outlook.refreshTokenConfigured), true);
    assert.equal(Boolean(sanitized.outlook.oauthConnected), true);
    assert.equal(sanitized.outlook.accountLabel, "sami@outlook.com");
    assert.ok(Array.isArray(sanitized.outlook.scopes));
    assert.ok(sanitized.outlook.scopes.includes("Mail.Read"));
    assert.ok(sanitized.outlook.scopes.includes("Calendars.Read"));
    assert.equal(Boolean(sanitized.automation.enabled), true);
    assert.equal(Boolean(sanitized.automation.autoSyncConnectedServices), true);
    assert.equal(Boolean(sanitized.automation.desktopNotifications), true);
    assert.equal(Array.isArray(sanitized.automation.automationRules), true);
    assert.equal(sanitized.automation.automationRules.length, 1);
    assert.equal(sanitized.automation.automationRules[0].summary, "WhatsApp'ta günaydın yazanlara kısa yanıt ver.");
    assert.deepEqual(sanitized.automation.automationRules[0].channels, ["whatsapp"]);
    assert.deepEqual(sanitized.automation.automationRules[0].targets, ["+905551112233"]);
    assert.ok(String(sanitized.provider.apiKeyMasked).includes("***"));
    assert.ok(String(sanitized.telegram.botTokenMasked).includes("***"));

    const oauthSaved = saveDesktopConfig(
      {
        provider: {
          type: "openai-codex",
          authMode: "oauth",
          model: "openai-codex/gpt-5.4",
          availableModels: ["openai-codex/gpt-5.4", "openai-codex/gpt-5.4-mini", "openai-codex/gpt-5.2-codex"],
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
    assert.equal(loaded.outlook.accountLabel, "sami@outlook.com");
    assert.equal(loaded.outlook.clientId, "outlook-client-id");
    assert.equal(encodeMimeHeaderValue("Kısa mesaj"), "=?UTF-8?B?S8Sxc2EgbWVzYWo=?=");
    const rawMime = Buffer.from(
      buildMimeMessage({
        to: "samiyusuf178@gmail.com",
        subject: "Kısa mesaj",
        body: "Merhaba",
      }).replace(/-/g, "+").replace(/_/g, "/"),
      "base64",
    ).toString("utf8");
    assert.ok(rawMime.includes("Subject: =?UTF-8?B?S8Sxc2EgbWVzYWo=?="));
    assert.ok(rawMime.includes("Content-Transfer-Encoding: quoted-printable"));
    const repairedSubjectMime = Buffer.from(
      buildMimeMessage({
        to: "samiyusuf178@gmail.com",
        subject: "KÄ±sa mesaj",
        body: "Merhaba, kısa bir mesaj iletmek istedim.",
      }).replace(/-/g, "+").replace(/_/g, "/"),
      "base64",
    ).toString("utf8");
    assert.ok(repairedSubjectMime.includes("Subject: =?UTF-8?B?S8Sxc2EgbWVzYWo=?="));
    assert.ok(repairedSubjectMime.includes("Merhaba, k=C4=B1sa bir mesaj iletmek istedim."));
    const tenantMismatch = describeOutlookCallbackError(
      "http://127.0.0.1:1458/outlook/auth/callback?error=access_denied&error_description=AADSTS50020%3A+Selected+user+account+does+not+exist+in+tenant+%27Microsoft+Services%27+and+needs+to+be+added+as+an+external+user+first.",
      { tenantId: "common", redirectUri: "http://127.0.0.1:1458/outlook/auth/callback" },
    );
    assert.ok(tenantMismatch.includes("Supported account types"));
    assert.ok(tenantMismatch.includes("common"));

    const redirectMismatch = describeOutlookCallbackError(
      "http://127.0.0.1:1458/outlook/auth/callback?error=invalid_request&error_description=AADSTS50011%3A+The+redirect+URI+is+not+registered.",
      { tenantId: "common", redirectUri: "http://127.0.0.1:1458/outlook/auth/callback" },
    );
    assert.ok(redirectMismatch.includes("Mobile and desktop applications"));
    assert.ok(redirectMismatch.includes("127.0.0.1:1458/outlook/auth/callback"));

    const runtimePaths = {
      repoRoot,
      browserWorkerRoot: path.join(repoRoot, "apps", "browser-worker"),
      artifactsRoot: path.join(tempRoot, "artifacts"),
      isPackaged: true,
    };
    const browserEntry = resolveBrowserWorkerEntry(runtimePaths);
    const browserInstallEntry = resolveBrowserWorkerInstallEntry(runtimePaths);
    assert.equal(browserEntry.endsWith(path.join("apps", "browser-worker", "dist", "index.js")), true);
    assert.equal(browserInstallEntry.endsWith(path.join("apps", "browser-worker", "node_modules", "playwright", "cli.js")), true);
    const env = backendEnv(loaded, runtimePaths);
    assert.equal(env.LAWCOPILOT_BROWSER_WORKER_ENABLED, "true");
    assert.equal(env.LAWCOPILOT_BROWSER_WORKER_ENTRY.endsWith(path.join("apps", "browser-worker", "dist", "index.js")), true);
    assert.equal(env.LAWCOPILOT_BROWSER_WORKER_INSTALL_ENTRY.endsWith(path.join("apps", "browser-worker", "node_modules", "playwright", "cli.js")), true);
    assert.equal(env.LAWCOPILOT_BROWSER_WORKER_BROWSERS_PATH.endsWith(path.join("apps", "browser-worker", ".bundled-browsers")), true);
    assert.equal(env.LAWCOPILOT_BROWSER_WORKER_COMMAND.length > 0, true);
    assert.equal(env.LAWCOPILOT_BROWSER_WORKER_RUN_AS_NODE, "true");
    assert.equal(env.LAWCOPILOT_BROWSER_ARTIFACTS_DIR.endsWith(path.join("artifacts", "browser", "artifacts")), true);
    assert.equal(env.PLAYWRIGHT_BROWSERS_PATH.endsWith(path.join("apps", "browser-worker", ".bundled-browsers")), true);

    if (server) {
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

      const geminiCheck = await validateProviderConfig({
        type: "gemini",
        baseUrl: `${baseUrl}/v1beta`,
        model: "gemini-2.5-flash",
        apiKey: "abc123456789xyz",
      });
      assert.equal(geminiCheck.ok, true);
      assert.ok(geminiCheck.provider.availableModels.includes("gemini-2.5-flash"));

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
    }

    console.log("integration-config-smoke-ok");
  } finally {
    if (server) {
      await new Promise((resolve) => server.close(resolve));
    }
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

    if (req.url === "/v1beta/models?key=abc123456789xyz") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ models: [{ name: "models/gemini-2.5-flash" }, { name: "models/gemini-2.5-pro" }] }));
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

  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.removeListener("error", reject);
      resolve(server);
    });
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
