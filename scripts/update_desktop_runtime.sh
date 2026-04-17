#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP_ROOT="$ROOT/apps/desktop"
UI_ROOT="$ROOT/apps/ui"
API_ROOT="$ROOT/apps/api"
BROWSER_WORKER_ROOT="$ROOT/apps/browser-worker"
APP_ROOT="$DESKTOP_ROOT/dist/linux-unpacked"
RESOURCES_ROOT="$APP_ROOT/resources"
APP_BINARY="$APP_ROOT/lawcopilot-desktop"
API_BINARY="$RESOURCES_ROOT/api-bin/lawcopilot-api"
APP_ASAR="$RESOURCES_ROOT/app.asar"
UI_TARGET="$RESOURCES_ROOT/ui-dist/index.html"
BROWSER_TARGET="$RESOURCES_ROOT/browser-worker/dist/index.js"
STARTUP_LOG_FILE="${TMPDIR:-/tmp}/lawcopilot-desktop-main.log"
QUIET=0
IF_NEEDED=0
FORCE_PACKAGE=0
FORCE_SYNC=0
LAUNCH=0
RESTART_RUNNING=0

usage() {
  cat <<'EOF'
Usage: update_desktop_runtime.sh [options]

Options:
  --if-needed      Only rebuild/sync when repo sources are newer than the packaged app.
  --force-package  Force a full Electron repack.
  --force-sync     Force backend/UI/browser-worker sync without a full repack.
  --launch         Launch the packaged desktop app after syncing.
  --restart-running Restart the packaged desktop app when runtime files changed.
  --quiet          Suppress non-error logs.
  -h, --help       Show this help message.
EOF
}

log() {
  if [[ "$QUIET" -eq 0 ]]; then
    printf '%s\n' "$*"
  fi
}

run_in() {
  local cwd="$1"
  shift
  log "[$(basename "$cwd")] $*"
  (
    cd "$cwd"
    "$@"
  )
}

desktop_config_dir() {
  if [[ -n "${LAWCOPILOT_DESKTOP_CONFIG_DIR:-}" ]]; then
    printf '%s\n' "$LAWCOPILOT_DESKTOP_CONFIG_DIR"
    return
  fi
  printf '%s\n' "$HOME/.config/LawCopilot"
}

