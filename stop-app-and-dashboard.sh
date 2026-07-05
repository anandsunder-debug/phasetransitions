#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/services.pid"

log() {
  echo
  echo "==> $1"
}

is_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

stop_pid() {
  local name="$1"
  local pid="$2"

  if ! is_running "$pid"; then
    echo "$name already stopped (pid $pid not running)."
    return
  fi

  echo "Stopping $name (pid $pid)..."
  kill "$pid" >/dev/null 2>&1 || true

  local retries=20
  while is_running "$pid" && [[ "$retries" -gt 0 ]]; do
    retries=$((retries - 1))
    sleep 0.2
  done

  if is_running "$pid"; then
    echo "Force killing $name (pid $pid)..."
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi

  echo "$name stopped."
}

if [[ ! -f "$PID_FILE" ]]; then
  echo "No PID file found at $PID_FILE. Nothing to stop."
  exit 0
fi

log "Stopping FreshCart services"
while IFS='=' read -r name pid; do
  [[ -z "${name:-}" || -z "${pid:-}" ]] && continue
  stop_pid "$name" "$pid"
done < "$PID_FILE"

rm -f "$PID_FILE" "$RUNTIME_DIR"/*.pid

echo
echo "All tracked services are stopped."
