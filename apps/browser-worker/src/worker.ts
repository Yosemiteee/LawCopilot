import fs from "node:fs";
import path from "node:path";

import { chromium, type Page } from "playwright";

import { assertUrlAllowed, buildPolicy } from "./policy.js";
import { buildArtifactPath, guessDownloadFileName, writeJsonArtifact } from "./artifacts.js";
import type {
  BrowserAction,
  BrowserActionResult,
  BrowserWorkerRequest,
  BrowserWorkerResponse,
  WorkerPolicy,
} from "./types.js";

async function navigate(page: Page, url: string, policy: WorkerPolicy, timeoutMs: number, waitUntil?: "load" | "domcontentloaded" | "networkidle" | "commit"): Promise<void> {
  assertUrlAllowed(url, policy);
  await page.goto(url, {
    timeout: timeoutMs,
    waitUntil: waitUntil ?? "domcontentloaded",
  });
}

async function runAction(
  page: Page,
  action: BrowserAction,
  policy: WorkerPolicy,
): Promise<BrowserActionResult> {
  const timeoutMs = action.timeoutMs ?? policy.timeoutMs;
  switch (action.type) {
    case "navigate": {
      await navigate(page, action.url, policy, timeoutMs, action.waitUntil);
      return {
        action: "navigate",
        ok: true,
        url: page.url(),
        data: {
          title: await page.title(),
        },
      };
    }
    case "extract": {
      const payload = await page.evaluate(
        ({ selector, includeHtml, includeLinks }) => {
          const root = selector ? document.querySelector(selector) : document.body;
          if (!root) {
            return {
              selector,
              found: false,
              title: document.title,
              url: window.location.href,
            };
          }
          const links = includeLinks
            ? Array.from(root.querySelectorAll("a[href]")).slice(0, 50).map((link) => ({
                text: (link.textContent || "").trim(),
                href: link.getAttribute("href"),
              }))
            : [];
          return {
            selector: selector || "body",
            found: true,
            title: document.title,
            url: window.location.href,
            text: (root.textContent || "").trim(),
            html: includeHtml ? root.innerHTML : undefined,
            links,
          };
        },
        {
          selector: action.selector,
          includeHtml: action.includeHtml ?? false,
          includeLinks: action.includeLinks ?? true,
        },
      );
      const artifactPath = await writeJsonArtifact(
        policy.artifactsDir,
        "extract",
        payload,
        action.selector ? "selector" : "page",
      );
      return {
        action: "extract",
        ok: true,
        url: page.url(),
        data: payload as Record<string, unknown>,
        artifactPaths: [artifactPath],
      };
    }
    case "screenshot": {
      const artifactPath = buildArtifactPath(
        policy.artifactsDir,
        "screenshot",
        "png",
        action.fileName,
      );
      if (action.selector) {
        await page.locator(action.selector).first().screenshot({
          path: artifactPath,
          timeout: timeoutMs,
        });
      } else {
        await page.screenshot({
          path: artifactPath,
          fullPage: action.fullPage ?? true,
          timeout: timeoutMs,
        });
      }
      return {
        action: "screenshot",
        ok: true,
        url: page.url(),
        artifactPaths: [artifactPath],
      };
    }
    case "click": {
      await page.locator(action.selector).first().click({ timeout: timeoutMs });
      return {
        action: "click",
        ok: true,
        url: page.url(),
        data: {
          selector: action.selector,
        },
      };
    }
    case "type": {
      const locator = page.locator(action.selector).first();
      if (action.clearFirst ?? true) {
        await locator.clear({ timeout: timeoutMs });
      }
      await locator.fill(action.text, { timeout: timeoutMs });
      return {
        action: "type",
        ok: true,
        url: page.url(),
        data: {
          selector: action.selector,
          length: action.text.length,
        },
      };
    }
    case "select": {
      const selectedValues = await page
        .locator(action.selector)
        .first()
        .selectOption(action.values, { timeout: timeoutMs });
      return {
        action: "select",
        ok: true,
        url: page.url(),
        data: {
          selector: action.selector,
          values: selectedValues,
        },
      };
    }
    case "download-plan": {
      let targetUrl = action.url;
      if (!targetUrl && action.selector) {
        const href = await page.evaluate((selector) => {
          const el = document.querySelector(selector);
          if (!(el instanceof HTMLAnchorElement)) {
            return null;
          }
          return el.href;
        }, action.selector);
        targetUrl = href ?? undefined;
      }
      if (!targetUrl) {
        throw new Error("download-plan requires url or selector that resolves to a link");
      }
      assertUrlAllowed(targetUrl, policy);
      const fileName = guessDownloadFileName(targetUrl, action.suggestedFileName);
      const targetPath = path.join(policy.downloadsDir, fileName);
      const payload = {
        plannedUrl: targetUrl,
        plannedPath: targetPath,
        fileName,
        requiresApproval: true,
        note: "download-plan does not execute the download; it prepares a safe target path for a future approved step.",
      };
      const artifactPath = await writeJsonArtifact(policy.artifactsDir, "download-plan", payload, fileName);
      return {
        action: "download-plan",
        ok: true,
        url: page.url(),
        data: payload,
        artifactPaths: [artifactPath],
      };
    }
  }
}

