#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-http://localhost:5000}"
max_wait="${2:-60}"
url="${base_url}/health"

for ((elapsed=0; elapsed<max_wait; elapsed+=2)); do
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 3 "$url" || true)
  if [ "$code" = "200" ]; then
    echo "[wait-for-api] API is ready: $url"
    exit 0
  fi
  sleep 2
done

echo "[wait-for-api] TIMEOUT: $url did not return HTTP 200" >&2
exit 1