desktop_config_value() {
  local key="$1"
  local fallback="$2"
  python3 - "$key" "$fallback" "$(desktop_config_dir)/desktop-config.json" <<'PY'
import json
import os
import sys

key = sys.argv[1]
fallback = sys.argv[2]
config_path = sys.argv[3]
if not os.path.exists(config_path):
    print(fallback)
    raise SystemExit(0)
try:
    with open(config_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    print(fallback)
    raise SystemExit(0)
value = data.get(key, fallback)
print(value if value not in (None, "") else fallback)
PY
}

desktop_related_pids() {
  python3 - "$APP_BINARY" "$API_BINARY" <<'PY'
import os
import sys

targets = {os.path.abspath(path) for path in sys.argv[1:]}
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    cmdline_path = os.path.join("/proc", pid, "cmdline")
    try:
        with open(cmdline_path, "rb") as handle:
            parts = [segment.decode("utf-8", "ignore") for segment in handle.read().split(b"\0") if segment]
    except OSError:
        continue
    if parts and os.path.abspath(parts[0]) in targets:
        print(pid)
PY
}

desktop_main_pids() {
  python3 - "$APP_BINARY" <<'PY'
import os
import sys

target = os.path.abspath(sys.argv[1])
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    cmdline_path = os.path.join("/proc", pid, "cmdline")
    try:
        with open(cmdline_path, "rb") as handle:
            parts = [segment.decode("utf-8", "ignore") for segment in handle.read().split(b"\0") if segment]
    except OSError:
        continue
    if not parts:
        continue
    if os.path.abspath(parts[0]) != target:
        continue
    if any(part.startswith("--type=") for part in parts[1:]):
        continue
    print(pid)
PY
}

whatsapp_session_pids() {
  python3 - "$(desktop_config_dir)/whatsapp-web-auth" <<'PY'
import os
import sys

target_root = os.path.abspath(sys.argv[1])
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    cmdline_path = os.path.join("/proc", pid, "cmdline")
    try:
        with open(cmdline_path, "rb") as handle:
            parts = [segment.decode("utf-8", "ignore") for segment in handle.read().split(b"\0") if segment]
    except OSError:
        continue
    if not parts:
        continue
    joined = " ".join(parts)
    if "--user-data-dir=" not in joined:
        continue
    if target_root in joined:
        print(pid)
PY
}

stop_running_desktop() {
  local pids
  pids="$(desktop_related_pids || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  log "Restart requested; stopping running desktop app."
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done <<< "$pids"
  for _ in $(seq 1 40); do
    if [[ -z "$(desktop_related_pids || true)" ]]; then
      return 0
    fi
    sleep 0.25
  done
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -9 "$pid" 2>/dev/null || true
  done <<< "$(desktop_related_pids || true)"
}

stop_whatsapp_session_processes() {
  local pids
  pids="$(whatsapp_session_pids || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  log "Stopping stale WhatsApp Web browser sessions."
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
  done <<< "$pids"
  for _ in $(seq 1 20); do
    if [[ -z "$(whatsapp_session_pids || true)" ]]; then
      return 0
    fi
    sleep 0.25
  done
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    kill -9 "$pid" 2>/dev/null || true
  done <<< "$(whatsapp_session_pids || true)"
}

launch_desktop() {
  (
    cd "$APP_ROOT"
    if command -v setsid >/dev/null 2>&1; then
      setsid -f env -u ELECTRON_RUN_AS_NODE "$APP_BINARY" >/dev/null 2>&1 </dev/null || nohup env -u ELECTRON_RUN_AS_NODE "$APP_BINARY" >/dev/null 2>&1 </dev/null &
    else
      nohup env -u ELECTRON_RUN_AS_NODE "$APP_BINARY" >/dev/null 2>&1 </dev/null &
    fi
  )
}

wait_for_desktop_health() {
  local api_base_url="$1"
  local timeout_seconds="${2:-75}"
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    if curl -fsS "${api_base_url}/health" >/dev/null 2>&1; then
      log "Desktop API is healthy at ${api_base_url}."
      return 0
    fi
    sleep 1
  done

  printf 'Desktop runtime did not become healthy at %s within %ss\n' "$api_base_url" "$timeout_seconds" >&2
  if [[ -f "$STARTUP_LOG_FILE" ]]; then
    printf '%s\n' '--- desktop startup log tail ---' >&2
    tail -n 80 "$STARTUP_LOG_FILE" >&2 || true
  fi
  local storage_root
  storage_root="$(desktop_config_value "storagePath" "$ROOT/artifacts")"
  local backend_log="$storage_root/runtime/desktop-backend.log"
  if [[ -f "$backend_log" ]]; then
    printf '%s\n' '--- desktop backend log tail ---' >&2
    tail -n 80 "$backend_log" >&2 || true
  fi
  return 1
}

latest_mtime() {
  python3 - "$@" <<'PY'
import os
import sys

skip_dirs = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}
latest = 0.0
for raw in sys.argv[1:]:
    path = os.path.abspath(raw)
    if not os.path.exists(path):
        continue
    if os.path.isfile(path):
        latest = max(latest, os.path.getmtime(path))
        continue
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            candidate = os.path.join(root, name)
            try:
                latest = max(latest, os.path.getmtime(candidate))
            except OSError:
                pass
print(int(latest))
PY
}

file_mtime() {
  local target="$1"
  if [[ -e "$target" ]]; then
    stat -c '%Y' "$target"
  else
    echo 0
  fi
}

sync_backend() {
  shopt -s nullglob
  local artifacts=("$API_ROOT/dist"/lawcopilot-api*)
  shopt -u nullglob
  if [[ "${#artifacts[@]}" -eq 0 ]]; then
    printf 'No backend artifacts found in %s\n' "$API_ROOT/dist" >&2
    return 1
  fi
  mkdir -p "$RESOURCES_ROOT/api-bin"
  rm -f "$RESOURCES_ROOT/api-bin"/lawcopilot-api*
  cp "${artifacts[@]}" "$RESOURCES_ROOT/api-bin/"
  chmod +x "$RESOURCES_ROOT/api-bin"/lawcopilot-api* 2>/dev/null || true
}

sync_browser_worker() {
  mkdir -p "$RESOURCES_ROOT/browser-worker/dist"
  rm -rf "$RESOURCES_ROOT/browser-worker/dist"
  cp -a "$BROWSER_WORKER_ROOT/dist" "$RESOURCES_ROOT/browser-worker/"
}

