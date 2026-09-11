# 🚀 Antigravity CLI Agent Execution Playbook

A simple, complete guide on installing the **Antigravity CLI (`agy`)** and running the **[AGENT_RUNBOOK.md](file:///c:/Users/aks89/Desktop/CT-RPG/AGENT_RUNBOOK.md)**.

---

## 1. Install & Set Up Antigravity CLI

### A. Installation

#### Windows (PowerShell):
```powershell
# Install via official installer script
irm https://antigravity.google/install.ps1 | iex
```

#### macOS / Linux (Terminal / Bash):
```bash
# Install via curl installer script
curl -fsSL https://antigravity.google/install.sh | bash
```

*(Alternatively, if installing the Python SDK & CLI bundle:)*
```bash
pip install google-antigravity
```

---

### B. Verify Installation & Authenticate
```bash
# Verify the binary is installed
agy --version

# Authenticate on first run (follows browser login prompt)
agy login
```

---

## 2. Running the Agent Runbook via CLI

Choose whichever method best suits your workflow:

### 🔹 Option 1: One-Shot Terminal Command (Headless)
Run this single command from the project root directory:

```bash
agy "Execute AGENT_RUNBOOK.md end-to-end. Run all 6 gates sequentially (prerequisites, port-forward, migration, parity, API, and tests) and print the final verification table."
```

---

### 🔹 Option 2: Interactive Terminal Mode (TUI)

1. Open your terminal in the project directory:
   ```bash
   cd c:\Users\aks89\Desktop\CT-RPG
   agy
   ```

2. Send the agent the prompt with file reference:
   ```text
   @AGENT_RUNBOOK.md Please execute this runbook step-by-step, verify all 6 gates, and print the completion report.
   ```

---

### 🔹 Option 3: Autonomous Run with `/goal` (Recommended)

When using interactive mode, you can trigger the `/goal` command for thorough, fully autonomous execution:

```text
/goal Follow AGENT_RUNBOOK.md:
1. Verify prerequisites with bash scripts/verify-prerequisites.sh
2. Ensure PgBouncer port-forward is running and verify DB connection
3. Run migration with python3 scripts/migrate_all.py --all
4. Run parity audit with python3 scripts/verify_raven_to_postgres.py
5. Start API container (docker compose up -d --build rpg-api) and check /health
6. Run tests with docker compose run --rm rpg-tests
7. Print the final verification summary table
```

---

## 3. What the Agent Executes (The 6 Gates)

| Gate | Target / Action | Pass Condition |
|---|---|---|
| **Gate 1: Preflight** | `bash scripts/verify-prerequisites.sh` | Exit code `0` |
| **Gate 2: DB Connectivity** | `psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d ctlytics_test -c "SELECT 1;"` | Exit code `0` |
| **Gate 3: Data Migration** | `python3 scripts/migrate_all.py --all` | Exit code `0` + View/Trigger verified |
| **Gate 4: Parity Audit** | `python3 scripts/verify_raven_to_postgres.py` | Exit code `0` + 0 discrepancies |
| **Gate 5: Web API Health** | `bash scripts/wait-for-api.sh http://localhost:5000 60` | HTTP `200` |
| **Gate 6: Test Suite** | `docker compose run --rm rpg-tests` | Exit code `0` |

---

## 4. Expected Final Report Output

Once execution finishes, the agent will present the status summary:

```text
===========================
CT-RPG Verification Report
===========================
Preflight:       PASS
PostgreSQL:      PASS
Migration:       PASS
Post-SQL:        PASS
Parity:          PASS
API Health:      PASS
Tests:           PASS

Overall:         PASS
===========================
```
