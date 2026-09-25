#!/usr/bin/env python3
"""
Extract Topics data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs and JSONBs,
and load into PostgreSQL.

Target table:
- topics
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
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
    topics_collection: str
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
        description="Migrate Topics from RavenDB to PostgreSQL"
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
        "--topics-collection",
        default=os.getenv("TOPICS_COLLECTION", "Topics"),
        help="RavenDB collection name for topics (default: Topics)",
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
        topics_collection=args.topics_collection,
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


# -----------------------------------------------------------------------------
# Enum Mappings (Exact match to C# Enums)
# -----------------------------------------------------------------------------

# RoleEnum: Admin = 10, Member = 20
ROLE_MAP: Dict[Any, str] = {
    10: "Admin",
    20: "Member",
    "admin": "Admin",
    "administrator": "Admin",
    "member": "Member",
    "user": "Member",
}

# CategoryEnum: PrivateToInstitue = 30, Public = 40
CATEGORY_MAP: Dict[Any, str] = {
    30: "PrivateToInstitue",
    40: "Public",
    "privatetoinstitue": "PrivateToInstitue",
    "privatetoinstitute": "PrivateToInstitue",
    "private_to_institute": "PrivateToInstitue",
    "private": "PrivateToInstitue",
    "public": "Public",
}

# AccessEnum: Open = 50, Restricted = 60
ACCESS_MAP: Dict[Any, str] = {
    50: "Open",
    60: "Restricted",
    "open": "Open",
    "restricted": "Restricted",
    "private": "Restricted",
}

# TopicStatusEnum: Unknown = 0, Active = 1, Disabled = 99
TOPIC_STATUS_MAP: Dict[Any, str] = {
    0: "Unknown",
    1: "Active",
    99: "Disabled",
    "unknown": "Unknown",
    "active": "Active",
    "disabled": "Disabled",
    "inactive": "Disabled",
}


def map_topic_role(val: Any) -> str:
    if val is None:
        return "Admin"
    if isinstance(val, int):
        return ROLE_MAP.get(val, "Admin")
    s = str(val).strip()
    if s.isdigit():
        return ROLE_MAP.get(int(s), "Admin")
    return ROLE_MAP.get(s.lower(), "Admin")


def map_topic_category(val: Any) -> str:
    if val is None:
        return "PrivateToInstitue"
    if isinstance(val, int):
        return CATEGORY_MAP.get(val, "PrivateToInstitue")
    s = str(val).strip()
    if s.isdigit():
        return CATEGORY_MAP.get(int(s), "PrivateToInstitue")
    norm = s.lower().replace(" ", "").replace("_", "")
    return CATEGORY_MAP.get(norm, "PrivateToInstitue")


def map_topic_access(val: Any) -> str:
    if val is None:
        return "Open"
    if isinstance(val, int):
        return ACCESS_MAP.get(val, "Open")
    s = str(val).strip()
    if s.isdigit():
        return ACCESS_MAP.get(int(s), "Open")
    return ACCESS_MAP.get(s.lower(), "Open")


def map_topic_status(val: Any) -> str:
    if val is None:
        return "Active"
    if isinstance(val, int):
        return TOPIC_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return TOPIC_STATUS_MAP.get(int(s), "Active")
    return TOPIC_STATUS_MAP.get(s.lower(), "Active")


# -----------------------------------------------------------------------------
# Document Field Extractor (Only RavenDB fields, no metadata columns)
# -----------------------------------------------------------------------------


def extract_topic_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for topics table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    topic_id = clean_uuid(raw_id)
    if not topic_id:
        raise ValueError(f"Topic missing valid UUID: {raw_id}")

    main_topic_id = clean_uuid(doc.get("MainTopicId"))
    name = clean_str(doc.get("Name"), 150)
    friendly_name = clean_str(doc.get("FriendlyName"), 150)
    description = clean_str(doc.get("Description"))

    role = map_topic_role(doc.get("Role"))
    category = map_topic_category(doc.get("Category"))
    access = map_topic_access(doc.get("Access"))
    subscriptions = as_json(doc.get("Subscriptions"))

    status = map_topic_status(doc.get("Status"))
    meta = as_json(doc.get("Meta") if isinstance(doc.get("Meta"), dict) else {}, default_val={})
    tags = clean_string_list(doc.get("Tags"))

    can_unsubscribe = clean_bool(doc.get("CanUnsubscribe"), False)
    can_publish = clean_bool(doc.get("CanPublish"), False)
    is_subscription_allowed = clean_bool(doc.get("IsSubscriptionAllowed"), False)
    handle = clean_str(doc.get("Handle"), 150)

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        topic_id,
        main_topic_id,
        name,
        friendly_name,
        description,
        role,
        category,
        access,
        subscriptions,
        status,
        meta,
        tags,
        can_unsubscribe,
        can_publish,
        is_subscription_allowed,
        handle,
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
    """Create target enums and topics table without secondary indexes."""
    cur.execute(
        """
        -- 1. Create Enums
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'topic_role_enum') THEN
                CREATE TYPE topic_role_enum AS ENUM (
                    'Admin',
                    'Member'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'topic_category_enum') THEN
                CREATE TYPE topic_category_enum AS ENUM (
                    'PrivateToInstitue',
                    'Public'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'topic_access_enum') THEN
                CREATE TYPE topic_access_enum AS ENUM (
                    'Open',
                    'Restricted'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'topic_status_enum') THEN
                CREATE TYPE topic_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Disabled'
                );
            END IF;
        END $$;

        -- Drop legacy views if they exist to prevent table/view name collisions
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'topics') THEN
                DROP VIEW topics CASCADE;
            END IF;
        END $$;

        -- 2. Create Target Table (No secondary indexes)
        CREATE TABLE IF NOT EXISTS topics (
            id UUID PRIMARY KEY,
            main_topic_id UUID,
            name VARCHAR(150),
            friendly_name VARCHAR(150),
            description TEXT,
            role topic_role_enum NOT NULL DEFAULT 'Admin',
            category topic_category_enum NOT NULL DEFAULT 'PrivateToInstitue',
            access topic_access_enum NOT NULL DEFAULT 'Open',
            subscriptions JSONB,
            status topic_status_enum NOT NULL DEFAULT 'Active',
            meta JSONB DEFAULT '{}'::jsonb,
            tags TEXT[] DEFAULT '{}'::text[],
            can_unsubscribe BOOLEAN DEFAULT FALSE,
            can_publish BOOLEAN DEFAULT FALSE,
            is_subscription_allowed BOOLEAN DEFAULT FALSE,
            handle VARCHAR(150),
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- Backward-compatibility view for singular 'topic' query
        CREATE OR REPLACE VIEW topic AS SELECT * FROM topics;
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operation
# -----------------------------------------------------------------------------


def upsert_topic(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> UpsertResult:
    """Idempotently upsert a Topic document."""
    fields = extract_topic_fields(doc)
    sql = """
        INSERT INTO topics (
            id, main_topic_id, name, friendly_name, description,
            role, category, access, subscriptions, status,
            meta, tags, can_unsubscribe, can_publish, is_subscription_allowed,
            handle, owner_id, parent_id, created_on, created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            main_topic_id = EXCLUDED.main_topic_id,
            name = EXCLUDED.name,
            friendly_name = EXCLUDED.friendly_name,
            description = EXCLUDED.description,
            role = EXCLUDED.role,
            category = EXCLUDED.category,
            access = EXCLUDED.access,
            subscriptions = EXCLUDED.subscriptions,
            status = EXCLUDED.status,
            meta = EXCLUDED.meta,
            tags = EXCLUDED.tags,
            can_unsubscribe = EXCLUDED.can_unsubscribe,
            can_publish = EXCLUDED.can_publish,
            is_subscription_allowed = EXCLUDED.is_subscription_allowed,
            handle = EXCLUDED.handle,
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
    """Run the end-to-end migration for Topics."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collection={cfg.topics_collection}"
        )
        print("[1/4] Fetching RavenDB documents...")
        topic_docs = raven_query_collection(
            requests_session, cfg, cfg.topics_collection
        )

        # Fallback to singular name if 0 docs fetched with default collection name
        if not topic_docs and cfg.topics_collection == "Topics":
            try:
                alt_docs = raven_query_collection(requests_session, cfg, "Topic")
                if alt_docs:
                    print(f"Fallback: Loaded {len(alt_docs)} docs from 'Topic'.")
                    topic_docs = alt_docs
            except Exception:
                pass

        print(f"Fetched topics={len(topic_docs)}")

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

        loaded_topics = 0
        new_topics = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/4] Upserting topics...")
                for d in topic_docs:
                    res = upsert_topic(cur, d)
                    loaded_topics += 1
                    new_topics += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collection": cfg.topics_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "topics_processed": loaded_topics,
                "new_topics_inserted": new_topics,
            },
        }

        print("Migration completed.")
        print(f"topics_processed: {loaded_topics}")
        print(f"new_topics_inserted: {new_topics}")

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
