const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { resolveWorkspaceChild, validateWorkspaceRoot } = require("../lib/workspace.cjs");

function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-workspace-"));
  const allowedRoot = path.join(tempRoot, "davalar");
  const childDir = path.join(allowedRoot, "2026");
  const outsideDir = path.join(tempRoot, "disarisi");
  fs.mkdirSync(childDir, { recursive: true });
  fs.mkdirSync(outsideDir, { recursive: true });

  const insideFile = path.join(childDir, "notlar.txt");
  const outsideFile = path.join(outsideDir, "gizli.txt");
  fs.writeFileSync(insideFile, "içerik");
  fs.writeFileSync(outsideFile, "dış içerik");

  const validated = validateWorkspaceRoot(allowedRoot);
  assert.equal(validated.displayName, "davalar");
  assert.ok(validated.rootHash);

  const insideResolved = resolveWorkspaceChild(validated.rootPath, "2026/notlar.txt");
  assert.equal(insideResolved, fs.realpathSync(insideFile));

  assert.throws(() => resolveWorkspaceChild(validated.rootPath, "../disarisi/gizli.txt"), /Seçilen klasör dışına erişim engellendi/);
  assert.throws(() => validateWorkspaceRoot(os.homedir()), /Kullanıcı klasörünün tamamı seçilemez/);

  if (process.platform !== "win32") {
    assert.throws(() => validateWorkspaceRoot("/"), /Disk kökleri çalışma klasörü olarak seçilemez/);
  }

  const symlinkPath = path.join(allowedRoot, "kacak-baglanti.txt");
  try {
    fs.symlinkSync(outsideFile, symlinkPath);
    assert.throws(() => resolveWorkspaceChild(validated.rootPath, "kacak-baglanti.txt"), /Seçilen klasör dışına erişim engellendi/);
  } catch {
    // Bazı ortamlarda sembolik bağ oluşturma izni olmayabilir.
  }

  console.log("workspace-security-smoke-ok");
}

main();
