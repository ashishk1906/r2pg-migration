#!/usr/bin/env python3
"""
Extract AssetViews data from RavenDB, transform it to PostgreSQL schema,
and load into PostgreSQL.

Target table:
- asset_views
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

import psycopg2
from psycopg2.extras import Json
import requests

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# C# AssetStatusEnum: Active=1, Cleared=90, Disabled=99
ASSET_STATUS_MAP: Dict[Any, str] = {
    1: "Active",
    90: "Cleared",
    99: "Disabled",
    "1": "Active",
    "90": "Cleared",
    "99": "Disabled",
    "active": "Active",
    "cleared": "Cleared",
    "disabled": "Disabled",
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
    asset_views_collection: str
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
    for env_path in (
        os.path.join(script_dir, "..", "..", ".env"),
        os.path.join(script_dir, "..", ".env"),
        os.path.join(script_dir, ".env"),
    ):
        if os.path.exists(env_path):
            load_env_file(env_path)
            break

    parser = argparse.ArgumentParser(
        description="Migrate RavenDB AssetViews to PostgreSQL table asset_views."
    )
    parser.add_argument("--raven-url", default=os.getenv("RAVEN_URL"))
    parser.add_argument(
        "--raven-db",
        default=os.getenv("RAVEN_DB") or os.getenv("RAVEN_DATABASE"),
    )
    parser.add_argument("--raven-cert-file", default=os.getenv("RAVEN_CERT_FILE"))
    parser.add_argument(
        "--raven-cert-password", default=os.getenv("RAVEN_CERT_PASSWORD")
    )
    parser.add_argument(
        "--raven-insecure",
        action="store_true",
        default=env_bool("RAVEN_INSECURE", False),
        help="Disable TLS certificate verification for RavenDB HTTPS.",
    )
    parser.add_argument("--pg-host", default=os.getenv("PG_HOST", "localhost"))
    parser.add_argument(
        "--pg-port", type=int, default=int(os.getenv("PG_PORT", "5432"))
    )
    parser.add_argument("--pg-db", default=os.getenv("PG_DB", "rpg"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    parser.add_argument("--pg-password", default=os.getenv("PG_PASSWORD"))

    parser.add_argument(
        "--asset-views-collection",
        default=os.getenv("ASSET_VIEWS_COLLECTION", "AssetViews"),
        help="RavenDB collection name for asset views (default: AssetViews)",
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
            for cert_dir in (
                os.path.join(script_dir, "..", "certs"),
                os.path.join(script_dir, ".."),
                os.path.join(script_dir, "..", ".."),
                script_dir,
            ):
                cand = os.path.join(cert_dir, args.raven_cert_file)
                if os.path.isfile(cand):
                    args.raven_cert_file = cand
                    break
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
        asset_views_collection=args.asset_views_collection,
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
    s = str(val).strip().lower()
    if s in {"true", "1", "yes", "t"}:
        return True
    if s in {"false", "0", "no", "n", "f"}:
        return False
    return default


def parse_decimal(val: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if val is None or val == "":
        return default
    try:
        return Decimal(str(val))
    except (ValueError, TypeError, InvalidOperation):
        return default


def clean_string_list(raw_val: Any) -> Optional[List[str]]:
    """Convert raw value to list of strings for TEXT[], preserving None as SQL NULL."""
    if raw_val is None:
        return None
    if isinstance(raw_val, list):
        cleaned = [str(item).strip() for item in raw_val if item is not None and str(item).strip()]
        return cleaned if cleaned else None
    if isinstance(raw_val, str):
        cleaned = raw_val.strip()
        return [cleaned] if cleaned else None
    return [str(raw_val)]


def as_json(value: Any) -> Optional[Json]:
    """Wrap dict/list/string into JSONB object, preserving None as SQL NULL."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return Json(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Json(json.loads(text))
        except Exception:
            return Json({"value": text})
    return Json(value)


def map_asset_status(raw_val: Any) -> Optional[str]:
    """Map status string/int to asset_status_enum. Returns None if null in RavenDB."""
    if raw_val is None or (isinstance(raw_val, str) and raw_val.strip() == ""):
        return None
    if isinstance(raw_val, int):
        return ASSET_STATUS_MAP.get(raw_val)
    norm = str(raw_val).strip().lower()
    if norm.isdigit():
        return ASSET_STATUS_MAP.get(int(norm))
    return ASSET_STATUS_MAP.get(norm)


