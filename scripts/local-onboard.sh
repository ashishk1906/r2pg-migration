#!/usr/bin/env bash
# =============================================================================
# local-onboard.sh
# End-to-end automated runner for CT-RPG onboarding and verification.
# Executable by developers and coding agents alike.
#
# Usage:
#   bash scripts/local-onboard.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Resolve a writable temporary directory across Linux, macOS, and Windows (Git Bash/WSL)
TMP_DIR="${TMPDIR:-${TEMP:-/tmp}}"
mkdir -p "$TMP_DIR"
PF_PID_FILE="$TMP_DIR/ct-rpg-pgbouncer-port-forward.pid"
PF_LOG_FILE="$TMP_DIR/ct-rpg-pgbouncer-port-forward.log"

PF_PID=""

cleanup() {
  local exit_code=$?
  if [ -n "$PF_PID" ] && kill -0 "$PF_PID" 2>/dev/null; then
    echo "[cleanup] Stopping background port-forward (PID: $PF_PID)..."
    kill "$PF_PID" 2>/dev/null || true
  elif [ -f "$PF_PID_FILE" ]; then
    local pid
    pid=$(cat "$PF_PID_FILE" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "[cleanup] Stopping background port-forward (PID: $pid)..."
      kill "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$PF_PID_FILE" 2>/dev/null || true
  if [ "$exit_code" -ne 0 ]; then
    echo ""
    echo "========================================="
    echo "CT-RPG Local Verification: FAILED (exit code: $exit_code)"
    echo "========================================="
  fi
}
trap cleanup EXIT INT TERM

echo "========================================="
echo "CT-RPG Local Verification — Starting Run"
echo "========================================="
echo ""

# Activate virtual environment if present (supporting both Linux and Windows venv layouts)
if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null || true
fi

# -----------------------------------------------------------------------------
# Gate 1: Prerequisites Check
# -----------------------------------------------------------------------------
echo "[1/8] Running prerequisite gate..."
bash scripts/verify-prerequisites.sh
echo "[OK] Prerequisite gate passed."
echo ""

# -----------------------------------------------------------------------------
# Non-Interactive Environment Setup
# -----------------------------------------------------------------------------
echo "[2/8] Setting up environment & non-interactive session..."

# Load .env non-interactively
set -a
# shellcheck disable=SC1091
source .env
set +a

export PGPASSWORD="$PG_PASSWORD"
PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-6432}"
PG_USER="${PG_USER:-postgres}"
PG_DB="${PG_DB:-rpg}"
API_PORT="${API_PORT:-5000}"

# -----------------------------------------------------------------------------
# Gate 2: Port-Forwarding & Database Connectivity
# -----------------------------------------------------------------------------
echo "[3/8] Checking port $PG_PORT and launching background port-forward..."

# Cross-platform port availability check via python
PORT_IN_USE=$(python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
result = s.connect_ex(('127.0.0.1', int('$PG_PORT')))
s.close()
print('YES' if result == 0 else 'NO')
")

if [ "$PORT_IN_USE" = "YES" ]; then
  echo "[-] Port $PG_PORT is already listening. Checking existing connectivity..."
else
  # Clean up stale PID file if process died
  if [ -f "$PF_PID_FILE" ]; then
    stale_pid=$(cat "$PF_PID_FILE" 2>/dev/null || true)
    if [ -n "$stale_pid" ] && ! kill -0 "$stale_pid" 2>/dev/null; then
      rm -f "$PF_PID_FILE"
    fi
  fi

  echo "[-] Starting kubectl port-forward for svc/pgbouncer-svc ($PG_PORT:$PG_PORT)..."
  kubectl port-forward -n test svc/pgbouncer-svc "${PG_PORT}:${PG_PORT}" > "$PF_LOG_FILE" 2>&1 &
  PF_PID=$!
  echo "$PF_PID" > "$PF_PID_FILE"

  bash scripts/wait-for-port-forward.sh "$PF_LOG_FILE" "$PG_PORT" 30
fi

echo "[-] Verifying PostgreSQL connectivity via maintenance database ctlytics_test..."
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d ctlytics_test -c "SELECT 1;" >/dev/null

echo "[-] Checking target database '$PG_DB'..."
DB_EXISTS=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d ctlytics_test -tAc "SELECT 1 FROM pg_database WHERE datname = '$PG_DB';")

