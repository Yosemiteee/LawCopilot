#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const platform = process.argv[2];
const distDir = path.resolve(process.argv[3] || "apps/desktop/dist");
const outFile = path.resolve(process.argv[4] || "artifacts/build-artifacts.json");
const packageJson = JSON.parse(fs.readFileSync(path.resolve("apps/desktop/package.json"), "utf8"));

if (!platform) {
  console.error("Kullanım: node scripts/write_artifact_manifest.cjs <windows|macos|linux> [distDir] [outFile]");
  process.exit(1);
}

const files = listFiles(distDir)
  .filter((file) => keepForPlatform(platform, file))
  .map((file) => {
    const full = path.join(distDir, file);
    const stat = fs.statSync(full);
    return {
      path: file,
      size_bytes: stat.size,
    };
  });

fs.mkdirSync(path.dirname(outFile), { recursive: true });
fs.writeFileSync(
  outFile,
  JSON.stringify(
    {
      product: packageJson.build?.productName || packageJson.name,
      version: packageJson.version,
      platform,
      generated_at: new Date().toISOString(),
      files,
    },
    null,
    2,
  ),
);

console.log(outFile);

function listFiles(dir) {
  if (!fs.existsSync(dir)) {
    return [];
  }
  const result = [];
  walk(dir, result);
  return result.map((entry) => path.relative(dir, entry).replace(/\\/g, "/")).sort();
}

function walk(dir, output) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, output);
    } else {
      output.push(full);
    }
  }
}

function keepForPlatform(platformName, file) {
  if (platformName === "windows") {
    return file.endsWith(".exe");
  }
  if (platformName === "macos") {
    return file.endsWith(".dmg") || file.endsWith(".zip");
  }
  return file.startsWith("linux-unpacked/");
}
