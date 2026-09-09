---
title: "Local Testing & Onboarding Playbook"
project: "CT-RPG"
purpose: "RavenDB to PostgreSQL migration and .NET 10 Web API verification"
version: "1.2"

execution:
  intended_for:
    - human
    - coding-agent
  working_directory: "repository-root"
  interactive_input_allowed: false
  stop_on_error: true
  destructive_actions_allowed: false

repository:
  url: "https://github.com/ashishk1906/r2pg-migration.git"
  directory: "r2pg-migration"

prerequisites:
  tools:
    - name: "git"
      required: true
    - name: "kubectl"
      required: true
      requirement: "Configured with access to the CT test Kubernetes cluster"
    - name: "psql"
      required: true
      description: "PostgreSQL CLI client"
    - name: "python"
      required: true
      minimum_version: "3.12"
    - name: "docker"
      required: true
      requirement: "Docker daemon running with Linux containers"
    - name: "docker-compose"
      required: true
      requirement: "Docker Compose v2 via `docker compose`"

  kubernetes:
    required: true
    expected_context: "do-blr1-k8s-1-22-8-do-1-blr1-1655977229480"
    namespace: "test"
    service: "pgbouncer-svc"
    local_port: 6432
    remote_port: 6432
    context_must_be_verified: true

  pgbouncer:
    wildcard_routing_required: true
    note: "PGBOUNCER_DATABASE='*' routing is a cluster bootstrap precondition managed by operators. Agents must never run kubectl set env to mutate PgBouncer."

  postgres:
    maintenance_database: "ctlytics_test"
    target_database: "rpg"
    required_role: "postgres"
    required_privileges:
      - "CONNECT to maintenance database"
      - "CREATE DATABASE for initial setup"
      - "Schema/data privileges required by migration scripts"

  ravendb:
    required: true
    certificate_required: true

  files:
    - path: ".env"
      required: true
      source: ".env.example"
      secret: true
    - path: "certs/free.btl.client.certificate.pfx"
      required: true
      secret: true

  environment:
    required_variables:
      - "EXPECTED_K8S_CONTEXT"
      - "PG_HOST"
      - "PG_PORT"
      - "PG_DB"
      - "PG_USER"
      - "PG_PASSWORD"
      - "API_PORT"
      - "RAVEN_URL"
      - "RAVEN_DB"
      - "RAVEN_CERT_FILE"

  api:
    base_url: "http://localhost:5000"
    health_path: "/health"
    sample_path: "/api/stu/student?limit=2"

commands:
  preflight: "./scripts/verify-prerequisites.sh"
  wait_port_forward: "bash scripts/wait-for-port-forward.sh /tmp/ct-rpg-pgbouncer-port-forward.log 6432 30"
  migrate: "python3 scripts/migrate_all.py --all"
  post_sql_check_view: "psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d rpg -c \"SELECT 1 FROM student_fee_summary_view LIMIT 1;\""
  post_sql_check_trigger: "psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d rpg -tAc \"SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_student_modified_on';\""
  verify_parity: "python3 scripts/verify_raven_to_postgres.py"
  start_api: "docker compose up -d --build rpg-api"
  wait_api: "bash scripts/wait-for-api.sh http://localhost:5000 60"
  sample_api: "curl --fail --silent --show-error http://localhost:5000/api/stu/student?limit=2"
  run_tests: "docker compose run --rm rpg-tests"

safety:
  never_commit:
    - ".env"
    - "*.pfx"
    - "scripts/certs/*"

  shared_environment_mutation:
    allowed: false
    note: "Do not modify Kubernetes Deployments, Services, ConfigMaps, Secrets, PgBouncer configuration, or other shared resources."

  database_reset:
    allowed_by_default: false
    requires_explicit_instruction: true

  database_drop:
    allowed_by_default: false
    requires_explicit_instruction: true

