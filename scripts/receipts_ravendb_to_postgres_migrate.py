#!/usr/bin/env python3
"""
Extract Receipts data from RavenDB, transform it to PostgreSQL schema,
and load into PostgreSQL.

Before running: set all required configuration values in .env
(or pass them explicitly as command-line arguments).

Target table:
- receipt
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
from typing import Any, Dict, List, Optional, Sequence, Tuple

import psycopg2
import requests

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# Enum mappings for Receipt
PAYMENT_MODE_MAP: Dict[str, int] = {
    "cash": 10,
    "cheque": 20,
    "check": 20,
    "dd": 30,
    "demanddraft": 30,
    "demand_draft": 30,
    "netbanking": 40,
    "net_banking": 40,
    "online": 40,
    "card": 40,
    "upi": 50,
}

STATUS_MAP: Dict[str, int] = {
    "active": 1,
    "cancelled": 99,
    "canceled": 99,
    "inactive": 99,
    "disabled": 99,
}

RECEIPT_TYPE_MAP: Dict[str, int] = {
    "unknown": 0,
    "regular": 10,
    "donation": 20,
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
    receipts_collection: str
    page_size: int
    timeout_sec: int
    summary_json_path: Optional[str]
    write_summary_json: bool
    inspect_source_only: bool = False


@dataclass
class UpsertResult:
    record_id: str
    inserted: bool


def load_env_file(env_path: str) -> None:
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
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
        description="Migrate Receipts data from RavenDB to PostgreSQL"
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
    )
    parser.add_argument(
        "--pg-host", default=os.getenv("PG_HOST", "localhost")
    )
    parser.add_argument(
        "--pg-port",
        type=int,
        default=int(os.getenv("PG_PORT", "5432")),
    )
    parser.add_argument("--pg-db", default=os.getenv("PG_DB", "rpg"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    parser.add_argument(
        "--pg-password", default=os.getenv("PG_PASSWORD", "")
    )
    parser.add_argument(
        "--receipts-collection",
        default=os.getenv("RECEIPTS_COLLECTION", "Receipts"),
        help="RavenDB collection name for receipts (default: Receipts)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=int(os.getenv("PAGE_SIZE", "500")),
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=int(os.getenv("TIMEOUT_SEC", "30")),
    )
    parser.add_argument(
        "--summary-json-path",
        default=os.getenv(
            "RECEIPTS_SUMMARY_JSON_PATH",
            os.path.join(script_dir, "..", "validation", "receipts_migration_summary.json"),
        ),
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--inspect-source-only",
        action="store_true",
        default=False,
        help="Only inspect RavenDB source collection; do not write to PostgreSQL",
    )

    args = parser.parse_args()

    if not args.raven_url:
        parser.error("Missing RavenDB URL. Provide --raven-url or set RAVEN_URL.")
    if not args.raven_db:
        parser.error("Missing RavenDB database. Provide --raven-db or set RAVEN_DB.")
    if args.page_size <= 0:
        parser.error("Invalid page size. --page-size must be greater than 0.")
    if args.timeout_sec <= 0:
        parser.error("Invalid timeout. --timeout-sec must be greater than 0.")

    if args.raven_cert_file:
        if not os.path.isfile(args.raven_cert_file):
            script_dir_cert = os.path.join(script_dir, args.raven_cert_file)
            if os.path.isfile(script_dir_cert):
                args.raven_cert_file = script_dir_cert
            else:
                parser.error(f"Raven cert file not found: {args.raven_cert_file}")

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
        inspect_source_only=args.inspect_source_only,
    )


# -----------------------------------------------------------------------------
# Type Conversion & Extraction Helpers
# -----------------------------------------------------------------------------

def get_nested(doc: Dict[str, Any], *path: str) -> Any:
    cur: Any = doc
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


def first_non_empty(*values: Any) -> Optional[Any]:
    for val in values:
        if val is None:
            continue
        if isinstance(val, str) and val.strip() == "":
            continue
        return val
    return None


def extract_uuid_from_any(value: Any) -> Optional[str]:
    """Extract standard UUID string. Returns None if value is empty, invalid, or missing."""
    if value is None:
        return None
    match = UUID_RE.search(str(value))
    return match.group(0).lower() if match else None


def parse_ts(value: Any) -> Optional[str]:
    """Parse timestamp into ISO 8601 string compatible with PostgreSQL TIMESTAMPTZ."""
    if value is None:
        return None
    text = str(value).strip()
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
        digits = "".join(ch for ch in frac_part if ch.isdigit())
        if len(digits) > 6:
            digits = digits[:6]
        normalized = f"{base}.{digits}{tz_part}" if digits else f"{base}{tz_part}"
    if "+" not in normalized[10:] and "-" not in normalized[10:]:
        normalized = f"{normalized}+00:00"

    try:
        datetime.fromisoformat(normalized)
        return normalized
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def parse_decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Parse numeric/decimal value into Decimal(18, 2)."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return default


def parse_bool(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    """Parse BIT/boolean field."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f"}:
        return False
    return default


