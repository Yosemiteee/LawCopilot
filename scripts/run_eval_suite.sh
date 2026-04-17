#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[eval] running epistemic eval suite"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  apps/api/tests/evals/test_epistemic_eval.py \
  apps/api/tests/test_epistemic.py \
  apps/api/tests/test_policy_decision.py

echo "[eval] completed"
