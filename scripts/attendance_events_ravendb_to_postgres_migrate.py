#!/usr/bin/env python3
"""
Extract AttendanceEvents data from RavenDB and load into PostgreSQL.

The RavenDB AttendanceEvent document is a flat structure with no nested
arrays or objects. All fields map directly to PostgreSQL columns.

Data type mappings (from C# AttendanceEvent read model):
  Id              : string    -> text  (PK, RavenDB doc id e.g. "AttendanceEvents/1-A")
  InstId          : string    -> text
  CourseId        : string    -> text
  TermName        : string    -> text
  SectionName     : string    -> text
  Date            : DateTime  -> timestamp without time zone
  PeriodNo        : int       -> integer
  SubjectName     : string    -> text
  IsOptionalSubject : bool    -> boolean
  StudentId       : string    -> text
  StaffId         : string    -> text
  Attendance      : string    -> text
  CreatedOn       : DateTime  -> timestamp without time zone
  CreatedBy       : string    -> text
  OwnerId         : string    -> text
  ParentId        : string    -> text
  ModifiedOn      : DateTime? -> timestamp without time zone  (nullable)
  ModifiedBy      : string    -> text                         (nullable)

Before running: set all required configuration values in .env
(or pass them explicitly as command-line arguments).

Target table:
  - attendance_event
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import psycopg2
import requests


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
    inspect_source_only: bool


@dataclass
class UpsertResult:
    record_id: str
    inserted: bool


# ---------------------------------------------------------------------------
# Environment & CLI helpers
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
    root_env = os.path.join(script_dir, "..", ".env")
    if os.path.exists(root_env):
        load_env_file(root_env)

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
        help=(
            "Optional output path for post-run JSON artifact. "
            "Default when omitted: validation/attendance-events-migration-summary-<timestamp>.json"
        ),
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        help="Disable writing post-run summary JSON artifact.",
    )
    parser.add_argument(
        "--inspect-source-only",
        action="store_true",
        help="Fetch RavenDB AttendanceEvents and print source shape/counts without writing PostgreSQL.",
    )

    args = parser.parse_args()

    if not args.raven_url or not args.raven_db:
        parser.error(
            "Missing RavenDB config. Provide --raven-url/--raven-db or set RAVEN_URL/RAVEN_DB."
        )
    if not args.inspect_source_only:
        if not args.pg_password:
            parser.error(
                "Missing PostgreSQL password. Provide --pg-password or set PG_PASSWORD."
            )
        if (
            not args.pg_host
            or args.pg_port is None
            or not args.pg_db
            or not args.pg_user
        ):
            parser.error(
                "Missing PostgreSQL config. Provide --pg-host/--pg-port/--pg-db/--pg-user or set PG_HOST/PG_PORT/PG_DB/PG_USER."
            )

    if args.raven_cert_file:
        cert_path = args.raven_cert_file
        if not os.path.isfile(cert_path):
            candidate = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), cert_path
            )
            if os.path.isfile(candidate):
                args.raven_cert_file = candidate
            else:
                parser.error(f"Raven cert file not found: {args.raven_cert_file}")
    if args.raven_cert_file and not args.raven_url.lower().startswith("https://"):
        parser.error(
            "RAVEN_CERT_FILE requires an https:// RavenDB URL because certificate authentication uses mutual TLS."
        )

    return Config(
        raven_url=args.raven_url.rstrip("/"),
        raven_db=args.raven_db,
        raven_cert_file=args.raven_cert_file,
        raven_cert_password=args.raven_cert_password,
        raven_insecure=args.raven_insecure,
        pg_host=args.pg_host or "",
        pg_port=args.pg_port or 0,
        pg_db=args.pg_db or "",
        pg_user=args.pg_user or "",
        pg_password=args.pg_password or "",
        attendance_events_collection=args.attendance_events_collection,
        page_size=max(1, args.page_size),
        timeout_sec=max(1, args.timeout_sec),
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
        inspect_source_only=args.inspect_source_only,
    )


# ---------------------------------------------------------------------------
# JSON summary helper
# ---------------------------------------------------------------------------

def write_summary_json(path_text: str, payload: Dict[str, Any]) -> str:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path.resolve())


# ---------------------------------------------------------------------------
# Parsing & Data Conversion Helpers
# ---------------------------------------------------------------------------

def as_text(value: Any) -> Optional[str]:
    """Convert to text, returning None for None/empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def parse_ts(value: Any) -> Optional[str]:
    """Parse a timestamp string into a normalized ISO format for PostgreSQL
    timestamp without time zone. Strips timezone info since the target column
    is 'timestamp without time zone'."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    # Remove trailing Z and treat as UTC
    if text.endswith("Z"):
        text = text[:-1]

    # Truncate fractional seconds to 6 digits (microseconds) for PostgreSQL
    if "." in text:
        base, frac = text.split(".", 1)
        # Separate any timezone part (should not be present after Z removal,
        # but handle defensively)
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
        text = f"{base}.{digits}{tz_part}" if digits else f"{base}{tz_part}"

    # Strip any remaining timezone offset for 'timestamp without time zone'
    # e.g. "+05:30" or "-04:00"
    if len(text) > 19:
        for sep in ("+", "-"):
            pos = text.find(sep, 19)
            if pos >= 0:
                text = text[:pos]
                break

    try:
        datetime.fromisoformat(text)
        return text
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    """Parse an integer value, returning None for non-parseable input."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def parse_bool(value: Any, default: bool = False) -> bool:
    """Parse a boolean value with fallback default."""
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


