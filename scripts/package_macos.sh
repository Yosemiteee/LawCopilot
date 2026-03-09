#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIST="$ROOT/apps/api/dist"
mkdir -p "$API_DIST"

if [ -n "${LAWCOPILOT_MAC_BACKEND_X64:-}" ]; then
  cp "$LAWCOPILOT_MAC_BACKEND_X64" "$API_DIST/lawcopilot-api-x64"
  chmod +x "$API_DIST/lawcopilot-api-x64"
fi
if [ -n "${LAWCOPILOT_MAC_BACKEND_ARM64:-}" ]; then
  cp "$LAWCOPILOT_MAC_BACKEND_ARM64" "$API_DIST/lawcopilot-api-arm64"
  chmod +x "$API_DIST/lawcopilot-api-arm64"
fi

if [ -f "$API_DIST/lawcopilot-api-x64" ] && [ -f "$API_DIST/lawcopilot-api-arm64" ]; then
  lipo -create \
    "$API_DIST/lawcopilot-api-x64" \
    "$API_DIST/lawcopilot-api-arm64" \
    -output "$API_DIST/lawcopilot-api"
  chmod +x "$API_DIST/lawcopilot-api"
  rm -f "$API_DIST/lawcopilot-api-x64" "$API_DIST/lawcopilot-api-arm64"
fi

cd "$ROOT/apps/api"
if [ ! -x .venv/bin/python ] && [ ! -x .venv/Scripts/python.exe ]; then
  python3 -m venv .venv
fi
PY_BIN=".venv/bin/python"
if [ ! -x "$PY_BIN" ]; then
  PY_BIN=".venv/Scripts/python.exe"
fi
"$PY_BIN" -m pip install -q -r requirements.txt

cd "$ROOT/apps/ui"
npm install
npm test
npm run build

cd "$ROOT/apps/desktop"
npm install
npm test
if [ ! -f "$API_DIST/lawcopilot-api" ]; then
  echo "macOS paketleme için universal backend ikilisi bulunamadı." >&2
  echo "Önce x64 ve arm64 backend artefact'ları hazırlanmalı." >&2
  exit 1
fi
npm run package:macos
