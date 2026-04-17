#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${LAWCOPILOT_ENV_FILE:-$ROOT/artifacts/runtime/pilot.env}"
PORT="${LAWCOPILOT_SMOKE_PORT:-18731}"
BASE_URL="${LAWCOPILOT_PILOT_BASE_URL:-http://127.0.0.1:${PORT}}"
OUT_DIR="${LAWCOPILOT_PILOT_DIAGNOSTICS_DIR:-$ROOT/artifacts/pilot-diagnostics}"
TOKEN="${LAWCOPILOT_PILOT_TOKEN:-}"

require_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 1; }; }
require_cmd curl
require_cmd python3

mkdir -p "$OUT_DIR"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

issue_token() {
  if [ -n "${TOKEN:-}" ]; then
    printf '%s\n' "$TOKEN"
    return
  fi
  local payload
  local response_file
  local status
  if [ -n "${LAWCOPILOT_BOOTSTRAP_ADMIN_KEY:-}" ]; then
    payload="{\"subject\":\"pilot-diagnostics\",\"role\":\"lawyer\",\"bootstrap_key\":\"${LAWCOPILOT_BOOTSTRAP_ADMIN_KEY}\"}"
  else
    payload='{"subject":"pilot-diagnostics","role":"lawyer"}'
  fi
  response_file="$(mktemp)"
  status="$(curl -sS -o "$response_file" -w "%{http_code}" -X POST "$BASE_URL/auth/token" -H 'Content-Type: application/json' -d "$payload" || true)"
  if [ "$status" != "200" ]; then
    echo "pilot_diagnostics: token alınamadı. LAWCOPILOT_PILOT_TOKEN veya geçerli LAWCOPILOT_BOOTSTRAP_ADMIN_KEY verin. status=$status" >&2
    cat "$response_file" >&2 || true
    rm -f "$response_file"
    exit 1
  fi
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' <"$response_file"
  rm -f "$response_file"
}

TOKEN="$(issue_token)"
STAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
HEALTH_FILE="$OUT_DIR/health-$STAMP.json"
TELEMETRY_FILE="$OUT_DIR/telemetry-health-$STAMP.json"
PILOT_FILE="$OUT_DIR/pilot-summary-$STAMP.json"

curl -fsS "$BASE_URL/health" >"$HEALTH_FILE"
curl -fsS "$BASE_URL/telemetry/health" -H "Authorization: Bearer $TOKEN" >"$TELEMETRY_FILE"
curl -fsS "$BASE_URL/telemetry/pilot-summary" -H "Authorization: Bearer $TOKEN" >"$PILOT_FILE"

python3 - "$HEALTH_FILE" "$TELEMETRY_FILE" "$PILOT_FILE" <<'PY'
import json
import sys
from pathlib import Path

health = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
telemetry = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
pilot = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))

print("pilot-diagnostics-ok")
print(f"app={health.get('app_name')} version={health.get('version')} mode={health.get('deployment_mode')}")
print(f"runtime={telemetry.get('assistant_runtime_mode')} workspace_ready={telemetry.get('openclaw_workspace_ready')}")
print(
    "pilot_status="
    f"{pilot.get('overall_status')} connectors_attention={pilot.get('health_counters', {}).get('connector_attention_required')} "
    f"reflection_due={pilot.get('health_counters', {}).get('reflection_due')}"
)
print(
    "feedback="
    f"accepted:{pilot.get('analytics', {}).get('recommendation_feedback', {}).get('accepted', 0)} "
    f"rejected:{pilot.get('analytics', {}).get('recommendation_feedback', {}).get('rejected', 0)} "
    f"memory_edits:{pilot.get('analytics', {}).get('user_interactions', {}).get('memory_edits', 0)}"
)
print(
    "runtime="
    f"ready_ms:{pilot.get('runtime_diagnostics', {}).get('last_backend_ready_elapsed_ms')} "
    f"recoveries:{pilot.get('runtime_diagnostics', {}).get('recovery_started_7d', 0)} "
    f"recovery_failed:{pilot.get('runtime_diagnostics', {}).get('recovery_failed_7d', 0)}"
)
if pilot.get("launch_blockers"):
    print("launch_blockers:")
    for item in pilot["launch_blockers"]:
        print(f"- {item}")
elif pilot.get("degraded_modes"):
    print("degraded_modes:")
    for item in pilot["degraded_modes"]:
        print(f"- {item}")
PY

echo "health_json=$HEALTH_FILE"
echo "telemetry_json=$TELEMETRY_FILE"
echo "pilot_summary_json=$PILOT_FILE"
