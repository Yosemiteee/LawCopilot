const fs = require("fs");
const path = require("path");

const { resolveConfigDir } = require("./config.cjs");

const SECRET_PATHS = [
  ["provider", "apiKey"],
  ["google", "clientSecret"],
  ["google", "accessToken"],
  ["google", "refreshToken"],
  ["googlePortability", "clientSecret"],
  ["googlePortability", "accessToken"],
  ["googlePortability", "refreshToken"],
  ["outlook", "accessToken"],
  ["outlook", "refreshToken"],
  ["telegram", "botToken"],
  ["whatsapp", "accessToken"],
  ["x", "clientSecret"],
  ["x", "accessToken"],
  ["x", "refreshToken"],
  ["linkedin", "clientSecret"],
  ["linkedin", "accessToken"],
  ["instagram", "clientSecret"],
  ["instagram", "accessToken"],
  ["instagram", "pageAccessToken"],
];

function secretFilePath(options = {}) {
  return path.join(resolveConfigDir(options), "desktop-secrets.json");
}

function getNested(target, keyPath) {
  return keyPath.reduce((current, key) => (current && typeof current === "object" ? current[key] : undefined), target);
}

function setNested(target, keyPath, value) {
  let current = target;
  for (let index = 0; index < keyPath.length - 1; index += 1) {
    const key = keyPath[index];
    if (!current[key] || typeof current[key] !== "object") {
      current[key] = {};
    }
    current = current[key];
  }
  current[keyPath[keyPath.length - 1]] = value;
}

function hasNested(target, keyPath) {
  let current = target;
  for (const key of keyPath) {
    if (!current || typeof current !== "object" || !Object.prototype.hasOwnProperty.call(current, key)) {
      return false;
    }
    current = current[key];
  }
  return true;
}

function cleanupEmptyContainers(target) {
  if (!target || typeof target !== "object") {
    return target;
  }
  for (const [key, value] of Object.entries(target)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      cleanupEmptyContainers(value);
      if (!Object.keys(value).length) {
        delete target[key];
      }
    }
  }
  return target;
}

function splitSecretConfigPatch(patch) {
  const secretPatch = {};
  const publicPatch = JSON.parse(JSON.stringify(patch || {}));
  for (const keyPath of SECRET_PATHS) {
    if (!hasNested(publicPatch, keyPath)) {
      continue;
    }
    const value = String(getNested(publicPatch, keyPath) || "");
    setNested(secretPatch, keyPath, value);
    setNested(publicPatch, keyPath, "");
  }
  cleanupEmptyContainers(secretPatch);
  cleanupEmptyContainers(publicPatch);
  return { secretPatch, publicPatch };
}

function mergeSecretConfig(config, secretPatch) {
  const next = JSON.parse(JSON.stringify(config || {}));
  for (const keyPath of SECRET_PATHS) {
    const value = String(getNested(secretPatch, keyPath) || "");
    if (!value) {
      continue;
    }
    setNested(next, keyPath, value);
  }
  return next;
}

function readSecretPayload(options = {}) {
  const filePath = secretFilePath(options);
  if (!fs.existsSync(filePath)) {
    return {};
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return {};
  }
}

function decodeSecretValue(value, safeStorage) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  if (raw.startsWith("enc:")) {
    const encrypted = raw.slice(4);
    if (!safeStorage?.decryptString) {
      return "";
    }
    try {
      return safeStorage.decryptString(Buffer.from(encrypted, "base64"));
    } catch {
      return "";
    }
  }
  return "";
}

function encodeSecretValue(value, safeStorage) {
  const raw = String(value || "");
  if (!raw) {
    return "";
  }
  if (!safeStorage?.isEncryptionAvailable?.() || !safeStorage?.encryptString) {
    throw new Error("secure_storage_unavailable");
  }
  return `enc:${safeStorage.encryptString(raw).toString("base64")}`;
}

function loadSecretConfig(options = {}, { safeStorage } = {}) {
  const payload = readSecretPayload(options);
  const decoded = {};
  for (const keyPath of SECRET_PATHS) {
    const stored = getNested(payload, keyPath);
    const value = decodeSecretValue(stored, safeStorage);
    if (value) {
      setNested(decoded, keyPath, value);
    }
  }
  return decoded;
}

function saveSecretConfig(secretPatch, options = {}, { safeStorage } = {}) {
  const dir = resolveConfigDir(options);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const current = readSecretPayload(options);
  const next = JSON.parse(JSON.stringify(current || {}));
  for (const keyPath of SECRET_PATHS) {
    if (!hasNested(secretPatch, keyPath)) {
      continue;
    }
    const value = String(getNested(secretPatch, keyPath) || "");
    setNested(next, keyPath, value ? encodeSecretValue(value, safeStorage) : "");
  }
  fs.writeFileSync(secretFilePath(options), JSON.stringify(cleanupEmptyContainers(next), null, 2), { mode: 0o600 });
  return loadSecretConfig(options, { safeStorage });
}

module.exports = {
  loadSecretConfig,
  mergeSecretConfig,
  saveSecretConfig,
  secretFilePath,
  splitSecretConfigPatch,
};
