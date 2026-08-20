#!/bin/sh
set -eu

if [ -z "${HERMES_HOME:-}" ]; then
  if [ "$(uname -s 2>/dev/null || true)" = Linux ] && [ -d /opt/data/skills ]; then
    HERMES_HOME=/opt/data
  else
    HERMES_HOME="$HOME/.hermes"
  fi
fi
DATA_ROOT="${TAVERN_DATA_ROOT:-$HERMES_HOME}"
APP_DIR="${TAVERN_APP_DIR:-$DATA_ROOT/apps/tavern-runtime}"
STATE_DIR="${TAVERN_STATE_DIR:-$DATA_ROOT/tavern-state}"
PORT="${TAVERN_PORT:-8799}"
HOST="${TAVERN_HOST:-127.0.0.1}"
PYTHON="${TAVERN_PYTHON:-$(command -v python3)}"
PID_FILE="$STATE_DIR/server.pid"
LOG_FILE="$STATE_DIR/server.log"
ENV_FILE="${TAVERN_ENV_FILE:-$DATA_ROOT/tavern.env}"

if [ -f "$APP_DIR/server.py" ]; then
  SERVER="$APP_DIR/server.py"
elif [ -f "$APP_DIR/backend/server.py" ]; then
  SERVER="$APP_DIR/backend/server.py"
else
  echo "Tavern runtime not found under $APP_DIR" >&2
  exit 1
fi

if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

is_running() {
  [ -f "$PID_FILE" ] || return 1
  pid=$(cat "$PID_FILE" 2>/dev/null || true)
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start() {
  mkdir -p "$STATE_DIR"
  if is_running; then
    echo "Tavern already running (pid $(cat "$PID_FILE"))"
    return 0
  fi
  export TAVERN_STATE_DIR="$STATE_DIR" TAVERN_PORT="$PORT" TAVERN_HOST="$HOST"
  nohup "$PYTHON" "$SERVER" --port "$PORT" >"$LOG_FILE" 2>&1 </dev/null &
  pid=$!
  printf '%s\n' "$pid" > "$PID_FILE"
  i=0
  while [ "$i" -lt 20 ]; do
    if curl -fsS "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
      echo "Tavern started: http://$HOST:$PORT/"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Tavern failed to start; see $LOG_FILE" >&2
      rm -f "$PID_FILE"
      return 1
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "Tavern health check timed out; see $LOG_FILE" >&2
  return 1
}

stop() {
  if ! is_running; then
    rm -f "$PID_FILE"
    echo "Tavern is not running"
    return 0
  fi
  pid=$(cat "$PID_FILE")
  kill "$pid"
  i=0
  while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 20 ]; do
    sleep 1
    i=$((i + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Tavern did not stop cleanly (pid $pid)" >&2
    return 1
  fi
  rm -f "$PID_FILE"
  echo "Tavern stopped"
}

status() {
  if is_running; then
    curl -fsS "http://$HOST:$PORT/api/health"
  else
    echo "Tavern is not running" >&2
    return 1
  fi
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  foreground)
    mkdir -p "$STATE_DIR"
    export TAVERN_STATE_DIR="$STATE_DIR" TAVERN_PORT="$PORT" TAVERN_HOST="$HOST"
    exec "$PYTHON" "$SERVER" --port "$PORT"
    ;;
  *) echo "usage: runtime.sh {start|stop|restart|status|foreground}" >&2; exit 2 ;;
esac