agent_execution_rules:
  - "Run from the repository root unless a step explicitly says otherwise."
  - "Run the prerequisite gate before migration or API commands."
  - "Verify the active Kubernetes context before accessing the cluster."
  - "Do not modify shared Kubernetes resources."
  - "Do not request interactive input."
  - "Do not print secrets or certificate contents."
  - "Treat missing credentials, configuration, or certificates as blocking preconditions."
  - "If target database 'rpg' already exists, proceed and log; do not drop or recreate unless explicitly instructed."
  - "Stop immediately when a required gate fails."
  - "Do not bypass a failed migration, post-SQL, parity, health, or test gate."
  - "On failure, report the step, command, exit code, and relevant stdout/stderr."
  - "Do not perform optional teardown unless explicitly requested."

gates:
  preflight:
    success:
      - "exit_code == 0"

  migration:
    success:
      - "exit_code == 0"
      - "post_sql_applied: student_fee_summary_view exists and returns rows"
      - "post_sql_applied: trg_student_modified_on trigger exists in pg_trigger"

  parity:
    success:
      - "exit_code == 0"
      - "report_file: newest validation/exhaustive-parity-report-*.json has overall_status == 'PASS'"
      - "missing_in_pg_count == 0"
      - "extra_in_pg_count == 0"
      - "field_mismatches_count == 0"

  api_health:
    success:
      - "http_status == 200"
      - "exit_code == 0"

  tests:
    success:
      - "exit_code == 0"

success_criteria:
  - "Prerequisite gate passes."
  - "Expected Kubernetes context is verified."
  - "PgBouncer connectivity succeeds."
  - "Target PostgreSQL database is available."
  - "Migration completes successfully with exit code 0."
  - "Post-migration views and triggers are verified in the database."
  - "RavenDB-to-PostgreSQL parity verification reports zero mismatches with exit code 0."
  - "Web API health endpoint returns HTTP 200."
  - "Automated tests complete with exit code 0."
---

# Local Testing & Onboarding Playbook

## CT-RPG: RavenDB → PostgreSQL Migration & .NET 10 Web API

This playbook defines the local setup and verification workflow for migrating CT-RPG data from RavenDB to PostgreSQL and validating the .NET 10 Web API.

It is intended to be executable by either a developer or an automated coding agent (e.g., Codex).

The YAML front matter above is the operational contract. The Markdown below specifies the exact execution steps.

---

## 1. Clone Repository

```bash
git clone https://github.com/ashishk1906/r2pg-migration.git
cd r2pg-migration
```

All commands in this playbook must be run from the repository root unless explicitly stated otherwise.

---

## 2. Configure Local Environment

Create the local environment file if it does not already exist:

```bash
cp .env.example .env
```

Configure the following variables in `.env`:

```dotenv
EXPECTED_K8S_CONTEXT=do-blr1-k8s-1-22-8-do-1-blr1-1655977229480

PG_HOST=localhost
PG_PORT=6432
PG_DB=rpg
PG_USER=postgres
PG_PASSWORD=<postgres-password>

API_PORT=5000

RAVEN_URL=https://a.free.btl.ravendb.cloud
RAVEN_DB=BTL
RAVEN_CERT_FILE=certs/free.btl.client.certificate.pfx
```

`RAVEN_CERT_FILE` is relative to the repository root. `certs/free.btl.client.certificate.pfx` matches `.env.example` and resolves cleanly in both host and Docker container paths.

### Secret handling

The following must never be committed to Git:

```text
.env
*.pfx
scripts/certs/*
```

Secrets must be supplied through `.env`, the environment, or an approved credential distribution mechanism. Never print secret values during verification.

---

## 2.1 Set Up Non-Interactive Environment

To comply with non-interactive execution (`interactive_input_allowed: false`), create a Python virtual environment and export `.env` variables (including `PGPASSWORD`) once into your shell:

```bash
python3 -m venv .venv
source .venv/bin/activate
set -a
source .env
set +a
export PGPASSWORD="$PG_PASSWORD"
```

