import readline from "node:readline";

import { executeRequest } from "./worker.js";
import type { BrowserAction, BrowserWorkerRequest, BrowserWorkerResponse } from "./types.js";

function parseArgs(argv: string[]): Record<string, string | boolean> {
  const parsed: Record<string, string | boolean> = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      continue;
    }
    const key = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      parsed[key] = true;
      continue;
    }
    parsed[key] = next;
    index += 1;
  }
  return parsed;
}

function buildRequestFromArgs(args: Record<string, string | boolean>): BrowserWorkerRequest {
  const actionName = String(args.action || "extract");
  const action: BrowserAction = (() => {
    switch (actionName) {
      case "navigate":
        return {
          type: "navigate",
          url: String(args.url || ""),
        };
      case "extract":
        return {
          type: "extract",
          url: args.url ? String(args.url) : undefined,
          selector: args.selector ? String(args.selector) : undefined,
          includeHtml: args["include-html"] === true,
          includeLinks: args["include-links"] !== false,
        };
      case "screenshot":
        return {
          type: "screenshot",
          url: args.url ? String(args.url) : undefined,
          selector: args.selector ? String(args.selector) : undefined,
          fullPage: args["full-page"] !== false,
          fileName: args.filename ? String(args.filename) : undefined,
        };
      case "click":
        return {
          type: "click",
          url: args.url ? String(args.url) : undefined,
          selector: String(args.selector || ""),
        };
      case "type":
        return {
          type: "type",
          url: args.url ? String(args.url) : undefined,
          selector: String(args.selector || ""),
          text: String(args.text || ""),
          clearFirst: args["no-clear"] ? false : true,
        };
      case "select":
        return {
          type: "select",
          url: args.url ? String(args.url) : undefined,
          selector: String(args.selector || ""),
          values: String(args.values || "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        };
      case "download-plan":
        return {
          type: "download-plan",
          selector: args.selector ? String(args.selector) : undefined,
          url: args.url ? String(args.url) : undefined,
          suggestedFileName: args.filename ? String(args.filename) : undefined,
        };
      default:
        throw new Error(`unsupported action: ${actionName}`);
    }
  })();
  return {
    requestId: args["request-id"] ? String(args["request-id"]) : undefined,
    headless: args.headless === "false" ? false : true,
    profileDir: args["profile-dir"] ? String(args["profile-dir"]) : undefined,
    artifactsDir: args["artifacts-dir"] ? String(args["artifacts-dir"]) : undefined,
    downloadsDir: args["downloads-dir"] ? String(args["downloads-dir"]) : undefined,
    allowedDomains: args["allowed-domains"]
      ? String(args["allowed-domains"])
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean)
      : undefined,
    action,
  };
}

async function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    process.stdin.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    process.stdin.on("error", reject);
  });
}

function writeResponse(response: BrowserWorkerResponse): void {
  process.stdout.write(`${JSON.stringify(response)}\n`);
}

function buildErrorResponse(
  request: BrowserWorkerRequest | undefined,
  error: unknown,
): BrowserWorkerResponse {
  const actions = request?.actions?.length
    ? request.actions
    : request?.action
      ? [request.action]
      : [];
  const message = error instanceof Error ? error.message : String(error);
  const warnings = message.includes("npx playwright install")
    ? ["Playwright browser executable is missing; run `npx playwright install chromium` before using this worker."]
    : [];
  return {
    ok: false,
    requestId: request?.requestId,
    startedAt: new Date().toISOString(),
    finishedAt: new Date().toISOString(),
    results: actions.map((action) => ({
      action: action.type,
      ok: false,
      error: message,
    })),
    warnings,
  };
}

async function handleOneShotRequest(request: BrowserWorkerRequest): Promise<void> {
  let response: BrowserWorkerResponse;
  try {
    response = await executeRequest(request);
  } catch (error) {
    response = buildErrorResponse(request, error);
  }
  writeResponse(response);
  process.exitCode = response.ok ? 0 : 1;
}

async function runServerMode(): Promise<void> {
  const rl = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });
  for await (const line of rl) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    try {
      const request = JSON.parse(trimmed) as BrowserWorkerRequest;
      let response: BrowserWorkerResponse;
      try {
        response = await executeRequest(request);
      } catch (error) {
        response = buildErrorResponse(request, error);
      }
      writeResponse(response);
    } catch (error) {
      writeResponse(buildErrorResponse(undefined, error));
      process.stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`);
    }
  }
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (args.server === true) {
    await runServerMode();
    return;
  }
  if (Object.keys(args).length > 0) {
    await handleOneShotRequest(buildRequestFromArgs(args));
    return;
  }
  if (!process.stdin.isTTY) {
    const raw = (await readStdin()).trim();
    if (!raw) {
      throw new Error("stdin did not contain a JSON request");
    }
    await handleOneShotRequest(JSON.parse(raw) as BrowserWorkerRequest);
    return;
  }
  throw new Error("no input received; pass JSON via stdin or use CLI args");
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack || error.message : String(error)}\n`);
  process.exitCode = 1;
});
