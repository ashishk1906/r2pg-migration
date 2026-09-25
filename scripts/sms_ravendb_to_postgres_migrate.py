#!/usr/bin/env python3
"""
Extract SMS-related data (SMs and SmsMessages) from RavenDB,
transform it to PostgreSQL schema, and load into PostgreSQL.

Source:
- SMs collection (ct._Core.Repo.Resource.SMS in ct.connect)
- SmsMessages collection (ct.connect.Repo.Resource.SmsMessage in ct.connect)

Target tables:
- sms
- sms_message

Target enums:
- sms_gateway_enum ('Unknown', 'Infini')
- sms_message_status_enum ('Pending', 'Active', 'Disapproved', 'Disabled')
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

# Gateway enum mapping
GATEWAY_NAME_TO_INT = {
    "unknown": -1,
    "infini": 2,
}
GATEWAY_INT_TO_NAME = {
    -1: "Unknown",
    2: "Infini",
}

# SMS Message status enum mapping
STATUS_NAME_TO_INT = {
    "pending": 0,
    "active": 1,
    "disapproved": 90,
    "disabled": 99,
}
STATUS_INT_TO_NAME = {
    0: "Pending",
    1: "Active",
    90: "Disapproved",
    99: "Disabled",
}


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
    sms_collection: str
    sms_messages_collection: str
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
        description="Migrate SMS-related collections (SMs, SmsMessages) from RavenDB to PostgreSQL"
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
        "--sms-collection",
        default=os.getenv("SMS_COLLECTION", "SMs"),
        help="RavenDB collection name for SMs (default: SMs)",
    )
    parser.add_argument(
        "--sms-messages-collection",
        default=os.getenv("SMS_MESSAGES_COLLECTION", "SmsMessages"),
        help="RavenDB collection name for SmsMessages (default: SmsMessages)",
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
            "Default when omitted: validation/sms-migration-summary-<timestamp>.json"
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
        sms_collection=args.sms_collection,
        sms_messages_collection=args.sms_messages_collection,
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
    """Validate and return canonical UUID string, converting empty string to None."""
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


def map_gateway(val: Any) -> str:
    """Map gateway value (string or integer) to sms_gateway_enum name ('Unknown', 'Infini')."""
    if val is None:
        return "Unknown"
    val_str = str(val).strip()
    try:
        # If integer
        val_int = int(val_str)
        return GATEWAY_INT_TO_NAME.get(val_int, "Unknown")
    except ValueError:
        # String name
        code = GATEWAY_NAME_TO_INT.get(val_str.lower(), -1)
        return GATEWAY_INT_TO_NAME.get(code, "Unknown")


def map_status(val: Any) -> Tuple[int, str]:
    """Map status value (string or integer) to (integer_code, enum_name)."""
    if val is None:
        return 0, "Pending"
    val_str = str(val).strip()
    try:
        # If integer
        val_int = int(val_str)
        name = STATUS_INT_TO_NAME.get(val_int, "Pending")
        return val_int, name
    except ValueError:
        # String name
        code = STATUS_NAME_TO_INT.get(val_str.lower(), 0)
        name = STATUS_INT_TO_NAME.get(code, "Pending")
        return code, name


def extract_sms_fields(
    doc: Dict[str, Any]
) -> Tuple[
    str,
    str,
    Optional[str],
    List[Dict[str, str]],
    str,
    Optional[str],
    Optional[str],
    Optional[str],
    datetime,
    Optional[str],
    Optional[datetime],
    Optional[str],
]:
    """Extract and validate fields for sms table."""
    metadata = doc.get("@metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    sms_id = clean_uuid(raw_id)
    if not sms_id:
        raise ValueError(f"SMS document missing valid GUID id: {raw_id}")

    gateway = map_gateway(doc.get("Gateway"))
    gateway_result = doc.get("GatewayResult")
    gateway_result_str = str(gateway_result).strip() if gateway_result is not None else None

    # Recipients (list of {name, mobile})
    raw_recipients = doc.get("Recipients")
    recipients: List[Dict[str, str]] = []
    if isinstance(raw_recipients, list):
        for item in raw_recipients:
            if isinstance(item, dict):
                recipients.append(
                    {
                        "name": str(item.get("name") or "").strip(),
                        "mobile": str(item.get("mobile") or "").strip(),
                    }
                )

    message = str(doc.get("Message") or "").strip()
    sms_ref_id_val = doc.get("SMSRefId")
    sms_ref_id = str(sms_ref_id_val).strip() if sms_ref_id_val is not None else None

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))

    raw_created_on = doc.get("CreatedOn") or metadata.get("@last-modified")
    created_on = parse_iso_timestamp(raw_created_on) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))

    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        sms_id,
        gateway,
        gateway_result_str,
        recipients,
        message,
        sms_ref_id,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


def extract_sms_message_fields(
    doc: Dict[str, Any]
) -> Tuple[
    str,
    str,
    int,
    str,
    str,
    int,
    int,
    Optional[str],
    Optional[str],
    Optional[str],
    datetime,
    Optional[str],
    Optional[datetime],
    Optional[str],
]:
    """Extract and validate fields for sms_message table."""
    metadata = doc.get("@metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    msg_id = clean_uuid(raw_id)
    if not msg_id:
        raise ValueError(f"SmsMessage document missing valid GUID id: {raw_id}")

    message = str(doc.get("Message") or "").strip()
    status_code, status_name = map_status(doc.get("Status"))
    status_as_string = str(doc.get("StatusAsString") or status_name).strip()

    try:
        length = int(doc.get("Length") or len(message))
    except (ValueError, TypeError):
        length = len(message)

    try:
        credits_val = int(doc.get("Credits") or 1)
    except (ValueError, TypeError):
        credits_val = 1

    reason_val = doc.get("Reason")
    reason = str(reason_val).strip() if reason_val is not None else None

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))

    raw_created_on = doc.get("CreatedOn") or metadata.get("@last-modified")
    created_on = parse_iso_timestamp(raw_created_on) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))

    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        msg_id,
        message,
        status_code,
        status_name,
        status_as_string,
        length,
        credits_val,
        reason,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
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
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sms_gateway_enum') THEN
                CREATE TYPE sms_gateway_enum AS ENUM (
                    'Unknown',
                    'Infini'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sms_message_status_enum') THEN
                CREATE TYPE sms_message_status_enum AS ENUM (
                    'Pending',
                    'Active',
                    'Disapproved',
                    'Disabled'
                );
            END IF;
        END $$;
        """
    )

    # 2. sms table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sms (
            id UUID PRIMARY KEY,
            gateway sms_gateway_enum NOT NULL,
            gateway_result TEXT,
            recipients JSONB NOT NULL DEFAULT '[]'::jsonb,
            message TEXT NOT NULL,
            sms_ref_id VARCHAR(100),
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );
        ALTER TABLE sms DROP COLUMN IF EXISTS gateway_name;
        ALTER TABLE sms DROP COLUMN IF EXISTS collection;
        ALTER TABLE sms DROP COLUMN IF EXISTS raven_clr_type;
        ALTER TABLE sms DROP COLUMN IF EXISTS raven_change_vector;
        ALTER TABLE sms DROP COLUMN IF EXISTS raven_last_modified;
        ALTER TABLE sms ALTER COLUMN sms_ref_id TYPE VARCHAR(100);
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sms' AND column_name = 'gateway' AND data_type = 'integer'
            ) THEN
                ALTER TABLE sms DROP COLUMN gateway;
                ALTER TABLE sms ADD COLUMN gateway sms_gateway_enum NOT NULL DEFAULT 'Unknown';
            END IF;
        END $$;
        """
    )

    # 3. sms_message table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sms_message (
            id UUID PRIMARY KEY,
            message TEXT NOT NULL,
            status INTEGER NOT NULL,
            status_name sms_message_status_enum NOT NULL,
            status_as_string TEXT NOT NULL,
            length INTEGER NOT NULL,
            credits INTEGER NOT NULL,
            reason TEXT,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );
        ALTER TABLE sms_message DROP COLUMN IF EXISTS collection;
        ALTER TABLE sms_message DROP COLUMN IF EXISTS raven_clr_type;
        ALTER TABLE sms_message DROP COLUMN IF EXISTS raven_change_vector;
        ALTER TABLE sms_message DROP COLUMN IF EXISTS raven_last_modified;
        """
    )

    # 4. Indexes
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS sms_owner_id_idx ON sms (owner_id);
        CREATE INDEX IF NOT EXISTS sms_created_on_idx ON sms (created_on);
        CREATE INDEX IF NOT EXISTS sms_created_by_idx ON sms (created_by);
        CREATE INDEX IF NOT EXISTS sms_gateway_idx ON sms (gateway);
        CREATE INDEX IF NOT EXISTS sms_recipients_gin_idx ON sms USING GIN (recipients);

        CREATE INDEX IF NOT EXISTS sms_message_owner_id_idx ON sms_message (owner_id);
        CREATE INDEX IF NOT EXISTS sms_message_created_on_idx ON sms_message (created_on);
        CREATE INDEX IF NOT EXISTS sms_message_status_idx ON sms_message (status);
        """
    )

    # Clean up any previously created views if present
    cur.execute(
        """
        DROP VIEW IF EXISTS sms_messages, v_sms_recipient CASCADE;
        """
    )


# ---------------------------------------------------------------------------
# Database Upsert Operations
# ---------------------------------------------------------------------------


def upsert_sms_document(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently insert or update an SMS document in PostgreSQL."""
    (
        sms_id,
        gateway,
        gateway_result_str,
        recipients,
        message,
        sms_ref_id,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    ) = extract_sms_fields(doc)

    sql = """
        INSERT INTO sms (
            id,
            gateway,
            gateway_result,
            recipients,
            message,
            sms_ref_id,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            gateway = EXCLUDED.gateway,
            gateway_result = EXCLUDED.gateway_result,
            recipients = EXCLUDED.recipients,
            message = EXCLUDED.message,
            sms_ref_id = EXCLUDED.sms_ref_id,
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
            sms_id,
            gateway,
            gateway_result_str,
            Json(recipients),
            message,
            sms_ref_id,
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
    return UpsertResult(record_id=sms_id, inserted=inserted)


def upsert_sms_message_document(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently insert or update an SmsMessage document in PostgreSQL."""
    (
        msg_id,
        message,
        status_code,
        status_name,
        status_as_string,
        length,
        credits_val,
        reason,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    ) = extract_sms_message_fields(doc)

    sql = """
        INSERT INTO sms_message (
            id,
            message,
            status,
            status_name,
            status_as_string,
            length,
            credits,
            reason,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            message = EXCLUDED.message,
            status = EXCLUDED.status,
            status_name = EXCLUDED.status_name,
            status_as_string = EXCLUDED.status_as_string,
            length = EXCLUDED.length,
            credits = EXCLUDED.credits,
            reason = EXCLUDED.reason,
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
            msg_id,
            message,
            status_code,
            status_name,
            status_as_string,
            length,
            credits_val,
            reason,
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
    return UpsertResult(record_id=msg_id, inserted=inserted)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Main Routine
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the end-to-end migration for SMs and SmsMessages."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collections=({cfg.sms_collection}, {cfg.sms_messages_collection})"
        )
        print("[1/5] Fetching RavenDB documents...")
        sms_docs = raven_query_collection(requests_session, cfg, cfg.sms_collection)
        sms_messages_docs = raven_query_collection(
            requests_session, cfg, cfg.sms_messages_collection
        )
        print(
            f"Fetched sms={len(sms_docs)}, sms_messages={len(sms_messages_docs)}"
        )

        print("[2/5] Connecting PostgreSQL...")
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

        loaded_sms = 0
        new_sms = 0
        loaded_sms_messages = 0
        new_sms_messages = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/5] Ensuring target schema & enums...")
                ensure_target_schema(cur)

                print("[4/5] Upserting SMs...")
                for d in sms_docs:
                    res = upsert_sms_document(cur, d)
                    loaded_sms += 1
                    new_sms += int(res.inserted)

                print("[5/5] Upserting SmsMessages...")
                for d in sms_messages_docs:
                    res = upsert_sms_message_document(cur, d)
                    loaded_sms_messages += 1
                    new_sms_messages += int(res.inserted)

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
                "sms_collection": cfg.sms_collection,
                "sms_messages_collection": cfg.sms_messages_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "sms_processed": loaded_sms,
                "new_sms_inserted": new_sms,
                "sms_messages_processed": loaded_sms_messages,
                "new_sms_messages_inserted": new_sms_messages,
            },
        }

        print("Migration completed.")
        print(f"sms_processed: {loaded_sms}")
        print(f"new_sms_inserted: {new_sms}")
        print(f"sms_messages_processed: {loaded_sms_messages}")
        print(f"new_sms_messages_inserted: {new_sms_messages}")

        if cfg.write_summary_json:
            ts_compact = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            summary_path = (
                cfg.summary_json_path
                or f"validation/sms-migration-summary-{ts_compact}.json"
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
