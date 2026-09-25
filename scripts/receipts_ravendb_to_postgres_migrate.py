#!/usr/bin/env python3
"""
Extract Receipts data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs and JSONBs,
and load into PostgreSQL.

Target table:
- receipts
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

UUID_NAMESPACE_RECEIPTS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


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
    receipts_collection: str
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
        description="Migrate Receipts from RavenDB to PostgreSQL"
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
        "--receipts-collection",
        default=os.getenv("RECEIPTS_COLLECTION", "Receipts"),
        help="RavenDB collection name for receipts (default: Receipts)",
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
        receipts_collection=args.receipts_collection,
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


def clean_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "1", "yes"}


def clean_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def clean_decimal(val: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Parse numeric/decimal value into Decimal(18, 2)."""
    if val is None:
        return default
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"))
    text = str(val).strip().replace(",", "")
    if not text:
        return default
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return default


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


# -----------------------------------------------------------------------------
# Enum Mappings (Exact match to C# Enums)
# -----------------------------------------------------------------------------

PAYMENT_MODE_MAP: Dict[Any, str] = {
    10: "Cash",
    20: "Cheque",
    30: "DemandDraft",
    40: "NetBanking",
    50: "UPI",
    "cash": "Cash",
    "cheque": "Cheque",
    "check": "Cheque",
    "dd": "DemandDraft",
    "demanddraft": "DemandDraft",
    "demand_draft": "DemandDraft",
    "netbanking": "NetBanking",
    "net_banking": "NetBanking",
    "online": "NetBanking",
    "card": "NetBanking",
    "upi": "UPI",
    "other": "Other",
    "unknown": "Unknown",
}

RECEIPT_STATUS_MAP: Dict[Any, str] = {
    0: "Unknown",
    1: "Active",
    99: "Cancelled",
    "active": "Active",
    "cancelled": "Cancelled",
    "canceled": "Cancelled",
    "disabled": "Cancelled",
    "inactive": "Cancelled",
    "unknown": "Unknown",
}

RECEIPT_TYPE_MAP: Dict[Any, str] = {
    0: "Unknown",
    10: "Regular",
    20: "Donation",
    "regular": "Regular",
    "donation": "Donation",
    "unknown": "Unknown",
}


def map_payment_mode(val: Any) -> str:
    if val is None:
        return "Cash"
    if isinstance(val, int):
        return PAYMENT_MODE_MAP.get(val, "Cash")
    s = str(val).strip()
    if s.isdigit():
        return PAYMENT_MODE_MAP.get(int(s), "Cash")
    norm = s.lower().replace(" ", "").replace("_", "")
    return PAYMENT_MODE_MAP.get(norm, "Cash")


def map_receipt_status(val: Any) -> str:
    if val is None:
        return "Active"
    if isinstance(val, int):
        return RECEIPT_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return RECEIPT_STATUS_MAP.get(int(s), "Active")
    norm = s.lower().replace(" ", "").replace("_", "")
    return RECEIPT_STATUS_MAP.get(norm, "Active")


def map_receipt_type(val: Any) -> str:
    if val is None:
        return "Regular"
    if isinstance(val, int):
        return RECEIPT_TYPE_MAP.get(val, "Regular")
    s = str(val).strip()
    if s.isdigit():
        return RECEIPT_TYPE_MAP.get(int(s), "Regular")
    norm = s.lower().replace(" ", "").replace("_", "")
    return RECEIPT_TYPE_MAP.get(norm, "Regular")


# -----------------------------------------------------------------------------
# Document Field Extractor (Only RavenDB fields, no metadata columns)
# -----------------------------------------------------------------------------


def extract_receipt_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for receipts table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    receipt_id = clean_uuid(raw_id)
    if not receipt_id and raw_id:
        receipt_id = str(
            uuid.uuid5(UUID_NAMESPACE_RECEIPTS, str(raw_id).strip())
        ).lower()
    if not receipt_id:
        raise ValueError(f"Receipt missing valid ID: {raw_id}")

    number = clean_str(doc.get("Number"), 50)
    inst_id = clean_uuid(doc.get("InstId"))
    date_val = parse_iso_timestamp(doc.get("Date"))

    customer = as_json(doc.get("Customer") if isinstance(doc.get("Customer"), dict) else {}, default_val={})
    order_items = as_json(doc.get("OrderItems") if isinstance(doc.get("OrderItems"), list) else [], default_val=[])

    total_amount = clean_decimal(doc.get("TotalAmount"), default=Decimal("0.00"))
    received_by = clean_str(doc.get("ReceivedBy"), 150)
    payment_mode = map_payment_mode(doc.get("PaymentMode"))

    fin_inst = doc.get("FinancialInstrument")
    financial_instrument = as_json(fin_inst) if fin_inst is not None else None

    status = map_receipt_status(doc.get("Status"))
    receipt_type = map_receipt_type(doc.get("ReceiptType"))
    revenue_sharing_enabled = clean_bool(doc.get("RevenueSharingEnabled"), default=False)
    # In .NET ct.gr Receipt.cs: public int RevenueShare { get; set; }
    revenue_share = clean_int(doc.get("RevenueShare")) or 0

    meta = as_json(doc.get("Meta") if isinstance(doc.get("Meta"), dict) else {}, default_val={})
    html = clean_str(doc.get("HTML"))
    # In .NET ct.gr Receipt.cs: public string RefNo { get; set; }
    ref_no = clean_str(doc.get("RefNo"), 100)

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        receipt_id,
        number,
        inst_id,
        date_val,
        customer,
        order_items,
        total_amount,
        received_by,
        payment_mode,
        financial_instrument,
        status,
        receipt_type,
        revenue_sharing_enabled,
        revenue_share,
        meta,
        html,
        ref_no,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup (Only primary key, no secondary indexes)
