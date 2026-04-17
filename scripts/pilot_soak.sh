#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${LAWCOPILOT_ENV_FILE:-$ROOT/artifacts/runtime/pilot.env}"
PORT="${LAWCOPILOT_SMOKE_PORT:-18731}"
BASE_URL="${LAWCOPILOT_PILOT_BASE_URL:-http://127.0.0.1:${PORT}}"
DURATION_SECONDS="${LAWCOPILOT_PILOT_SOAK_DURATION_SECONDS:-1800}"
INTERVAL_SECONDS="${LAWCOPILOT_PILOT_SOAK_INTERVAL_SECONDS:-30}"
OUT_DIR="${LAWCOPILOT_PILOT_SOAK_DIR:-$ROOT/artifacts/pilot-soak}"
TOKEN="${LAWCOPILOT_PILOT_TOKEN:-}"
ALLOW_LAUNCH_BLOCKED="${LAWCOPILOT_PILOT_ALLOW_LAUNCH_BLOCKED:-false}"

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
    payload="{\"subject\":\"pilot-soak\",\"role\":\"lawyer\",\"bootstrap_key\":\"${LAWCOPILOT_BOOTSTRAP_ADMIN_KEY}\"}"
  else
    payload='{"subject":"pilot-soak","role":"lawyer"}'
  fi
  response_file="$(mktemp)"
  status="$(curl -sS -o "$response_file" -w "%{http_code}" -X POST "$BASE_URL/auth/token" -H 'Content-Type: application/json' -d "$payload" || true)"
  if [ "$status" != "200" ]; then
    echo "pilot_soak: token alınamadı. LAWCOPILOT_PILOT_TOKEN veya geçerli LAWCOPILOT_BOOTSTRAP_ADMIN_KEY verin. status=$status" >&2
    cat "$response_file" >&2 || true
    rm -f "$response_file"
    exit 1
  fi
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' <"$response_file"
  rm -f "$response_file"
}

TOKEN="$(issue_token)"
STAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
OUT_FILE="$OUT_DIR/soak-$STAMP.jsonl"
END_TS=$(( $(date +%s) + DURATION_SECONDS ))
FAILURES=0
SAMPLES=0

while [ "$(date +%s)" -lt "$END_TS" ]; do
  SAMPLE_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  HEALTH_PAYLOAD="$(mktemp)"
  PILOT_PAYLOAD="$(mktemp)"
  CONNECTOR_PAYLOAD="$(mktemp)"
  ORCH_PAYLOAD="$(mktemp)"
  SAMPLE_FAILED=0

  if ! curl -fsS "$BASE_URL/health" >"$HEALTH_PAYLOAD"; then
    SAMPLE_FAILED=1
  fi
  if ! curl -fsS "$BASE_URL/telemetry/pilot-summary" -H "Authorization: Bearer $TOKEN" >"$PILOT_PAYLOAD"; then
    SAMPLE_FAILED=1
  fi
  curl -fsS "$BASE_URL/assistant/connectors/sync-status" -H "Authorization: Bearer $TOKEN" >"$CONNECTOR_PAYLOAD" || printf '{}' >"$CONNECTOR_PAYLOAD"
  curl -fsS "$BASE_URL/assistant/orchestration/status" -H "Authorization: Bearer $TOKEN" >"$ORCH_PAYLOAD" || printf '{}' >"$ORCH_PAYLOAD"

  if [ "$SAMPLE_FAILED" -ne 0 ]; then
    FAILURES=$((FAILURES + 1))
  fi

  python3 - "$SAMPLE_TS" "$SAMPLE_FAILED" "$ALLOW_LAUNCH_BLOCKED" "$HEALTH_PAYLOAD" "$PILOT_PAYLOAD" "$CONNECTOR_PAYLOAD" "$ORCH_PAYLOAD" >>"$OUT_FILE" <<'PY'
import json
import sys
from pathlib import Path

sample_ts = sys.argv[1]
sample_failed = bool(int(sys.argv[2]))
allow_launch_blocked = str(sys.argv[3]).strip().lower() == "true"

def load_json(path_str: str):
    path = Path(path_str)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

health = load_json(sys.argv[4])
pilot = load_json(sys.argv[5])
connector = load_json(sys.argv[6])
orch = load_json(sys.argv[7])

status = "ok"
if sample_failed:
    status = "request_failed"
elif pilot.get("overall_status") == "launch_blocked" and not allow_launch_blocked:
    status = "launch_blocked"

payload = {
    "ts": sample_ts,
    "status": status,
    "health_ok": health.get("ok"),
    "pilot_status": pilot.get("overall_status"),
    "connector_attention_required": (((connector or {}).get("summary") or {}).get("attention_required")),
    "connector_retry_scheduled": (((connector or {}).get("summary") or {}).get("retry_scheduled")),
    "reflection_due": ((pilot.get("health_counters") or {}).get("reflection_due")),
    "runtime_recent_recoveries": ((pilot.get("health_counters") or {}).get("runtime_recent_recoveries")),
    "runtime_recovery_failed_7d": ((pilot.get("runtime_diagnostics") or {}).get("recovery_failed_7d")),
    "orchestration_attention_required": (((orch or {}).get("summary") or {}).get("attention_required")),
    "launch_blockers": list(pilot.get("launch_blockers") or []),
    "degraded_modes": list(pilot.get("degraded_modes") or []),
}
print(json.dumps(payload, ensure_ascii=False))
PY

  rm -f "$HEALTH_PAYLOAD" "$PILOT_PAYLOAD" "$CONNECTOR_PAYLOAD" "$ORCH_PAYLOAD"
  SAMPLES=$((SAMPLES + 1))
  sleep "$INTERVAL_SECONDS"
done

python3 - "$OUT_FILE" "$SAMPLES" "$FAILURES" "$ALLOW_LAUNCH_BLOCKED" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
samples = int(sys.argv[2])
failures = int(sys.argv[3])
allow_launch_blocked = str(sys.argv[4]).strip().lower() == "true"
lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
launch_blocked = sum(1 for item in lines if item.get("status") == "launch_blocked")
request_failed = sum(1 for item in lines if item.get("status") == "request_failed")

print("pilot-soak-complete")
print(f"samples={samples} request_failures={request_failed} explicit_failures={failures} launch_blocked_samples={launch_blocked}")
print(f"output={path}")

if request_failed > 0:
    raise SystemExit(1)
if launch_blocked > 0 and not allow_launch_blocked:
    raise SystemExit(1)
PY
