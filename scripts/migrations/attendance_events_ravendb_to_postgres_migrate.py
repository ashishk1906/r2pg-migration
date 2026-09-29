#!/usr/bin/env python3
"""
Extract AttendanceEvents data from RavenDB and load into PostgreSQL.

Target table:
- attendance_event
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import requests

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
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
    attendance_events_collection: str
    page_size: int
    timeout_sec: int
    summary_json_path: Optional[str]
    write_summary_json: bool


@dataclass
class UpsertResult:
    record_id: str
    inserted: bool


# ---------------------------------------------------------------------------
# Environment & CLI Configuration
# ---------------------------------------------------------------------------

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
        description="Migrate AttendanceEvents data from RavenDB to PostgreSQL"
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
        help="Disable TLS certificate verification for RavenDB HTTPS.",
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
        "--attendance-events-collection",
        default=os.getenv("ATTENDANCE_EVENTS_COLLECTION", "AttendanceEvents"),
        help="RavenDB collection name for attendance events (default: AttendanceEvents)",
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
        default=os.getenv("MIGRATION_SUMMARY_JSON"),
        help="Optional output path for post-run summary JSON artifact.",
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        help="Disable writing post-run summary JSON artifact.",
    )

    args = parser.parse_args()

    if args.raven_cert_file and not os.path.isabs(args.raven_cert_file):
        for cert_dir in (
            os.getcwd(),
            os.path.join(script_dir, "..", ".."),
            os.path.join(script_dir, ".."),
            script_dir,
        ):
            cand = os.path.join(cert_dir, args.raven_cert_file)
            if os.path.isfile(cand):
                args.raven_cert_file = cand
                break

    return Config(
        raven_url=(args.raven_url or "").rstrip("/"),
        raven_db=args.raven_db or "",
        raven_cert_file=args.raven_cert_file,
        raven_cert_password=args.raven_cert_password,
        raven_insecure=args.raven_insecure,
        pg_host=args.pg_host,
        pg_port=args.pg_port,
        pg_db=args.pg_db,
        pg_user=args.pg_user,
        pg_password=args.pg_password,
        attendance_events_collection=args.attendance_events_collection,
        page_size=max(1, args.page_size),
        timeout_sec=max(1, args.timeout_sec),
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
    )


def write_summary_json(path_text: str, payload: Dict[str, Any]) -> str:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path.resolve())


# ---------------------------------------------------------------------------
# Data Parsing & Normalization Helpers
# ---------------------------------------------------------------------------

def clean_uuid(raw_val: Any) -> Optional[str]:
    """Extract and validate UUID string, returning None if missing or invalid."""
    if not raw_val:
        return None
    val_str = str(raw_val).strip()
    match = UUID_RE.search(val_str)
    return match.group(0).lower() if match else None


def clean_str(val: Any, max_len: Optional[int] = None) -> Optional[str]:
    """Clean string value, stripping whitespace and enforcing optional max length."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if max_len and len(s) > max_len:
        s = s[:max_len]
    return s


def clean_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    """Parse integer value with fallback."""
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def clean_bool(val: Any, default: bool = False) -> bool:
    """Parse boolean value with fallback."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "1", "t", "yes", "y"):
        return True
    if s in ("false", "0", "f", "no", "n"):
        return False
    return default


def parse_iso_timestamp(val: Any) -> Optional[datetime]:
    """Parse ISO timestamp strings from RavenDB to UTC datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    val_str = str(val).strip()
    if not val_str:
        return None
    if val_str.endswith("Z"):
        val_str = val_str[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(val_str)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    if "." in val_str:
        parts = val_str.split(".")
        main_part = parts[0]
        tz_part = ""
        sub_part = parts[1]
        if "+" in sub_part:
            sub_part, tz_part = sub_part.split("+", 1)
            tz_part = "+" + tz_part
        elif "-" in sub_part:
            sub_part, tz_part = sub_part.split("-", 1)
            tz_part = "-" + tz_part
        elif "Z" in sub_part:
            sub_part = sub_part.replace("Z", "")
            tz_part = "+00:00"
        sub_part = (sub_part + "000000")[:6]
        try:
            iso_clean = f"{main_part}.{sub_part}{tz_part}"
            dt = datetime.fromisoformat(iso_clean)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def extract_attendance_event_fields(doc: Dict[str, Any]) -> Optional[Tuple]:
    """Extract and validate business fields from RavenDB document.

    C# AttendanceEvent (extends Entity) fields:
    Entity base: Id, OwnerId, ParentId, CreatedOn, CreatedBy, ModifiedOn, ModifiedBy
    AttendanceEvent: InstId, CourseId, TermName, SectionName, Date (DateTime),
    PeriodNo (int), SubjectName, IsOptionalSubject (bool), StudentId, StaffId,
    Attendance (string - plain string, not an enum in C#)
    """
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    if not raw_id:
        return None
    event_id = str(raw_id).strip()

    inst_id = clean_uuid(doc.get("InstId"))
    course_id = clean_uuid(doc.get("CourseId"))
    term_name = clean_str(doc.get("TermName"), 100)
    section_name = clean_str(doc.get("SectionName"), 50)
    event_date = parse_iso_timestamp(doc.get("Date"))
    period_no = clean_int(doc.get("PeriodNo"))
    subject_name = clean_str(doc.get("SubjectName"), 200)
    is_optional_subject = clean_bool(doc.get("IsOptionalSubject"), False)
    student_id = clean_uuid(doc.get("StudentId"))
    staff_id = clean_str(doc.get("StaffId"), 100)
    attendance = clean_str(doc.get("Attendance"), 50)
    created_on = parse_iso_timestamp(doc.get("CreatedOn")) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        event_id,
        inst_id,
        course_id,
        term_name,
        section_name,
        event_date,
        period_no,
        subject_name,
        is_optional_subject,
        student_id,
        staff_id,
        attendance,
        created_on,
        created_by,
        owner_id,
        parent_id,
        modified_on,
        modified_by,
    )


