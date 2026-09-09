#!/usr/bin/env bash
# =============================================================================
# wait-for-port-forward.sh
# Waits until a kubectl port-forward is ready by polling the log file.
# Returns non-zero on timeout or error — does NOT call exit so an agent
# shell session stays alive.
#
# Usage: bash scripts/wait-for-port-forward.sh <log-file> <port> [max-seconds]
# =============================================================================
LOG_FILE="${1:-}"
PORT="${2:-6432}"
MAX_WAIT="${3:-30}"

if [ -z "$LOG_FILE" ]; then
  echo "[wait-for-port-forward] ERROR: log file argument required" >&2
  return 1 2>/dev/null || exit 1
fi

ELAPSED=0
while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  if [ -f "$LOG_FILE" ]; then
    if grep -qi "error:" "$LOG_FILE" 2>/dev/null; then
      echo "[wait-for-port-forward] ERROR: port-forward log contains error:" >&2
      grep -i "error:" "$LOG_FILE" >&2
      return 1 2>/dev/null || exit 1
    fi
    if grep -q "Forwarding from" "$LOG_FILE" 2>/dev/null; then
      echo "[wait-for-port-forward] Port $PORT is ready."
      return 0 2>/dev/null || exit 0
    fi
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

echo "[wait-for-port-forward] TIMEOUT: port $PORT not ready after ${MAX_WAIT}s" >&2
if [ -f "$LOG_FILE" ]; then
  echo "[wait-for-port-forward] Last log output:" >&2
  tail -5 "$LOG_FILE" >&2
fi
return 1 2>/dev/null || exit 1