def derive_event_id(doc: Dict[str, Any]) -> Optional[str]:
    """Extract the document ID from a RavenDB AttendanceEvent document.

    RavenDB AttendanceEvents use string IDs like 'AttendanceEvents/1-A'
    (not UUIDs), so we return the full document ID as text.
    """
    metadata = doc.get("@metadata")
    if isinstance(metadata, dict):
        meta_id = metadata.get("@id")
        if meta_id:
            return str(meta_id).strip()

    # Fallback to top-level Id field
    doc_id = doc.get("Id") or doc.get("id")
    if doc_id:
        return str(doc_id).strip()

    return None


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
            raise RuntimeError(
                f"Unexpected RavenDB response for {collection_name}"
            )
        results = body.get("Results", [])
        if not isinstance(results, list):
            raise RuntimeError(
                f"Unexpected RavenDB response for {collection_name}"
            )
        if any(not isinstance(result, dict) for result in results):
            raise RuntimeError(
                f"RavenDB returned a non-document result for {collection_name}"
            )
        if not results:
            break

        docs.extend(results)
        start += len(results)

    return docs


# ---------------------------------------------------------------------------
# PostgreSQL Schema Setup
# ---------------------------------------------------------------------------

def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create attendance_event table with exact target schema.

    All string fields use TEXT (not UUID) and timestamps use
    'timestamp without time zone' per the C# AttendanceEvent model.
    """
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_event (
            id                  TEXT PRIMARY KEY,
            inst_id             TEXT,
            course_id           TEXT,
            term_name           TEXT,
            section_name        TEXT,
            date                TIMESTAMP WITHOUT TIME ZONE,
            period_no           INTEGER,
            subject_name        TEXT,
            is_optional_subject BOOLEAN DEFAULT FALSE,
            student_id          TEXT,
            staff_id            TEXT,
            attendance          TEXT,
            created_on          TIMESTAMP WITHOUT TIME ZONE,
            created_by          TEXT,
            owner_id            TEXT,
            parent_id           TEXT,
            modified_on         TIMESTAMP WITHOUT TIME ZONE,
            modified_by         TEXT
        );
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    """Verify that the attendance_event table has all required columns
    with the correct data types."""
    required_columns: Dict[str, Sequence[str]] = {
        "attendance_event": (
            "id",
            "inst_id",
            "course_id",
            "term_name",
            "section_name",
            "date",
            "period_no",
            "subject_name",
            "is_optional_subject",
            "student_id",
            "staff_id",
            "attendance",
            "created_on",
            "created_by",
            "owner_id",
            "parent_id",
            "modified_on",
            "modified_by",
        )
    }
    required_types: Dict[str, Dict[str, Sequence[str]]] = {
        "attendance_event": {
            "id": ("text",),
            "inst_id": ("text",),
            "course_id": ("text",),
            "term_name": ("text",),
            "section_name": ("text",),
            "date": ("timestamp without time zone",),
            "period_no": ("integer",),
            "subject_name": ("text",),
            "is_optional_subject": ("boolean",),
            "student_id": ("text",),
            "staff_id": ("text",),
            "attendance": ("text",),
            "created_on": ("timestamp without time zone",),
            "created_by": ("text",),
            "owner_id": ("text",),
            "parent_id": ("text",),
            "modified_on": ("timestamp without time zone",),
            "modified_by": ("text",),
        }
    }

    for table_name, columns in required_columns.items():
        cur.execute(
            """
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        )
        rows = cur.fetchall()
        existing = {row[0] for row in rows}
        type_by_column = {row[0]: str(row[1]).lower() for row in rows}
        udt_by_column = {row[0]: str(row[2]).lower() for row in rows}

        if not existing:
            raise RuntimeError(f"Missing required table public.{table_name}.")
        missing = [col for col in columns if col not in existing]
        if missing:
            raise RuntimeError(
                f"Table public.{table_name} is missing required columns: {', '.join(missing)}"
            )

        mismatches = []
        for column_name, expected_types in required_types.get(table_name, {}).items():
            actual_type = type_by_column.get(column_name)
            actual_udt = udt_by_column.get(column_name)
            if actual_type is None:
                continue
            if actual_type not in expected_types and actual_udt not in expected_types:
                mismatches.append(
                    f"{column_name} expected {', '.join(expected_types)} but found {actual_type} ({actual_udt})"
                )
        if mismatches:
            raise RuntimeError(
                f"Table public.{table_name} has datatype mismatches: {'; '.join(mismatches)}"
            )


