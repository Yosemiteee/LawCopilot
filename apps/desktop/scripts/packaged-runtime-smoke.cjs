const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const { loadDesktopConfig, resolveRuntimePaths, saveDesktopConfig } = require("../lib/config.cjs");

function main() {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "lawcopilot-packaged-"));
  const resourcesPath = path.join(tempRoot, "resources");
  const userDataPath = path.join(tempRoot, "user-data");
  const configDir = path.join(tempRoot, "config");
  fs.mkdirSync(path.join(resourcesPath, "ui-dist"), { recursive: true });
  fs.mkdirSync(path.join(resourcesPath, "api-bin"), { recursive: true });

  const runtimePaths = resolveRuntimePaths({
    repoRoot: path.resolve(__dirname, "..", "..", ".."),
    isPackaged: true,
    resourcesPath,
    userDataPath,
  });

  assert.equal(runtimePaths.uiDist, path.join(resourcesPath, "ui-dist"));
  assert.equal(runtimePaths.apiRoot, path.join(resourcesPath, "api-bin"));
  assert.equal(runtimePaths.backendBinRoot, path.join(resourcesPath, "api-bin"));
  assert.equal(runtimePaths.artifactsRoot, path.join(userDataPath, "artifacts"));

  const saved = saveDesktopConfig(
    {
      deploymentMode: "local-only",
      workspaceRootPath: path.join(tempRoot, "davalar"),
      workspaceRootName: "davalar",
      workspaceRootHash: "deneme-hash",
      storagePath: runtimePaths.artifactsRoot,
      scanOnStartup: true,
    },
    {
      repoRoot: runtimePaths.repoRoot,
      overrideDir: configDir,
      storagePath: runtimePaths.artifactsRoot,
    },
  );

  const loaded = loadDesktopConfig({
    repoRoot: runtimePaths.repoRoot,
    overrideDir: configDir,
    storagePath: runtimePaths.artifactsRoot,
  });

  assert.equal(saved.storagePath, runtimePaths.artifactsRoot);
  assert.equal(saved.envFile, path.join(runtimePaths.artifactsRoot, "runtime", "pilot.env"));
  assert.equal(loaded.workspaceRootName, "davalar");
  assert.equal(loaded.workspaceRootHash, "deneme-hash");
  assert.equal(loaded.storagePath, runtimePaths.artifactsRoot);

  console.log("packaged-runtime-smoke-ok");
}

main();