if [ "$DB_EXISTS" = "1" ]; then
  echo "[-] Target database '$PG_DB' already exists. Proceeding with idempotent migration."
else
  echo "[-] Target database '$PG_DB' does not exist. Creating..."
  psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d ctlytics_test -c "CREATE DATABASE $PG_DB;"
fi

# Preflight routing check for PgBouncer
if ! psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -c "SELECT 1;" >/dev/null 2>&1; then
  echo "[!] ERROR: Cannot connect to '$PG_DB' via PgBouncer." >&2
  echo "[!] PgBouncer wildcard routing is not enabled on cluster. Operator action required (PGBOUNCER_DATABASE='*')." >&2
  exit 1
fi
echo "[OK] PostgreSQL connectivity and target database verified."
echo ""

# -----------------------------------------------------------------------------
# Gate 3: Data Migration & Post-Migration SQL
# -----------------------------------------------------------------------------
echo "[4/8] Running RavenDB -> PostgreSQL Migration..."
python3 scripts/migrate_all.py --all

echo "[-] Verifying post-migration views and triggers..."
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -c "SELECT 1 FROM student_fee_summary_view LIMIT 1;" >/dev/null
TRG_COUNT=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -tAc "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_student_modified_on';")
if [ "$TRG_COUNT" -lt 1 ]; then
  echo "[!] ERROR: Trigger trg_student_modified_on not found in pg_trigger." >&2
  exit 1
fi
echo "[OK] Migration and post-SQL objects verified."
echo ""

# -----------------------------------------------------------------------------
# Gate 4: Exhaustive Parity Verification
# -----------------------------------------------------------------------------
echo "[5/8] Running RavenDB -> PostgreSQL Parity Verification..."
python3 scripts/verify_raven_to_postgres.py

echo "[-] Asserting parity report results..."
python3 -c "
import json, glob, os, sys
reports = glob.glob('validation/exhaustive-parity-report-*.json')
if not reports:
    print('ERROR: No parity report found in validation/', file=sys.stderr)
    sys.exit(1)
latest = max(reports, key=os.path.getctime)
with open(latest, 'r', encoding='utf-8') as f:
    data = json.load(f)
status = data.get('overall_status')
results = data.get('results', [])
missing = sum(r.get('missing_in_pg_count', 0) for r in results)
extra = sum(r.get('extra_in_pg_count', 0) for r in results)
mismatches = sum(r.get('field_mismatches_count', 0) for r in results)
print(f'Parity Summary: status={status}, missing={missing}, extra={extra}, mismatches={mismatches}')
if status != 'PASS' or missing != 0 or extra != 0 or mismatches != 0:
    print('Parity gate failed!', file=sys.stderr)
    sys.exit(1)
"
echo "[OK] Parity verification passed with 0 mismatches."
echo ""

# -----------------------------------------------------------------------------
# Gate 5: Web API Startup & Health Check
# -----------------------------------------------------------------------------
echo "[6/8] Starting .NET 10 Web API..."
docker compose up -d --build rpg-api

echo "[-] Waiting for API health check on http://localhost:$API_PORT/health..."
bash scripts/wait-for-api.sh "http://localhost:$API_PORT" 60

echo "[-] Testing sample API endpoint..."
curl --fail --silent --show-error "http://localhost:$API_PORT/api/stu/student?limit=2" >/dev/null
echo "[OK] Web API is healthy and responding to requests."
echo ""

# -----------------------------------------------------------------------------
# Gate 6: Automated Integration & Unit Tests
# -----------------------------------------------------------------------------
echo "[7/8] Running automated tests..."
docker compose run --rm rpg-tests
echo "[OK] Automated tests passed."
echo ""

# -----------------------------------------------------------------------------
# Completion Report
# -----------------------------------------------------------------------------
echo "[8/8] Generating final verification report..."
echo ""
echo "==========================="
echo "CT-RPG Local Verification"
echo "==========================="
echo "Preflight:       PASS"
echo "PostgreSQL:      PASS"
echo "Migration:       PASS"
echo "Post-SQL:        PASS"
echo "Parity:          PASS"
echo "API Health:      PASS"
echo "Tests:           PASS"
echo ""
echo "Overall:         PASS"
echo "==========================="
