const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function candidatePaths() {
  const desktopRoot = path.resolve(__dirname, "..");
  const distRoot = path.join(desktopRoot, "dist", "linux-unpacked");
  return [
    path.join(distRoot, "lawcopilot-desktop"),
    path.join(distRoot, "LawCopilot"),
    path.join(distRoot, "resources", "api-bin", "lawcopilot-api"),
    path.join(distRoot, "resources", "api-bin", "lawcopilot-api.exe"),
  ].map((entry) => path.normalize(entry));
}

function listProcesses() {
  if (process.platform === "win32") {
    const output = execFileSync(
      "powershell",
      [
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
      ],
      { encoding: "utf8" },
    );
    const parsed = JSON.parse(output || "[]");
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    return rows
      .filter((row) => Number(row.ProcessId) > 0)
      .map((row) => ({
        pid: Number(row.ProcessId),
        command: String(row.CommandLine || "").trim(),
      }));
  }
  const output = execFileSync("ps", ["-eo", "pid=,args="], { encoding: "utf8" });
  return output
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const splitIndex = line.indexOf(" ");
      if (splitIndex <= 0) {
        return null;
      }
      const pid = Number(line.slice(0, splitIndex).trim());
      const command = line.slice(splitIndex + 1).trim();
      if (!Number.isFinite(pid) || pid <= 0 || !command) {
        return null;
      }
      return { pid, command };
    })
    .filter(Boolean);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function terminatePid(pid) {
  try {
    process.kill(pid, "SIGTERM");
  } catch {
    return;
  }
  for (let attempt = 0; attempt < 15; attempt += 1) {
    if (!isAlive(pid)) {
      return;
    }
    await sleep(200);
  }
  try {
    process.kill(pid, "SIGKILL");
  } catch {
    return;
  }
  for (let attempt = 0; attempt < 10; attempt += 1) {
    if (!isAlive(pid)) {
      return;
    }
    await sleep(100);
  }
}

function matchesCandidate(command, candidates) {
  const normalized = path.normalize(command);
  return candidates.some((candidate) => candidate && normalized.includes(candidate));
}

async function main() {
  const candidates = candidatePaths().filter((entry) => fs.existsSync(entry));
  if (!candidates.length) {
    return;
  }
  const processes = listProcesses().filter((entry) => entry.pid !== process.pid);
  const matches = processes.filter((entry) => matchesCandidate(entry.command, candidates));
  if (!matches.length) {
    return;
  }
  console.log(`[lawcopilot] closing ${matches.length} running desktop process(es) before packaging`);
  for (const match of matches) {
    console.log(`[lawcopilot] stopping pid=${match.pid} cmd=${match.command}`);
    await terminatePid(match.pid);
  }
}

main().catch((error) => {
  console.error("[lawcopilot] failed to close running packaged desktop instances", error);
  process.exit(1);
});
