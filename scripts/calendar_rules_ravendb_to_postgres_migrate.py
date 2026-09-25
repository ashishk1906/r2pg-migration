#!/usr/bin/env python3
"""
Extract CalendarRules data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs,
and load into PostgreSQL.

Target table:
- calendar_rules
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
import uuid

import psycopg2
import requests

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

UUID_NAMESPACE_CALENDAR_RULES = uuid.UUID("6ba7b81a-9dad-11d1-80b4-00c04fd430c8")

CALENDAR_RULE_STATUS_MAP: Dict[Any, str] = {
    0: "Unknown",
    1: "Active",
    99: "Disabled",
    "unknown": "Unknown",
    "active": "Active",
    "disabled": "Disabled",
    "inactive": "Disabled",
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
    calendar_rules_collection: str
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
        description="Migrate CalendarRules from RavenDB to PostgreSQL"
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
        "--calendar-rules-collection",
        default=os.getenv("CALENDAR_RULES_COLLECTION", "CalendarRules"),
        help="RavenDB collection name for calendar rules (default: CalendarRules)",
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
        calendar_rules_collection=args.calendar_rules_collection,
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


def clean_int(val: Any, default: Optional[int] = 0) -> Optional[int]:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def clean_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "1", "yes"}


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


def map_calendar_rule_status(val: Any) -> str:
    """Map status string/int to calendar_rule_status_enum."""
    if val is None:
        return "Active"
    if isinstance(val, int):
        return CALENDAR_RULE_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return CALENDAR_RULE_STATUS_MAP.get(int(s), "Active")
    return CALENDAR_RULE_STATUS_MAP.get(s.lower(), "Active")


# -----------------------------------------------------------------------------
# Document Field Extractor (Only RavenDB fields, no metadata columns)
# -----------------------------------------------------------------------------


def extract_calendar_rule_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for calendar_rules table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    rule_id = None
    if raw_id:
        clean_raw = str(raw_id).strip()
        last_part = clean_raw.rsplit("/", 1)[-1]
        if UUID_RE.fullmatch(last_part):
            rule_id = last_part.lower()
        elif UUID_RE.fullmatch(clean_raw):
            rule_id = clean_raw.lower()
        else:
            rule_id = str(
                uuid.uuid5(UUID_NAMESPACE_CALENDAR_RULES, clean_raw)
            ).lower()
    if not rule_id:
        raise ValueError(f"CalendarRule missing valid ID: {raw_id}")

    title = clean_str(doc.get("Title"), 255)
    cron_expression = clean_str(doc.get("CronExpression"), 100)
    calendar_rule_status = map_calendar_rule_status(doc.get("CalendarRuleStatus"))
    calendar_event_category = clean_str(doc.get("CalendarEventCategory"), 100)
    weight = clean_int(doc.get("Weight"), default=0)
    duration = clean_int(doc.get("Duration"), default=0)
    topic_id = clean_uuid(doc.get("TopicId"))
    user_id = clean_uuid(doc.get("UserId"))
    create_meeting_link = clean_bool(doc.get("CreateMeetingLink"), default=False)
    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        rule_id,
        title,
        cron_expression,
        calendar_rule_status,
        calendar_event_category,
        weight,
        duration,
        topic_id,
        user_id,
        create_meeting_link,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup (Only primary key, no secondary indexes, no views)
# -----------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target enums and calendar_rules table without secondary indexes or views."""
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'calendar_rule_status_enum') THEN
                CREATE TYPE calendar_rule_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Disabled'
                );
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS calendar_rules (
            id UUID PRIMARY KEY,
            title VARCHAR(255),
            cron_expression VARCHAR(100),
            calendar_rule_status calendar_rule_status_enum NOT NULL DEFAULT 'Active',
            calendar_event_category VARCHAR(100),
            weight INTEGER DEFAULT 0,
            duration INTEGER DEFAULT 0,
            topic_id UUID,
            user_id UUID,
            create_meeting_link BOOLEAN DEFAULT FALSE,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operation
# -----------------------------------------------------------------------------


def upsert_calendar_rule(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert a CalendarRule document."""
    fields = extract_calendar_rule_fields(doc)
    sql = """
        INSERT INTO calendar_rules (
            id,
            title,
            cron_expression,
            calendar_rule_status,
            calendar_event_category,
            weight,
            duration,
            topic_id,
            user_id,
            create_meeting_link,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            cron_expression = EXCLUDED.cron_expression,
            calendar_rule_status = EXCLUDED.calendar_rule_status,
            calendar_event_category = EXCLUDED.calendar_event_category,
            weight = EXCLUDED.weight,
            duration = EXCLUDED.duration,
            topic_id = EXCLUDED.topic_id,
            user_id = EXCLUDED.user_id,
            create_meeting_link = EXCLUDED.create_meeting_link,
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
    """Run the end-to-end migration for CalendarRules."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collection={cfg.calendar_rules_collection}"
        )
        print("[1/4] Fetching RavenDB documents...")
        rule_docs = raven_query_collection(
            requests_session, cfg, cfg.calendar_rules_collection
        )

        # Fallback to singular name if 0 docs fetched with default collection name
        if not rule_docs and cfg.calendar_rules_collection == "CalendarRules":
            try:
                alt_docs = raven_query_collection(requests_session, cfg, "CalendarRule")
                if alt_docs:
                    print(f"Fallback: Loaded {len(alt_docs)} docs from 'CalendarRule'.")
                    rule_docs = alt_docs
            except Exception:
                pass

        print(f"Fetched calendar_rules={len(rule_docs)}")

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

        loaded_rules = 0
        new_rules = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/4] Upserting calendar rules...")
                for d in rule_docs:
                    res = upsert_calendar_rule(cur, d)
                    loaded_rules += 1
                    new_rules += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collection": cfg.calendar_rules_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "calendar_rules_processed": loaded_rules,
                "new_calendar_rules_inserted": new_rules,
            },
        }

        print("Migration completed.")
        print(f"calendar_rules_processed: {loaded_rules}")
        print(f"new_calendar_rules_inserted: {new_rules}")

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
