#!/usr/bin/env python3
"""
Extract Email-related data from RavenDB, transform it to PostgreSQL schema,
and load into PostgreSQL.

Source:
- RavenDB Emails collection (Repo.Resource.Email in ct.connect)

Target table:
- email

Target schema:
- id                  UUID PRIMARY KEY
- recipients          TEXT[] NOT NULL
- message             TEXT NOT NULL
- type                VARCHAR(50) NOT NULL DEFAULT 'Generic'
- "from"              VARCHAR(255) NOT NULL
- subject             VARCHAR(500)
- attachments         JSONB
- owner_id            UUID
- parent_id           UUID
- created_on          TIMESTAMPTZ NOT NULL
- created_by          UUID
- modified_on         TIMESTAMPTZ
- modified_by         UUID
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
    emails_collection: str
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
        description="Migrate Emails data from RavenDB to PostgreSQL"
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
        "--emails-collection",
        default=os.getenv("EMAILS_COLLECTION", "Emails"),
        help="RavenDB collection name for Emails (default: Emails)",
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
            "Default when omitted: validation/emails-migration-summary-<timestamp>.json"
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
        emails_collection=args.emails_collection,
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


def clean_string_list(raw_val: Any) -> List[str]:
    """Ensure raw value is converted to a clean list of strings for TEXT[]."""
    if raw_val is None:
        return []
    if isinstance(raw_val, list):
        return [str(item).strip() for item in raw_val if str(item).strip()]
    if isinstance(raw_val, str):
        cleaned = raw_val.strip()
        return [cleaned] if cleaned else []
    return [str(raw_val)]


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


def extract_email_fields(
    doc: Dict[str, Any], default_collection: str
) -> Tuple[
    str,
    List[str],
    str,
    str,
    str,
    Optional[str],
    Optional[Any],
    Optional[str],
    Optional[str],
    datetime,
    Optional[str],
    Optional[datetime],
    Optional[str],
]:
    """Extract and validate all fields for the email table."""
    metadata = doc.get("@metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    # 1. Document ID (must be a valid UUID)
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    email_id = clean_uuid(raw_id)
    if not email_id:
        raise ValueError(f"Email document missing valid GUID id: {raw_id}")

    # 2. Recipients (list of email strings)
    recipients = clean_string_list(doc.get("Recipients"))

    # 3. Message (HTML body)
    message = str(doc.get("Message") or "").strip()

    # 4. Type (e.g. Generic)
    type_str = str(doc.get("Type") or "Generic").strip()

    # 5. From address
    from_addr = str(doc.get("From") or "").strip()

    # 6. Subject
    subject_val = doc.get("Subject")
    subject = str(subject_val).strip() if subject_val is not None else None

    # 7. Attachments (JSON array of attachment dicts)
    raw_attachments = doc.get("Attachments")
    attachments: Optional[List[Dict[str, Any]]] = None
    if isinstance(raw_attachments, list):
        attachments = []
        for item in raw_attachments:
            if isinstance(item, dict):
                attachments.append(
                    {
                        "FilePath": str(item.get("FilePath") or "").strip(),
                        "FileName": str(item.get("FileName") or "").strip(),
                    }
                )

    # 8. OwnerId (UUID)
    owner_id = clean_uuid(doc.get("OwnerId"))

    # 9. ParentId (UUID, safely converting "" to None)
    parent_id = clean_uuid(doc.get("ParentId"))

    # 10. Timestamps and audit users
    raw_created_on = doc.get("CreatedOn") or metadata.get("@last-modified")
    created_on = parse_iso_timestamp(raw_created_on) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))

    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        email_id,
        recipients,
        message,
        type_str,
        from_addr,
        subject,
        attachments,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


# ---------------------------------------------------------------------------
# Schema Management (Tables, Indexes, Views)
# ---------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create email table, indexes, and views idempotently."""
    # 1. Main email table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS email (
            id UUID PRIMARY KEY,
            recipients TEXT[] NOT NULL,
            message TEXT NOT NULL,
            type VARCHAR(50) NOT NULL DEFAULT 'Generic',
            "from" VARCHAR(255) NOT NULL,
            subject VARCHAR(500),
            attachments JSONB,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );
        ALTER TABLE email DROP COLUMN IF EXISTS from_address;
        ALTER TABLE email DROP COLUMN IF EXISTS audited;
        ALTER TABLE email DROP COLUMN IF EXISTS collection;
        ALTER TABLE email DROP COLUMN IF EXISTS raven_clr_type;
        ALTER TABLE email DROP COLUMN IF EXISTS raven_change_vector;
        ALTER TABLE email DROP COLUMN IF EXISTS raven_last_modified;
        ALTER TABLE email ALTER COLUMN type TYPE VARCHAR(50);
        ALTER TABLE email ALTER COLUMN "from" TYPE VARCHAR(255);
        ALTER TABLE email ALTER COLUMN subject TYPE VARCHAR(500);
        """
    )

    # 2. Indexes
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS email_owner_id_idx ON email (owner_id);
        CREATE INDEX IF NOT EXISTS email_created_on_idx ON email (created_on);
        CREATE INDEX IF NOT EXISTS email_created_by_idx ON email (created_by);
        CREATE INDEX IF NOT EXISTS email_type_idx ON email (type);
        CREATE INDEX IF NOT EXISTS email_recipients_gin_idx ON email USING GIN (recipients);
        CREATE INDEX IF NOT EXISTS email_attachments_gin_idx ON email USING GIN (attachments);
        """
    )

    # Clean up any previously created views if present
    cur.execute(
        """
        DROP VIEW IF EXISTS emails, v_email_attachment CASCADE;
        """
    )


