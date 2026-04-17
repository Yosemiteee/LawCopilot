import os from "node:os";
import path from "node:path";
import fs from "node:fs/promises";

import type { BrowserWorkerRequest, WorkerPolicy } from "./types.js";

const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_WORK_ROOT = path.join(os.tmpdir(), "lawcopilot-browser-worker");

function parseAllowedDomains(value: string | undefined): string[] {
  if (!value) {
    return [];
  }
  return value
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function normalizeDir(input: string | undefined, fallbackName: string): string {
  if (!input) {
    return path.join(DEFAULT_WORK_ROOT, fallbackName);
  }
  return path.resolve(input);
}

export async function buildPolicy(request: BrowserWorkerRequest): Promise<WorkerPolicy> {
  const allowedDomains =
    request.allowedDomains?.map((item) => item.trim().toLowerCase()).filter(Boolean) ??
    parseAllowedDomains(process.env.LAW_BROWSER_ALLOWED_DOMAINS);
  const profileDir = normalizeDir(
    request.profileDir ?? process.env.LAW_BROWSER_PROFILE_DIR,
    "profile",
  );
  const artifactsDir = normalizeDir(
    request.artifactsDir ?? process.env.LAW_BROWSER_ARTIFACTS_DIR,
    "artifacts",
  );
  const downloadsDir = normalizeDir(
    request.downloadsDir ?? process.env.LAW_BROWSER_DOWNLOADS_DIR,
    "downloads",
  );
  await Promise.all([
    fs.mkdir(profileDir, { recursive: true }),
    fs.mkdir(artifactsDir, { recursive: true }),
    fs.mkdir(downloadsDir, { recursive: true }),
  ]);
  return {
    allowedDomains,
    profileDir,
    artifactsDir,
    downloadsDir,
    headless: request.headless ?? true,
    timeoutMs: request.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  };
}

export function assertUrlAllowed(url: string, policy: WorkerPolicy): void {
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`unsupported protocol: ${parsed.protocol}`);
  }
  if (policy.allowedDomains.length === 0) {
    throw new Error("navigation blocked: empty domain allowlist");
  }
  const hostname = parsed.hostname.toLowerCase();
  const allowed = policy.allowedDomains.some(
    (domain) => hostname === domain || hostname.endsWith(`.${domain}`),
  );
  if (!allowed) {
    throw new Error(`navigation blocked by domain allowlist: ${hostname}`);
  }
}
