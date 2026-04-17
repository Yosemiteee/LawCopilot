import fs from "node:fs/promises";
import path from "node:path";

function sanitizeSegment(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "artifact";
}

export function buildArtifactPath(
  artifactsDir: string,
  prefix: string,
  extension: string,
  hint?: string,
): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const safeHint = hint ? `-${sanitizeSegment(hint)}` : "";
  return path.join(artifactsDir, `${prefix}-${stamp}${safeHint}.${extension}`);
}

export async function writeJsonArtifact(
  artifactsDir: string,
  prefix: string,
  payload: unknown,
  hint?: string,
): Promise<string> {
  const filePath = buildArtifactPath(artifactsDir, prefix, "json", hint);
  await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf8");
  return filePath;
}

export function guessDownloadFileName(url: string, suggestedFileName?: string): string {
  if (suggestedFileName?.trim()) {
    return sanitizeSegment(suggestedFileName.trim());
  }
  const pathname = new URL(url).pathname.split("/").filter(Boolean).pop();
  return sanitizeSegment(pathname || "download.bin");
}
