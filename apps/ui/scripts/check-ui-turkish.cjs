const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "src");
const FAILURES = [];
const BANNED = [
  "dashboard",
  "workspace",
  "documents",
  "settings",
  "assistant",
  "draft",
  "review",
  "task",
  "timeline",
  "search",
  "summary",
  "onboarding",
  "workbench",
  "connector",
  "loading",
  "error",
  "ready",
  "client",
  "meeting",
  "question",
  "upload",
  "save",
  "cancel",
  "open",
  "close",
];
const ALLOW = new Set([
  "LawCopilot",
  "Electron",
  "Tauri",
  "OpenAI",
  "Codex",
  "ChatGPT",
  "Ollama",
  "Telegram",
  "PDF",
  "DOCX",
  "TXT",
  "MD",
  "API",
  "URL",
  "ID",
]);

walk(ROOT);

if (FAILURES.length) {
  console.error("Türkçe arayüz denetimi başarısız:");
  for (const item of FAILURES) {
    console.error(`- ${item.file}:${item.line} -> ${item.literal}`);
  }
  process.exit(1);
}

console.log("ui-turkish-ok");

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (["test", "types", "services"].includes(entry.name)) {
        continue;
      }
      walk(full);
      continue;
    }
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\./.test(entry.name) || entry.name.endsWith(".d.ts")) {
      continue;
    }
    inspectFile(full);
  }
}

function inspectFile(file) {
  const source = fs.readFileSync(file, "utf8");
  const lines = source.split("\n");
  const literalRegex = /(["'`])((?:\\.|(?!\1)[\s\S])*?)\1/g;
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.includes("import ") || line.includes(" from ") || line.includes("className=")) {
      continue;
    }
    let match;
    while ((match = literalRegex.exec(line))) {
      const literal = match[2].trim();
      if (!literal || shouldIgnore(literal)) {
        continue;
      }
      const normalized = literal.replace(/\$\{[^}]+\}/g, "").trim();
      if (!normalized || shouldIgnore(normalized)) {
        continue;
      }
      const lowered = normalized
        .replace(/OpenAI/gi, "")
        .replace(/ChatGPT/gi, "")
        .replace(/Codex/gi, "")
        .replace(/Ollama/gi, "")
        .replace(/Telegram/gi, "")
        .toLowerCase();
      if (BANNED.some((term) => lowered.includes(term))) {
        FAILURES.push({
          file: path.relative(path.resolve(__dirname, "..", "..", ".."), file),
          line: index + 1,
          literal: normalized,
        });
      }
    }
  }
}

function shouldIgnore(literal) {
  if (ALLOW.has(literal)) {
    return true;
  }
  if (/^[A-Za-z][A-Za-z0-9_]*$/.test(literal)) {
    return true;
  }
  if (literal.startsWith(".") || literal.startsWith("/") || literal.startsWith("http") || literal.startsWith("#")) {
    return true;
  }
  if (!/[A-Za-z]/.test(literal)) {
    return true;
  }
  if (/^[a-z0-9_:/.-]+$/i.test(literal) && !/[A-ZÇĞİÖŞÜ]/.test(literal)) {
    return true;
  }
  if (/^(GET|POST|PUT|DELETE|PATCH)\b/.test(literal)) {
    return true;
  }
  return false;
}
