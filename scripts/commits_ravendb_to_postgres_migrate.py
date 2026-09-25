#!/usr/bin/env python3
"""
Extract Commit-related data (CommitAssets, Commits, CommitAcs) from RavenDB,
transform it to PostgreSQL schema, and load into PostgreSQL.

Applies the Common Commit Wrapper across all three event-sourced collections:
- CommitAssets (Asset Domain events)
- Commits (Library Domain events)
- CommitAcs (Accounting Domain events)

Target tables:
- commit_asset
- commits
- commit_ac

Target enums:
- asset_status_enum
- material_status_enum
- owner_status_enum
- inventory_journal_status_enum
- voucher_type_enum
- voucher_status_enum
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json
import requests

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass
class Config:
    raven_url: str
    raven_db: str
    raven_cert_file: Optional[str]
    raven_cert_password: Optional[str]
    raven_insecure: bool
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str
    commit_assets_collection: str
    commits_collection: str
    commit_acs_collection: str
    page_size: int
    timeout_sec: int
    summary_json_path: Optional[str]
    write_summary_json: bool


@dataclass
class UpsertResult:
    record_id: str
    inserted: bool


def load_env_file(env_path: str) -> None:
    """Load KEY=VALUE entries from .env into os.environ when missing."""
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and os.getenv(key) is None:
                os.environ[key] = value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> Config:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_env = os.path.join(script_dir, "..", ".env")
    if os.path.exists(root_env):
        load_env_file(root_env)

    parser = argparse.ArgumentParser(
        description="Migrate Commit-related collections (CommitAssets, Commits, CommitAcs) from RavenDB to PostgreSQL"
    )
    parser.add_argument("--raven-url", default=os.getenv("RAVEN_URL"))
    parser.add_argument("--raven-db", default=os.getenv("RAVEN_DB"))
    parser.add_argument("--raven-cert-file", default=os.getenv("RAVEN_CERT_FILE"))
    parser.add_argument(
        "--raven-cert-password", default=os.getenv("RAVEN_CERT_PASSWORD")
    )
    parser.add_argument(
        "--raven-insecure",
        action="store_true",
        default=env_bool("RAVEN_INSECURE", False),
        help="Disable TLS certificate verification for RavenDB HTTPS (not for production).",
    )

    parser.add_argument("--pg-host", default=os.getenv("PG_HOST", "localhost"))
    parser.add_argument(
        "--pg-port",
        type=int,
        default=int(os.getenv("PG_PORT", "5432")),
    )
    parser.add_argument("--pg-db", default=os.getenv("PG_DB", "rpg"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    parser.add_argument("--pg-password", default=os.getenv("PG_PASSWORD"))

    parser.add_argument(
        "--commit-assets-collection",
        default=os.getenv("COMMIT_ASSETS_COLLECTION", "CommitAssets"),
        help="RavenDB collection name for CommitAssets (default: CommitAssets)",
    )
    parser.add_argument(
        "--commits-collection",
        default=os.getenv("COMMITS_COLLECTION", "Commits"),
        help="RavenDB collection name for Commits (default: Commits)",
    )
    parser.add_argument(
        "--commit-acs-collection",
        default=os.getenv("COMMIT_ACS_COLLECTION", "CommitAcs"),
        help="RavenDB collection name for CommitAcs (default: CommitAcs)",
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=int(os.getenv("PAGE_SIZE", "500")),
        help="Batch pagination size for querying RavenDB",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=int(os.getenv("TIMEOUT_SEC", "30")),
        help="HTTP request timeout in seconds",
    )
    parser.add_argument(
        "--summary-json-path",
        default=os.getenv("MIGRATION_SUMMARY_JSON"),
        help=(
            "Optional output path for post-run JSON artifact. "
            "Default when omitted: validation/commits-migration-summary-<timestamp>.json"
        ),
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        help="Disable writing post-run summary JSON artifact.",
    )
    args = parser.parse_args()

    if not args.raven_url or not args.raven_db:
        parser.error(
            "Missing RavenDB config. Provide --raven-url/--raven-db or set RAVEN_URL/RAVEN_DB."
        )

    if not args.pg_password:
        parser.error(
            "Missing PostgreSQL password. Provide --pg-password or set PG_PASSWORD."
        )

    if not args.pg_host or args.pg_port is None or not args.pg_db or not args.pg_user:
        parser.error(
            "Missing PostgreSQL config. Provide --pg-host/--pg-port/--pg-db/--pg-user or set PG_HOST/PG_PORT/PG_DB/PG_USER."
        )

    if args.page_size <= 0:
        parser.error("Invalid page size. --page-size must be greater than 0.")

    if args.timeout_sec <= 0:
        parser.error("Invalid timeout. --timeout-sec must be greater than 0.")

    if args.raven_cert_file:
        if not os.path.isfile(args.raven_cert_file):
            script_dir_cert = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), args.raven_cert_file
            )
            if os.path.isfile(script_dir_cert):
                args.raven_cert_file = script_dir_cert
            else:
                parser.error(f"Raven cert file not found: {args.raven_cert_file}")
        if not args.raven_url.lower().startswith("https://"):
            parser.error(
                "RAVEN_CERT_FILE requires an https:// RavenDB URL because certificate "
                "authentication uses mutual TLS."
            )

    return Config(
        raven_url=args.raven_url.rstrip("/"),
        raven_db=args.raven_db,
        raven_cert_file=args.raven_cert_file,
        raven_cert_password=args.raven_cert_password,
        raven_insecure=args.raven_insecure,
        pg_host=args.pg_host,
        pg_port=args.pg_port,
        pg_db=args.pg_db,
        pg_user=args.pg_user,
        pg_password=args.pg_password,
        commit_assets_collection=args.commit_assets_collection,
        commits_collection=args.commits_collection,
        commit_acs_collection=args.commit_acs_collection,
        page_size=args.page_size,
        timeout_sec=args.timeout_sec,
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
    )


def write_summary_json(path_text: str, payload: Dict[str, Any]) -> str:
    """Write migration summary JSON artifact and return absolute path."""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path.resolve())


# ---------------------------------------------------------------------------
# RavenDB Connection & Extraction
# ---------------------------------------------------------------------------


def configure_raven_session(session: requests.Session, cfg: Config) -> None:
    """Configure RavenDB TLS verification and optional PKCS#12 client auth."""
    if cfg.raven_cert_file:
        try:
            from requests_pkcs12 import Pkcs12Adapter
        except ImportError as exc:
            raise RuntimeError(
                "PKCS#12 RavenDB authentication requires requests-pkcs12. "
                "Install with: python -m pip install requests-pkcs12"
            ) from exc

        session.mount(
            "https://",
            Pkcs12Adapter(
                pkcs12_filename=cfg.raven_cert_file,
                pkcs12_password=cfg.raven_cert_password or "",
            ),
        )

    if cfg.raven_insecure:
        session.verify = False
        print("Warning: RavenDB TLS verification is disabled (--raven-insecure).")


