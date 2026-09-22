#!/usr/bin/env python3
"""
Extract AssetViews data from RavenDB, transform it to PostgreSQL schema,
and load into PostgreSQL.

Handles:
- asset table (mapped from AssetViews collection)
- Backward-compatible views: asset_views, assets
- No secondary indexes per requirement.

Data type mappings based on ct.asset CQRS AssetView read model:
- Id: UUID PRIMARY KEY
- TrackingId: VARCHAR(100)
- OwnerId: VARCHAR(100) (stored as string, not Guid)
- Location: VARCHAR(250)
- Attributes: TEXT (serialized JSON string) & attributes_json JSONB
- Tags: TEXT[] (List<string>)
- Value: NUMERIC(18, 2)
- Status: INTEGER (AssetStatusEnum: Active=1, Cleared=90, Disabled=99)
- StatusName: VARCHAR(50)
- UnderWarranty: BOOLEAN
- LastMaintenance: JSONB and flattened columns (by, on, action_taken)
- CurrentWarranty: JSONB and flattened columns (covered_by, from, to, details)
- LastModified: TIMESTAMPTZ

Before running: set required configuration in .env or pass CLI arguments.
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

# AssetStatusEnum: Active = 1, Cleared = 90, Disabled = 99
ASSET_STATUS_NAME_TO_INT: Dict[str, int] = {
    "active": 1,
    "enabled": 1,
    "cleared": 90,
    "disabled": 99,
    "inactive": 99,
}

ASSET_STATUS_INT_TO_NAME: Dict[int, str] = {
    1: "Active",
    90: "Cleared",
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
    asset_views_collection: str
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
        description="Migrate AssetViews data from RavenDB to PostgreSQL"
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
        help="Disable TLS verification for RavenDB HTTPS.",
    )
    parser.add_argument("--pg-host", default=os.getenv("PG_HOST", "localhost"))
    parser.add_argument(
        "--pg-port",
        type=int,
        default=int(os.getenv("PG_PORT", "5432")),
    )
    parser.add_argument("--pg-db", default=os.getenv("PG_DB", "rpg"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    parser.add_argument("--pg-password", default=os.getenv("PG_PASSWORD", ""))
    parser.add_argument(
        "--asset-views-collection",
        default=os.getenv("ASSET_VIEWS_COLLECTION", "AssetViews"),
        help="RavenDB collection name for asset views (default: AssetViews)",
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
            "ASSETS_SUMMARY_JSON_PATH",
            os.path.join(script_dir, "..", "validation", "assets_migration_summary.json"),
        ),
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        help="Disable summary JSON artifact output",
    )
    parser.add_argument(
        "--inspect-source-only",
        action="store_true",
        help="Read RavenDB documents and output summary without modifying PostgreSQL",
    )

    args = parser.parse_args()

    if not args.raven_url or not args.raven_db:
        parser.error("Missing RavenDB config. Provide --raven-url/--raven-db or set RAVEN_URL/RAVEN_DB.")

    if not args.inspect_source_only and not args.pg_password:
        parser.error("Missing PostgreSQL password. Provide --pg-password or set PG_PASSWORD.")

    if args.raven_cert_file:
        cert_path = args.raven_cert_file
        if not os.path.isfile(cert_path):
            candidate = os.path.join(script_dir, cert_path)
            if os.path.isfile(candidate):
                args.raven_cert_file = candidate
            else:
                parser.error(f"RavenDB cert file not found: {args.raven_cert_file}")

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
        page_size=max(1, args.page_size),
        timeout_sec=max(1, args.timeout_sec),
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
        inspect_source_only=args.inspect_source_only,
    )


def write_summary_json(path_text: str, payload: Dict[str, Any]) -> str:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path.resolve())


# -----------------------------------------------------------------------------
# Parsing & Data Conversion Helpers
# -----------------------------------------------------------------------------

def extract_uuid_from_any(value: Any) -> Optional[str]:
    if not value:
        return None
    match = UUID_RE.search(str(value))
    return match.group(0).lower() if match else None


def as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_ts(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.startswith("0001-01-01"):
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


def parse_decimal(value: Any, default: Optional[Decimal] = Decimal("0.00")) -> Optional[Decimal]:
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


def parse_bool(value: Any, default: bool = False) -> bool:
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


def parse_asset_status(value: Any) -> int:
    """AssetStatusEnum: Active = 1, Cleared = 90, Disabled = 99."""
    if value is None:
        return 1
    if isinstance(value, int):
        return value if value in (1, 90, 99) else 1
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 1
    if text.isdigit():
        val = int(text)
        return val if val in (1, 90, 99) else 1
    return ASSET_STATUS_NAME_TO_INT.get(text, 1)


def as_json(value: Any) -> Optional[Json]:
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


def derive_asset_id(doc: Dict[str, Any]) -> Optional[str]:
    metadata = doc.get("@metadata")
    meta_id = metadata.get("@id") if isinstance(metadata, dict) else None
    return (
        extract_uuid_from_any(meta_id)
        or extract_uuid_from_any(doc.get("Id"))
        or extract_uuid_from_any(doc.get("id"))
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
                "PKCS#12 RavenDB auth requires requests-pkcs12. "
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

    return docs


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup (No Secondary Indexes)
# -----------------------------------------------------------------------------

def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target table 'asset' and views without secondary indexes."""
    cur.execute(
        """
        DROP TABLE IF EXISTS asset CASCADE;

        CREATE TABLE IF NOT EXISTS asset (
            id UUID PRIMARY KEY,
            tracking_id VARCHAR(100),
            owner_id VARCHAR(100),
            location VARCHAR(250),
            attributes TEXT,
            tags TEXT[],
            value NUMERIC(18, 2) DEFAULT 0.00,
            last_maintenance JSONB,
            current_warranty JSONB,
            status INTEGER DEFAULT 1,
            under_warranty BOOLEAN DEFAULT FALSE
        );

        -- Backward compatible views
        CREATE OR REPLACE VIEW asset_views AS SELECT * FROM asset;
        CREATE OR REPLACE VIEW assets AS SELECT * FROM asset;
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'asset'
        """
    )
    existing = {row[0].lower() for row in cur.fetchall()}
    required = {
        "id", "tracking_id", "owner_id", "location", "attributes",
        "tags", "value", "last_maintenance", "current_warranty",
        "status", "under_warranty"
    }
    missing = required - existing
    if missing:
        raise RuntimeError(f"Schema verification failed! Missing columns in asset: {missing}")