# ---------------------------------------------------------------------------
# Database Upsert Operation
# ---------------------------------------------------------------------------


def upsert_email_document(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any], default_collection: str
) -> UpsertResult:
    """Idempotently insert or update an email document in PostgreSQL."""
    (
        email_id,
        recipients,
        message,
        type_str,
        from_addr,
        subject,
        attachments,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    ) = extract_email_fields(doc, default_collection)

    attachments_json = Json(attachments) if attachments is not None else None

    sql = """
        INSERT INTO email (
            id,
            recipients,
            message,
            type,
            "from",
            subject,
            attachments,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            recipients = EXCLUDED.recipients,
            message = EXCLUDED.message,
            type = EXCLUDED.type,
            "from" = EXCLUDED."from",
            subject = EXCLUDED.subject,
            attachments = EXCLUDED.attachments,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by
        RETURNING (xmax = 0);
    """

    cur.execute(
        sql,
        (
            email_id,
            recipients,
            message,
            type_str,
            from_addr,
            subject,
            attachments_json,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by,
        ),
    )
    row = cur.fetchone()
    inserted = bool(row[0]) if row else False
    return UpsertResult(record_id=email_id, inserted=inserted)




# ---------------------------------------------------------------------------
# Main Routine
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the end-to-end migration for Emails."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collections=({cfg.emails_collection})"
        )
        print("[1/4] Fetching RavenDB documents...")
        emails_docs = raven_query_collection(
            requests_session, cfg, cfg.emails_collection
        )
        print(f"Fetched emails={len(emails_docs)}")

        print("[2/4] Connecting PostgreSQL...")
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

        loaded_emails = 0
        new_emails = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema & views...")
                ensure_target_schema(cur)

                print("[4/4] Upserting emails...")
                for d in emails_docs:
                    res = upsert_email_document(cur, d, cfg.emails_collection)
                    loaded_emails += 1
                    new_emails += int(res.inserted)

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
                "emails_collection": cfg.emails_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "emails_processed": loaded_emails,
                "new_emails_inserted": new_emails,
            },
        }

        print("Migration completed.")
        print(f"emails_processed: {loaded_emails}")
        print(f"new_emails_inserted: {new_emails}")

        if cfg.write_summary_json:
            ts_compact = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            summary_path = (
                cfg.summary_json_path
                or f"validation/emails-migration-summary-{ts_compact}.json"
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
