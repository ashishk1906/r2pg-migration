#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

[ -f .env ] || { echo "[FAIL] .env is required" >&2; exit 1; }
set -a
# shellcheck disable=SC1091
source .env
set +a

if ! command -v psql >/dev/null 2>&1; then
  postgres_client=$(find \
    "/c/Program Files/PostgreSQL" \
    "/mnt/c/Program Files/PostgreSQL" \
    -type f \( -name psql.exe -o -name psql \) -print -quit 2>/dev/null || true)
  if [ -n "$postgres_client" ]; then
    bootstrap_bin="/tmp/ct-rpg-bin"
    mkdir -p "$bootstrap_bin"
    printf '#!/usr/bin/env bash\nexec "%s" "$@"\n' "$postgres_client" > "$bootstrap_bin/psql"
    chmod +x "$bootstrap_bin/psql"
    export PATH="$bootstrap_bin:$(dirname "$postgres_client"):$PATH"
  fi
fi

if command -v kubectl >/dev/null 2>&1; then
  if ! kubectl config get-contexts -o name 2>/dev/null | grep -Fxq "$EXPECTED_K8S_CONTEXT"; then
    for kubeconfig in "$HOME/.kube/config" "/c/Users/"*/.kube/config "/mnt/c/Users/"*/.kube/config; do
      if [ -f "$kubeconfig" ]; then
        export KUBECONFIG="$kubeconfig"
        kubectl config get-contexts -o name 2>/dev/null | grep -Fxq "$EXPECTED_K8S_CONTEXT" && break
      fi
    done
  fi
  kubectl config use-context "$EXPECTED_K8S_CONTEXT" >/dev/null 2>&1 || true
fi

python_cmd=""
for candidate in python.exe python python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys' >/dev/null 2>&1; then
    python_cmd="$candidate"
    break
  fi
done

if [ -z "$python_cmd" ]; then
  echo "[FAIL] A working Python interpreter is required" >&2
  exit 1
fi

work_tmp="${TMPDIR:-${TEMP:-/tmp}}"
pid_file="$work_tmp/ct-rpg-agent-port-forwards.pid"
pf_log="$work_tmp/ct-rpg-pgbouncer-port-forward.log"
admin_log="$work_tmp/ct-rpg-postgres-port-forward.log"
pf_pid=""
admin_pid=""

cleanup() {
  local code=$?
  [ -n "$pf_pid" ] && kill "$pf_pid" 2>/dev/null || true
  [ -n "$admin_pid" ] && kill "$admin_pid" 2>/dev/null || true
  rm -f "$pid_file" "$pf_log" "$admin_log"
  if [ "$code" -ne 0 ]; then
    echo "[FAIL] CT-RPG verification stopped with exit code $code" >&2
  fi
}
trap cleanup EXIT INT TERM

bash agent-runbook/scripts/verify-prerequisites.sh

if ! "$python_cmd" -c 'import psycopg2' >/dev/null 2>&1; then
  echo "[-] Installing migration dependencies..."
  if [ "$python_cmd" = "python.exe" ] && command -v pip.exe >/dev/null 2>&1; then
    pip.exe install -r scripts/requirements.txt
  elif command -v pip3 >/dev/null 2>&1; then
    pip3 install -r scripts/requirements.txt
  elif command -v pip >/dev/null 2>&1; then
    pip install -r scripts/requirements.txt
  elif command -v pip.exe >/dev/null 2>&1 && command -v python.exe >/dev/null 2>&1; then
    python_cmd="python.exe"
    pip.exe install -r scripts/requirements.txt
  else
    "$python_cmd" -m pip install -r scripts/requirements.txt
  fi
fi

export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"
admin_conn="host=$PG_ADMIN_HOST port=$PG_ADMIN_PORT user=$PG_USER dbname=$PG_MAINTENANCE_DB password=$PG_PASSWORD connect_timeout=$PGCONNECT_TIMEOUT"
app_conn="host=$PG_HOST port=$PG_PORT user=$PG_USER dbname=$PG_DB password=$PG_PASSWORD connect_timeout=$PGCONNECT_TIMEOUT"

port_busy() { "$python_cmd" -c 'import socket,sys; s=socket.socket(); s.settimeout(1); r=s.connect_ex((sys.argv[1], int(sys.argv[2]))); s.close(); print("YES" if r == 0 else "NO")' 127.0.0.1 "$1"; }

if [ "$(port_busy "$PG_PORT")" != "YES" ]; then
  kubectl port-forward -n test svc/pgbouncer-svc "${PG_PORT}:6432" >"$pf_log" 2>&1 &
  pf_pid=$!
  echo "$pf_pid" >>"$pid_file"
  bash agent-runbook/scripts/wait-for-port-forward.sh "$pf_log" "$PG_PORT" 30
fi

if [ "$PG_ADMIN_HOST" = "localhost" ] || [ "$PG_ADMIN_HOST" = "127.0.0.1" ]; then
  if [ "$(port_busy "$PG_ADMIN_PORT")" != "YES" ]; then
    kubectl port-forward -n test svc/postgresql "${PG_ADMIN_PORT}:5432" >"$admin_log" 2>&1 &
    admin_pid=$!
    echo "$admin_pid" >>"$pid_file"
    bash agent-runbook/scripts/wait-for-port-forward.sh "$admin_log" "$PG_ADMIN_PORT" 30
  fi
fi

psql "$admin_conn" -c "SELECT 1;" >/dev/null

# The target database is fixed by this environment and the query is idempotent.
db_exists="$(psql "$admin_conn" -tAc "SELECT 1 FROM pg_database WHERE datname = 'rpg';" | tr -d '[:space:]')"
if [ "$db_exists" != "1" ]; then
  psql "$admin_conn" -c "CREATE DATABASE rpg;"
fi

psql "$app_conn" -c "SELECT 1;" >/dev/null
"$python_cmd" scripts/migrate_all.py --all

psql "$app_conn" -c "SELECT 1 FROM student_fee_summary_view LIMIT 1;" >/dev/null
trigger_count="$(psql "$app_conn" -tAc "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_student_modified_on';" | tr -d '[:space:]')"
[ "${trigger_count:-0}" -ge 1 ]

"$python_cmd" scripts/verify_raven_to_postgres.py
"$python_cmd" - <<'PY'
import glob, json, os, sys
reports = glob.glob("validation/exhaustive-parity-report-*.json")
if not reports:
    raise SystemExit("No parity report found")
latest = max(reports, key=os.path.getctime)
data = json.load(open(latest, encoding="utf-8"))
results = data.get("results", [])
missing = sum(r.get("missing_in_pg_count", 0) for r in results)
extra = sum(r.get("extra_in_pg_count", 0) for r in results)
mismatches = sum(r.get("field_mismatches_count", 0) for r in results)
if data.get("overall_status") != "PASS" or missing or extra or mismatches:
    raise SystemExit(f"Parity failed: status={data.get('overall_status')} missing={missing} extra={extra} mismatches={mismatches}")
print("[PASS] Parity: zero discrepancies")
PY

docker compose up -d --build rpg-api
bash agent-runbook/scripts/wait-for-api.sh "http://localhost:${API_PORT}" 60
curl --fail --silent --show-error "http://localhost:${API_PORT}/api/stu/student?limit=2" >/dev/null
docker compose run --rm rpg-tests

cat <<'EOF'
CT-RPG Local Verification
Preflight:       PASS
PostgreSQL:      PASS
Migration:       PASS
Post-SQL:        PASS
Parity:          PASS
API Health:      PASS
Tests:           PASS
Overall:         PASS
EOF
