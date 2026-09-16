#!/usr/bin/env bash
# ==============================================================================
# verify-prerequisites.sh — CT-RPG Docker Playbook Preflight Gate
# Verifies all required tools, configuration, and credentials
# for the Docker-based migration and API verification workflow.
#
# Exit 0 = all checks pass
# Exit 1 = one or more checks failed
#
# NEVER echoes secret values.
# ==============================================================================

set -euo pipefail

FAIL_COUNT=0
WARN_COUNT=0

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
warn() { echo "[WARN] $1"; WARN_COUNT=$((WARN_COUNT + 1)); }
info() { echo "[INFO] $1"; }

# --------------------------------------------------------------------------
# 1. Required CLI tools
# --------------------------------------------------------------------------
info "Checking required tools..."

if command -v git &>/dev/null; then
    pass "git is installed"
else
    fail "git is not installed or not in PATH"
fi

if command -v docker &>/dev/null; then
    pass "docker is installed"
else
    fail "docker is not installed or not in PATH"
fi

if command -v curl &>/dev/null; then
    pass "curl is installed"
else
    fail "curl is not installed or not in PATH"
fi

# --------------------------------------------------------------------------
# 2. Docker daemon running
# --------------------------------------------------------------------------
info "Checking Docker daemon..."
if docker info &>/dev/null; then
    pass "Docker daemon is running"
else
    fail "Docker daemon is not running or not accessible"
fi

# --------------------------------------------------------------------------
# 3. Docker Compose v2
# --------------------------------------------------------------------------
info "Checking Docker Compose v2..."
if docker compose version &>/dev/null; then
    COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || docker compose version 2>/dev/null)
    pass "Docker Compose v2 is available ($COMPOSE_VERSION)"
else
    fail "Docker Compose v2 is not available (need 'docker compose', not 'docker-compose')"
fi

# --------------------------------------------------------------------------
# 4. .env file exists and required variables are set
# --------------------------------------------------------------------------
info "Checking .env file..."
if [ -f ".env" ]; then
    pass ".env file exists"
else
    fail ".env file does not exist — copy from .env.example and configure"
fi

REQUIRED_VARS=(
    "PG_PORT"
    "PG_DB"
    "PG_USER"
    "PG_PASSWORD"
    "RAVEN_URL"
    "RAVEN_DB"
    "RAVEN_CERT_FILE"
    "API_PORT"
)

if [ -f ".env" ]; then
    info "Checking required environment variables..."
    for var in "${REQUIRED_VARS[@]}"; do
        VAL=$(grep -E "^${var}=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "")
        if [ -n "$VAL" ] && [[ "$VAL" != *"<"* ]]; then
            pass "$var is set (value hidden)"
        else
            fail "$var is missing or contains a placeholder in .env"
        fi
    done
fi

# --------------------------------------------------------------------------
# 5. RavenDB certificate exists
# --------------------------------------------------------------------------
info "Checking RavenDB certificate..."
if [ -f ".env" ]; then
    CERT_FILE=$(grep -E '^RAVEN_CERT_FILE=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "")
    if [ -n "$CERT_FILE" ]; then
        # Check repo-root-relative and scripts/-prefixed paths
        if [ -f "scripts/$CERT_FILE" ]; then
            pass "RavenDB certificate found at scripts/$CERT_FILE"
        elif [ -f "$CERT_FILE" ]; then
            pass "RavenDB certificate found at $CERT_FILE"
        else
            fail "RavenDB certificate not found at 'scripts/$CERT_FILE' or '$CERT_FILE'"
        fi
    else
        fail "RAVEN_CERT_FILE is not set in .env"
    fi
else
    fail "Cannot check certificate — .env file missing"
fi

# --------------------------------------------------------------------------
# 6. docker-compose.yml exists
# --------------------------------------------------------------------------
info "Checking docker-compose.yml..."
if [ -f "docker-compose.yml" ]; then
    pass "docker-compose.yml exists"
else
    fail "docker-compose.yml not found in repository root"
fi

# --------------------------------------------------------------------------
# 7. Secrets not tracked by Git
# --------------------------------------------------------------------------
info "Checking that secrets are not tracked by Git..."
TRACKED_SECRETS=$(git ls-files .env '*.pfx' 'scripts/certs/*' ':!scripts/certs/.gitkeep' 2>/dev/null || echo "")
if [ -z "$TRACKED_SECRETS" ]; then
    pass "No secret files tracked by Git"
else
    fail "Secret files are tracked by Git: $TRACKED_SECRETS"
fi

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
echo ""
echo "============================================================"
if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "[PREFLIGHT PASS] All checks passed ($WARN_COUNT warnings)."
    echo "============================================================"
    exit 0
else
    echo "[PREFLIGHT FAIL] $FAIL_COUNT check(s) failed, $WARN_COUNT warning(s)."
    echo "============================================================"
    exit 1
fi
