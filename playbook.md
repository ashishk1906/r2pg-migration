# Local Docker Playbook
## CT-RPG: RavenDB to PostgreSQL Migration & .NET 10 Web API

A streamlined, **Docker-based** onboarding playbook. Everything runs inside Docker containers—**zero local installations** of Python, .NET SDK, or PostgreSQL/psql are required on your host machine. All commands work identically in **PowerShell** and **Command Prompt (CMD)**.

---

## 1. Prerequisites

You only need two things on your system:

1. **Docker Desktop** (running with Linux containers)
2. **RavenDB Client Certificate** (`.pfx` file for secure RavenDB Cloud access)

> **No host runtimes required:** PostgreSQL, Python ETL, .NET 10 Web API, and xUnit test runners run entirely inside Docker containers.

---

## 2. Configuration Setup

All configuration parameters are centralized in a single root **`.env`** file.

### Step A: Create `.env` from Template

In **PowerShell** or **CMD**:

```cmd
cp .env.example .env
```
*(In CMD, you can also use: `copy .env.example .env`)*

#### Key Settings in `.env`

| Variable | Default Value | Description |
|---|---|---|
| `PG_PORT` | `15432` | Host port mapped to Docker PostgreSQL (`15432:5432` to avoid local 5432 conflicts) |
| `API_PORT` | `5000` | Host port for the .NET 10 Web API (`http://localhost:5000`) |
| `PG_DB` | `rpg` | Target PostgreSQL database name |
| `PG_USER` | `postgres` | Target PostgreSQL username |
| `PG_PASSWORD` | `<your-postgres-password>` | Target PostgreSQL password |
| `RAVEN_URL` | `https://<cluster>.ravendb.cloud` | RavenDB Cloud URL |
| `RAVEN_DB` | `BTL` | Source RavenDB database name |
| `RAVEN_CERT_FILE` | `certs/free.btl.client.certificate.pfx` | Path to the RavenDB client certificate relative to the repository root |

---

### Step B: Place RavenDB Client Certificate

If connecting to RavenDB Cloud over HTTPS, download the client certificate from the shared Google Drive:

