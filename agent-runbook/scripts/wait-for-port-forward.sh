#!/usr/bin/env bash
set -euo pipefail

log_file="${1:?log file required}"
port="${2:?port required}"
max_wait="${3:-30}"

for ((elapsed=0; elapsed<max_wait; elapsed++)); do
  if [ -f "$log_file" ]; then
    if grep -qi "error:" "$log_file"; then
      echo "[wait-for-port-forward] ERROR: port $port failed" >&2
      tail -5 "$log_file" >&2
      exit 1
    fi
    if grep -q "Forwarding from" "$log_file"; then
      echo "[wait-for-port-forward] Port $port is ready."
      exit 0
    fi
  fi
  sleep 1
done

echo "[wait-for-port-forward] TIMEOUT: port $port not ready after ${max_wait}s" >&2
[ -f "$log_file" ] && tail -5 "$log_file" >&2
exit 1