def raven_query_collection(
    session: requests.Session, cfg: Config, collection_name: str
) -> List[Dict[str, Any]]:
    """Query all documents from a given RavenDB collection with pagination."""
    url = f"{cfg.raven_url}/databases/{cfg.raven_db}/queries"
    start = 0
    docs: List[Dict[str, Any]] = []
    escaped_collection = collection_name.replace("\\", "\\\\").replace('"', '\\"')

    while True:
        payload = {
            "Query": f'from "{escaped_collection}" order by id()',
            "Start": start,
            "PageSize": cfg.page_size,
        }
        resp = session.post(url, json=payload, timeout=cfg.timeout_sec)
        resp.raise_for_status()

        body = resp.json()
        if not isinstance(body, dict):
            raise RuntimeError(f"Unexpected response format for {collection_name}")
        results = body.get("Results", [])
        if not isinstance(results, list):
            raise RuntimeError(f"Unexpected Results format for {collection_name}")

        if not results:
            break

        docs.extend(results)
        start += len(results)

        total_results = body.get("TotalResults")
        if total_results is not None and len(docs) >= total_results:
            break

    return docs


# ---------------------------------------------------------------------------
# Data Transformation Helpers
# ---------------------------------------------------------------------------


def clean_uuid(raw_val: Any) -> Optional[str]:
    """
    Validate and return canonical UUID string.
    Safely converts empty strings, None, or invalid values to None.
    """
    if raw_val is None:
        return None
    val_str = str(raw_val).strip()
    if not val_str:
        return None
    if UUID_RE.match(val_str):
        return val_str.lower()
    return None


