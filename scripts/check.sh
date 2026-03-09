#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/api"

PY_BIN="python3"
if [ -x ".venv/bin/python" ]; then
  PY_BIN=".venv/bin/python"
fi

"$PY_BIN" -m compileall -q lawcopilot_api
LAWCOPILOT_BOOTSTRAP_ADMIN_KEY="" "$PY_BIN" -m pytest -q tests

cd "$ROOT/apps/ui"
npm test
npm run build
test -f legacy-index.html
echo "UI shell validation: OK"

cd "$ROOT/apps/desktop"
npm test
echo "Desktop shell validation: OK"
