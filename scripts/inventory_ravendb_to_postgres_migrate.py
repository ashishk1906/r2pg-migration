#!/usr/bin/env python3
"""
Extract InventoryItemViews and InventoryJournalViews data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs and JSONB,
and load into PostgreSQL.

Target tables:
- inventory_item_views
- inventory_journal_views
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
import uuid

import psycopg2
from psycopg2.extras import Json
import requests

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

UUID_NAMESPACE_INVENTORY_ITEMS = uuid.UUID("6ba7b813-9dad-11d1-80b4-00c04fd430c8")
UUID_NAMESPACE_INVENTORY_JOURNALS = uuid.UUID("6ba7b814-9dad-11d1-80b4-00c04fd430c8")

INVENTORY_STATUS_MAP: Dict[Any, str] = {
    "active": "Active",
    "disabled": "Disabled",
    "archived": "Archived",
    "unknown": "Unknown",
    "1": "Active",
    "99": "Disabled",
    1: "Active",
    99: "Disabled",
}

INVENTORY_TYPE_MAP: Dict[str, str] = {
    "item": "Item",
    "group": "Group",
    "unknown": "Unknown",
}

JOURNAL_ENTRY_TYPE_MAP: Dict[str, str] = {
    "cr": "Cr",
    "credit": "Cr",
    "dr": "Dr",
    "debit": "Dr",
    "unknown": "Unknown",
}


# -----------------------------------------------------------------------------
# Configuration & Data Models
# -----------------------------------------------------------------------------


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
    inventory_item_views_collection: str
    inventory_journal_views_collection: str
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
        description="Migrate Inventory data from RavenDB to PostgreSQL"
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
    parser.add_argument("--pg-port", type=int, default=int(os.getenv("PG_PORT", "5432")))
    parser.add_argument("--pg-db", default=os.getenv("PG_DB", "rpg"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    parser.add_argument("--pg-password", default=os.getenv("PG_PASSWORD"))

    parser.add_argument(
        "--inventory-item-views-collection",
        default=os.getenv("INVENTORY_ITEM_VIEWS_COLLECTION", "InventoryItemViews"),
        help="RavenDB collection name for inventory item views (default: InventoryItemViews)",
    )
    parser.add_argument(
        "--inventory-journal-views-collection",
        default=os.getenv("INVENTORY_JOURNAL_VIEWS_COLLECTION", "InventoryJournalViews"),
        help="RavenDB collection name for inventory journal views (default: InventoryJournalViews)",
    )
    parser.add_argument(
        "--page-size", type=int, default=int(os.getenv("PAGE_SIZE", "500"))
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=int(os.getenv("TIMEOUT_SEC", "30"))
    )
    parser.add_argument(
        "--summary-json-path",
        default=os.getenv("MIGRATION_SUMMARY_JSON"),
        help="Optional output path for post-run JSON artifact.",
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
    if args.raven_cert_file and not args.raven_url.lower().startswith("https://"):
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
        inventory_item_views_collection=args.inventory_item_views_collection,
        inventory_journal_views_collection=args.inventory_journal_views_collection,
        page_size=args.page_size,
        timeout_sec=args.timeout_sec,
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
    )


def write_summary_json(path_text: str, payload: Dict[str, Any]) -> str:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path.resolve())


# -----------------------------------------------------------------------------
# Cleaners & Value Helpers
# -----------------------------------------------------------------------------


def clean_uuid(val: Any) -> Optional[str]:
    """Extract standard UUID lowercase string from text/metadata."""
    if not val:
        return None
    match = UUID_RE.search(str(val))
    return match.group(0).lower() if match else None


def clean_str(val: Any, max_len: Optional[int] = None) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return s[:max_len] if max_len else s


def clean_decimal(
    val: Any, default: Optional[Decimal] = Decimal("0.00")
) -> Optional[Decimal]:
    if val is None:
        return default
    try:
        return Decimal(str(val).strip().replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return default


def clean_quantity(
    val: Any, default: Optional[Decimal] = Decimal("0.0000")
) -> Optional[Decimal]:
    if val is None:
        return default
    try:
        return Decimal(str(val).strip().replace(",", "")).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError, TypeError):
        return default


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


def as_json(value: Any, default_val: Any = None) -> Optional[Json]:
    """Wrap dict/list for JSONB writes while preserving SQL NULL semantics."""
    if value is None:
        return Json(default_val) if default_val is not None else None
    return Json(value)


def parse_iso_timestamp(val: Any) -> Optional[datetime]:
    """Parse ISO timestamp safely, preserving 0001-01-01 without converting to NULL."""
    if not val:
        return None
    text = str(val).strip()
    if not text:
        return None

    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    if "." in normalized:
        base, frac = normalized.split(".", 1)
        tz_pos = max(frac.find("+"), frac.find("-"))
        if tz_pos >= 0:
            frac_part = frac[:tz_pos]
            tz_part = frac[tz_pos:]
        else:
            frac_part = frac
            tz_part = ""
        digits = "".join(ch for ch in frac_part if ch.isdigit())[:6]
        normalized = f"{base}.{digits}{tz_part}" if digits else f"{base}{tz_part}"
    if "+" not in normalized[10:] and "-" not in normalized[10:]:
        normalized = f"{normalized}+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def map_inventory_status(raw_val: Any) -> str:
    """Map status string/int to inventory_status_enum."""
    if raw_val is None:
        return "Active"
    if isinstance(raw_val, int):
        return INVENTORY_STATUS_MAP.get(raw_val, "Active")
    norm = str(raw_val).strip().lower()
    return INVENTORY_STATUS_MAP.get(norm, "Active")


def map_inventory_type(raw_val: Any) -> str:
    """Map inventory type string to inventory_type_enum."""
    if raw_val is None:
        return "Item"
    norm = str(raw_val).strip().lower()
    return INVENTORY_TYPE_MAP.get(norm, "Item")


def map_journal_entry_type(raw_val: Any) -> str:
    """Map journal entry type string to journal_entry_type_enum."""
    if raw_val is None:
        return "Cr"
    norm = str(raw_val).strip().lower()
    return JOURNAL_ENTRY_TYPE_MAP.get(norm, "Cr")


# -----------------------------------------------------------------------------
# Document Field Extractors (Only RavenDB fields, no metadata columns)
# -----------------------------------------------------------------------------


def extract_inventory_item_view_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for inventory_item_views table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    item_id = clean_uuid(raw_id)
    if not item_id and raw_id:
        item_id = str(
            uuid.uuid5(UUID_NAMESPACE_INVENTORY_ITEMS, str(raw_id).strip())
        ).lower()
    if not item_id:
        raise ValueError(f"InventoryItemView missing valid ID: {raw_id}")

    name = clean_str(doc.get("Name"), 255)
    group_id = clean_uuid(doc.get("GroupId"))
    inventory_type = map_inventory_type(doc.get("InventoryType"))
    uom = clean_str(doc.get("UOM"), 50)
    owner_id = clean_uuid(doc.get("OwnerId"))
    tags = clean_string_list(doc.get("Tags"))
    attributes = as_json(
        doc.get("Attributes") if isinstance(doc.get("Attributes"), dict) else {},
        default_val={},
    )
    status = map_inventory_status(doc.get("Status"))

    return (
        item_id,
        name,
        group_id,
        inventory_type,
        uom,
        owner_id,
        tags,
        attributes,
        status,
    )


def extract_inventory_journal_view_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for inventory_journal_views table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    journal_id = clean_uuid(raw_id)
    if not journal_id and raw_id:
        journal_id = str(
            uuid.uuid5(UUID_NAMESPACE_INVENTORY_JOURNALS, str(raw_id).strip())
        ).lower()
    if not journal_id:
        raise ValueError(f"InventoryJournalView missing valid ID: {raw_id}")

    owner_id = clean_uuid(doc.get("OwnerId"))
    inventory_item_id = clean_uuid(doc.get("InventoryItemId"))
    name = clean_str(doc.get("Name"), 255)
    date_val = parse_iso_timestamp(doc.get("Date"))
    uom = clean_str(doc.get("UOM"), 50)
    quantity = clean_quantity(doc.get("Quantity"), default=Decimal("0.0000"))
    rate = clean_decimal(doc.get("Rate"), default=Decimal("0.00"))
    particulars = clean_str(doc.get("Particulars"))
    reference = clean_str(doc.get("Reference"), 255)
    inventory_journal_id = clean_uuid(doc.get("InventoryJournalId"))
    accounting_journal_id = clean_uuid(doc.get("AccountingJournalId"))
    party_id = clean_uuid(doc.get("PartyId"))
    party_name = clean_str(doc.get("PartyName"), 255)
    journal_entry_type = map_journal_entry_type(doc.get("JournalEntryType"))
    status = map_inventory_status(doc.get("Status"))

    return (
        journal_id,
        owner_id,
        inventory_item_id,
        name,
        date_val,
        uom,
        quantity,
        rate,
        particulars,
        reference,
        inventory_journal_id,
        accounting_journal_id,
        party_id,
        party_name,
        journal_entry_type,
        status,
    )


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup (Only primary key, no secondary indexes, no views)
# -----------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target enums and inventory tables without secondary indexes or views."""
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'inventory_status_enum') THEN
                CREATE TYPE inventory_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Disabled',
                    'Archived'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'inventory_type_enum') THEN
                CREATE TYPE inventory_type_enum AS ENUM (
                    'Unknown',
                    'Item',
                    'Group'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'journal_entry_type_enum') THEN
                CREATE TYPE journal_entry_type_enum AS ENUM (
                    'Unknown',
                    'Cr',
                    'Dr'
                );
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS inventory_item_views (
            id UUID PRIMARY KEY,
            name VARCHAR(255),
            group_id UUID,
            inventory_type inventory_type_enum NOT NULL DEFAULT 'Item',
            uom VARCHAR(50),
            owner_id UUID,
            tags TEXT[] DEFAULT '{}'::text[],
            attributes JSONB DEFAULT '{}'::jsonb,
            status inventory_status_enum NOT NULL DEFAULT 'Active'
        );

        CREATE TABLE IF NOT EXISTS inventory_journal_views (
            id UUID PRIMARY KEY,
            owner_id UUID,
            inventory_item_id UUID,
            name VARCHAR(255),
            date TIMESTAMPTZ,
            uom VARCHAR(50),
            quantity NUMERIC(18, 4) DEFAULT 0.0000,
            rate NUMERIC(18, 2) DEFAULT 0.00,
            particulars TEXT,
            reference VARCHAR(255),
            inventory_journal_id UUID,
            accounting_journal_id UUID,
            party_id UUID,
            party_name VARCHAR(255),
            journal_entry_type journal_entry_type_enum NOT NULL DEFAULT 'Cr',
            status inventory_status_enum NOT NULL DEFAULT 'Active'
        );
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operations
# -----------------------------------------------------------------------------


