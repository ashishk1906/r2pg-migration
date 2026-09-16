#!/usr/bin/env bash
# ==============================================================================
# wait-for-api.sh — Bounded readiness check for the .NET Web API health endpoint
#
# Usage: ./scripts/wait-for-api.sh [url] [max_attempts]
#
# Waits for HTTP 200 from the health endpoint.
# Returns non-zero instead of exit 1 (safe for agent shells).
# ==============================================================================

# Load API_PORT from .env if available
if [ -f ".env" ]; then
    API_PORT_FROM_ENV=$(grep -E '^API_PORT=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "")
fi

DEFAULT_PORT="${API_PORT_FROM_ENV:-${API_PORT:-5000}}"
HEALTH_URL="${1:-http://localhost:${DEFAULT_PORT}/health}"
MAX_ATTEMPTS="${2:-30}"
SLEEP_INTERVAL=2

echo "[INFO] Waiting for API readiness at $HEALTH_URL (max ${MAX_ATTEMPTS} attempts, ${SLEEP_INTERVAL}s interval)..."

for i in $(seq 1 "$MAX_ATTEMPTS"); do
    HTTP_CODE=$(curl --fail --silent --show-error --output /dev/null --write-out "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        echo "[PASS] API is healthy — HTTP $HTTP_CODE (attempt $i/$MAX_ATTEMPTS)"
        return 0 2>/dev/null || exit 0
    fi

    if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
        echo "[FAIL] API health check failed after $MAX_ATTEMPTS attempts ($(( MAX_ATTEMPTS * SLEEP_INTERVAL ))s)" >&2
        echo "[INFO] Last HTTP status: $HTTP_CODE" >&2
        echo "[INFO] Check API logs: docker compose logs rpg-api" >&2
        return 1 2>/dev/null || exit 1
    fi

    sleep "$SLEEP_INTERVAL"
done
