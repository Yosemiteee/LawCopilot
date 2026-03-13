const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { shell } = require("electron");

const WINDOWS_SYSTEM_ROOTS = new Set(["windows", "program files", "program files (x86)", "programdata"]);
const WINDOWS_SHALLOW_ROOTS = new Set(["users"]);
const MAC_SYSTEM_ROOTS = new Set(["applications", "library", "system"]);
const MAC_SHALLOW_ROOTS = new Set(["users"]);
const LINUX_SYSTEM_ROOTS = new Set(["bin", "boot", "dev", "etc", "lib", "lib64", "opt", "proc", "root", "run", "sbin", "srv", "sys"]);
const LINUX_SHALLOW_ROOTS = new Set(["home", "usr", "var"]);

function sha256(value) {
  return crypto.createHash("sha256").update(String(value)).digest("hex");
}

function resolveRootPath(rawPath) {
  if (!rawPath || !String(rawPath).trim()) {
    throw new Error("Çalışma klasörü boş olamaz.");
  }
  const resolved = fs.realpathSync(path.resolve(rawPath));
  const stat = fs.statSync(resolved);
  if (!stat.isDirectory()) {
    throw new Error("Seçilen yol bir klasör olmalı.");
  }
  return resolved;
}

function validateWorkspaceRoot(rawPath) {
  const resolved = resolveRootPath(rawPath);
  const home = os.homedir();
  if (path.resolve(resolved) === path.resolve(home)) {
    throw new Error("Kullanıcı klasörünün tamamı seçilemez.");
  }
  if (process.platform === "win32") {
    const parsed = path.parse(resolved);
    const normalized = resolved.replace(/[\\/]+$/, "").toLowerCase();
    if (normalized === parsed.root.replace(/[\\/]+$/, "").toLowerCase()) {
      throw new Error("Disk kökleri çalışma klasörü olarak seçilemez.");
    }
    const parts = resolved.split(/[\\/]+/).filter(Boolean);
    const first = parts[0] ? parts[0].toLowerCase() : "";
    if (first && WINDOWS_SYSTEM_ROOTS.has(first)) {
      throw new Error("Sistem klasörleri çalışma klasörü olarak seçilemez.");
    }
    // Allow Users/username/subfolder (depth >= 3 parts)
    if (first && WINDOWS_SHALLOW_ROOTS.has(first) && parts.length < 3) {
      throw new Error("Sistem klasörleri çalışma klasörü olarak seçilemez.");
    }
    if (resolved.startsWith("\\\\")) {
      throw new Error("Ağ paylaşımları ilk sürümde desteklenmiyor.");
    }
  } else if (process.platform === "darwin") {
    if (resolved === "/") {
      throw new Error("Disk kökleri çalışma klasörü olarak seçilemez.");
    }
    const parts = resolved.split("/").filter(Boolean);
    const first = parts[0] ? parts[0].toLowerCase() : "";
    if (first && MAC_SYSTEM_ROOTS.has(first)) {
      throw new Error("Sistem klasörleri çalışma klasörü olarak seçilemez.");
    }
    // Allow /Users/username/subfolder (depth >= 3 parts)
    if (first && MAC_SHALLOW_ROOTS.has(first) && parts.length < 3) {
      throw new Error("Sistem klasörleri çalışma klasörü olarak seçilemez.");
    }
  } else {
    if (resolved === "/") {
      throw new Error("Disk kökleri çalışma klasörü olarak seçilemez.");
    }
    const parts = resolved.split("/").filter(Boolean);
    const first = parts[0] ? parts[0].toLowerCase() : "";
    if (first && LINUX_SYSTEM_ROOTS.has(first)) {
      throw new Error("Sistem klasörleri çalışma klasörü olarak seçilemez.");
    }
    // /home → blocked, /home/sami → blocked (user home, caught above)
    // /home/sami/Documents → allowed (3+ parts)
    if (first && LINUX_SHALLOW_ROOTS.has(first) && parts.length < 3) {
      throw new Error("Sistem klasörleri çalışma klasörü olarak seçilemez.");
    }
  }
  return {
    rootPath: resolved,
    displayName: path.basename(resolved),
    rootHash: sha256(resolved),
  };
}

function resolveWorkspaceChild(rootPath, relativePath) {
  const root = resolveRootPath(rootPath);
  const child = fs.realpathSync(path.resolve(root, relativePath));
  const normalizedRoot = `${root}${path.sep}`;
  if (!(child === root || child.startsWith(normalizedRoot))) {
    throw new Error("Seçilen klasör dışına erişim engellendi.");
  }
  return child;
}

async function revealWorkspacePath(config, relativePath) {
  const target = resolveWorkspaceChild(config.workspaceRootPath, relativePath);
  await shell.showItemInFolder(target);
  return { ok: true, target };
}

async function openWorkspacePath(config, relativePath) {
  const target = resolveWorkspaceChild(config.workspaceRootPath, relativePath);
  await shell.openPath(target);
  return { ok: true, target };
}

module.exports = {
  openWorkspacePath,
  resolveWorkspaceChild,
  revealWorkspacePath,
  validateWorkspaceRoot,
};
