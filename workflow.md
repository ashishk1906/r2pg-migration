# CT-RPG Work Process

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Agent
    participant K8s as Kubernetes
    participant PG as PostgreSQL (:5432)
    participant PB as PgBouncer (:6432)
    participant Raven as RavenDB
    participant API as Web API Container
    participant Tests as Tests Container

    User->>User: Configure .env and certificate
    User->>K8s: Verify context and services
    User->>K8s: Start port-forwards (5432 & 6432)
    K8s-->>User: PostgreSQL and PgBouncer ready

    %% Database Admin (Direct PG)
    User->>PG: Connect to maintenance db (postgres)
    User->>PG: Create or reuse target db (rpg)
    User->>PB: Verify routing to rpg
    PB->>PG: Route test query
    PG-->>User: Database ready

    %% Migration (via PgBouncer)
    User->>PB: Run Python migration (scripts/migrate_all.py)
    PB-->>Raven: (ETL reads source collections via mTLS)
    PB->>PG: Load tables, views, indexes, triggers
    PG-->>User: Migration complete (Gate 2: PASS)

    %% Parity Audit
    User->>PB: Run parity check (scripts/verify_raven_to_postgres.py)
    PB-->>Raven: Compare RavenDB docs vs PostgreSQL rows
    PB-->>User: Zero mismatches (Gate 3: PASS)

    %% API & Tests
    User->>API: Start API container (rpg-api)
    API->>PB: Connect to rpg (:6432)
    User->>API: Check /health and sample endpoint
    API-->>User: HTTP 200 (Gate 4a: PASS)

    User->>Tests: Run test container (rpg-tests --rm)
    Tests->>PB: Run integration tests via API / DB
    Tests-->>User: Tests pass (Gate 4b: PASS)
    Note over Tests: Container self-terminates (--rm)

    User->>K8s: Stop port-forwards
    User-->>User: Overall: PASS
```

Runtime summary:

- Docker: one persistent `rpg-api` container and one temporary `rpg-tests` container.
- Kubernetes: PostgreSQL and PgBouncer.
- Migration: runs locally with Python.