Throughout this playbook, all `psql` invocations use `$PG_HOST`, `$PG_PORT`, and `$PG_USER` from `.env` with non-interactive authentication.

---

## 3. Install RavenDB Certificate

Obtain the RavenDB client certificate through the approved internal credential-distribution mechanism.

Place it at:

```text
certs/free.btl.client.certificate.pfx
```

Do not continue if the certificate is unavailable. Missing certificates are a blocking precondition.

---

## 4. Run Prerequisite Gate

Execute the machine-checkable verification script:

```bash
./scripts/verify-prerequisites.sh
```

The script verifies:
- Required tools (`git`, `kubectl`, `psql`, `python3`, `docker`, `docker compose v2`) are installed and functional.
- Python is version 3.12 or newer.
- Docker daemon is running with Linux container support.
- Docker Compose v2 is available via `docker compose`.
- The active Kubernetes context matches `$EXPECTED_K8S_CONTEXT`.
- Namespace `test` and service `pgbouncer-svc` exist.
- `.env` exists and contains all required variables (including `API_PORT` and `EXPECTED_K8S_CONTEXT`).
- The RavenDB client certificate file exists at `$RAVEN_CERT_FILE`.
- `git ls-files` confirms no `.env`, `*.pfx`, or `scripts/certs/*` files are tracked in the Git index.
- No secret values are echoed to stdout or stderr.

### Gate

Success requires:

```text
exit code == 0
```

If the script exits non-zero, stop immediately and report the failures.

> **Diagnostic fallback:** If needed for manual troubleshooting, run:
> ```bash
> kubectl version --client
> psql --version
> python3 --version
> docker version
> docker compose version
> kubectl config current-context
> kubectl get namespace test
> kubectl get svc pgbouncer-svc -n test
> ```

---

## 5. Install Migration Dependencies

Run within the active virtual environment:

```bash
python3 -m pip install -r scripts/requirements.txt
```

Success requires exit code `0`.

---

## 6. Start PgBouncer Port Forward

### Check port availability

Check if local port `6432` is already in use:

```bash
if ss -ltn | grep -q ':6432'; then
  echo "Port 6432 is already occupied" >&2
  exit 1
fi
```

### Clean up stale PID

If a port-forward PID file exists from a previous session, verify if the process is still running:

```bash
if [ -f /tmp/ct-rpg-pgbouncer-port-forward.pid ]; then
  PID=$(cat /tmp/ct-rpg-pgbouncer-port-forward.pid)
  if kill -0 "$PID" 2>/dev/null; then
    echo "Port-forward process $PID is already running" >&2
    exit 1
  else
    rm -f /tmp/ct-rpg-pgbouncer-port-forward.pid
  fi
fi
```

### Start port-forward

Start the forward in the background:

```bash
kubectl port-forward -n test svc/pgbouncer-svc 6432:6432 \
  > /tmp/ct-rpg-pgbouncer-port-forward.log 2>&1 &

echo $! > /tmp/ct-rpg-pgbouncer-port-forward.pid
```

### Wait for readiness

Wait for the port-forward using the bounded readiness script:

```bash
bash scripts/wait-for-port-forward.sh /tmp/ct-rpg-pgbouncer-port-forward.log 6432 30
```

The script polls the log file for `"Forwarding from"` and halts immediately if `"error:"` is detected.

Do not continue until the port-forward is confirmed ready with exit code `0`.

---

## 7. Verify PostgreSQL Connectivity

`ctlytics_test` is the existing maintenance database used for initial connectivity and administrative operations.

Run:

```bash
psql \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d ctlytics_test \
  -c "SELECT 1;"
```

Expected result:

```text
 ?column? 
----------
        1
(1 row)
```

Success requires exit code `0`. If connectivity fails, stop and report.

---

## 8. Verify or Create Target Database & PgBouncer Routing

### Idempotent database check

Check whether `rpg` already exists:

