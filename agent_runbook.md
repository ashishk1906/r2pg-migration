---
runbook: "CT-RPG Docker Migration & API Verification"
version: "2.1.0"
execution_mode: "docker-canonical"
interactive: false
stop_on_error: true
terminal: "host-terminal"
safety:
  never_commit:
    - ".env"
    - "*.pfx"
    - "scripts/certs/*"
gates:
  - step: 0
    name: "Preflight Verification"
    command: "bash scripts/verify-prerequisites.sh"
    criteria: "Exit code 0"
  - step: 1
    name: "Start PostgreSQL & Web API"
    command: "docker compose up -d --build rpg-api"
    criteria: "PostgreSQL returns 1; API health returns HTTP 200 with status Healthy"
  - step: 2
    name: "Run Data Migration"
    command: "docker compose run --rm rpg-migrator --all"
    criteria: "Exit code 0; all tables migrated and views/triggers applied"
  - step: 3
    name: "Verify Data Parity"
    command: "docker compose run --rm --entrypoint python rpg-migrator verify_raven_to_postgres.py"
    criteria: "Exit code 0; overall_status PASS with 0 missing, 0 extra, 0 mismatches"
  - step: 4
    name: "Verify REST APIs"
    command: "curl -s -f http://localhost:5000/api/stu/student?limit=2"
    criteria: "HTTP 200; valid JSON array returned"
  - step: 5
    name: "Run Automated Tests"
    command: "docker compose run --rm rpg-tests"
    criteria: "Exit code 0; all xUnit tests pass"
---

# Agent Runbook: CT-RPG Docker Migration & Verification

Execute all steps in order from the repository root. Everything runs inside Docker containers—no local installations of Python, .NET, or PostgreSQL are needed.

---

## Agent Execution Rules

1. **Non-Interactive**: Execute all commands non-interactively without user prompts.
2. **Stop on Error**: If any step or assertion fails, stop execution immediately and report the error.
3. **No Secrets in Git**: Never commit `.env`, `*.pfx`, or files in `scripts/certs/`. Never echo secrets to terminal logs.
4. **All Docker**: Do not run local Python, psql, or .NET on the host. Run everything through Docker Compose.

---

## Step 0: Preflight Verification

Verify that Docker, Compose v2, `.env`, and the RavenDB certificate are present.

```bash
bash scripts/verify-prerequisites.sh
```

- **Expected result:** Exit code `0` and `[PREFLIGHT PASS] All checks passed`.

---

## Step 1: Start PostgreSQL & .NET 10 Web API

Starts PostgreSQL (auto-creating the `rpg` database) and builds/starts the API:

```bash
docker compose up -d --build rpg-api
```

### Verify Readiness:
1. **Check Database:**
   ```bash
   docker compose exec rpg-postgres psql -U postgres -d rpg -c "SELECT 1;"
   ```
   - **Expected result:** Returns `1` and exit code `0`.

2. **Check API Health:**
   ```bash
   curl -s -f http://localhost:5000/health
   ```
   - **Expected result:** HTTP `200` with `{"status":"Healthy","database":"Connected"}`.

---

## Step 2: Run Data Migration via Docker

Runs the Python ETL container to migrate all entities from RavenDB to PostgreSQL and apply post-migration views and triggers:

```bash
docker compose run --rm rpg-migrator --all
```

- **Expected result:** Exit code `0` and `All migrations and post-migration scripts completed successfully`.

### Verify Migrated Tables:
```bash
docker compose exec rpg-postgres psql -U postgres -d rpg -c "\dt"
```
- **Expected result:** Lists the 9 migrated tables (`course`, `exam`, `fee`, `fee_transaction`, `institute`, `organization`, `persona`, `staff`, `student`).

---

## Step 3: Verify Data Parity via Docker

Runs the automated parity audit comparing RavenDB source documents against PostgreSQL records:

```bash
docker compose run --rm --entrypoint python rpg-migrator verify_raven_to_postgres.py
```

- **Expected result:** Exit code `0`, `Overall Status: PASS`, and 0 missing, 0 extra, 0 mismatched records.

---

## Step 4: Verify REST APIs

Test the live API endpoints:

1. **Get Students:**
   ```bash
   curl -s -f "http://localhost:5000/api/stu/student?limit=2"
   ```
   - **Expected result:** HTTP `200` with JSON student records.

2. **Get Fee Transactions:**
   ```bash
   curl -s -f "http://localhost:5000/api/feeTx?limit=2"
   ```
   - **Expected result:** HTTP `200` with JSON fee transaction records.

3. **Insert Fee Transaction (Write Test):**
   ```bash
   curl -s -f -X POST "http://localhost:5000/api/feeTx" \
     -H "Content-Type: application/json" \
     -d "{\"studentId\": \"cc93c106-82ea-4610-9873-3db87f1307c6\", \"amount\": 500.00, \"status\": \"Active\", \"feeId\": \"a7e2851c-2321-4adc-993a-387deefee3a8\", \"refNo\": \"AGENT-DEMO-01\"}"
   ```
   - **Expected result:** HTTP `200` or `201` with created transaction JSON.

---

## Step 5: Run Automated Tests via Docker

Run the entire xUnit integration and unit test suite inside the test container:

```bash
docker compose run --rm rpg-tests
```

- **Expected result:** Exit code `0`, all tests pass (`Passed! - Failed: 0, Passed: X, Skipped: 0`).

---

## Step 6: Teardown & Reset (When Done)

- **Stop containers (preserve data):**
  ```bash
  docker compose down
  ```

- **Clean reset (wipe database volume):**
  ```bash
  docker compose down -v
  ```

---

## Summary Contract

When all steps succeed, report:

```markdown
### Onboarding Status: SUCCESS
- Step 0 (Preflight): PASS
- Step 1 (Services Ready): PASS
- Step 2 (Migration): PASS
- Step 3 (Parity Audit): PASS
- Step 4 (API Verification): PASS
- Step 5 (Automated Tests): PASS
```
