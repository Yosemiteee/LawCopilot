#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${LAWCOPILOT_ENV_FILE:-$ROOT/artifacts/runtime/pilot.env}"
API_ROOT="$ROOT/apps/api"
PORT="${LAWCOPILOT_SMOKE_PORT:-18731}"
BASE_URL="http://127.0.0.1:${PORT}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd curl
require_cmd python3

choose_port() {
  python3 - "$1" <<'PY'
import socket
import sys

base = int(sys.argv[1])
for port in range(base, base + 30):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("no_free_smoke_port")
PY
}

if [ ! -f "$ENV_FILE" ]; then
  "$ROOT/scripts/pilot_local.sh" >/tmp/lawcopilot_pilot_local.out 2>/tmp/lawcopilot_pilot_local.err
fi

cd "$API_ROOT"
set -a
source "$ENV_FILE"
set +a

PORT="$(choose_port "$PORT")"
BASE_URL="http://127.0.0.1:${PORT}"

.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/lawcopilot_api_smoke.log 2>&1 &
PID=$!
trap 'kill $PID >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 50); do
  if curl -fsS "$BASE_URL/health" >/tmp/lawcopilot_smoke_health.json; then
    break
  fi
  sleep 0.25
done

curl -fsS "$BASE_URL/health" >/tmp/lawcopilot_smoke_health.json
if [ -n "${LAWCOPILOT_BOOTSTRAP_ADMIN_KEY:-}" ]; then
  TOKEN="$(curl -fsS -X POST "$BASE_URL/auth/token" -H 'Content-Type: application/json' -d "{\"subject\":\"smoke-lawyer\",\"role\":\"lawyer\",\"bootstrap_key\":\"${LAWCOPILOT_BOOTSTRAP_ADMIN_KEY}\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
else
  TOKEN="$(curl -fsS -X POST "$BASE_URL/auth/token" -H 'Content-Type: application/json' -d '{"subject":"smoke-lawyer","role":"lawyer"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
fi
curl -fsS "$BASE_URL/telemetry/health" -H "Authorization: Bearer $TOKEN" >/tmp/lawcopilot_smoke_telemetry.json
curl -fsS "$BASE_URL/telemetry/pilot-summary" -H "Authorization: Bearer $TOKEN" >/tmp/lawcopilot_smoke_pilot_summary.json
echo "api-smoke-ok"
