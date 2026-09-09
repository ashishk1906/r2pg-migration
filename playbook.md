# Local Testing & Onboarding Playbook
## CT-RPG: RavenDB to PostgreSQL Migration & .NET 10 Web API

A guide for developers to configure credentials, connect to the Kubernetes PostgreSQL cluster via PgBouncer port-forward, create the target database, run migrations, verify data parity, and execute tests.

---

## Onboarding Success Contract

Onboarding is complete when **all four gates pass in order**:

| Gate | Command | Pass Condition |
|---|---|---|
| **1 — Connectivity** | `psql ... -c "SELECT 1;"` | Returns `1` with exit code 0 |
| **2 — Migration** | `python scripts/migrate_all.py --all` | Exit code 0; all tables present in `\dt` |
| **3 — Parity** | `python scripts/verify_raven_to_postgres.py` | Exit code 0; **zero** missing, extra, or mismatched records |
| **4 — API & Tests** | `curl .../health` + `docker compose run --rm rpg-tests` | HTTP 200; all tests pass with exit code 0 |

Do not advance to the next gate until the current one passes.

---

## 1. Clone & Prerequisites

### Clone Repository
```bash
git clone https://github.com/ashishk1906/r2pg-migration.git
cd r2pg-migration
```

### Prerequisites
- **kubectl** configured with access to the cluster
- **psql** (PostgreSQL CLI client)
- **Python 3.12+**
- **Docker Desktop** (running with Linux containers)
- **RavenDB Client Certificate** (`.pfx` file)

### Install Python Dependencies
Install all required dependencies for running migrations and parity audits:
```bash
pip install -r scripts/requirements.txt
```

---

## 2. Configuration Setup

> [!CAUTION]
> **Never commit secrets to version control.**
> The following must remain local and are already covered by `.gitignore`:
> - `.env` — contains passwords and connection strings
> - `certs/*.pfx` — RavenDB client certificates
> - Any file containing passwords, API keys, or tokens
>
> If you accidentally commit a secret, treat it as **compromised** and rotate it immediately.

### Step A: Create `.env`
```bash
cp .env.example .env
```

Update `.env` with these values for Kubernetes:

| Variable | Value | Description |
|---|---|---|
| `PG_HOST` | `localhost` | PostgreSQL host (via port-forward) |
| `PG_PORT` | `6432` | PgBouncer port |
| `PG_DB` | `rpg` | Target PostgreSQL database name |
| `PG_USER` | `postgres` | Username |
| `PG_PASSWORD` | `<your-postgres-password>` | PostgreSQL password |
| `API_PORT` | `5000` | Host port for the Web API container |
| `RAVEN_URL` | `https://a.free.btl.ravendb.cloud` | RavenDB instance URL |
| `RAVEN_DB` | `BTL` | Source RavenDB database name |
| `RAVEN_CERT_FILE` | `certs/free.btl.client.certificate.pfx` | Certificate path — **relative to the repo root** |

### Step B: Place RavenDB Certificate

> [!NOTE]
> `RAVEN_CERT_FILE` is resolved **relative to the repo root** — the directory from which you run migration commands. The default value `certs/free.btl.client.certificate.pfx` means the file must be placed at `<repo-root>/certs/<your-certificate>.pfx`. Do not place it inside `scripts/`.

