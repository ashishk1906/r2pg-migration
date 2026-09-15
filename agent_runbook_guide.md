# CT-RPG Agent Runbook Guide

Use this guide to install Antigravity and run `agent_runbook.md`.

## Prerequisites

Before starting the agent, the machine must have:

- Bash: Git Bash, WSL, or another Bash-compatible shell
- Git
- `kubectl`
- PostgreSQL `psql` client
- Python 3.12+
- Docker Desktop with Linux containers
- Docker Compose v2
- `curl`
- Access to the expected Kubernetes context:
  `do-blr1-k8s-1-22-8-do-1-blr1-1655977229480`
- Access to the Kubernetes `test` namespace and services `pgbouncer-svc` and `postgresql`
- A local `.env` containing the real credentials
- RavenDB certificate at `certs/free.btl.client.certificate.pfx`

The agent verifies these prerequisites, but it cannot invent missing credentials, certificate files, Docker, or Kubernetes access. If a required item is unavailable, execution must stop before migration.

## 1. Install Antigravity

### Windows PowerShell

Open PowerShell and run:

```powershell
irm https://antigravity.google/cli/install.ps1 | iex
```

### Windows Command Prompt (CMD)

```cmd
curl -fsSL https://antigravity.google/cli/install.cmd -o install.cmd && install.cmd && del install.cmd
```

### macOS / Linux / Git Bash / WSL

Run:

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash
```

Verify the installation:

```bash
agy --version
```

A version number should be displayed.

> No additional agent installation is required. Antigravity is the agent used for this runbook.

## 2. Clone the Repository

Run this from PowerShell, Git Bash, or WSL:

```bash
git clone https://github.com/ashishk1906/r2pg-migration.git
cd r2pg-migration
```

If the repository is already cloned, only change into its directory:

```powershell
cd C:\Users\<your-user>\Desktop\r2pg-migration
```

## 3. Configure `.env`

Create the local environment file:

```bash
cp .env.example .env
```

Open `.env`, keep the existing settings, and enter the correct real password and credentials. At minimum, verify these values:

```dotenv
EXPECTED_K8S_CONTEXT=do-blr1-k8s-1-22-8-do-1-blr1-1655977229480

PG_HOST=localhost
PG_PORT=6432
PG_ADMIN_HOST=localhost
PG_ADMIN_PORT=5432
PG_MAINTENANCE_DB=postgres
PG_DB=rpg
PG_USER=postgres
PG_PASSWORD=<your-real-postgres-password>

API_PORT=5000
RAVEN_URL=https://a.free.btl.ravendb.cloud
RAVEN_DB=BTL
RAVEN_CERT_FILE=certs/free.btl.client.certificate.pfx
```

Do not commit `.env` or print the password.

## 4. Download and Place the RavenDB Certificate

Download the certificate from the project link:

[Download RavenDB client certificate](https://drive.google.com/file/d/1tcdrDU3Q1zzWBqs-BS0_0PGGvXjR2INI/view?usp=drive_link)

Place the downloaded file at this exact path inside the repository:

```text
r2pg-migration/certs/free.btl.client.certificate.pfx
```

The path must match `RAVEN_CERT_FILE` in `.env`.

## 5. Open the Repository Terminal

Open a new terminal and change to the repository folder:

### PowerShell

```powershell
cd C:\Users\<your-user>\Desktop\r2pg-migration
```

### Git Bash

```bash
cd /c/Users/<your-user>/Desktop/r2pg-migration
```

Confirm that these files exist:

```bash
ls agent_runbook.md agent-runbook/scripts/local-onboard.sh .env certs/free.btl.client.certificate.pfx
```

## 6. Sign In and Start Antigravity

Start Antigravity:

```bash
agy
```

If Antigravity asks you to sign in, complete the browser sign-in flow. If it is already authenticated, continue.

## 7. Send This Prompt

Paste this exact prompt into Antigravity:

```text
Execute agent_runbook.md end-to-end from the repository root. Run every gate in order, stop on any failure, never print secrets, and report the final PASS/FAIL table with the failed command and non-secret error output if applicable.
```

The agent should follow `agent_runbook.md`, including the prerequisite check, PostgreSQL setup, migration, parity verification, API health check, and automated tests.

## 8. Expected Output

When everything succeeds, Antigravity should report:

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

If any step fails, the agent must stop and report the failed command, exit code, and relevant non-secret error output. Do not continue by skipping a failed gate.
