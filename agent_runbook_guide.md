# Simple Agent Guide: CT-RPG

A simple, complete guide to set up and run the **CT-RPG (RavenDB to PostgreSQL Migration & .NET 10 Web API)** onboarding using an AI agent.

Everything runs inside Docker containers—**zero local installations** of Python, .NET SDK, or PostgreSQL are required.

---

## 1. Install Prerequisites

### A. Install Docker Desktop
Run this command in an **Administrator PowerShell** window:
```powershell
winget install -e --id Docker.DockerDesktop
```
Launch Docker Desktop, ensure **Linux containers** mode is active, and verify:
```powershell
docker --version
docker compose version
```

### B. Install Antigravity
Install **Antigravity** (IDE or CLI):
- **Antigravity IDE**: Download and install from [Antigravity](https://antigravity.google).
- **Antigravity CLI (`agy`)**: If using the CLI, ensure `agy` is installed and in your PATH. Verify in terminal:
  ```bash
  agy --version
  ```

---

## 2. Clone Repo & Configuration Setup

### A. Clone the Repository & Navigate to Folder
```bash
git clone https://github.com/ashishk1906/r2pg-migration.git
cd r2pg-migration
```

### B. Configure `.env` File
```bash
# In Bash / PowerShell:
cp .env.example .env

# In Windows Command Prompt (CMD):
copy .env.example .env
```
Fill in your database and RavenDB settings in `.env`.

### C. Place RavenDB Client Certificate
Copy your client `.pfx` certificate into:
```text
scripts/certs/<your-client-cert>.pfx
```
Ensure the filename matches `RAVEN_CERT_FILE` in your `.env` (e.g., `certs/free.btl.client.certificate.pfx`).

---

## 🤖 Launch Antigravity & Run the Agent

1. In your terminal inside the `CT-RPG` folder, start the agent CLI:
   ```bash
   agy
   ```
   *(Or open the `CT-RPG` folder in the **Antigravity IDE** and open the chat sidebar).*

2. Paste this prompt to the agent:

> **"Please execute all steps in @agent_runbook.md sequentially from start to finish. Ensure each step succeeds before proceeding."**

The agent will autonomously execute all steps in [agent_runbook.md](file:///c:/Users/aks89/Desktop/CT-RPG/agent_runbook.md) (Preflight -> Services Startup -> Migration -> Parity Audit -> API Verification -> Automated Tests).

---

## 3. Preflight Check (Optional Manual Verification)

To manually verify all prerequisites before launching the agent:
```bash
bash scripts/verify-prerequisites.sh
```
If it outputs `[PREFLIGHT PASS]`, the environment is ready.

---

## Teardown

- **Stop containers (preserve data):**
  ```bash
  docker compose down
  ```
- **Full reset (wipe database volume):**
  ```bash
  docker compose down -v
  ```
