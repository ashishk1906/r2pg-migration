#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
errors=0
fail() { echo "[FAIL] $1" >&2; errors=$((errors + 1)); }
ok() { echo "[OK]   $1"; }

if [ -f "$repo_root/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

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

if command -v kubectl >/dev/null 2>&1 && [ -n "${EXPECTED_K8S_CONTEXT:-}" ]; then
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

for tool in git kubectl psql docker curl; do
  if command -v "$tool" >/dev/null 2>&1; then ok "$tool found"; else fail "$tool not found"; fi
done
if docker compose version >/dev/null 2>&1; then ok "docker compose v2 found"; else fail "docker compose v2 not found"; fi

[ -f "$repo_root/.env" ] || fail ".env not found"

expected_context="${EXPECTED_K8S_CONTEXT:-}"
actual_context="$(kubectl config current-context 2>/dev/null || true)"
[ -n "$expected_context" ] || fail "EXPECTED_K8S_CONTEXT is not set"
[ "$actual_context" = "$expected_context" ] || fail "Kubernetes context '$actual_context' does not match expected context"
kubectl get namespace test >/dev/null 2>&1 || fail "namespace test not found"
kubectl get svc pgbouncer-svc -n test >/dev/null 2>&1 || fail "svc/pgbouncer-svc not found"
kubectl get svc postgresql -n test >/dev/null 2>&1 || fail "svc/postgresql not found"

python_cmd=""
for candidate in python.exe python python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys' >/dev/null 2>&1; then
    python_cmd="$candidate"
    break
  fi
done

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