function bundledBrowserExecutable(): string {
  const browsersRoot = String(process.env.PLAYWRIGHT_BROWSERS_PATH || "").trim();
  if (!browsersRoot || !fs.existsSync(browsersRoot)) {
    return "";
  }
  const candidates = [
    path.join(browsersRoot, "chromium-1217", "chrome-linux64", "chrome"),
    path.join(browsersRoot, "chromium-1217", "chrome-linux64", "chrome-wrapper"),
  ];
  for (const entry of fs.readdirSync(browsersRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.startsWith("chromium-")) {
      continue;
    }
    candidates.push(
      path.join(browsersRoot, entry.name, "chrome-linux", "chrome"),
      path.join(browsersRoot, entry.name, "chrome-linux", "chrome-wrapper"),
      path.join(browsersRoot, entry.name, "chrome-linux64", "chrome"),
      path.join(browsersRoot, entry.name, "chrome-linux64", "chrome-wrapper"),
      path.join(browsersRoot, entry.name, "chrome-win", "chrome.exe"),
      path.join(browsersRoot, entry.name, "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
    );
  }
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function systemChromiumExecutable(): string {
  const candidates = [
    process.env.LAWCOPILOT_BROWSER_WORKER_EXECUTABLE,
    process.env.CHROME_PATH,
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/snap/bin/chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter(Boolean) as string[];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function normalizeActions(request: BrowserWorkerRequest): BrowserAction[] {
  if (request.actions?.length) {
    return request.actions;
  }
  if (request.action) {
    return [request.action];
  }
  throw new Error("request must include action or actions");
}

export async function executeRequest(request: BrowserWorkerRequest): Promise<BrowserWorkerResponse> {
  const startedAt = new Date().toISOString();
  const policy = await buildPolicy(request);
  const actions = normalizeActions(request);
  const warnings: string[] = [];
  if (policy.allowedDomains.length === 0) {
    warnings.push("no allowlist configured; all http/https domains are currently permitted");
  }
  const bundledExecutablePath = bundledBrowserExecutable();
  const executablePath = bundledExecutablePath || systemChromiumExecutable() || undefined;
  if (executablePath && !bundledExecutablePath) {
    warnings.push("bundled_playwright_chromium_unavailable_using_system_chrome");
  }
  const context = await chromium.launchPersistentContext(policy.profileDir, {
    headless: policy.headless,
    acceptDownloads: true,
    downloadsPath: policy.downloadsDir,
    executablePath,
  });
  const page = context.pages()[0] ?? (await context.newPage());
  const results: BrowserActionResult[] = [];
  try {
    for (const action of actions) {
      try {
        if (action.url && action.type !== "navigate" && action.type !== "download-plan") {
          await navigate(page, action.url, policy, action.timeoutMs ?? policy.timeoutMs);
        }
        const result = await runAction(page, action, policy);
        results.push(result);
      } catch (error) {
        results.push({
          action: action.type,
          ok: false,
          url: page.url(),
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
  } finally {
    await context.close();
  }
  const finishedAt = new Date().toISOString();
  return {
    ok: results.every((item) => item.ok),
    requestId: request.requestId,
    startedAt,
    finishedAt,
    results,
    warnings,
  };
}
