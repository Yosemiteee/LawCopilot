#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="local-only"
PACKAGE_DIR=0

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      MODE="${2:?missing deployment mode}"
      shift 2
      ;;
    --package-dir)
      PACKAGE_DIR=1
      shift
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd python3
require_cmd npm

RUNTIME_DIR="$ROOT/artifacts/runtime"
ENV_FILE="$RUNTIME_DIR/pilot.env"
mkdir -p "$RUNTIME_DIR"

if [ ! -f "$ENV_FILE" ]; then
  python3 - <<'PY' > "$ENV_FILE"
import secrets
print(f"LAWCOPILOT_JWT_SECRET={secrets.token_urlsafe(48)}")
print(f"LAWCOPILOT_BOOTSTRAP_ADMIN_KEY={secrets.token_urlsafe(32)}")
print("LAWCOPILOT_OFFICE_ID=default-office")
print("LAWCOPILOT_RELEASE_CHANNEL=pilot")
print("LAWCOPILOT_ENVIRONMENT=pilot")
print("LAWCOPILOT_CONNECTOR_DRY_RUN=true")
PY
  chmod 600 "$ENV_FILE"
fi

python3 - "$ENV_FILE" "$MODE" <<'PY'
from pathlib import Path
import sys
env_path = Path(sys.argv[1])
mode = sys.argv[2]
rows = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if "=" in line:
        key, value = line.split("=", 1)
        rows[key] = value
rows["LAWCOPILOT_DEPLOYMENT_MODE"] = mode
env_path.write_text("\n".join(f"{k}={v}" for k, v in rows.items()) + "\n", encoding="utf-8")
PY

cd "$ROOT/apps/api"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

cd "$ROOT/apps/ui"
npm install
npm run build

cd "$ROOT/apps/desktop"
npm install
npm test

if [ "$PACKAGE_DIR" -eq 1 ]; then
  npm run package:dir
fi

cat <<EOF
Pilot local setup ready.

Env file: $ENV_FILE
Deployment mode: $MODE

Manual run:
  1. Backend:  cd $ROOT/apps/api && set -a && source $ENV_FILE && set +a && .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 18731
  2. Desktop:  cd $ROOT/apps/desktop && npm run dev

Smoke:
  - bash $ROOT/scripts/smoke_api.sh
  - bash $ROOT/scripts/smoke_desktop.sh
EOF