# ---------------------------------------------------------------------------
# RavenDB Connection & Extraction
# ---------------------------------------------------------------------------

def configure_raven_session(session: requests.Session, cfg: Config) -> None:
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


def fetch_all_raven_documents(
    session: requests.Session, cfg: Config, collection_name: str
) -> List[Dict[str, Any]]:
    """Fetch all documents from a RavenDB collection using paged RQL queries."""
    url = f"{cfg.raven_url}/databases/{cfg.raven_db}/queries"
    start = 0
    docs: List[Dict[str, Any]] = []
    escaped = collection_name.replace("\\", "\\\\").replace('"', '\\"')

    while True:
        payload = {
            "Query": f'from "{escaped}" order by id()',
            "Start": start,
            "PageSize": cfg.page_size,
        }
        resp = session.post(url, json=payload, timeout=cfg.timeout_sec)
        resp.raise_for_status()

        body = resp.json()
        results = body.get("Results", [])
        if not results:
            break

        docs.extend(results)
        start += len(results)

    return docs


# ---------------------------------------------------------------------------
# Target Schema Setup
# ---------------------------------------------------------------------------

def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target attendance_event table with correct schema.

    C# AttendanceEvent has no enum fields - Attendance is a plain string.
    No NOT NULL constraints or DEFAULT values are added beyond the primary key.
    """
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_event (
            id                  VARCHAR(100) PRIMARY KEY,
            inst_id             UUID,
            course_id           UUID,
            term_name           VARCHAR(100),
            section_name        VARCHAR(50),
            date                TIMESTAMPTZ,
            period_no           INTEGER,
            subject_name        VARCHAR(200),
            is_optional_subject BOOLEAN,
            student_id          UUID,
            staff_id            VARCHAR(100),
            attendance          VARCHAR(50),
            created_on          TIMESTAMPTZ,
            created_by          UUID,
            owner_id            UUID,
            parent_id           UUID,
            modified_on         TIMESTAMPTZ,
            modified_by         UUID
        );
        """
    )


# ---------------------------------------------------------------------------
# Idempotent Upsert Operation
# ---------------------------------------------------------------------------

def upsert_attendance_event(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> Optional[UpsertResult]:
    """Idempotently insert or update a single AttendanceEvent row."""
    record = extract_attendance_event_fields(doc)
    if not record:
        return None

    event_id = record[0]
    cur.execute("SELECT 1 FROM attendance_event WHERE id = %s;", (event_id,))
    is_new = cur.fetchone() is None

    cur.execute(
        """
        INSERT INTO attendance_event (
            id,
            inst_id,
            course_id,
            term_name,
            section_name,
            date,
            period_no,
            subject_name,
            is_optional_subject,
            student_id,
            staff_id,
            attendance,
            created_on,
            created_by,
            owner_id,
            parent_id,
            modified_on,
            modified_by
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            inst_id             = EXCLUDED.inst_id,
            course_id           = EXCLUDED.course_id,
            term_name           = EXCLUDED.term_name,
            section_name        = EXCLUDED.section_name,
            date                = EXCLUDED.date,
            period_no           = EXCLUDED.period_no,
            subject_name        = EXCLUDED.subject_name,
            is_optional_subject = EXCLUDED.is_optional_subject,
            student_id          = EXCLUDED.student_id,
            staff_id            = EXCLUDED.staff_id,
            attendance          = EXCLUDED.attendance,
            created_on          = EXCLUDED.created_on,
            created_by          = EXCLUDED.created_by,
            owner_id            = EXCLUDED.owner_id,
            parent_id           = EXCLUDED.parent_id,
            modified_on         = EXCLUDED.modified_on,
            modified_by         = EXCLUDED.modified_by;
        """,
        record,
    )
    return UpsertResult(record_id=event_id, inserted=is_new)


# ---------------------------------------------------------------------------
# Main Execution Workflow
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = parse_args()
    requests_session = requests.Session()
    conn = None

    try:
        configure_raven_session(requests_session, cfg)
        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collection={cfg.attendance_events_collection}"
        )

        print("[1/4] Fetching RavenDB documents...")
        event_docs = fetch_all_raven_documents(
            requests_session, cfg, cfg.attendance_events_collection
        )
        print(f"Fetched attendance_events={len(event_docs)}")

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

        print("[3/4] Setting up target schema...")
        with conn:
            with conn.cursor() as cur:
                ensure_target_schema(cur)

        print("[4/4] Upserting attendance events...")
        events_processed = 0
        events_inserted = 0

        with conn:
            with conn.cursor() as cur:
                for doc in event_docs:
                    result = upsert_attendance_event(cur, doc)
                    if result is not None:
                        events_processed += 1
                        events_inserted += int(result.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collection": cfg.attendance_events_collection,
                "documents_fetched": len(event_docs),
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "table": "attendance_event",
            },
            "run_stats": {
                "attendance_events_processed": events_processed,
                "new_attendance_events_inserted": events_inserted,
            },
        }

        print("Migration completed.")
        print(f"attendance_events_processed: {events_processed}")
        print(f"new_attendance_events_inserted: {events_inserted}")

        if cfg.write_summary_json:
            output_path = cfg.summary_json_path
            if not output_path:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                output_path = f"validation/attendance-events-migration-summary-{timestamp}.json"
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
