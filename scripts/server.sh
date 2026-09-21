#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/log"
PID_DIR="$ROOT_DIR/pid"
LOG_FILE="$LOG_DIR/server.log"
PID_FILE="$PID_DIR/server.pid"
PYTHON_BIN="${PYTHON_BIN:-python3}"

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' < "$PID_FILE"
  fi
}

is_server_process() {
  local process_id="$1"
  [[ "$process_id" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$process_id" 2>/dev/null || return 1
  ps -p "$process_id" -o command= 2>/dev/null | grep -Fq "$ROOT_DIR/server.py"
}

start_server() {
  mkdir -p "$LOG_DIR" "$PID_DIR"

  local process_id
  process_id="$(read_pid)"
  if [[ -n "$process_id" ]] && is_server_process "$process_id"; then
    echo "Server is already running (PID $process_id)."
    return 0
  fi

  rm -f "$PID_FILE"
  cd "$ROOT_DIR" || return 1
  nohup "$PYTHON_BIN" "$ROOT_DIR/server.py" >> "$LOG_FILE" 2>&1 &
  process_id=$!
  printf '%s\n' "$process_id" > "$PID_FILE"

  sleep 1
  if ! is_server_process "$process_id"; then
    echo "Server failed to start. See $LOG_FILE" >&2
    rm -f "$PID_FILE"
    return 1
  fi

  echo "Server started (PID $process_id)."
  echo "Log: $LOG_FILE"
}

stop_server() {
  local process_id
  process_id="$(read_pid)"
  if [[ -z "$process_id" ]]; then
    echo "Server is not running."
    return 0
  fi
  if ! is_server_process "$process_id"; then
    echo "Stale PID file removed; server is not running."
    rm -f "$PID_FILE"
    return 0
  fi

  kill "$process_id"
  local attempts=0
  while kill -0 "$process_id" 2>/dev/null && [[ "$attempts" -lt 50 ]]; do
    sleep 0.1
    attempts=$((attempts + 1))
  done
  if kill -0 "$process_id" 2>/dev/null; then
    echo "Server did not stop in time (PID $process_id)." >&2
    return 1
  fi
  rm -f "$PID_FILE"
  echo "Server stopped."
}

show_status() {
  local process_id
  process_id="$(read_pid)"
  if [[ -n "$process_id" ]] && is_server_process "$process_id"; then
    echo "Server is running (PID $process_id)."
    return 0
  fi
  echo "Server is not running."
  return 1
}

case "${1:-}" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  restart)
    stop_server && start_server
    ;;
  status)
    show_status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 2
    ;;
esac
