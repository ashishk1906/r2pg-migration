#!/usr/bin/env bash
# =============================================================================
# verify-prerequisites.sh
# Checks all local prerequisites before running onboarding.
# Exit 0 = all checks passed. Exit 1 = one or more checks failed.
# Never echoes secret values.
# =============================================================================
set -euo pipefail

ERRORS=0
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() { echo "[FAIL] $1" >&2; ERRORS=$((ERRORS + 1)); }
pass() { echo "[OK]   $1"; }

echo "=== Prerequisites Check ==="
echo ""

# --- Tool versions ---
if command -v kubectl &>/dev/null; then
  pass "kubectl: $(kubectl version --client --short 2>/dev/null | head -1)"
else
  fail "kubectl not found"
fi

if command -v psql &>/dev/null; then
  pass "psql: $(psql --version)"
else
  fail "psql not found"
fi

if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -gt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 12 ]; }; then
    pass "python3: $PY_VER (>= 3.12)"
  else
    fail "python3 $PY_VER < 3.12 required"
  fi
else
  fail "python3 not found"
fi

if command -v docker &>/dev/null; then
  pass "docker: $(docker version --format '{{.Client.Version}}' 2>/dev/null)"
else
  fail "docker not found"
fi

if docker compose version &>/dev/null 2>&1; then
  pass "docker compose v2: $(docker compose version --short 2>/dev/null)"
else
  fail "docker compose v2 not found (docker-compose v1 is not supported)"
fi

echo ""
echo "=== Kubernetes Context ==="

# Load EXPECTED_K8S_CONTEXT from .env if set
ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi

EXPECTED_K8S_CONTEXT="${EXPECTED_K8S_CONTEXT:-}"
ACTUAL_CONTEXT=$(kubectl config current-context 2>/dev/null || true)

if [ -z "$EXPECTED_K8S_CONTEXT" ]; then
  fail "EXPECTED_K8S_CONTEXT is not set in .env — cannot verify cluster identity"
elif [ "$ACTUAL_CONTEXT" = "$EXPECTED_K8S_CONTEXT" ]; then
  pass "kubectl context: $ACTUAL_CONTEXT"
else
  fail "kubectl context is '$ACTUAL_CONTEXT', expected '$EXPECTED_K8S_CONTEXT'"
fi

if kubectl get namespace test &>/dev/null; then
  pass "namespace 'test' exists"
else
  fail "namespace 'test' not found"
fi

if kubectl get svc pgbouncer-svc -n test &>/dev/null; then
  pass "svc/pgbouncer-svc found in namespace test"
else
  fail "svc/pgbouncer-svc not found in namespace test"
fi

if kubectl get svc postgresql -n test &>/dev/null; then
  pass "svc/postgresql found in namespace test"
else
  fail "svc/postgresql not found in namespace test"
fi

echo ""
echo "=== .env File & Required Variables ==="

if [ ! -f "$ENV_FILE" ]; then
  fail ".env file not found at $REPO_ROOT/.env"
else
  pass ".env file found"
fi

REQUIRED_VARS=(
  PG_HOST PG_PORT PG_DB PG_USER PG_PASSWORD
  RAVEN_URL RAVEN_DB RAVEN_CERT_FILE
  API_PORT EXPECTED_K8S_CONTEXT
)

for VAR in "${REQUIRED_VARS[@]}"; do
  VAL="${!VAR:-}"
  if [ -z "$VAL" ]; then
    fail "$VAR is not set or empty in .env"
  else
    pass "$VAR is set"
  fi
done

echo ""
echo "=== RavenDB Certificate ==="

CERT_PATH="$REPO_ROOT/${RAVEN_CERT_FILE:-}"
if [ -z "${RAVEN_CERT_FILE:-}" ]; then
  fail "RAVEN_CERT_FILE is not set — cannot locate certificate"
elif [ -f "$CERT_PATH" ]; then
  pass "Certificate found: $RAVEN_CERT_FILE"
else
  fail "Certificate not found at $CERT_PATH"
  echo "       Download it from the Google Drive link in PLAYBOOK.md and place it at:" >&2
  echo "       $CERT_PATH" >&2
fi

echo ""
echo "=== Secrets Not Committed ==="

COMMITTED_SECRETS=$(git -C "$REPO_ROOT" ls-files -- '.env' '*.pfx' 'certs/*' 'scripts/certs/*' ':!:scripts/certs/.gitkeep' ':!:scripts/certs/README.md' ':!:certs/.gitkeep' 2>/dev/null || true)
if [ -z "$COMMITTED_SECRETS" ]; then
  pass "No secrets found in git index"
else
  fail "Secrets are tracked by git:"
  echo "$COMMITTED_SECRETS" | while read -r f; do echo "       $f" >&2; done
  echo "       Run: git rm --cached <file> and add to .gitignore" >&2
fi

echo ""
echo "==========================="
if [ "$ERRORS" -eq 0 ]; then
  echo "[PASS] All prerequisites satisfied."
  exit 0
else
  echo "[FAIL] $ERRORS prerequisite(s) failed. Fix the errors above before continuing."
  exit 1
fi