# -----------------------------------------------------------------------------
# Document Field Extractor
# -----------------------------------------------------------------------------


def extract_asset_view_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for asset_views table.

    C# AssetView fields: Id, TrackingId, OwnerId, Location, Attributes (string),
    Tags (List<string>), Value (decimal), LastMaintenance (Maintenance object),
    CurrentWarranty (Warranty object), Status (AssetStatusEnum), UnderWarranty (computed).
    """
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    asset_id = clean_uuid(raw_id)
    if not asset_id:
        raise ValueError(f"AssetView missing valid ID: {raw_id}")

    tracking_id = clean_str(doc.get("TrackingId"), 100)
    owner_id = clean_uuid(doc.get("OwnerId"))
    location = clean_str(doc.get("Location"), 250)
    attributes = as_json(doc.get("Attributes"))
    tags = clean_string_list(doc.get("Tags"))
    value = parse_decimal(doc.get("Value"), default=Decimal("0.00"))
    last_maintenance = as_json(doc.get("LastMaintenance"))
    current_warranty = as_json(doc.get("CurrentWarranty"))
    status = map_asset_status(doc.get("Status"))
    # UnderWarranty is a computed property in C# (not stored independently in RavenDB)
    under_warranty = clean_bool(doc.get("UnderWarranty"), default=False)

    return (
        asset_id,
        tracking_id,
        owner_id,
        location,
        attributes,
        tags,
        value,
        last_maintenance,
        current_warranty,
        status,
        under_warranty,
    )


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup (Only primary key, no secondary indexes)
# -----------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target enums and asset_views table without secondary indexes."""
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'asset_status_enum') THEN
                CREATE TYPE asset_status_enum AS ENUM (
                    'Active',
                    'Cleared',
                    'Disabled'
                );
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS asset_views (
            id UUID PRIMARY KEY,
            tracking_id VARCHAR(100),
            owner_id UUID,
            location VARCHAR(250),
            attributes JSONB,
            tags TEXT[],
            value NUMERIC(18, 2),
            last_maintenance JSONB,
            current_warranty JSONB,
            status asset_status_enum,
            under_warranty BOOLEAN
        );
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operation
# -----------------------------------------------------------------------------


def upsert_asset_view(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert an AssetView document."""
    fields = extract_asset_view_fields(doc)
    sql = """
        INSERT INTO asset_views (
            id,
            tracking_id,
            owner_id,
            location,
            attributes,
            tags,
            value,
            last_maintenance,
            current_warranty,
            status,
            under_warranty
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            tracking_id = EXCLUDED.tracking_id,
            owner_id = EXCLUDED.owner_id,
            location = EXCLUDED.location,
            attributes = EXCLUDED.attributes,
            tags = EXCLUDED.tags,
            value = EXCLUDED.value,
            last_maintenance = EXCLUDED.last_maintenance,
            current_warranty = EXCLUDED.current_warranty,
            status = EXCLUDED.status,
            under_warranty = EXCLUDED.under_warranty
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
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None

    try:
        configure_raven_session(requests_session, cfg)

        asset_docs = raven_query_collection(
            requests_session, cfg, cfg.asset_views_collection
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

        loaded_assets = 0
        new_assets = 0

        with conn:
            with conn.cursor() as cur:
                ensure_target_schema(cur)

                for d in asset_docs:
                    res = upsert_asset_view(cur, d)
                    loaded_assets += 1
                    new_assets += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collection": cfg.asset_views_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "asset_views_processed": loaded_assets,
                "new_asset_views_inserted": new_assets,
            },
        }

        print("Migration completed.")
        print(f"asset_views_processed: {loaded_assets}")
        print(f"new_asset_views_inserted: {new_assets}")

        if cfg.write_summary_json:
            output_path = cfg.summary_json_path
            if not output_path:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                output_path = f"validation/migration-summary-{timestamp}.json"
            written = write_summary_json(output_path, summary)

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
