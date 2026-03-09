#!/usr/bin/env bash
set -euo pipefail
echo "[LawCopilot] OpenClaw kontrol ediliyor..."
if command -v openclaw >/dev/null 2>&1; then
  echo "openclaw bulundu: $(command -v openclaw)"
else
  echo "openclaw bulunamadı. TODO: OS'e gore otomatik kurulum"
  exit 2
fi
openclaw gateway status || true
openclaw gateway start || true
openclaw gateway status || true
