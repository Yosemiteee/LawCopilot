#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-full}"

run_api() {
  cd "$ROOT/apps/api"

  PY_BIN="python3"
  if [ -x ".venv/bin/python" ]; then
    PY_BIN=".venv/bin/python"
  fi

  "$PY_BIN" -m compileall -q lawcopilot_api
  LAWCOPILOT_ENVIRONMENT=test LAWCOPILOT_ALLOW_LOCAL_TOKEN_BOOTSTRAP=true LAWCOPILOT_BOOTSTRAP_ADMIN_KEY="" "$PY_BIN" -m pytest -q tests
}

run_ui() {
  cd "$ROOT/apps/ui"
  npm test -- --run
  npm run build
  test -f dist/index.html
  echo "UI shell validation: OK"
}

run_desktop() {
  cd "$ROOT/apps/desktop"
  npm test
  echo "Desktop shell validation: OK"
}

case "$TARGET" in
  api)
    run_api
    ;;
  ui)
    run_ui
    ;;
  desktop)
    run_desktop
    ;;
  full)
    "$ROOT/scripts/check.sh"
    ;;
  *)
    echo "Usage: $0 {api|ui|desktop|full}" >&2
    exit 1
    ;;
esac