**[Download RavenDB Client Certificate (.pfx)](https://drive.google.com/file/d/1tcdrDU3Q1zzWBqs-BS0_0PGGvXjR2INI/view?usp=drive_link)**

Copy the downloaded .pfx certificate into:

```text
scripts/
└── certs/
    └── <your-client-certificate>.pfx
```
*(All `.pfx` files in this directory are automatically ignored by Git.)*

---

## 3. Step-by-Step Docker Execution Flow

Run all steps in order from your project root in **PowerShell** or **CMD**:

---

### Step 1: Start PostgreSQL & .NET 10 Web API (Single Command)

Because `rpg-api` depends on `rpg-postgres` with `condition: service_healthy`, running this single command:
1. Automatically starts `rpg-postgres`.
2. Automatically creates the database (`rpg`), user, and password specified in `.env`.
3. Waits for the PostgreSQL health check to pass.
4. Builds and starts `rpg-api` connected to PostgreSQL.

```cmd
docker compose up -d --build rpg-api
```

#### Verify Database & API are Ready

Check that PostgreSQL is healthy and initialized:
```cmd
docker compose exec rpg-postgres psql -U postgres -d rpg -c "SELECT 1;"
```
> **Expected Output:** Returns `1` indicating the database is created and ready.

Check API health:
```cmd
curl.exe -s http://localhost:5000/health
```
> **Expected Output:** `{"status":"Healthy","database":"Connected",...}`

---

### Step 2: Run Data Migration via Docker

Runs the Python ETL container to extract data from RavenDB Cloud, create relational tables, convert documents, and set up views and triggers:

```cmd
docker compose run --rm rpg-migrator --all
```

> **Selective Module Migration:** To migrate only specific modules (e.g. students and fees):
> ```cmd
> docker compose run --rm rpg-migrator --module student,fees
> ```

#### Inspect Migrated Tables in Terminal

Inspect the PostgreSQL schema directly inside the container:

```cmd
docker compose exec rpg-postgres psql -U postgres -d rpg -c "\dt"
```
> **Expected Output:** Shows all 9 migrated tables (`student`, `fee`, `fee_transaction`, `course`, `institute`, `organization`, `persona`, `staff`, `exam`).

---

### Step 3: Verify Data Parity via Docker

Run the automated parity verification audit inside the Docker container to ensure 100% field-by-field parity between RavenDB source documents and PostgreSQL records:

```cmd
docker compose run --rm --entrypoint python rpg-migrator verify_raven_to_postgres.py
```
> **Expected Output:** Zero missing, zero extra, zero mismatched records (`Overall: PASS`).

---

### Step 4: Verify REST APIs & Swagger UI

Open **Swagger UI** in your browser: 👉 **[http://localhost:5000](http://localhost:5000)**

Or test the live API endpoints directly from PowerShell / CMD:

```cmd
# 1. CampusTrack Students endpoint (GET /api/stu/student):
curl.exe -s "http://localhost:5000/api/stu/student?limit=2"

# 2. CampusTrack Fee Transactions endpoint (GET /api/feeTx):
curl.exe -s "http://localhost:5000/api/feeTx?limit=2"

# 3. Insert Fee Transaction (POST /api/feeTx write test with audit trigger):
curl.exe -s -X POST "http://localhost:5000/api/feeTx" -H "Content-Type: application/json" -d "{\"studentId\": \"cc93c106-82ea-4610-9873-3db87f1307c6\", \"amount\": 500.00, \"status\": \"Active\", \"feeId\": \"a7e2851c-2321-4adc-993a-387deefee3a8\", \"refNo\": \"DEMO-CURL-01\"}"
```

---

### Step 5: Run Automated Tests via Docker

Run the entire xUnit integration and unit test suite inside the official .NET 10 test container:

```cmd
docker compose run --rm rpg-tests
```
> **Expected Output:** All unit and integration tests pass with exit code `0`. Container self-terminates (`--rm`).

---

## 4. Database Verification & SQL Inspection (Docker)

Run verification SQL queries directly against the PostgreSQL container using `docker compose exec`:

### 1. Verify Entity Record Counts

```cmd
docker compose exec rpg-postgres psql -U postgres -d rpg -c "SELECT 'organization' AS entity, COUNT(*) FROM organization UNION ALL SELECT 'institute', COUNT(*) FROM institute UNION ALL SELECT 'student', COUNT(*) FROM student UNION ALL SELECT 'fee', COUNT(*) FROM fee UNION ALL SELECT 'fee_transaction', COUNT(*) FROM fee_transaction UNION ALL SELECT 'persona', COUNT(*) FROM persona UNION ALL SELECT 'course', COUNT(*) FROM course UNION ALL SELECT 'staff', COUNT(*) FROM staff UNION ALL SELECT 'exam', COUNT(*) FROM exam;"
```

### 2. Verify Cross-Module View (`student_fee_summary_view`)

```cmd
docker compose exec rpg-postgres psql -U postgres -d rpg -c "SELECT student_code, student_name, course_name, fee_name, amount, paid_amount, status FROM student_fee_summary_view LIMIT 10;"
```

### 3. Verify PostgreSQL Trigger Audit Trail (`fee_transaction_audit`)

```cmd
docker compose exec rpg-postgres psql -U postgres -d rpg -c "SELECT tx_no, student_id, amount, status, action, logged_at FROM fee_transaction_audit ORDER BY logged_at DESC LIMIT 5;"
```

---

## 5. Teardown & Clean Reset

To stop all running containers:
```cmd
docker compose down
```

To stop containers and wipe the database volume for a completely fresh start:
```cmd
docker compose down -v
```
