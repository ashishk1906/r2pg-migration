#!/usr/bin/env bash
# =============================================================================
# wait-for-api.sh
# Waits until the Web API health endpoint returns HTTP 200.
# Returns non-zero on timeout — does NOT call exit so an agent shell stays alive.
#
# Usage: bash scripts/wait-for-api.sh [base-url] [max-seconds]
# =============================================================================
BASE_URL="${1:-http://localhost:5000}"
MAX_WAIT="${2:-60}"
HEALTH_PATH="/health"
URL="${BASE_URL}${HEALTH_PATH}"

ELAPSED=0
while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$URL" 2>/dev/null || true)
  if [ "$HTTP_CODE" = "200" ]; then
    echo "[wait-for-api] API is ready: $URL returned HTTP 200."
    return 0 2>/dev/null || exit 0
  fi
  echo "[wait-for-api] Waiting for $URL (got HTTP ${HTTP_CODE:-000})... ${ELAPSED}s"
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

echo "[wait-for-api] TIMEOUT: $URL did not return HTTP 200 after ${MAX_WAIT}s" >&2
echo "[wait-for-api] Last HTTP status: ${HTTP_CODE:-000}" >&2
return 1 2>/dev/null || exit 1
