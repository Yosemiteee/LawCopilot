#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

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
npm run package:windows