def parse_iso_timestamp(raw_val: Any) -> Optional[datetime]:
    """Parse ISO-8601 UTC timestamp safely."""
    if not raw_val:
        return None
    val_str = str(raw_val).strip()
    if not val_str:
        return None
    try:
        if val_str.endswith("Z"):
            val_str = val_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(val_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def extract_commit_fields(
    doc: Dict[str, Any], default_collection: str
) -> Tuple[
    str,
    Optional[str],
    int,
    Optional[str],
    Optional[str],
    datetime,
    Dict[str, Any],
]:
    """Extract and validate all fields for the Common Commit Wrapper."""
    metadata = doc.get("@metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    # 1. Document ID (must be a valid UUID)
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    commit_id = clean_uuid(raw_id)
    if not commit_id:
        raise ValueError(f"Document missing valid GUID id: {raw_id}")

    # 2. Aggregate ID (UUID or None)
    raw_agg_id = doc.get("AggregateId") or doc.get("aggregate_id")
    agg_id = clean_uuid(raw_agg_id)

    # 3. Version (int)
    raw_ver = doc.get("Version", 1)
    try:
        version = int(raw_ver)
    except (ValueError, TypeError):
        version = 1

    # 4. UserId (UUID or None)
    user_id = clean_uuid(doc.get("UserId"))

    # 5. InstId (UUID or None - gracefully handles empty string "")
    inst_id = clean_uuid(doc.get("InstId"))

    # 6. Timestamp
    raw_ts = doc.get("TimeStamp") or metadata.get("@last-modified")
    ts = parse_iso_timestamp(raw_ts) or datetime.now(timezone.utc)

    # 7. EventMessage (dict / JSON payload)
    event_msg = doc.get("EventMessage")
    if not isinstance(event_msg, dict):
        event_msg = {"Payload": event_msg}

    return (
        commit_id,
        agg_id,
        version,
        user_id,
        inst_id,
        ts,
        event_msg,
    )


# ---------------------------------------------------------------------------
# Schema Management (Enums, Tables, Indexes, Views)
# ---------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create all enums, tables, views, and indexes idempotently."""
    # 1. Custom PostgreSQL ENUMs
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'inventory_journal_status_enum') THEN
                CREATE TYPE inventory_journal_status_enum AS ENUM (
                    'Active',
                    'Disabled'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'asset_status_enum') THEN
                CREATE TYPE asset_status_enum AS ENUM (
                    'Active',
                    'Cleared',
                    'Disabled'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'material_status_enum') THEN
                CREATE TYPE material_status_enum AS ENUM (
                    'Active',
                    'Reserved',
                    'Issued',
                    'UnderMaintenance',
                    'OutOfCirculation',
                    'Disabled'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'owner_status_enum') THEN
                CREATE TYPE owner_status_enum AS ENUM (
                    'Current',
                    'Past'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'voucher_type_enum') THEN
                CREATE TYPE voucher_type_enum AS ENUM (
                    'Expense',
                    'Income',
                    'Journal'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'voucher_status_enum') THEN
                CREATE TYPE voucher_status_enum AS ENUM (
                    'Active',
                    'Disabled'
                );
            END IF;
        END $$;
        """
    )

    # 2. Target Tables: commit_asset, commits, commit_ac
    table_definitions = [
        ("commit_asset", "CommitAssets"),
        ("commits", "Commits"),
        ("commit_ac", "CommitAcs"),
    ]

    for table_name, default_coll in table_definitions:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id UUID PRIMARY KEY,
                aggregate_id UUID,
                version INTEGER NOT NULL,
                user_id UUID,
                inst_id UUID,
                timestamp TIMESTAMPTZ NOT NULL,
                event_message JSONB NOT NULL
            );
            ALTER TABLE {table_name} ALTER COLUMN aggregate_id DROP NOT NULL;
            ALTER TABLE {table_name} DROP COLUMN IF EXISTS event_type;
            ALTER TABLE {table_name} DROP COLUMN IF EXISTS collection;
            ALTER TABLE {table_name} DROP COLUMN IF EXISTS raven_clr_type;
            ALTER TABLE {table_name} DROP COLUMN IF EXISTS raven_change_vector;
            ALTER TABLE {table_name} DROP COLUMN IF EXISTS raven_last_modified;
            DROP INDEX IF EXISTS {table_name}_event_type_idx;
            """
        )

        # Performance Indexes
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {table_name}_aggregate_id_idx ON {table_name} (aggregate_id);
            CREATE INDEX IF NOT EXISTS {table_name}_timestamp_idx ON {table_name} (timestamp);
            CREATE INDEX IF NOT EXISTS {table_name}_inst_id_idx ON {table_name} (inst_id);
            CREATE INDEX IF NOT EXISTS {table_name}_event_message_gin_idx ON {table_name} USING GIN (event_message);
            """
        )

    # Clean up any previously created views if present
    cur.execute(
        """
        DROP VIEW IF EXISTS commit_assets, commit_acs, v_all_commits,
            v_asset_created_event, v_stock_verified_event, v_material_created_event,
            v_inventory_journal_created_event, v_voucher_created_event CASCADE;
        """
    )


# ---------------------------------------------------------------------------
# Database Upsert Operation
# ---------------------------------------------------------------------------


def upsert_commit_document(
    cur: psycopg2.extensions.cursor,
    table_name: str,
    doc: Dict[str, Any],
    default_collection: str,
) -> UpsertResult:
    """Idempotently insert or update a commit document in the target table."""
    (
        commit_id,
        agg_id,
        version,
        user_id,
        inst_id,
        ts,
        event_msg,
    ) = extract_commit_fields(doc, default_collection)

    sql = f"""
        INSERT INTO {table_name} (
            id,
            aggregate_id,
            version,
            user_id,
            inst_id,
            timestamp,
            event_message
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            aggregate_id = EXCLUDED.aggregate_id,
            version = EXCLUDED.version,
            user_id = EXCLUDED.user_id,
            inst_id = EXCLUDED.inst_id,
            timestamp = EXCLUDED.timestamp,
            event_message = EXCLUDED.event_message
        RETURNING (xmax = 0);
    """

    cur.execute(
        sql,
        (
            commit_id,
            agg_id,
            version,
            user_id,
            inst_id,
            ts,
            Json(event_msg),
        ),
    )
    row = cur.fetchone()
    inserted = bool(row[0]) if row else False
    return UpsertResult(record_id=commit_id, inserted=inserted)


# ---------------------------------------------------------------------------
# Main Routine
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the end-to-end migration for CommitAssets, Commits, and CommitAcs."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collections=({cfg.commit_assets_collection}, {cfg.commits_collection}, {cfg.commit_acs_collection})"
        )
        print("[1/6] Fetching RavenDB documents...")
        commit_assets_docs = raven_query_collection(
            requests_session, cfg, cfg.commit_assets_collection
        )
        commits_docs = raven_query_collection(
            requests_session, cfg, cfg.commits_collection
        )
        commit_acs_docs = raven_query_collection(
            requests_session, cfg, cfg.commit_acs_collection
        )
        print(
            f"Fetched commit_assets={len(commit_assets_docs)}, "
            f"commits={len(commits_docs)}, "
            f"commit_acs={len(commit_acs_docs)}"
        )

        print("[2/6] Connecting PostgreSQL...")
        print(
            f"PostgreSQL target: host={cfg.pg_host}, port={cfg.pg_port}, "
            f"db={cfg.pg_db}, user={cfg.pg_user}"
        )
        conn = psycopg2.connect(
            host=cfg.pg_host,
            port=cfg.pg_port,
            dbname=cfg.pg_db,
            user=cfg.pg_user,
            password=cfg.pg_password,
        )
        conn.autocommit = True
        with conn.cursor() as tz_cur:
            tz_cur.execute("SET TIME ZONE 'UTC';")
        conn.autocommit = False

        loaded_commit_assets = 0
        new_commit_assets = 0
        loaded_commits = 0
        new_commits = 0
        loaded_commit_acs = 0
        new_commit_acs = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/6] Ensuring target schema & enums...")
                ensure_target_schema(cur)

                print("[4/6] Upserting CommitAssets...")
                for d in commit_assets_docs:
                    res = upsert_commit_document(
                        cur, "commit_asset", d, cfg.commit_assets_collection
                    )
                    loaded_commit_assets += 1
                    new_commit_assets += int(res.inserted)

                print("[5/6] Upserting Commits...")
                for d in commits_docs:
                    res = upsert_commit_document(
                        cur, "commits", d, cfg.commits_collection
                    )
                    loaded_commits += 1
                    new_commits += int(res.inserted)

                print("[6/6] Upserting CommitAcs...")
                for d in commit_acs_docs:
                    res = upsert_commit_document(
                        cur, "commit_ac", d, cfg.commit_acs_collection
                    )
                    loaded_commit_acs += 1
                    new_commit_acs += int(res.inserted)

        # Generate summary payload
        timestamp_str = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        summary = {
            "generated_at_utc": timestamp_str,
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "commit_assets_collection": cfg.commit_assets_collection,
                "commits_collection": cfg.commits_collection,
                "commit_acs_collection": cfg.commit_acs_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "commit_assets_processed": loaded_commit_assets,
                "new_commit_assets_inserted": new_commit_assets,
                "commits_processed": loaded_commits,
                "new_commits_inserted": new_commits,
                "commit_acs_processed": loaded_commit_acs,
                "new_commit_acs_inserted": new_commit_acs,
            },
        }

        print("Migration completed.")
        print(f"commit_assets_processed: {loaded_commit_assets}")
        print(f"new_commit_assets_inserted: {new_commit_assets}")
        print(f"commits_processed: {loaded_commits}")
        print(f"new_commits_inserted: {new_commits}")
        print(f"commit_acs_processed: {loaded_commit_acs}")
        print(f"new_commit_acs_inserted: {new_commit_acs}")

        if cfg.write_summary_json:
            ts_compact = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            summary_path = (
                cfg.summary_json_path
                or f"validation/commits-migration-summary-{ts_compact}.json"
            )
            abs_summary = write_summary_json(summary_path, summary)
            print(f"summary_json: {abs_summary}")

        return 0

    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()
        requests_session.close()


if __name__ == "__main__":
    sys.exit(main())

