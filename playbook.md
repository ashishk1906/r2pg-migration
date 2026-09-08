# Local Testing & Onboarding Playbook
## CT-RPG: RavenDB to PostgreSQL Migration & .NET 10 Web API

A streamlined guide for developers to configure credentials, choose a database target (Local Docker or Kubernetes PgBouncer), run migrations, verify 100% data parity, and execute tests.

---

## 1. Clone & Prerequisites

### Clone Repository
```bash
git clone https://github.com/ashishk1906/r2pg-migration.git
cd r2pg-migration
```

### Prerequisites
- **Docker Desktop** (Running with Linux containers)
- **RavenDB Client Certificate** (`.pfx` file)
- *(Optional)* Python 3.12 & .NET 10 SDK (only needed if running directly on host without Docker)

---

## 2. Configuration Setup

### Step A: Create `.env`
```bash
cp .env.example .env
```

| Variable | Local Docker (Default) | Kubernetes (PgBouncer) | Description |
|---|---|---|---|
| `PG_HOST` | `localhost` | `localhost` | PostgreSQL host |
| `PG_PORT` | `15432` | `6432` | PostgreSQL port |
| `PG_DB` | `rpg` | `rpg` | Database name |
| `PG_USER` | `postgres` | `postgres` | Username |
| `PG_PASSWORD` | `postgres` | `<your-postgres-password>` | Target PostgreSQL password |
| `RAVEN_URL` | `https://a.free.btl.ravendb.cloud` | `https://a.free.btl.ravendb.cloud` | RavenDB instance URL |
| `RAVEN_DB` | `BTL` | `BTL` | Source RavenDB database name |
| `RAVEN_CERT_FILE` | `certs/free.btl.client.certificate.pfx` | `certs/free.btl.client.certificate.pfx` | Client certificate path inside `scripts/certs/` |

### Step B: Place RavenDB Certificate
Download the client certificate from **[Google Drive](https://drive.google.com/file/d/1tcdrDU3Q1zzWBqs-BS0_0PGGvXjR2INI/view?usp=drive_link)** and place it into:
```text
scripts/certs/<your-client-certificate>.pfx
```
*(All `.pfx` certificate files in this directory are automatically ignored by Git).*

---

## 3. Database Target (Choose Option A or B)

### Option A: Local Docker PostgreSQL (Zero-Config)
Start the local PostgreSQL container on port `15432`:
```bash
docker compose --profile local-db up -d rpg-postgres
```

### Option B: Remote Kubernetes PostgreSQL (via PgBouncer)
1. **Enable wildcard routing** on PgBouncer (one-time setup so it accepts the `rpg` database):
   ```bash
   kubectl set env deployment/pgbouncer -n test PGBOUNCER_DATABASE="*"
   kubectl rollout status deployment/pgbouncer -n test
   ```
2. **Start port-forwarding** in a separate terminal:
   ```bash
   kubectl port-forward svc/pgbouncer-svc -n test 6432:6432
   ```
   *(Ensure `.env` has `PG_PORT=6432` and `PG_PASSWORD=<your-postgres-password>`)*.

---

## 4. Run Migration & Parity Verification

### Step 1: Run Data Migration
Runs the Python ETL pipeline to create base tables, transform documents, and apply indexes, views, and triggers:
```bash
# Run all 6 modules via Docker:
docker compose run --rm rpg-migrator --all

# (Or run directly on host: python scripts/migrate_all.py --all)
```
> **Selective Migration**: To run only specific modules:  
> `docker compose run --rm rpg-migrator --module student,fees`

### Step 2: Verify 100% Data Parity
Audit all 9 domains field-by-field against RavenDB:
```bash
python scripts/verify_raven_to_postgres.py
```

---

## 5. Start Web API & Run Tests

### Step 1: Start .NET 10 Web API
```bash
docker compose up -d --build rpg-api
```
Open **Swagger UI** in your browser: 👉 **[http://localhost:5000](http://localhost:5000)**

Quick API check in terminal:
```bash
curl -s http://localhost:5000/health
curl -s "http://localhost:5000/api/stu/student?limit=2"
```

### Step 2: Run Automated Tests
Execute all xUnit integration & unit tests inside the .NET 10 container:
```bash
docker compose run --rm rpg-tests
```

---

## 6. Database Inspection (pgAdmin & SQL)

### Connect pgAdmin:
1. In pgAdmin, right-click **Servers** ➔ **Register** ➔ **Server...**
2. In **Connection** tab:
   - **Host name/address**: `localhost`
   - **Port**: `15432` (Option A) or `6432` (Option B)
   - **Maintenance database**: `rpg`
   - **Username**: `postgres`
   - **Password**: `<your-postgres-password>`

### Verification SQL Queries:
Run in pgAdmin Query Tool or `psql` to verify data integrity:

```sql
-- 1. Verify record counts across all 9 tables:
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
```bash
# Stop running containers:
docker compose down

# Wipe local Docker database volume if needed:
docker compose down -v
```
