---
title: "CT-RPG Agent Runbook"
project: "CT-RPG"
purpose: "Deterministic RavenDB to PostgreSQL migration and .NET 10 Web API verification"
version: "1.0"

execution:
  intended_for:
    - coding-agent
  working_directory: "repository-root"
  shell: "bash"
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
      requirement: "Configured with access to the expected CT test cluster"
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
      requirement: "Docker Compose v2 via docker compose"

  kubernetes:
    required: true
    expected_context: "do-blr1-k8s-1-22-8-do-1-blr1-1655977229480"
    namespace: "test"
    services:
      - "pgbouncer-svc"
      - "postgresql"
    context_must_be_verified: true

  postgres:
    maintenance_database: "postgres"
    target_database: "rpg"
    admin_port: 5432
    pgbouncer_port: 6432
    required_role: "postgres"
    required_privileges:
      - "CONNECT to postgres"
      - "CREATE DATABASE for initial setup"
      - "Schema and data privileges required by migration scripts"

  ravendb:
    required: true
    certificate_required: true

  files:
    - path: ".env"
      required: true
      secret: true
    - path: "certs/free.btl.client.certificate.pfx"
      required: true
      secret: true

  environment:
    required_variables:
      - "EXPECTED_K8S_CONTEXT"
      - "PG_HOST"
      - "PG_PORT"
      - "PG_ADMIN_HOST"
      - "PG_ADMIN_PORT"
      - "PG_MAINTENANCE_DB"
      - "PG_DB"
      - "PG_USER"
      - "PG_PASSWORD"
      - "API_PORT"
      - "RAVEN_URL"
      - "RAVEN_DB"
      - "RAVEN_CERT_FILE"

commands:
  wrapper: "bash agent-runbook/scripts/local-onboard.sh"
  preflight: "bash agent-runbook/scripts/verify-prerequisites.sh"
  migrate: "python scripts/migrate_all.py --all"
  verify_parity: "python scripts/verify_raven_to_postgres.py"
  start_api: "docker compose up -d --build rpg-api"
  run_tests: "docker compose run --rm rpg-tests"

safety:
  never_commit:
    - ".env"
    - "*.pfx"
    - "certs/*"
    - "scripts/certs/*"
    - ".ct-rpg-pgpass"

  shared_environment_mutation:
    allowed: false
    note: "Do not modify Kubernetes Deployments, Services, ConfigMaps, Secrets, or PgBouncer configuration."

  database_reset:
    allowed_by_default: false
    requires_explicit_instruction: true

  database_drop:
    allowed_by_default: false
    requires_explicit_instruction: true

agent_execution_rules:
  - "Run from the repository root."
  - "Run only the canonical wrapper; do not duplicate its manual steps."
  - "Do not modify shared Kubernetes resources."
  - "Do not request interactive input."
  - "Do not print passwords, .env contents, RavenDB credentials, or certificate contents."
  - "Verify the configured Kubernetes context before using Kubernetes."
  - "Treat missing credentials, tools, certificates, or cluster resources as blocking preconditions."
  - "Reuse an existing rpg database; do not drop, reset, or recreate it unless explicitly instructed."
  - "Stop immediately on any failed command or verification gate."
  - "Do not bypass migration, post-SQL, parity, API, or test failures."
  - "Report the failed step, exact command, exit code, and relevant non-secret stderr/stdout."
  - "Clean up only processes and containers started by the wrapper."

pgbouncer:
  wildcard_routing_required: true
  operator_action_only: true
  failure_message: "PgBouncer wildcard routing is not enabled; requires operator action."