def upsert_inventory_item_view(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert an InventoryItemView document."""
    fields = extract_inventory_item_view_fields(doc)
    sql = """
        INSERT INTO inventory_item_views (
            id,
            name,
            group_id,
            inventory_type,
            uom,
            owner_id,
            tags,
            attributes,
            status
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            group_id = EXCLUDED.group_id,
            inventory_type = EXCLUDED.inventory_type,
            uom = EXCLUDED.uom,
            owner_id = EXCLUDED.owner_id,
            tags = EXCLUDED.tags,
            attributes = EXCLUDED.attributes,
            status = EXCLUDED.status
        RETURNING (xmax = 0);
    """
    cur.execute(sql, fields)
    row = cur.fetchone()
    inserted = bool(row[0]) if row else False
    return UpsertResult(record_id=fields[0], inserted=inserted)


def upsert_inventory_journal_view(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert an InventoryJournalView document."""
    fields = extract_inventory_journal_view_fields(doc)
    sql = """
        INSERT INTO inventory_journal_views (
            id,
            owner_id,
            inventory_item_id,
            name,
            date,
            uom,
            quantity,
            rate,
            particulars,
            reference,
            inventory_journal_id,
            accounting_journal_id,
            party_id,
            party_name,
            journal_entry_type,
            status
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            owner_id = EXCLUDED.owner_id,
            inventory_item_id = EXCLUDED.inventory_item_id,
            name = EXCLUDED.name,
            date = EXCLUDED.date,
            uom = EXCLUDED.uom,
            quantity = EXCLUDED.quantity,
            rate = EXCLUDED.rate,
            particulars = EXCLUDED.particulars,
            reference = EXCLUDED.reference,
            inventory_journal_id = EXCLUDED.inventory_journal_id,
            accounting_journal_id = EXCLUDED.accounting_journal_id,
            party_id = EXCLUDED.party_id,
            party_name = EXCLUDED.party_name,
            journal_entry_type = EXCLUDED.journal_entry_type,
            status = EXCLUDED.status
        RETURNING (xmax = 0);
    """
    cur.execute(sql, fields)
    row = cur.fetchone()
    inserted = bool(row[0]) if row else False
    return UpsertResult(record_id=fields[0], inserted=inserted)


# -----------------------------------------------------------------------------
# RavenDB Connection & Extraction
# -----------------------------------------------------------------------------


def configure_raven_session(session: requests.Session, cfg: Config) -> None:
    """Configure RavenDB TLS verification and optional PKCS#12 client auth."""
    if cfg.raven_cert_file:
        try:
            from requests_pkcs12 import Pkcs12Adapter
        except ImportError as exc:
            raise RuntimeError(
                "PKCS#12 RavenDB authentication requires requests-pkcs12. "
                "Install dependencies with: python -m pip install requests-pkcs12"
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
            raise RuntimeError(f"Unexpected RavenDB response for {collection_name}")
        results = body.get("Results", [])
        if not isinstance(results, list):
            raise RuntimeError(f"Unexpected RavenDB response for {collection_name}")

        if not results:
            break

        docs.extend(results)
        start += len(results)

    return docs


# -----------------------------------------------------------------------------
# Main Routine
# -----------------------------------------------------------------------------


def main() -> int:
    """Run the end-to-end migration for Inventory tables."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}\n"
            f"  - items collection: {cfg.inventory_item_views_collection}\n"
            f"  - journals collection: {cfg.inventory_journal_views_collection}"
        )
        print("[1/4] Fetching RavenDB documents...")
        item_docs = raven_query_collection(
            requests_session, cfg, cfg.inventory_item_views_collection
        )
        if not item_docs and cfg.inventory_item_views_collection == "InventoryItemViews":
            try:
                alt_docs = raven_query_collection(requests_session, cfg, "InventoryItemView")
                if alt_docs:
                    print(f"Fallback: Loaded {len(alt_docs)} docs from 'InventoryItemView'.")
                    item_docs = alt_docs
            except Exception:
                pass

        journal_docs = raven_query_collection(
            requests_session, cfg, cfg.inventory_journal_views_collection
        )
        if not journal_docs and cfg.inventory_journal_views_collection == "InventoryJournalViews":
            try:
                alt_docs = raven_query_collection(requests_session, cfg, "InventoryJournalView")
                if alt_docs:
                    print(f"Fallback: Loaded {len(alt_docs)} docs from 'InventoryJournalView'.")
                    journal_docs = alt_docs
            except Exception:
                pass

        print(f"Fetched inventory_items={len(item_docs)}, inventory_journals={len(journal_docs)}")

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

        loaded_items = 0
        new_items = 0
        loaded_journals = 0
        new_journals = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/4] Upserting inventory items...")
                for d in item_docs:
                    res = upsert_inventory_item_view(cur, d)
                    loaded_items += 1
                    new_items += int(res.inserted)

                print("[4/4] Upserting inventory journals...")
                for d in journal_docs:
                    res = upsert_inventory_journal_view(cur, d)
                    loaded_journals += 1
                    new_journals += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collections": [
                    cfg.inventory_item_views_collection,
                    cfg.inventory_journal_views_collection,
                ],
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "inventory_item_views_processed": loaded_items,
                "new_inventory_item_views_inserted": new_items,
                "inventory_journal_views_processed": loaded_journals,
                "new_inventory_journal_views_inserted": new_journals,
            },
        }

        print("Migration completed.")
        print(f"inventory_item_views_processed: {loaded_items} (new: {new_items})")
        print(f"inventory_journal_views_processed: {loaded_journals} (new: {new_journals})")

        if cfg.write_summary_json:
            output_path = cfg.summary_json_path
            if not output_path:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                output_path = f"validation/migration-summary-{timestamp}.json"
            written = write_summary_json(output_path, summary)
            print(f"Summary JSON written: {written}")

        return 0

    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()
        requests_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