def as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_payment_mode(value: Any) -> Optional[int]:
    """
    Map PaymentMode enum:
    Cash=10, Cheque=20, DD=30, Netbanking=40, UPI=50
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return PAYMENT_MODE_MAP.get(text)


def parse_status(value: Any) -> Optional[int]:
    """
    Map Status enum:
    Active=1, Cancelled=99
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return STATUS_MAP.get(text)


def parse_receipt_type(value: Any) -> Optional[int]:
    """
    Map ReceiptType enum:
    Unknown=0, Regular=10, Donation=20
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    return RECEIPT_TYPE_MAP.get(text, 0)


def derive_receipt_id(doc: Dict[str, Any]) -> Optional[str]:
    """Derive primary key GUID for receipt."""
    return first_non_empty(
        extract_uuid_from_any(get_nested(doc, "@metadata", "@id")),
        extract_uuid_from_any(doc.get("Id")),
        extract_uuid_from_any(doc.get("ReceiptId")),
    )


# -----------------------------------------------------------------------------
# RavenDB Connection & Extraction
# -----------------------------------------------------------------------------

def configure_raven_session(session: requests.Session, cfg: Config) -> None:
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
        print("[!] Warning: RavenDB TLS verification is disabled (--raven-insecure).")


def raven_query_collection(
    session: requests.Session, cfg: Config, collection_name: str
) -> List[Dict[str, Any]]:
    url = f"{cfg.raven_url}/databases/{cfg.raven_db}/queries"
    start = 0
    docs: List[Dict[str, Any]] = []
    escaped_collection = collection_name.replace("\\", "\\\\").replace('"', '\\"')

    print(f"[*] Querying RavenDB collection: '{collection_name}'...")
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
        if any(not isinstance(result, dict) for result in results):
            raise RuntimeError(
                f"RavenDB returned a non-document result for {collection_name}"
            )
        if not results:
            break

        docs.extend(results)
        start += len(results)
        print(f"    - Retrieved {len(docs)} documents so far...")

    print(f"[+] Total documents fetched from '{collection_name}': {len(docs)}")
    return docs


# -----------------------------------------------------------------------------
# PostgreSQL Target Schema DDL
# -----------------------------------------------------------------------------

def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create receipt table and indexes with exact target schema."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS receipt (
            id UUID PRIMARY KEY,
            number VARCHAR(50),
            inst_id UUID,
            date TIMESTAMPTZ,
            total_amount NUMERIC(18, 2),
            received_by VARCHAR(150),
            payment_mode INTEGER,
            status INTEGER,
            receipt_type INTEGER,
            revenue_sharing_enabled BOOLEAN,
            revenue_share INTEGER,
            html TEXT,
            ref_no VARCHAR(100),
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- Performance and query indexes
        CREATE INDEX IF NOT EXISTS idx_receipt_inst_id ON receipt (inst_id);
        CREATE INDEX IF NOT EXISTS idx_receipt_number ON receipt (number);
        CREATE INDEX IF NOT EXISTS idx_receipt_date ON receipt (date);
        CREATE INDEX IF NOT EXISTS idx_receipt_status ON receipt (status);
        CREATE INDEX IF NOT EXISTS idx_receipt_payment_mode ON receipt (payment_mode);
        CREATE INDEX IF NOT EXISTS idx_receipt_ref_no ON receipt (ref_no);
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    """Assert all required columns and correct types exist in receipt table."""
    required_columns = {
        "id",
        "number",
        "inst_id",
        "date",
        "total_amount",
        "received_by",
        "payment_mode",
        "status",
        "receipt_type",
        "revenue_sharing_enabled",
        "revenue_share",
        "html",
        "ref_no",
        "owner_id",
        "parent_id",
        "created_on",
        "created_by",
        "modified_on",
        "modified_by",
    }

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'receipt'
        """
    )
    found_columns = {row[0].lower() for row in cur.fetchall()}
    missing = required_columns - found_columns
    if missing:
        raise RuntimeError(f"Missing required columns in table 'receipt': {sorted(missing)}")


