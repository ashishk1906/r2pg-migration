#!/usr/bin/env python3
"""
Extract MaterialViews data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL types and JSONB,
and load into PostgreSQL.

Target table:
- material_views
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

UUID_NAMESPACE_MATERIAL_VIEWS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

MATERIAL_STATUSES = {
    "active": "Active",
    "issued": "Issued",
    "undermaintenance": "UnderMaintenance",
    "under_maintenance": "UnderMaintenance",
    "under maintenance": "UnderMaintenance",
    "disabled": "Disabled",
    "archived": "Archived",
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
    material_views_collection: str
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
        description="Migrate MaterialViews from RavenDB to PostgreSQL"
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
        "--material-views-collection",
        default=os.getenv("MATERIAL_VIEWS_COLLECTION", "MaterialViews"),
        help="RavenDB collection name for material views (default: MaterialViews)",
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
        material_views_collection=args.material_views_collection,
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


def clean_int(val: Any, default: Optional[int] = 0) -> Optional[int]:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def clean_epoch_ms(val: Any) -> Optional[int]:
    """Convert epoch milliseconds or ISO timestamp string to integer epoch ms."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if not s:
        return None
    if s.isdigit():
        try:
            return int(s)
        except ValueError:
            pass
    # If passed as ISO datetime string
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        pass
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


def map_material_status(raw_val: Any) -> str:
    """Map string status to material_status_enum."""
    if raw_val is None:
        return "Active"
    norm = str(raw_val).strip().lower()
    return MATERIAL_STATUSES.get(norm, "Active")


def as_json(value: Any, default_val: Any = None) -> Optional[Json]:
    """Wrap dict/list for JSONB writes while preserving SQL NULL semantics."""
    if value is None:
        return Json(default_val) if default_val is not None else None
    return Json(value)


# -----------------------------------------------------------------------------
# Document Field Extractor (Only RavenDB fields, no metadata columns)
# -----------------------------------------------------------------------------


def extract_material_view_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for material_views table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    material_view_id = clean_uuid(raw_id)
    if not material_view_id and raw_id:
        material_view_id = str(
            uuid.uuid5(UUID_NAMESPACE_MATERIAL_VIEWS, str(raw_id).strip())
        ).lower()
    if not material_view_id:
        raise ValueError(f"MaterialView missing valid ID: {raw_id}")

    tracking_id = clean_str(doc.get("TrackingId"), 100)
    isbn = clean_str(doc.get("ISBN"), 100)
    title = clean_str(doc.get("Title"))
    author = clean_str(doc.get("Author"), 255)
    publisher = clean_str(doc.get("Publisher"), 255)
    owner_id = clean_uuid(doc.get("OwnerId"))

    raw_ownership = doc.get("OwnerShip")
    if isinstance(raw_ownership, list):
        ownership = as_json(raw_ownership, default_val=[])
    else:
        ownership = as_json([], default_val=[])

    location = clean_str(doc.get("Location"), 255)

    raw_attrs = doc.get("Attributes")
    if isinstance(raw_attrs, dict):
        attributes = as_json(raw_attrs, default_val={})
    elif raw_attrs is None:
        attributes = as_json({}, default_val={})
    else:
        attributes = as_json(raw_attrs, default_val={})

    tags = clean_string_list(doc.get("Tags"))
    value = clean_decimal(doc.get("Value"), default=Decimal("0.00"))
    status = map_material_status(doc.get("Status"))
    last_verified_on = clean_epoch_ms(doc.get("LastVerifiedOn"))
    pages = clean_int(doc.get("Pages"), default=0)

    return (
        material_view_id,
        tracking_id,
        isbn,
        title,
        author,
        publisher,
        owner_id,
        ownership,
        location,
        attributes,
        tags,
        value,
        status,
        last_verified_on,
        pages,
    )


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup (Only primary key, no secondary indexes, no views)
# -----------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target enum and material_views table without secondary indexes or views."""
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'material_status_enum') THEN
                CREATE TYPE material_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Issued',
                    'UnderMaintenance',
                    'Disabled',
                    'Archived'
                );
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS material_views (
            id UUID PRIMARY KEY,
            tracking_id VARCHAR(100),
            isbn VARCHAR(100),
            title TEXT,
            author VARCHAR(255),
            publisher VARCHAR(255),
            owner_id UUID,
            ownership JSONB DEFAULT '[]'::jsonb,
            location VARCHAR(255),
            attributes JSONB DEFAULT '{}'::jsonb,
            tags TEXT[] DEFAULT '{}'::text[],
            value NUMERIC(18, 2) DEFAULT 0.00,
            status material_status_enum NOT NULL DEFAULT 'Active',
            last_verified_on BIGINT,
            pages INTEGER DEFAULT 0
        );
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operation
# -----------------------------------------------------------------------------


def upsert_material_view(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert a MaterialView document."""
    fields = extract_material_view_fields(doc)
    sql = """
        INSERT INTO material_views (
            id,
            tracking_id,
            isbn,
            title,
            author,
            publisher,
            owner_id,
            ownership,
            location,
            attributes,
            tags,
            value,
            status,
            last_verified_on,
            pages
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            tracking_id = EXCLUDED.tracking_id,
            isbn = EXCLUDED.isbn,
            title = EXCLUDED.title,
            author = EXCLUDED.author,
            publisher = EXCLUDED.publisher,
            owner_id = EXCLUDED.owner_id,
            ownership = EXCLUDED.ownership,
            location = EXCLUDED.location,
            attributes = EXCLUDED.attributes,
            tags = EXCLUDED.tags,
            value = EXCLUDED.value,
            status = EXCLUDED.status,
            last_verified_on = EXCLUDED.last_verified_on,
            pages = EXCLUDED.pages
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
    """Run the end-to-end migration for MaterialViews."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collection={cfg.material_views_collection}"
        )
        print("[1/4] Fetching RavenDB documents...")
        material_docs = raven_query_collection(
            requests_session, cfg, cfg.material_views_collection
        )

        # Fallback to singular name if 0 docs fetched with default collection name
        if not material_docs and cfg.material_views_collection == "MaterialViews":
            try:
                alt_docs = raven_query_collection(
                    requests_session, cfg, "MaterialView"
                )
                if alt_docs:
                    print(f"Fallback: Loaded {len(alt_docs)} docs from 'MaterialView'.")
                    material_docs = alt_docs
            except Exception:
                pass

        print(f"Fetched material_views={len(material_docs)}")

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

        loaded_views = 0
        new_views = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/4] Upserting material views...")
                for d in material_docs:
                    res = upsert_material_view(cur, d)
                    loaded_views += 1
                    new_views += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collection": cfg.material_views_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "material_views_processed": loaded_views,
                "new_material_views_inserted": new_views,
            },
        }

        print("Migration completed.")
        print(f"material_views_processed: {loaded_views}")
        print(f"new_material_views_inserted: {new_views}")

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
