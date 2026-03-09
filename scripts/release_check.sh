#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACT_DIR="$ROOT/artifacts"
OUT="$ARTIFACT_DIR/release_checklist.md"
mkdir -p "$ARTIFACT_DIR"

PASS=0
FAIL=0

now_utc() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

record() {
  local status="$1"
  local name="$2"
  local detail="$3"
  if [ "$status" = "PASS" ]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
  printf -- "- [%s] %s — %s\n" "$status" "$name" "$detail" >> "$OUT"
}

printf "# Release / Installer Doğrulama Checklisti\n\n" > "$OUT"
printf "Generated: %s\n\n" "$(now_utc)" >> "$OUT"

# 1) Syntax + tests + basic UI integrity
if "$ROOT/scripts/check.sh" >/tmp/lawcopilot_check.out 2>/tmp/lawcopilot_check.err; then
  record "PASS" "scripts/check.sh" "API tests + UI + desktop validation geçti"
else
  record "FAIL" "scripts/check.sh" "Detay: /tmp/lawcopilot_check.err"
fi

# 2) API smoke
if "$ROOT/scripts/smoke_api.sh" >/tmp/lawcopilot_api_smoke.out 2>/tmp/lawcopilot_api_smoke.err; then
  record "PASS" "scripts/smoke_api.sh" "API boot + health + telemetry smoke geçti"
else
  record "FAIL" "scripts/smoke_api.sh" "Detay: /tmp/lawcopilot_api_smoke.err"
fi

# 3) Desktop smoke
if "$ROOT/scripts/smoke_desktop.sh" >/tmp/lawcopilot_desktop_smoke.out 2>/tmp/lawcopilot_desktop_smoke.err; then
  record "PASS" "scripts/smoke_desktop.sh" "Desktop config + backend boot smoke geçti"
else
  record "FAIL" "scripts/smoke_desktop.sh" "Detay: /tmp/lawcopilot_desktop_smoke.err"
fi

# 4) Desktop packaging (dir target + bundled backend)
if (cd "$ROOT/apps/desktop" && npm run package:dir) >/tmp/lawcopilot_pkg.out 2>/tmp/lawcopilot_pkg.err \
  && node "$ROOT/scripts/verify_packaged_artifacts.cjs" linux "$ROOT/apps/desktop/dist" >/tmp/lawcopilot_pkg_verify.out 2>/tmp/lawcopilot_pkg_verify.err \
  && node "$ROOT/scripts/write_artifact_manifest.cjs" linux "$ROOT/apps/desktop/dist" "$ROOT/artifacts/linux-build-artifacts.json" >/tmp/lawcopilot_pkg_manifest.out 2>/tmp/lawcopilot_pkg_manifest.err; then
  record "PASS" "apps/desktop package:dir" "Desktop dir package, gömülü backend ve Linux artefact manifesti üretildi"
else
  record "FAIL" "apps/desktop package:dir" "Detay: /tmp/lawcopilot_pkg.err"
fi

# 5) Installer/bootstrap script sanity
if [ -x "$ROOT/scripts/pilot_local.sh" ]; then
  record "PASS" "pilot_local.sh" "Pilot bootstrap script executable"
else
  record "FAIL" "pilot_local.sh" "Executable değil"
fi

# 6) Cross-platform packaging scripts
if [ -x "$ROOT/scripts/package_windows.sh" ] && [ -x "$ROOT/scripts/package_macos.sh" ]; then
  record "PASS" "package scripts" "Windows ve macOS paket scriptleri mevcut"
else
  record "FAIL" "package scripts" "Cross-platform paket scriptleri eksik"
fi

# 7) CI packaging workflow
if [ -f "$ROOT/.github/workflows/build-desktop.yml" ]; then
  record "PASS" "build-desktop workflow" "Windows/macOS artifact pipeline tanımlı"
else
  record "FAIL" "build-desktop workflow" "CI packaging workflow eksik"
fi

# 8) Artifact verification scripts
if [ -f "$ROOT/scripts/verify_packaged_artifacts.cjs" ] && [ -f "$ROOT/scripts/write_artifact_manifest.cjs" ]; then
  record "PASS" "artifact verification scripts" "Artefact doğrulama ve raporlama scriptleri mevcut"
else
  record "FAIL" "artifact verification scripts" "Artefact doğrulama scriptleri eksik"
fi

printf "\n## Summary\n- PASS: %d\n- FAIL: %d\n" "$PASS" "$FAIL" >> "$OUT"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