gates:
  preflight:
    success:
      - "exit_code == 0"
      - "required tools found"
      - "expected Kubernetes context active"
      - "namespace test and services pgbouncer-svc/postgresql exist"
      - ".env and certificate exist"
      - "required variables are non-empty"

  postgres:
    success:
      - "direct connection to postgres succeeds"
      - "target rpg exists or is created"
      - "connection to rpg through PgBouncer succeeds"

  migration:
    success:
      - "exit_code == 0"

  post_sql:
    success:
      - "student_fee_summary_view is queryable"
      - "trg_student_modified_on exists"

  parity:
    success:
      - "exit_code == 0"
      - "newest validation/exhaustive-parity-report-*.json has overall_status PASS"
      - "sum of missing_in_pg_count == 0"
      - "sum of extra_in_pg_count == 0"
      - "sum of field_mismatches_count == 0"

  api_health:
    success:
      - "health endpoint returns HTTP 200"
      - "sample API request succeeds"

  tests:
    success:
      - "docker compose run --rm rpg-tests exits 0"

success_criteria:
  - "Every gate passes in order."
  - "No interactive input or secret output occurs."
  - "No shared Kubernetes resource is modified."
  - "Port-forwards are cleaned up."
  - "The final report has Overall: PASS."
---

# CT-RPG Agent Runbook

This is the deterministic agent contract for the human workflow in `playbook.md`. The implementation is in `agent-runbook/scripts`; the agent must not manually reinterpret the human steps.

## Required Precondition

The repository must contain `.env` with the real credentials and:

```dotenv
EXPECTED_K8S_CONTEXT=do-blr1-k8s-1-22-8-do-1-blr1-1655977229480
PG_HOST=localhost
PG_PORT=6432
PG_ADMIN_HOST=localhost
PG_ADMIN_PORT=5432
PG_MAINTENANCE_DB=postgres
PG_DB=rpg
PG_USER=postgres
PG_PASSWORD=<configured-secret>
API_PORT=5000
RAVEN_URL=https://a.free.btl.ravendb.cloud
RAVEN_DB=BTL
RAVEN_CERT_FILE=certs/free.btl.client.certificate.pfx
```

The RavenDB certificate must already exist at `certs/free.btl.client.certificate.pfx`. The agent must not download credentials, request passwords, or print secret values.

## Canonical Command

From the repository root, execute exactly once:

```bash
bash agent-runbook/scripts/local-onboard.sh
```

Do not execute the manual commands from `playbook.md` in addition to the wrapper. The wrapper owns environment bootstrap, dependency installation, context selection, prerequisite checks, port-forward processes, readiness waits, database setup, migration, SQL verification, parity, API checks, tests, cleanup, and final reporting.

## Execution Order

The wrapper executes these steps in order:

1. Load `.env` and prepare the local Bash/Python/PostgreSQL environment.
2. Verify required tools, Python 3.12+, Docker Compose, certificate, `.env`, Kubernetes context, namespace, and services.
3. Start and wait for the PgBouncer forward from local port `6432` to service port `6432`.
4. Start and wait for the direct PostgreSQL forward from local port `5432` to service port `5432`.
5. Connect directly to the maintenance database `postgres` without interactive password input.
6. Reuse `rpg` if it exists; otherwise create it idempotently.
7. Verify that PgBouncer routes connections to `rpg`; stop if wildcard routing is unavailable.
8. Run `python scripts/migrate_all.py --all`.
9. Verify `student_fee_summary_view` and `trg_student_modified_on`.
10. Run parity and require a PASS report with zero missing, extra, and field-mismatched records.
11. Start the API, wait for HTTP 200 from `/health`, and verify the sample endpoint.
12. Run `docker compose run --rm rpg-tests` and require exit code 0.
13. Stop only wrapper-managed port-forwards and print the final report.

## Failure Policy

On the first failed command or gate, stop. Report the step, exact command, exit code, and relevant non-secret output. Do not continue to later gates, modify shared Kubernetes resources, or perform destructive database operations.

## Expected Success Output

```text
Preflight:       PASS
PostgreSQL:      PASS
Migration:       PASS
Post-SQL:        PASS
Parity:          PASS
API Health:      PASS
Tests:           PASS

Overall:         PASS
```
