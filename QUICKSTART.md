# 🚀 Quickstart Guide: From Zero to Migration & Showcase UI

Welcome! This guide is written from the perspective of someone opening this project for the very first time. It walks you through each step sequentially so you can configure, migrate, and inspect the live data in under 5 minutes.

---

## 🎯 The Workflow at a Glance

```text
[Step 1: Config] ➔ [Step 2: Start DB] ➔ [Step 3: Run Migration] ➔ [Step 4: Launch UI] ➔ [Step 5: View & Verify]
   .env & Cert        PostgreSQL & API      RavenDB ➔ PostgreSQL      Bridge & Web App      http://localhost:5173
```

> **💡 Why must you run the migration before checking the UI?**
>
> **Yes, you are 100% right!** When you start PostgreSQL for the first time, the database is completely empty (no tables, no rows). RavenDB Cloud already has your live source documents.
>
> Running the migration script **first** creates all relational tables, types, and indexes in PostgreSQL and transfers all records over. Once migrated, the UI can fetch from both databases side-by-side to show live comparisons and 100% parity!

---

## 📋 Prerequisites

Before starting, ensure you have:
1. **Docker Desktop** installed and running.
2. **Node.js** (v18+) & **npm** installed.
3. Your RavenDB client certificate file (`.pfx`).

---

## 🛠️ Step 1: Place Certificate & Configure `.env`

### 1.1 Place your RavenDB Client Certificate
Copy your `.pfx` certificate file into the `scripts/certs/` directory:
```text
scripts/
└── certs/
    └── <your-client-cert>.pfx
```
*(Note: All `.pfx` certificate files in this directory are git-ignored and won't be committed).*

### 1.2 Create your `.env` File
In your terminal at the root of `CT-RPG`:

**In PowerShell / CMD:**
```powershell
copy .env.example .env
```
*(Or in Bash: `cp .env.example .env`)*

### 1.3 Fill in your Credentials in `.env`
Open `.env` in your text editor and ensure the following keys are set:

```ini
# PostgreSQL Settings
PG_PORT=15432
PG_HOST=localhost
PG_DB=rpg
PG_USER=postgres
PG_PASSWORD=YourSecurePasswordHere

# RavenDB Cloud Source Settings
RAVEN_URL=https://<your-cluster-name>.ravendb.cloud
RAVEN_DB=btl
RAVEN_CERT_FILE=certs/<your-client-cert>.pfx
RAVEN_CERT_PASSWORD=
```

---

## 🐳 Step 2: Start PostgreSQL & .NET API Containers

From the root project folder, launch the database and API containers:

```bash
docker compose up -d --build rpg-api
```

*(Note: `rpg-api` automatically starts and waits for `rpg-postgres` to become healthy).*

Verify that the containers are healthy:
```bash
docker compose ps
```
You should see `rpg-postgres` (`healthy`) and `rpg-api` running.

---

## 🔄 Step 3: Run Data Migration (Populate PostgreSQL)

Now that PostgreSQL is running and empty, run the migrator container to extract data from RavenDB Cloud, create tables, transform documents, and load them into PostgreSQL:

### Standard Command (Docker):
```bash
docker compose run --rm rpg-migrator --all
```

> **💡 Selective Module Migration (Optional):**
> If you only want to migrate specific modules (e.g. students and fees):
> ```bash
> docker compose run --rm rpg-migrator --module student,fees
> ```

> **🐍 Alternative (Local Python without Docker):**
> If you have Python 3.10+ installed locally:
> ```bash
> pip install -r scripts/requirements.txt
> python scripts/migrate_all.py --all
> ```

### Verify Migrated Tables:
Confirm that all 42 relational tables were successfully created in PostgreSQL:
```bash
docker compose exec rpg-postgres psql -U postgres -d rpg -c "\dt"
```

### Verify Data Parity (Optional Audit):
Run the automated parity verification audit to ensure 100% field parity:
```bash
docker compose run --rm --entrypoint python rpg-migrator verify_raven_to_postgres.py
```
*(Expected: `Overall Status: PASS` with 0 missing, 0 extra, 0 mismatched records).*

---

## 💻 Step 4: Launch the Migration Showcase UI

The UI provides a live, side-by-side visual parity audit and interactive comparison between RavenDB and PostgreSQL.

### 4.1 Install UI Dependencies (First time only)
```bash
cd showcase-ui
npm install
```

### 4.2 Start the Backend Bridge Server
In a dedicated terminal (inside the `showcase-ui` folder):
```bash
npm run server
```
*You will see:*
```text
🚀 Showcase UI Backend Bridge listening on http://localhost:3001
🔌 Postgres connection verified successfully.
🦅 RavenDB Cloud connection verified successfully.
```

### 4.3 Start the Frontend Development Server
In a **second** terminal (inside the `showcase-ui` folder):
```bash
npm run dev
```
*You will see:*
```text
  VITE v6.x.x  ready in 200 ms
  ➜  Local:   http://localhost:5173/
```

---

## 🌐 Step 5: Open & Explore the UI

Open your browser to:
👉 **[http://localhost:5173](http://localhost:5173)**

### What you can see in the UI:
- **Live Parity Metrics**: Side-by-side record counts and match percentages for all collections.
- **Side-by-Side Record Comparison**: Select any collection (e.g., `Students`, `Staffs`, `Fees`, `Receipts`) to view the raw RavenDB JSON document on the left and the normalized PostgreSQL row on the right with deterministic ID alignment.
- **Interactive SQL Console**: Run live read queries against your local PostgreSQL database.
- **Automated Parity Audit Suite**: Run automated test suites verifying schemas, field counts, and JSON parity directly from the browser.

---

## 🧪 Optional: Run Automated .NET Tests

To run the automated xUnit / Npgsql integration test suite:

```bash
docker compose --profile test run --rm rpg-tests
```

---

## ❓ Troubleshooting & FAQs

### Q: Why does the UI say "Failed to fetch from RavenDB / Postgres"?
- Check that the backend server is running in terminal 1 (`npm run server` inside `showcase-ui`).
- Check that your `.env` file exists at the root `CT-RPG/.env` and has the correct `PG_PASSWORD` and `RAVEN_CERT_FILE` path.

### Q: What if PostgreSQL port 5432 is already used on my PC?
- No problem! Docker maps PostgreSQL to `15432` by default (`PG_PORT=15432` in `.env`), so it will never conflict with an existing local PostgreSQL installation.

### Q: How do I stop the Docker services when I'm done?
```bash
docker compose down
```
*(Your data remains safely stored in the `postgres_data` Docker volume).*