# ---------------------------------------------------------------------------
# Upsert: AttendanceEvent
# ---------------------------------------------------------------------------

def upsert_attendance_event(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> Optional[UpsertResult]:
    """Insert or update a single AttendanceEvent row."""
    event_id = derive_event_id(doc)
    if not event_id:
        return None

    cur.execute("SELECT 1 FROM attendance_event WHERE id = %s", (event_id,))
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
        ON CONFLICT (id)
        DO UPDATE SET
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
            modified_by         = EXCLUDED.modified_by
        RETURNING id;
        """,
        (
            event_id,
            as_text(doc.get("InstId")),
            as_text(doc.get("CourseId")),
            as_text(doc.get("TermName")),
            as_text(doc.get("SectionName")),
            parse_ts(doc.get("Date")),
            parse_int(doc.get("PeriodNo")),
            as_text(doc.get("SubjectName")),
            parse_bool(doc.get("IsOptionalSubject"), False),
            as_text(doc.get("StudentId")),
            as_text(doc.get("StaffId")),
            as_text(doc.get("Attendance")),
            parse_ts(doc.get("CreatedOn")),
            as_text(doc.get("CreatedBy")),
            as_text(doc.get("OwnerId")),
            as_text(doc.get("ParentId")),
            parse_ts(doc.get("ModifiedOn")),
            as_text(doc.get("ModifiedBy")),
        ),
    )

    row = cur.fetchone()
    if not row:
        return None
    return UpsertResult(str(row[0]), is_new)


# ---------------------------------------------------------------------------
# Source Inspection
# ---------------------------------------------------------------------------

def build_source_profile(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a summary profile of the source RavenDB documents."""
    profile: Dict[str, Any] = {
        "attendance_event_documents": len(docs),
        "with_event_id": 0,
        "distinct_inst_ids": set(),
        "distinct_course_ids": set(),
        "distinct_student_ids": set(),
        "distinct_staff_ids": set(),
        "attendance_values": set(),
        "period_no_range": {"min": None, "max": None},
        "first_event": None,
    }

    for doc in docs:
        if derive_event_id(doc):
            profile["with_event_id"] += 1

        inst_id = doc.get("InstId")
        if inst_id:
            profile["distinct_inst_ids"].add(inst_id)

        course_id = doc.get("CourseId")
        if course_id:
            profile["distinct_course_ids"].add(course_id)

        student_id = doc.get("StudentId")
        if student_id:
            profile["distinct_student_ids"].add(student_id)

        staff_id = doc.get("StaffId")
        if staff_id:
            profile["distinct_staff_ids"].add(staff_id)

        attendance = doc.get("Attendance")
        if attendance:
            profile["attendance_values"].add(attendance)

        period_no = parse_int(doc.get("PeriodNo"))
        if period_no is not None:
            if profile["period_no_range"]["min"] is None or period_no < profile["period_no_range"]["min"]:
                profile["period_no_range"]["min"] = period_no
            if profile["period_no_range"]["max"] is None or period_no > profile["period_no_range"]["max"]:
                profile["period_no_range"]["max"] = period_no

    if docs:
        first = docs[0]
        profile["first_event"] = {
            "id": derive_event_id(first),
            "inst_id": first.get("InstId"),
            "course_id": first.get("CourseId"),
            "student_id": first.get("StudentId"),
            "attendance": first.get("Attendance"),
            "date": first.get("Date"),
            "period_no": first.get("PeriodNo"),
        }

    # Convert sets to sorted lists for JSON serialization
    profile["distinct_inst_ids"] = sorted(profile["distinct_inst_ids"])
    profile["distinct_course_ids"] = sorted(profile["distinct_course_ids"])
    profile["distinct_student_ids"] = sorted(profile["distinct_student_ids"])
    profile["distinct_staff_ids"] = sorted(profile["distinct_staff_ids"])
    profile["attendance_values"] = sorted(profile["attendance_values"])

    return profile


# ---------------------------------------------------------------------------
# API Payload Validation
# ---------------------------------------------------------------------------

def iso_utc(value: Any) -> Optional[str]:
    """Format a datetime as a UTC ISO string for API payload output."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(timespec="microseconds")
            .rstrip("0")
            .rstrip(".")
            + "Z"
        )
    return str(value)


def to_camel_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a snake_case DB row dict to camelCase for API payload validation."""
    return {
        "id": row.get("id"),
        "instId": row.get("inst_id"),
        "courseId": row.get("course_id"),
        "termName": row.get("term_name"),
        "sectionName": row.get("section_name"),
        "date": iso_utc(row.get("date")),
        "periodNo": row.get("period_no"),
        "subjectName": row.get("subject_name"),
        "isOptionalSubject": row.get("is_optional_subject"),
        "studentId": row.get("student_id"),
        "staffId": row.get("staff_id"),
        "attendance": row.get("attendance"),
        "createdOn": iso_utc(row.get("created_on")),
        "createdBy": row.get("created_by"),
        "ownerId": row.get("owner_id"),
        "parentId": row.get("parent_id") or "",
        "modifiedOn": iso_utc(row.get("modified_on")),
        "modifiedBy": row.get("modified_by"),
    }


def build_attendance_events_list_payload(
    cur: psycopg2.extensions.cursor, params: Dict[str, Any]
) -> Dict[str, Any]:
    top = int(params.get("recordsPerPage") or 256)
    current_page = int(params.get("currentPage") or 0)
    offset = current_page * top

    cur.execute("SELECT COUNT(*) FROM attendance_event")
    total_records = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT
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
        FROM attendance_event
        ORDER BY created_on DESC NULLS LAST, id
        LIMIT %s OFFSET %s
        """,
        (top, offset),
    )

    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    data = [to_camel_dict(row) for row in rows]
    total_pages = (total_records + top - 1) // top if top > 0 else 0

    return {
        "data": data,
        "meta": None,
        "createdOn": iso_utc(datetime.now(timezone.utc)),
        "requestUrl": None,
        "requestVerb": None,
        "pagedResults": False,
        "currentPage": current_page,
        "recordsPerPage": top,
        "totalRecords": total_records,
        "totalPages": total_pages,
    }


def build_api_payload_validation(
    cur: psycopg2.extensions.cursor,
) -> Dict[str, Any]:
    list_params = {
        "currentPage": 0,
        "recordsPerPage": 256,
    }
    return {
        "reference": {
            "note": "PostgreSQL-derived API-shaped payloads for attendance_event read parity validation.",
        },
        "endpoints": {
            "attendanceEventsList": {
                "request": list_params,
                "response": build_attendance_events_list_payload(cur, list_params),
            }
        },
    }


# ---------------------------------------------------------------------------
# Main Execution
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
        print("[1/3] Fetching RavenDB AttendanceEvents documents...")
        event_docs = raven_query_collection(
            requests_session, cfg, cfg.attendance_events_collection
        )
        print(f"Fetched attendance_events={len(event_docs)}")

        if cfg.inspect_source_only:
            print(json.dumps(build_source_profile(event_docs), indent=2))
            return 0

        print("[2/3] Connecting PostgreSQL...")
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

        events_processed = 0
        events_inserted = 0
        skipped_missing_id = 0

        with conn:
            with conn.cursor() as cur:
                ensure_target_schema(cur)
                assert_required_schema(cur)

                print("[3/3] Upserting attendance events...")
                for doc in event_docs:
                    result = upsert_attendance_event(cur, doc)
                    if result is None:
                        skipped_missing_id += 1
                        continue
                    events_processed += 1
                    events_inserted += int(result.inserted)

        # Post-load counts and optional API payload validation
        api_payload_validation: Optional[Dict[str, Any]] = None
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM attendance_event")
            event_count = int(cur.fetchone()[0])
            api_payload_validation = build_api_payload_validation(cur)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "attendance_events_collection": cfg.attendance_events_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
                "table": "attendance_event",
            },
            "run_stats": {
                "events_processed": events_processed,
                "new_events_inserted": events_inserted,
                "skipped_missing_id": skipped_missing_id,
            },
            "post_load_counts": {
                "attendance_event": event_count,
            },
        }
        if api_payload_validation is not None:
            summary["api_payload_validation"] = api_payload_validation

        print("\n" + "=" * 50)
        print("AttendanceEvents Migration Completed Successfully.")
        print(f"Events processed:    {events_processed}")
        print(f"New rows inserted:   {events_inserted}")
        print(f"Skipped (no id):     {skipped_missing_id}")
        print(f"Total rows in table: {event_count}")
        print("=" * 50)

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