Download the client certificate from **[Google Drive](https://drive.google.com/file/d/1tcdrDU3Q1zzWBqs-BS0_0PGGvXjR2INI/view?usp=drive_link)** and place it at:
```text
certs/<your-client-certificate>.pfx
```
*(All `.pfx` files in `certs/` are automatically ignored by Git.)*

---

## 3. Kubernetes PostgreSQL Setup (via PgBouncer)

> [!IMPORTANT]
> **Cluster prerequisite — not an onboarding step:** PgBouncer must already be provisioned with wildcard routing (`PGBOUNCER_DATABASE=*`). This is an environment/bootstrap responsibility configured by the platform team during cluster setup. Individual developers do not modify PgBouncer configuration during onboarding.

> [!NOTE]
> **DB administration uses a direct PostgreSQL connection (not PgBouncer).** DDL commands (`CREATE DATABASE`, `DROP DATABASE`) run through **Terminal C: postgres-admin** on port `5432`, which port-forwards directly to `svc/postgresql`. PgBouncer (port `6432`) is reserved for application connectivity and migration scripts only. `ctlytics_test` is used as the superuser maintenance database because `rpg` does not exist yet at this point.

### Step 1: Start Port-Forwarding
You need two port-forwards running simultaneously in separate terminals.

**Terminal A: port-forward** — PgBouncer for app connectivity and migration scripts:
```bash
kubectl port-forward -n test svc/pgbouncer-svc 6432:6432
```

**Terminal C: postgres-admin** — Direct PostgreSQL for DB administration (DDL only):
```bash
kubectl port-forward -n test svc/postgresql 5432:5432
```

> [!NOTE]
> If either port-forward fails with:
> ```
> error: error upgrading connection: unable to upgrade connection: error dialing backend: No agent available
> ```
> Wait a few minutes and run the command again. Keep both terminals open for the entire session.

### Step 2: Verify Connectivity (Gate 1)
In **Terminal B: repository commands**, confirm the cluster is reachable via both connections:
```bash
# PgBouncer (app connectivity)
psql -h localhost -p 6432 -U postgres -d ctlytics_test -c "SELECT 1;"

# Direct PostgreSQL (admin)
psql -h localhost -p 5432 -U postgres -d ctlytics_test -c "SELECT 1;"
```
Expected result for each:
```
 ?column?
----------
        1
(1 row)
```
**Gate 1 passed** — both connections are reachable. Proceed to create the target database.

### Step 3: Create the `rpg` Database
Run DDL directly against PostgreSQL (port `5432`) — not through PgBouncer:
```bash
psql -h localhost -p 5432 -U postgres -d ctlytics_test -c "CREATE DATABASE rpg;"
```

Verify the database was created:
```bash
psql -h localhost -p 5432 -U postgres -d ctlytics_test -c "SELECT datname FROM pg_database WHERE datname = 'rpg';"
```
Expected output:
```
 datname
---------
 rpg
(1 row)
```
Expected result — `rpg` database is created. Move to the next step.

---

## 4. Run Migration & Parity Verification

> [!IMPORTANT]
> **Canonical execution path: local Python.** All migration and parity verification commands run locally from **Terminal B: repository commands** using `python scripts/...`. Docker Compose is used only for the Web API and automated tests (Section 5). Do not mix execution paths.

### Step 1: Run Data Migration (Gate 2)
```bash
python scripts/migrate_all.py --all
```

This runs the full ETL pipeline: creates all tables, transforms documents from RavenDB, and applies indexes, views, and triggers into the `rpg` database.

> [!NOTE]
> **Selective migration:** To migrate only specific domains, pass `--module`:
> ```bash
> python scripts/migrate_all.py --module student,fees
> ```

**Gate 2 pass condition:** Command exits with code 0. Verify tables were created:
```bash
psql -h localhost -p 6432 -U postgres -d rpg -c "\dt"
```
Expected output — all tables present:
```
          List of relations
 Schema |       Name        | Type  |  Owner
--------+-------------------+-------+----------
 public | course            | table | postgres
 public | exam              | table | postgres
 public | fee               | table | postgres
 public | fee_transaction   | table | postgres
 public | institute         | table | postgres
 public | organization      | table | postgres
 public | persona           | table | postgres
 public | staff             | table | postgres
 public | student           | table | postgres
```

### Step 2: Verify Data Parity (Gate 3)
```bash
python scripts/verify_raven_to_postgres.py
```

**Gate 3 pass condition:** Command exits with code 0 and reports **zero missing, zero extra, and zero mismatched records** across all domains. Any non-zero discrepancy is a failure — do not proceed to Section 5 until parity is clean.

---

## 5. Start Web API & Run Tests

### Step 1: Start .NET 10 Web API
```bash
docker compose up -d --build rpg-api
```
Open **Swagger UI** in your browser: 👉 **[http://localhost:5000](http://localhost:5000)**

**Gate 4a pass condition:** Health endpoint returns HTTP 200:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health
```
Expected result: `200`

Quick data check:
```bash
curl -s "http://localhost:5000/api/stu/student?limit=2"
```

### Step 2: Run Automated Tests (Gate 4b)
```bash
docker compose run --rm rpg-tests
```

**Gate 4b pass condition:** All xUnit integration and unit tests pass; container exits with code 0.

---

## 6. Database Inspection (pgAdmin & SQL)

### Connect pgAdmin:
1. In pgAdmin, right-click **Servers** ➔ **Register** ➔ **Server...**
2. In **Connection** tab:
   - **Host name/address**: `localhost`
   - **Port**: `6432`
   - **Maintenance database**: `rpg`
   - **Username**: `postgres`
   - **Password**: `<your-postgres-password>`

### Verification SQL Queries:
Run in pgAdmin Query Tool or `psql` to verify data integrity:

```sql
-- 1. Verify record counts across all tables:
SELECT 'organization' AS entity, COUNT(*) FROM organization
UNION ALL SELECT 'institute', COUNT(*) FROM institute
UNION ALL SELECT 'student', COUNT(*) FROM student
UNION ALL SELECT 'fee', COUNT(*) FROM fee
UNION ALL SELECT 'fee_transaction', COUNT(*) FROM fee_transaction
UNION ALL SELECT 'persona', COUNT(*) FROM persona
UNION ALL SELECT 'course', COUNT(*) FROM course
UNION ALL SELECT 'staff', COUNT(*) FROM staff
UNION ALL SELECT 'exam', COUNT(*) FROM exam;

-- 2. Verify cross-module view:
SELECT student_code, student_name, course_name, fee_name, amount, paid_amount, status
FROM student_fee_summary_view
LIMIT 10;

-- 3. Verify PostgreSQL trigger audit trail:
SELECT tx_no, student_id, amount, status, action, logged_at
FROM fee_transaction_audit
ORDER BY logged_at DESC
LIMIT 5;
```

---

## 7. Teardown

### Step 1: Stop Running Containers
```bash
docker compose down
```

### Step 2: Delete `rpg` Database (Optional / Reset)
Run DDL directly against PostgreSQL (port `5432`) — not through PgBouncer:
```bash
psql -h localhost -p 5432 -U postgres -d ctlytics_test -c "DROP DATABASE rpg WITH (FORCE);"
```

Verify the database has been deleted:
```bash
psql -h localhost -p 5432 -U postgres -d ctlytics_test -c "SELECT datname FROM pg_database WHERE datname = 'rpg';"
```
Expected output:
```
 datname
---------
(0 rows)
```
*(Expected result — `rpg` database is deleted).*
