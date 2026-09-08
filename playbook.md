# Local Testing & Onboarding Playbook
## CT-RPG: RavenDB to PostgreSQL Migration & .NET 10 Web API

A streamlined guide for developers to configure credentials, connect to the **Kubernetes SVC PostgreSQL cluster via PgBouncer port-forward**, create the target database, run migrations, verify 100% data parity, and execute tests.

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
- **Docker Desktop** (Running with Linux containers)
- **RavenDB Client Certificate** (`.pfx` file)

### Install Dependencies
Install all required Python dependencies for running migrations and parity audits:
```bash
pip install -r scripts/requirements.txt
```

---

## 2. Configuration Setup

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
| `RAVEN_URL` | `https://a.free.btl.ravendb.cloud` | RavenDB instance URL |
| `RAVEN_DB` | `BTL` | Source RavenDB database name |
| `RAVEN_CERT_FILE` | `certs/free.btl.client.certificate.pfx` | Client certificate path inside `scripts/certs/` |

### Step B: Place RavenDB Certificate
Download the client certificate from **[Google Drive](https://drive.google.com/file/d/1tcdrDU3Q1zzWBqs-BS0_0PGGvXjR2INI/view?usp=drive_link)** and place it into:
```text
scripts/certs/<your-client-certificate>.pfx
```
*(All `.pfx` certificate files in this directory are automatically ignored by Git).*

---

## 3. Kubernetes PostgreSQL Setup (via PgBouncer)

### Step 1: Enable Wildcard Database Routing on PgBouncer
This is a **one-time setup** so PgBouncer accepts any database (including `rpg`):
```bash
kubectl set env deployment/pgbouncer -n test PGBOUNCER_DATABASE="*"
kubectl rollout status deployment/pgbouncer -n test
```

### Step 2: Start Port-Forwarding
Run this in a **separate terminal** and keep it open:
```bash
kubectl port-forward -n test svc/pgbouncer-svc 6432:6432
```

> [!NOTE]
> If you get this error:
> ```
> error: error upgrading connection: unable to upgrade connection: error dialing backend: No agent available
> ```
> Wait a few minutes and run the command again.

### Step 3: Create the `rpg` Database
Open a **new terminal** and run:
```bash
psql -h localhost -p 6432 -U postgres -d ctlytics_test -c "CREATE DATABASE rpg;"
```

Verify the `rpg` database was created successfully:
```bash
psql -h localhost -p 6432 -U postgres -d ctlytics_test -c "SELECT datname FROM pg_database WHERE datname = 'rpg';"
```
Expected output:
```
 datname
---------
 rpg
(1 row)
```
Confirmed — `rpg` database is created. Move to the next step.

---

## 4. Run Migration & Parity Verification

### Step 1: Run Data Migration
Runs the Python ETL pipeline to create all tables, transform documents from RavenDB, and apply indexes, views, and triggers into the `rpg` database:
```bash
# Run all 6 modules:
python scripts/migrate_all.py --all
```
> **Selective Migration**: To run only specific modules:
> `docker compose run --rm rpg-migrator --module student,fees`

After migration completes, verify the tables were created in the `rpg` database:
```bash
psql -h localhost -p 6432 -U postgres -d rpg -c "\dt"
```
Expected output — you should see all 9 tables:
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
   - **Port**: `6432`
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

### Step 1: Stop Running Containers
```bash
docker compose down
```

### Step 2: Delete `rpg` Database (Optional / Reset)
To delete the newly created `rpg` database from terminal, connect to `ctlytics_test` and force-drop it:
```bash
psql -h localhost -p 6432 -U postgres -d ctlytics_test -c "DROP DATABASE rpg WITH (FORCE);"
```

Verify the database has been deleted:
```bash
psql -h localhost -p 6432 -U postgres -d ctlytics_test -c "SELECT datname FROM pg_database WHERE datname = 'rpg';"
```
Expected output:
```
 datname 
---------
(0 rows)
```
*(Confirmed — `rpg` database is deleted).*