needs_package() {
  local desktop_source_mtime package_mtime
  desktop_source_mtime="$(latest_mtime \
    "$DESKTOP_ROOT/main.cjs" \
    "$DESKTOP_ROOT/preload.cjs" \
    "$DESKTOP_ROOT/lib" \
    "$DESKTOP_ROOT/scripts" \
    "$DESKTOP_ROOT/package.json")"
  package_mtime="$(file_mtime "$APP_ASAR")"
  [[ ! -x "$APP_BINARY" || ! -f "$APP_ASAR" || "$desktop_source_mtime" -gt "$package_mtime" ]]
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --if-needed)
        IF_NEEDED=1
        ;;
      --force-package)
        FORCE_PACKAGE=1
        ;;
      --force-sync)
        FORCE_SYNC=1
        ;;
      --launch)
        LAUNCH=1
        ;;
      --restart-running)
        RESTART_RUNNING=1
        ;;
      --quiet)
        QUIET=1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        printf 'Unknown option: %s\n' "$1" >&2
        usage >&2
        exit 2
        ;;
    esac
    shift
  done

  local do_package=0
  local do_backend=0
  local do_ui=0
  local do_browser=0
  local runtime_changed=0
  local app_running=0
  local backend_source_mtime=0
  local ui_source_mtime=0
  local browser_source_mtime=0
  local backend_target_mtime=0
  local ui_target_mtime=0
  local browser_target_mtime=0

  if [[ "$FORCE_PACKAGE" -eq 1 ]]; then
    do_package=1
  else
    if needs_package; then
      do_package=1
    fi
  fi

  backend_source_mtime="$(latest_mtime "$API_ROOT/lawcopilot_api" "$API_ROOT/packaging" "$API_ROOT/requirements.txt")"
  ui_source_mtime="$(latest_mtime "$UI_ROOT/src" "$UI_ROOT/public" "$UI_ROOT/package.json" "$UI_ROOT/tsconfig.json" "$UI_ROOT/vite.config.ts")"
  browser_source_mtime="$(latest_mtime "$BROWSER_WORKER_ROOT/src" "$BROWSER_WORKER_ROOT/package.json" "$BROWSER_WORKER_ROOT/tsconfig.json")"
  backend_target_mtime="$(file_mtime "$RESOURCES_ROOT/api-bin/lawcopilot-api")"
  ui_target_mtime="$(file_mtime "$UI_TARGET")"
  browser_target_mtime="$(file_mtime "$BROWSER_TARGET")"

  if [[ "$FORCE_SYNC" -eq 1 ]]; then
    do_backend=1
    do_ui=1
    do_browser=1
  elif [[ "$do_package" -eq 0 ]]; then
    [[ "$backend_source_mtime" -gt "$backend_target_mtime" ]] && do_backend=1
    [[ "$ui_source_mtime" -gt "$ui_target_mtime" ]] && do_ui=1
    [[ "$browser_source_mtime" -gt "$browser_target_mtime" ]] && do_browser=1
  fi

  if [[ "$IF_NEEDED" -eq 1 && "$do_package" -eq 0 && "$do_backend" -eq 0 && "$do_ui" -eq 0 && "$do_browser" -eq 0 ]]; then
    log "Desktop runtime already up to date."
    if [[ -n "$(desktop_main_pids || true)" ]]; then
      app_running=1
    fi
    if [[ "$RESTART_RUNNING" -eq 1 && "$LAUNCH" -eq 1 && "$app_running" -eq 1 ]]; then
      stop_running_desktop
      stop_whatsapp_session_processes
      launch_desktop
      wait_for_desktop_health "$(desktop_config_value "apiBaseUrl" "http://127.0.0.1:18731")"
      exit 0
    fi
    if [[ "$LAUNCH" -eq 1 && "$app_running" -eq 0 ]]; then
      stop_running_desktop
      stop_whatsapp_session_processes
      launch_desktop
      wait_for_desktop_health "$(desktop_config_value "apiBaseUrl" "http://127.0.0.1:18731")"
    fi
    exit 0
  fi

  if [[ "$do_package" -eq 1 ]]; then
    log "Desktop shell changed or packaged runtime missing; rebuilding packaged app."
    run_in "$UI_ROOT" npm run build:desktop
    run_in "$DESKTOP_ROOT" npm run package:dir
    runtime_changed=1
  else
    if [[ "$do_backend" -eq 1 ]]; then
      run_in "$DESKTOP_ROOT" npm run build:backend
      sync_backend
      runtime_changed=1
    fi
    if [[ "$do_ui" -eq 1 ]]; then
      run_in "$UI_ROOT" npm run build:desktop
      runtime_changed=1
    fi
    if [[ "$do_browser" -eq 1 ]]; then
      run_in "$DESKTOP_ROOT" npm run build:browser-worker
      sync_browser_worker
      runtime_changed=1
    fi
  fi

  if [[ -n "$(desktop_main_pids || true)" ]]; then
    app_running=1
  fi

  if [[ "$RESTART_RUNNING" -eq 1 && "$runtime_changed" -eq 1 && "$app_running" -eq 1 ]]; then
    stop_running_desktop
    stop_whatsapp_session_processes
    app_running=0
    launch_desktop
    wait_for_desktop_health "$(desktop_config_value "apiBaseUrl" "http://127.0.0.1:18731")"
    exit 0
  fi

  if [[ "$LAUNCH" -eq 1 && "$app_running" -eq 0 ]]; then
    stop_running_desktop
    stop_whatsapp_session_processes
    launch_desktop
    wait_for_desktop_health "$(desktop_config_value "apiBaseUrl" "http://127.0.0.1:18731")"
  fi
}

main "$@"