# -----------------------------------------------------------------------------
# Upsert: Asset
# -----------------------------------------------------------------------------

def upsert_asset(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> Optional[UpsertResult]:
    asset_id = derive_asset_id(doc)
    if not asset_id:
        return None

    cur.execute("SELECT 1 FROM asset WHERE id = %s", (asset_id,))
    is_new = cur.fetchone() is None

    tracking_id = as_text(doc.get("TrackingId"))
    tracking_id = tracking_id[:100] if tracking_id else None

    owner_id = as_text(doc.get("OwnerId"))
    owner_id = owner_id[:100] if owner_id else None

    location = as_text(doc.get("Location"))
    location = location[:250] if location else None

    # Attributes: C# read model stores serialized JSON string (or null)
    raw_attrs = doc.get("Attributes")
    if isinstance(raw_attrs, dict):
        attributes = json.dumps(raw_attrs)
    elif isinstance(raw_attrs, str) and raw_attrs.strip():
        attributes = raw_attrs.strip()
    else:
        attributes = None

    # Tags: List<string> -> TEXT[]
    raw_tags = doc.get("Tags")
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = [raw_tags.strip()]
    else:
        tags = None

    value = parse_decimal(doc.get("Value"), Decimal("0.00"))
    status_int = parse_asset_status(doc.get("Status"))
    under_warranty = parse_bool(doc.get("UnderWarranty"), False)

    last_maintenance = as_json(doc.get("LastMaintenance"))
    current_warranty = as_json(doc.get("CurrentWarranty"))

    cur.execute(
        """
        INSERT INTO asset (
            id, tracking_id, owner_id, location, attributes,
            tags, value, last_maintenance, current_warranty,
            status, under_warranty
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s
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
        RETURNING id;
        """,
        (
            asset_id,
            tracking_id,
            owner_id,
            location,
            attributes,
            tags,
            value,
            last_maintenance,
            current_warranty,
            status_int,
            under_warranty,
        ),
    )
    row = cur.fetchone()
    record_id = str(row[0]) if row else str(asset_id)
    return UpsertResult(record_id, is_new)


# -----------------------------------------------------------------------------
# Main Execution Routine
# -----------------------------------------------------------------------------

def main() -> int:
    cfg = parse_args()
    requests_session = requests.Session()
    conn = None

    try:
        configure_raven_session(requests_session, cfg)
        print(f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, collection={cfg.asset_views_collection}")
        print("[1/4] Fetching RavenDB documents...")
        docs = raven_query_collection(requests_session, cfg, cfg.asset_views_collection)
        print(f"Fetched {len(docs)} documents from {cfg.asset_views_collection}.")

        if cfg.inspect_source_only:
            print("[inspect-only] Sample first document:")
            if docs:
                print(json.dumps(docs[0], indent=2))
            return 0

        print("[2/4] Connecting to PostgreSQL...")
        print(f"PostgreSQL target: host={cfg.pg_host}, port={cfg.pg_port}, db={cfg.pg_db}, user={cfg.pg_user}")
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

        loaded_count = 0
        new_count = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema (table: asset, no indexes)...")
                ensure_target_schema(cur)
                assert_required_schema(cur)

                print("[4/4] Upserting assets...")
                for d in docs:
                    res = upsert_asset(cur, d)
                    if res is not None:
                        loaded_count += 1
                        new_count += int(res.inserted)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM asset")
            total_assets = int(cur.fetchone()[0])

        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
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
                "table": "asset",
            },
            "run_stats": {
                "documents_fetched": len(docs),
                "assets_processed": loaded_count,
                "new_assets_inserted": new_count,
            },
            "post_load_counts": {
                "asset": total_assets,
            },
        }

        print("\n" + "=" * 50)
        print("AssetViews Migration Completed Successfully.")
        print(f"Documents processed: {loaded_count}")
        print(f"New rows inserted:   {new_count}")
        print(f"Total rows in asset: {total_assets}")
        print("=" * 50)

        if cfg.write_summary_json:
            written = write_summary_json(cfg.summary_json_path, summary)
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