```bash
DB_EXISTS=$(psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d ctlytics_test -tAc "SELECT 1 FROM pg_database WHERE datname = 'rpg';")

if [ "$DB_EXISTS" = "1" ]; then
  echo "Target database 'rpg' already exists. Proceeding with idempotent migration."
else
  echo "Target database 'rpg' does not exist. Creating..."
  psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d ctlytics_test -c "CREATE DATABASE rpg;"
fi
```

Verify creation:

```bash
psql \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d ctlytics_test \
  -tAc "SELECT datname FROM pg_database WHERE datname = 'rpg';"
```

Expected output: `rpg`

### PgBouncer routing preflight check

After ensuring `rpg` exists, verify that PgBouncer routes connections to it:

```bash
psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d rpg -c "SELECT 1;"
```

If this fails with a PgBouncer `"no such database"` error:
- **Stop and report:** `"PgBouncer wildcard routing not enabled; requires operator action to configure PGBOUNCER_DATABASE='*' on the deployment."`
- **Do not modify Kubernetes:** Never run `kubectl set env` or attempt to reconfigure PgBouncer directly. Shared cluster configuration is operator-only.

---

## 9. Run RavenDB → PostgreSQL Migration

Execute the canonical migration command:

```bash
python3 scripts/migrate_all.py --all
```