# -----------------------------------------------------------------------------
# Data Transformation & Upsert
# -----------------------------------------------------------------------------

def transform_receipt_doc(doc: Dict[str, Any]) -> Tuple[Any, ...]:
    """
    Transform RavenDB receipt document into row values matching the 19 table fields:
    Id, Number, InstId, Date, TotalAmount, ReceivedBy, PaymentMode, Status,
    ReceiptType, RevenueSharingEnabled, RevenueShare, HTML, RefNo, OwnerId,
    ParentId, CreatedOn, CreatedBy, ModifiedOn, ModifiedBy.
    """
    receipt_id = derive_receipt_id(doc)
    if not receipt_id:
        raise ValueError(f"Document missing valid GUID Id: {doc.get('Id') or doc.get('@metadata', {}).get('@id')}")

    # Number: NVARCHAR(50), e.g. "29/BTLCOL", do NOT use numeric type
    number_raw = first_non_empty(
        doc.get("Number"), doc.get("ReceiptNumber"), doc.get("ReceiptNo"), doc.get("No")
    )
    number = as_text(number_raw)[:50] if number_raw is not None else None

    # InstId: UNIQUEIDENTIFIER
    inst_id = extract_uuid_from_any(
        first_non_empty(doc.get("InstId"), doc.get("InstituteId"), doc.get("Institute_Id"))
    )

    # Date: DATETIME2(7)
    date = parse_ts(first_non_empty(doc.get("Date"), doc.get("ReceiptDate"), doc.get("TxDate")))

    # TotalAmount: DECIMAL(18,2)
    total_amount = parse_decimal(
        first_non_empty(doc.get("TotalAmount"), doc.get("Amount"), doc.get("Total")),
        default=Decimal("0.00"),
    )

    # ReceivedBy: NVARCHAR(150), nullable
    received_by_raw = as_text(doc.get("ReceivedBy"))
    received_by = received_by_raw[:150] if received_by_raw else None

    # PaymentMode: INT (Cash=10, Cheque=20, DD=30, Netbanking=40, UPI=50)
    payment_mode = parse_payment_mode(doc.get("PaymentMode"))

    # Status: INT (Active=1, Cancelled=99)
    status = parse_status(doc.get("Status"))

    # ReceiptType: INT (Unknown=0, Regular=10, Donation=20)
    receipt_type = parse_receipt_type(doc.get("ReceiptType"))

    # RevenueSharingEnabled: BIT (true/false)
    revenue_sharing_enabled = parse_bool(doc.get("RevenueSharingEnabled"), default=False)

    # RevenueShare: INT (e.g. 0, 30, 40)
    revenue_share = parse_int(
        first_non_empty(doc.get("RevenueShare"), doc.get("RevenueSharePercentage"))
    )

    # HTML: NVARCHAR(MAX)
    html = as_text(first_non_empty(doc.get("HTML"), doc.get("Html"), doc.get("ReceiptHtml")))

    # RefNo: NVARCHAR(100), nullable
    ref_no_raw = as_text(
        first_non_empty(doc.get("RefNo"), doc.get("ReferenceNo"), doc.get("ReferenceNumber"))
    )
    ref_no = ref_no_raw[:100] if ref_no_raw else None

    # OwnerId: UNIQUEIDENTIFIER
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))

    # ParentId: UNIQUEIDENTIFIER NULL (in JSON empty string -> in SQL keep NULL)
    parent_id = extract_uuid_from_any(doc.get("ParentId"))

    # CreatedOn: DATETIME2(7), required audit field
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()

    # CreatedBy: UNIQUEIDENTIFIER NULL
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))

    # ModifiedOn: DATETIME2(7) NULL
    modified_on = parse_ts(doc.get("ModifiedOn"))

    # ModifiedBy: UNIQUEIDENTIFIER NULL
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

    return (
        receipt_id,
        number,
        inst_id,
        date,
        total_amount,
        received_by,
        payment_mode,
        status,
        receipt_type,
        revenue_sharing_enabled,
        revenue_share,
        html,
        ref_no,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


def upsert_receipt(
    cur: psycopg2.extensions.cursor, row_values: Tuple[Any, ...]
) -> UpsertResult:
    receipt_id = row_values[0]

    cur.execute("SELECT 1 FROM receipt WHERE id = %s", (receipt_id,))
    is_new = cur.fetchone() is None

    cur.execute(
        """
        INSERT INTO receipt (
            id,
            number,
            inst_id,
            date,
            total_amount,
            received_by,
            payment_mode,
            status,
            receipt_type,
            revenue_sharing_enabled,
            revenue_share,
            html,
            ref_no,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id)
        DO UPDATE SET
            number = EXCLUDED.number,
            inst_id = EXCLUDED.inst_id,
            date = EXCLUDED.date,
            total_amount = EXCLUDED.total_amount,
            received_by = EXCLUDED.received_by,
            payment_mode = EXCLUDED.payment_mode,
            status = EXCLUDED.status,
            receipt_type = EXCLUDED.receipt_type,
            revenue_sharing_enabled = EXCLUDED.revenue_sharing_enabled,
            revenue_share = EXCLUDED.revenue_share,
            html = EXCLUDED.html,
            ref_no = EXCLUDED.ref_no,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by
        RETURNING id;
        """,
        row_values,
    )
    return UpsertResult(record_id=str(receipt_id), inserted=is_new)


# -----------------------------------------------------------------------------
# Main Migration Routine
# -----------------------------------------------------------------------------

def main() -> None:
    cfg = parse_args()

    print("=" * 70)
    print("CT-RPG: RavenDB to PostgreSQL Migration — Receipts Module")
    print("=" * 70)
    print(f"[*] RavenDB URL:     {cfg.raven_url}")
    print(f"[*] RavenDB DB:      {cfg.raven_db}")
    print(f"[*] Collection:      {cfg.receipts_collection}")
    print(f"[*] PostgreSQL Host: {cfg.pg_host}:{cfg.pg_port}")
    print(f"[*] PostgreSQL DB:   {cfg.pg_db} (User: {cfg.pg_user})")
    print("=" * 70)

    # 1. Fetch documents from RavenDB
    session = requests.Session()
    configure_raven_session(session, cfg)

    try:
        docs = raven_query_collection(session, cfg, cfg.receipts_collection)
    except requests.HTTPError as ex:
        # Fallback to singular collection name if plural doesn't exist
        if cfg.receipts_collection == "Receipts":
            print("[!] Collection 'Receipts' returned error. Attempting fallback to 'Receipt'...")
            docs = raven_query_collection(session, cfg, "Receipt")
        else:
            raise ex

    if not docs and cfg.receipts_collection == "Receipts":
        print("[!] 0 documents found in 'Receipts'. Attempting fallback to 'Receipt'...")
        try:
            docs = raven_query_collection(session, cfg, "Receipt")
        except Exception:
            pass

    print(f"[+] Loaded {len(docs)} receipt document(s) from RavenDB.")

    if cfg.inspect_source_only:
        print("[*] Inspect source only specified. Sample document keys:")
        if docs:
            print(json.dumps(list(docs[0].keys()), indent=2))
        sys.exit(0)

    # 2. Connect to PostgreSQL and prepare schema
    print("\n[*] Connecting to PostgreSQL...")
    conn = psycopg2.connect(
        host=cfg.pg_host,
        port=cfg.pg_port,
        dbname=cfg.pg_db,
        user=cfg.pg_user,
        password=cfg.pg_password,
    )
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print("[*] Ensuring target table 'receipt' and indexes exist...")
            ensure_target_schema(cur)
            assert_required_schema(cur)
            conn.commit()
            print("[+] Schema verified successfully.")

            # 3. Transform and Upsert documents
            print(f"\n[*] Starting migration of {len(docs)} documents into PostgreSQL...")
            inserted_count = 0
            updated_count = 0
            error_count = 0
            skipped_count = 0
            errors: List[Dict[str, Any]] = []

            for idx, doc in enumerate(docs, 1):
                try:
                    row_values = transform_receipt_doc(doc)
                    res = upsert_receipt(cur, row_values)
                    if res.inserted:
                        inserted_count += 1
                    else:
                        updated_count += 1
                except Exception as ex:
                    error_count += 1
                    doc_id = doc.get("Id") or get_nested(doc, "@metadata", "@id") or f"index_{idx}"
                    errors.append({"id": str(doc_id), "error": str(ex)})
                    if error_count <= 5:
                        print(f"[!] Error migrating doc {doc_id}: {ex}")

                if idx % 500 == 0 or idx == len(docs):
                    conn.commit()
                    print(f"    - Processed {idx}/{len(docs)} (Inserted: {inserted_count}, Updated: {updated_count}, Errors: {error_count})")

            conn.commit()

            # 4. Final verification query
            cur.execute("SELECT COUNT(*) FROM receipt")
            total_in_pg = cur.fetchone()[0]

            print("\n" + "=" * 70)
            print("Migration Summary: Receipts")
            print("=" * 70)
            print(f"[+] Total RavenDB Documents: {len(docs)}")
            print(f"[+] Records Inserted:        {inserted_count}")
            print(f"[+] Records Updated:         {updated_count}")
            print(f"[+] Records with Errors:     {error_count}")
            print(f"[+] Total Rows in 'receipt': {total_in_pg}")
            print("=" * 70)

            # 5. Write summary JSON
            if cfg.write_summary_json and cfg.summary_json_path:
                summary_data = {
                    "module": "receipts",
                    "target_table": "receipt",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_count": len(docs),
                    "inserted_count": inserted_count,
                    "updated_count": updated_count,
                    "error_count": error_count,
                    "total_pg_records": total_in_pg,
                    "errors": errors[:50],
                }
                summary_file = Path(cfg.summary_json_path)
                summary_file.parent.mkdir(parents=True, exist_ok=True)
                summary_file.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
                print(f"[+] Summary written to: {summary_file.resolve()}")

    except Exception as ex:
        conn.rollback()
        print(f"[!] Fatal error during migration: {ex}")
        conn.close()
        sys.exit(1)
    finally:
        conn.close()

    if error_count > 0:
        print(f"[!] Completed with {error_count} error(s).")
        sys.exit(1)
    else:
        print("[+] Receipts migration completed successfully with 0 errors.")
        sys.exit(0)


if __name__ == "__main__":
    main()
