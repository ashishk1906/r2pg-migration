#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
errors=0
fail() { echo "[FAIL] $1" >&2; errors=$((errors + 1)); }
ok() { echo "[OK]   $1"; }

for tool in git kubectl psql python3 docker curl; do
  if command -v "$tool" >/dev/null 2>&1; then ok "$tool found"; else fail "$tool not found"; fi
done
if docker compose version >/dev/null 2>&1; then ok "docker compose v2 found"; else fail "docker compose v2 not found"; fi

[ -f "$repo_root/.env" ] || fail ".env not found"
if [ -f "$repo_root/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

expected_context="${EXPECTED_K8S_CONTEXT:-}"
actual_context="$(kubectl config current-context 2>/dev/null || true)"
[ -n "$expected_context" ] || fail "EXPECTED_K8S_CONTEXT is not set"
[ "$actual_context" = "$expected_context" ] || fail "Kubernetes context '$actual_context' does not match expected context"
kubectl get namespace test >/dev/null 2>&1 || fail "namespace test not found"
kubectl get svc pgbouncer-svc -n test >/dev/null 2>&1 || fail "svc/pgbouncer-svc not found"
kubectl get svc postgresql -n test >/dev/null 2>&1 || fail "svc/postgresql not found"

python_cmd="python3"
if ! command -v "$python_cmd" >/dev/null 2>&1 && command -v python.exe >/dev/null 2>&1; then
  python_cmd="python.exe"
fi

if ! command -v "$python_cmd" >/dev/null 2>&1; then
  fail "Python 3.12+ interpreter not found"
else
  if "$python_cmd" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ is required")
PY
  then
    ok "Python 3.12+ found"
  else
    fail "Python 3.12+ is required"
  fi
fi

required=(PG_HOST PG_PORT PG_ADMIN_HOST PG_ADMIN_PORT PG_MAINTENANCE_DB PG_DB PG_USER PG_PASSWORD API_PORT RAVEN_URL RAVEN_DB RAVEN_CERT_FILE)
for name in "${required[@]}"; do
  [ -n "${!name:-}" ] || fail "$name is not set"
done
[ "${PG_MAINTENANCE_DB:-}" = "postgres" ] || fail "PG_MAINTENANCE_DB must be postgres"
cert_path="$repo_root/${RAVEN_CERT_FILE:-}"
[ -f "$cert_path" ] || fail "RavenDB certificate not found at $cert_path"

tracked_secrets="$(git -C "$repo_root" ls-files -- \
  '.env' '*.pfx' 'certs/*' 'scripts/certs/*' \
  ':!:certs/.gitkeep' ':!:scripts/certs/.gitkeep' ':!:scripts/certs/README.md')"
[ -z "$tracked_secrets" ] || fail "secret files are tracked by Git"

if [ "$errors" -ne 0 ]; then
  echo "[FAIL] $errors prerequisite(s) failed." >&2
  exit 1
fi
echo "[PASS] All prerequisites satisfied."