The migration is idempotent (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT (id)` upserts) and is responsible for:
- Reading RavenDB source documents.
- Transforming source data into relational models.
- Creating PostgreSQL tables and applying indexes.
- Loading migrated records.
- Applying post-migration views (`01_student_fee_view.sql`).
- Applying post-migration triggers (`02_trigger.sql`).

Note: `migrate_all.py` fails hard (exit code 1) if post-migration SQL scripts cannot be found or fail during execution.

### Migration gate

Success requires:

```text
exit code == 0
```

If the migration fails:
- Stop immediately.
- Do not proceed to schema verification or parity checks.
- Report the command, exit code, and stdout/stderr.

---

## 10. Verify PostgreSQL Schema & Post-Migration Objects

Run post-migration object verification to ensure all views and triggers were applied successfully:

### Verify view
```bash
psql \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d rpg \
  -c "SELECT 1 FROM student_fee_summary_view LIMIT 1;"
```

### Verify trigger
```bash
psql \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d rpg \
  -tAc "SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_student_modified_on';"
```

Expected output: `1`

### Inspect tables
```bash
psql \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d rpg \
  -c "\dt"
```

Tables verified include `course`, `exam`, `fee`, `fee_transaction`, `institute`, `organization`, `persona`, `staff`, and `student`.

### Post-SQL gate

Success requires:
```text
exit code == 0
student_fee_summary_view exists and is queryable
trg_student_modified_on trigger count == 1
```

---

## 11. Verify RavenDB → PostgreSQL Data Parity

Run the comprehensive parity audit:

```bash
python3 scripts/verify_raven_to_postgres.py
```

The verifier writes a JSON report to `validation/exhaustive-parity-report-<timestamp>.json`.

Inspect the latest report file:

```bash
LATEST_REPORT=$(ls -t validation/exhaustive-parity-report-*.json | head -1)
echo "Latest report: $LATEST_REPORT"
grep '"overall_status"' "$LATEST_REPORT"
```

### Parity gate

Success requires:

```text
exit code == 0
overall_status == "PASS"
missing_in_pg_count == 0 (across all domains)
extra_in_pg_count == 0 (across all domains)
field_mismatches_count == 0 (across all domains)
```

Any discrepancy is a blocking failure. If parity fails:
- Stop immediately.
- Do not start the API or tests.
- Report the affected domain, counts, and relevant report output.

---

## 12. Start .NET 10 Web API

Start the Web API container in detached mode:

```bash
docker compose up -d --build rpg-api
```

Verify container status:

```bash
docker compose ps
```

The `rpg-api` container must have status `Up`.

---

## 13. Wait for API Readiness

Wait for the API health check using the bounded readiness script:

```bash
bash scripts/wait-for-api.sh http://localhost:5000 60
```

The script polls `http://localhost:5000/health` every 2 seconds for up to 60 seconds.

### API health gate

Success requires:

```text
HTTP status == 200
exit code == 0
```

If the health check fails or times out:
- Inspect logs: `docker compose logs rpg-api`
- Stop and report the failure.

---

## 14. Verify Representative API Request

Query the sample endpoint:

```bash
curl \
  --fail \
  --silent \
  --show-error \
  "http://localhost:5000/api/stu/student?limit=2"
```

Success requires:
```text
HTTP status == 200
curl exit code == 0
```

Swagger UI is available at `http://localhost:5000` for optional human inspection.

---

## 15. Run Automated Tests

Execute the automated test suite:

```bash
docker compose run --rm rpg-tests
```

> [!NOTE]
> `DbWriteTests` inserts and subsequently deletes a `fee_transaction` row during the test run. The `trg_fee_transaction_modified_on` trigger will leave audit trail records in `fee_transaction_audit`. This is expected behavior and not a data defect.

### Test gate

Success requires:

```text
exit code == 0
```

If tests fail, report the failing test names, error messages, and exit code.

---

## 16. Optional Database Inspection

Informational queries for diagnosis and manual inspection:

### Record counts
```sql
SELECT 'organization' AS entity, COUNT(*) FROM organization
UNION ALL SELECT 'institute', COUNT(*) FROM institute
UNION ALL SELECT 'student', COUNT(*) FROM student
UNION ALL SELECT 'fee', COUNT(*) FROM fee
UNION ALL SELECT 'fee_transaction', COUNT(*) FROM fee_transaction
UNION ALL SELECT 'persona', COUNT(*) FROM persona
UNION ALL SELECT 'course', COUNT(*) FROM course
UNION ALL SELECT 'staff', COUNT(*) FROM staff
UNION ALL SELECT 'exam', COUNT(*) FROM exam;
```

### View query
```sql
SELECT student_code, student_name, course_name, fee_name, amount, paid_amount, status
FROM student_fee_summary_view
LIMIT 5;
```

---

## 17. Optional pgAdmin Connection

For manual inspection:

```text
Host:                 localhost
Port:                 6432
Maintenance database: rpg
Username:             postgres
Password:             value of PG_PASSWORD
```

---

## 18. Completion Criteria & Final Report

The playbook is complete only when every gate passes:

```text
[PASS] Prerequisite gate
[PASS] Expected Kubernetes context verified
[PASS] PgBouncer reachable
[PASS] Target PostgreSQL database available
[PASS] Migration exit code = 0
[PASS] Post-SQL view and trigger verified
[PASS] RavenDB/PostgreSQL parity verification passed
[PASS] Missing records = 0, Extra records = 0, Field mismatches = 0
[PASS] API health = HTTP 200
[PASS] Automated tests = exit code 0
```

Required final report format:

```text
CT-RPG Local Verification

Preflight:       PASS
PostgreSQL:      PASS
Migration:       PASS
Post-SQL:        PASS
Parity:          PASS
API Health:      PASS
Tests:           PASS

Overall:         PASS
```

If any gate fails, overall status is `FAIL`.

---

## 19. Teardown

Teardown is optional and should not be run during a standard verification pass.

### Stop application containers
```bash
docker compose down
```

### Terminate background port-forward
```bash
if [ -f /tmp/ct-rpg-pgbouncer-port-forward.pid ]; then
  kill "$(cat /tmp/ct-rpg-pgbouncer-port-forward.pid)" 2>/dev/null || true
  rm -f /tmp/ct-rpg-pgbouncer-port-forward.pid
fi
```

### Drop target database (Explicit instruction only)
```bash
psql \
  -h "$PG_HOST" \
  -p "$PG_PORT" \
  -U "$PG_USER" \
  -d ctlytics_test \
  -c "DROP DATABASE rpg WITH (FORCE);"
```