# -----------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target enums and receipts table without secondary indexes."""
    cur.execute(
        """
        -- 1. Create or extend Enums
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'receipt_payment_mode_enum') THEN
                CREATE TYPE receipt_payment_mode_enum AS ENUM (
                    'Cash',
                    'Cheque',
                    'DemandDraft',
                    'NetBanking',
                    'UPI',
                    'Other',
                    'Unknown'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'receipt_status_enum') THEN
                CREATE TYPE receipt_status_enum AS ENUM (
                    'Active',
                    'Cancelled',
                    'Disabled',
                    'Unknown'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'receipt_type_enum') THEN
                CREATE TYPE receipt_type_enum AS ENUM (
                    'Regular',
                    'Donation',
                    'Unknown'
                );
            END IF;
        END $$;

        -- 2. Create Target Table (No secondary indexes)
        CREATE TABLE IF NOT EXISTS receipts (
            id UUID PRIMARY KEY,
            number VARCHAR(50),
            inst_id UUID,
            date TIMESTAMPTZ,
            customer JSONB DEFAULT '{}'::jsonb,
            order_items JSONB DEFAULT '[]'::jsonb,
            total_amount NUMERIC(18, 2),
            received_by VARCHAR(150),
            payment_mode receipt_payment_mode_enum NOT NULL DEFAULT 'Cash',
            financial_instrument JSONB,
            status receipt_status_enum NOT NULL DEFAULT 'Active',
            receipt_type receipt_type_enum NOT NULL DEFAULT 'Regular',
            revenue_sharing_enabled BOOLEAN DEFAULT FALSE,
            revenue_share INTEGER DEFAULT 0,
            meta JSONB DEFAULT '{}'::jsonb,
            html TEXT,
            ref_no VARCHAR(100),
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- Backward-compatibility view for singular 'receipt'
        CREATE OR REPLACE VIEW receipt AS SELECT * FROM receipts;
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operation
# -----------------------------------------------------------------------------


def upsert_receipt(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert a Receipt document."""
    fields = extract_receipt_fields(doc)
    sql = """
        INSERT INTO receipts (
            id,
            number,
            inst_id,
            date,
            customer,
            order_items,
            total_amount,
            received_by,
            payment_mode,
            financial_instrument,
            status,
            receipt_type,
            revenue_sharing_enabled,
            revenue_share,
            meta,
            html,
            ref_no,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            number = EXCLUDED.number,
            inst_id = EXCLUDED.inst_id,
            date = EXCLUDED.date,
            customer = EXCLUDED.customer,
            order_items = EXCLUDED.order_items,
            total_amount = EXCLUDED.total_amount,
            received_by = EXCLUDED.received_by,
            payment_mode = EXCLUDED.payment_mode,
            financial_instrument = EXCLUDED.financial_instrument,
            status = EXCLUDED.status,
            receipt_type = EXCLUDED.receipt_type,
            revenue_sharing_enabled = EXCLUDED.revenue_sharing_enabled,
            revenue_share = EXCLUDED.revenue_share,
            meta = EXCLUDED.meta,
            html = EXCLUDED.html,
            ref_no = EXCLUDED.ref_no,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by
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
    """Run the end-to-end migration for Receipts."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collection={cfg.receipts_collection}"
        )
        print("[1/4] Fetching RavenDB documents...")
        receipt_docs = raven_query_collection(
            requests_session, cfg, cfg.receipts_collection
        )

        # Fallback to singular name if 0 docs fetched with default collection name
        if not receipt_docs and cfg.receipts_collection == "Receipts":
            try:
                alt_docs = raven_query_collection(requests_session, cfg, "Receipt")
                if alt_docs:
                    print(f"Fallback: Loaded {len(alt_docs)} docs from 'Receipt'.")
                    receipt_docs = alt_docs
            except Exception:
                pass

        print(f"Fetched receipts={len(receipt_docs)}")

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

        loaded_receipts = 0
        new_receipts = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/4] Upserting receipts...")
                for d in receipt_docs:
                    res = upsert_receipt(cur, d)
                    loaded_receipts += 1
                    new_receipts += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collection": cfg.receipts_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "receipts_processed": loaded_receipts,
                "new_receipts_inserted": new_receipts,
            },
        }

        print("Migration completed.")
        print(f"receipts_processed: {loaded_receipts}")
        print(f"new_receipts_inserted: {new_receipts}")

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
