#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const platform = process.argv[2];
const distDir = path.resolve(process.argv[3] || "apps/desktop/dist");

if (!platform) {
  console.error("Kullanım: node scripts/verify_packaged_artifacts.cjs <windows|macos|linux> [distDir]");
  process.exit(1);
}

const checks = {
  windows() {
    requireAny("*.exe", "Windows kurulum paketi");
  },
  macos() {
    requireAny("*.dmg", "macOS DMG paketi");
    requireAny("*.zip", "macOS ZIP paketi");
  },
  linux() {
    const unpacked = path.join(distDir, "linux-unpacked");
    requirePath(unpacked, "Linux açılmış uygulama dizini");
    requirePath(path.join(unpacked, "resources", "ui-dist", "index.html"), "Paket içi arayüz dosyası");
    requireAny("linux-unpacked/resources/api-bin/lawcopilot-api*", "Paket içi backend ikilisi");
  },
};

if (!checks[platform]) {
  console.error(`Bilinmeyen platform: ${platform}`);
  process.exit(1);
}

checks[platform]();
console.log(`packaged-artifacts-ok:${platform}`);

function requirePath(targetPath, description) {
  if (!fs.existsSync(targetPath)) {
    throw new Error(`${description} bulunamadı: ${targetPath}`);
  }
}

function requireAny(pattern, description) {
  const regex = globToRegex(pattern);
  const matches = listFiles(distDir).filter((file) => regex.test(file));
  if (!matches.length) {
    throw new Error(`${description} bulunamadı: ${pattern}`);
  }
}

function listFiles(dir) {
  if (!fs.existsSync(dir)) {
    return [];
  }
  const output = [];
  walk(dir, output);
  return output.map((entry) => path.relative(distDir, entry).replace(/\\/g, "/"));
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

function globToRegex(pattern) {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`^${escaped}$`);
}
