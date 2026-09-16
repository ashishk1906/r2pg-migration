# CT-RPG Playbook Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as LOCAL: User
    participant Docker as DOCKER: Docker Compose
    participant PG as DOCKER: rpg-postgres
    participant API as DOCKER: rpg-api
    participant Migrator as DOCKER: rpg-migrator
    participant Tests as DOCKER: rpg-tests
    participant Raven as HOSTED: RavenDB Cloud

    User->>User: Configure .env and scripts/certs certificate
    User->>Docker: Start rpg-postgres and rpg-api
    Docker->>PG: Start PostgreSQL
    PG-->>Docker: Health check passes
    Docker->>API: Start Web API

    User->>PG: Run terminal psql SELECT 1
    PG-->>User: Database ready

    User->>Migrator: Run migration --all
    Migrator->>Raven: Read source collections
    Raven-->>Migrator: RavenDB documents
    Migrator->>PG: Create tables and upsert data
    Migrator->>PG: Apply views, indexes, and triggers
    PG-->>User: Migration complete

    User->>PG: Inspect tables with psql
    User->>Migrator: Run parity verification
    Migrator->>Raven: Compare source records
    Migrator->>PG: Compare target records
    PG-->>User: Zero mismatches

    User->>API: Check /health and sample endpoints
    API->>PG: Read application data
    API-->>User: HTTP 200

    User->>Tests: Run dotnet tests
    Tests->>PG: Run integration tests
    Tests-->>User: Exit code 0

    User->>Docker: Stop containers
    User-->>User: Overall PASS
```

## Runtime Locations

- LOCAL: `.env`, terminal `psql`, `curl`, and commands.
- DOCKER: PostgreSQL, API, migration, and test containers.
- HOSTED: RavenDB Cloud source database.
