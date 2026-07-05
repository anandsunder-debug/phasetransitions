#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/services.pid"
LOG_DIR="$RUNTIME_DIR/logs"

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

log() {
  echo
  echo "==> $1"
}

ensure_command() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "$cmd is required but not found. $hint" >&2
    exit 1
  fi
}

resolve_python_cmd() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return
  fi
  echo ""
}

is_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

write_env_if_missing() {
  local file="$1"
  local content="$2"
  if [[ ! -f "$file" ]]; then
    printf "%s\n" "$content" > "$file"
  fi
}

append_line_if_missing() {
  local file="$1"
  local line="$2"
  touch "$file"
  if ! grep -Fxq "$line" "$file"; then
    printf "%s\n" "$line" >> "$file"
  fi
}

cleanup_stale_pid_file() {
  if [[ ! -f "$PID_FILE" ]]; then
    return
  fi

  local any_running=0
  while IFS='=' read -r name pid; do
    [[ -z "${name:-}" || -z "${pid:-}" ]] && continue
    if is_running "$pid"; then
      any_running=1
      break
    fi
  done < "$PID_FILE"

  if [[ "$any_running" -eq 0 ]]; then
    rm -f "$PID_FILE"
  fi
}

start_service() {
  local name="$1"
  local cwd="$2"
  local command="$3"
  local logfile="$LOG_DIR/${name}.log"

  (
    cd "$cwd"
    nohup bash -lc "$command" > "$logfile" 2>&1 &
    echo $! > "$RUNTIME_DIR/${name}.pid"
  )

  local pid
  pid="$(cat "$RUNTIME_DIR/${name}.pid")"
  echo "$name=$pid" >> "$PID_FILE"
  echo "Started $name (pid $pid)"
}

open_url() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$url" >/dev/null 2>&1 || true
  fi
}

SKIP_INSTALL=0
NO_BROWSER=0

for arg in "$@"; do
  case "$arg" in
    --skip-install) SKIP_INSTALL=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: ./start-app-and-dashboard.sh [--skip-install] [--no-browser]" >&2
      exit 1
      ;;
  esac
done

log "Checking prerequisites"
PYTHON_CMD="$(resolve_python_cmd)"
if [[ -z "$PYTHON_CMD" ]]; then
  echo "python3/python is required but not found. Install Python 3.11+." >&2
  exit 1
fi
ensure_command node "Install Node.js 18+"

if command -v yarn >/dev/null 2>&1; then
  FRONTEND_PM="yarn"
  FRONTEND_RUN_CMD="yarn start"
elif command -v npm >/dev/null 2>&1; then
  FRONTEND_PM="npm"
  FRONTEND_RUN_CMD="npm start"
else
  echo "Neither yarn nor npm was found. Install Yarn 1.22+ or npm." >&2
  exit 1
fi

cleanup_stale_pid_file
if [[ -f "$PID_FILE" ]]; then
  echo "Services appear to already be running. Use ./stop-app-and-dashboard.sh first." >&2
  exit 1
fi

log "Preparing backend environment"
if [[ ! -f "$BACKEND_DIR/venv/bin/python" && ! -f "$BACKEND_DIR/venv/Scripts/python.exe" ]]; then
  (cd "$BACKEND_DIR" && "$PYTHON_CMD" -m venv venv)
fi

VENV_PY="$BACKEND_DIR/venv/bin/python"
VENV_UVICORN="$BACKEND_DIR/venv/bin/uvicorn"
if [[ -f "$BACKEND_DIR/venv/Scripts/python.exe" ]]; then
  VENV_PY="$BACKEND_DIR/venv/Scripts/python.exe"
fi
if [[ -f "$BACKEND_DIR/venv/Scripts/uvicorn.exe" ]]; then
  VENV_UVICORN="$BACKEND_DIR/venv/Scripts/uvicorn.exe"
fi

if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  JWT_SECRET="$($PYTHON_CMD - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
)"
  cat > "$BACKEND_DIR/.env" <<EOF
MONGO_URL=mongodb://localhost:27017
DB_NAME=freshcart
JWT_SECRET=$JWT_SECRET
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=
INFLUX_ORG=freshcart
INFLUX_BUCKET=metrics
EOF
fi

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  if [[ ! -f "$VENV_UVICORN" ]]; then
    (cd "$BACKEND_DIR" && "$VENV_PY" -m pip install --upgrade pip && "$VENV_PY" -m pip install -r requirements.txt)
  fi
fi

log "Preparing frontend environment"
append_line_if_missing "$FRONTEND_DIR/.env" "PORT=3001"
append_line_if_missing "$FRONTEND_DIR/.env" "REACT_APP_BACKEND_URL=http://localhost:8001"
if [[ "$SKIP_INSTALL" -eq 0 && ! -d "$FRONTEND_DIR/node_modules" ]]; then
  if [[ "$FRONTEND_PM" == "yarn" ]]; then
    (cd "$FRONTEND_DIR" && yarn install)
  else
    (cd "$FRONTEND_DIR" && npm install)
  fi
fi

log "Checking MongoDB availability"
if command -v nc >/dev/null 2>&1; then
  if ! nc -z localhost 27017 >/dev/null 2>&1; then
    echo "Warning: MongoDB is not reachable on localhost:27017. Backend may fail until MongoDB is running."
  fi
else
  echo "Warning: 'nc' not found; skipped MongoDB port check."
fi

: > "$PID_FILE"

log "Starting observability service (8002)"
start_service "backend_obs" "$BACKEND_DIR" "\"$VENV_PY\" -m uvicorn obs_server:app --host 0.0.0.0 --port 8002 --reload"

log "Starting main backend service (8001)"
start_service "backend" "$BACKEND_DIR" "\"$VENV_PY\" -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload"

log "Starting frontend (3001)"
start_service "frontend" "$FRONTEND_DIR" "PORT=3001 $FRONTEND_RUN_CMD"

echo
echo "Startup triggered successfully."
echo "Main app:          http://localhost:3001"
echo "Ops dashboard:     http://localhost:3001/dashboard"
echo "Backend API:       http://localhost:8001"
echo "Observability API: http://localhost:8002"
echo "Logs:              $LOG_DIR"

if [[ "$NO_BROWSER" -eq 0 ]]; then
  log "Opening app and operations dashboard"
  open_url "http://localhost:3001"
  open_url "http://localhost:3001/dashboard"
fi
