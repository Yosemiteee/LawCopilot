#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

MODE="${LAWCOPILOT_DEPLOYMENT_MODE:-local-first-hybrid}"

if [ ! -x "$ROOT/scripts/pilot_local.sh" ]; then
  echo "[LawCopilot] ERROR: missing pilot_local.sh" >&2
  exit 1
fi

exec "$ROOT/scripts/pilot_local.sh" --mode "$MODE" "$@"
