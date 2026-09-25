#!/usr/bin/env python3
"""
Extract Staffs data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs and JSONBs,
and load into PostgreSQL.

Target table:
- staff (with backward-compatible view: staffs)
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
    staffs_collection: str
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
        description="Migrate Staffs from RavenDB to PostgreSQL"
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
        "--staffs-collection",
        default=os.getenv("STAFFS_COLLECTION", "Staffs"),
        help="RavenDB collection name for staffs (default: Staffs)",
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
        staffs_collection=args.staffs_collection,
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

STAFF_STATUS_MAP: Dict[Any, str] = {
    0: "Unknown",
    1: "Active",
    99: "Disabled",
    "unknown": "Unknown",
    "active": "Active",
    "disabled": "Disabled",
    "inactive": "Disabled",
}

STAFF_GENDER_MAP: Dict[str, str] = {
    "female": "Female",
    "f": "Female",
    "male": "Male",
    "m": "Male",
    "other": "Other",
    "noinfo": "NoInfo",
    "unknown": "NoInfo",
}


def map_staff_status(val: Any) -> str:
    if val is None:
        return "Active"
    if isinstance(val, int):
        return STAFF_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return STAFF_STATUS_MAP.get(int(s), "Active")
    return STAFF_STATUS_MAP.get(s.lower(), "Active")


def map_staff_gender(val: Any) -> str:
    if val is None:
        return "NoInfo"
    s = str(val).strip().lower()
    return STAFF_GENDER_MAP.get(s, "NoInfo")


# -----------------------------------------------------------------------------
# Document Field Extractor (Only RavenDB fields, no metadata columns)
# -----------------------------------------------------------------------------


def extract_staff_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for staff table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    staff_id = clean_uuid(raw_id)
    if not staff_id:
        raise ValueError(f"Staff missing valid UUID: {raw_id}")

    inst_id = clean_uuid(doc.get("InstId"))
    doj = parse_iso_timestamp(doc.get("DOJ"))
    designations = as_json(doc.get("Designations") if isinstance(doc.get("Designations"), list) else [], default_val=[])
    status = map_staff_status(doc.get("Status"))
    employment_history = as_json(doc.get("EmploymentHistory") if isinstance(doc.get("EmploymentHistory"), list) else [], default_val=[])
    course_subject_list = as_json(doc.get("CourseSubjectList") if isinstance(doc.get("CourseSubjectList"), list) else [], default_val=[])
    alias = clean_str(doc.get("Alias"), 200)
    class_teacher = as_json(doc.get("ClassTeacher") if isinstance(doc.get("ClassTeacher"), dict) else {}, default_val={})
    ref_id = clean_str(doc.get("RefId"), 100)
    user_id = clean_uuid(doc.get("UserId"))
    salaries = as_json(doc.get("Salaries") if isinstance(doc.get("Salaries"), list) else [], default_val=[])
    payslips = as_json(doc.get("Payslips") if isinstance(doc.get("Payslips"), list) else [], default_val=[])

    first_name = clean_str(doc.get("FirstName"), 150)
    middle_name = clean_str(doc.get("MiddleName"), 150)
    last_name = clean_str(doc.get("LastName"), 150)
    name = clean_str(doc.get("Name"), 250)
    title = clean_str(doc.get("Title"), 50)
    gender = map_staff_gender(doc.get("Gender"))
    dob = parse_iso_timestamp(doc.get("DOB"))
    email = clean_str(doc.get("Email"), 255)
    mobile = clean_str(doc.get("Mobile"), 50)
    virtual_id = clean_str(doc.get("VirtualId"), 255)

    contacts = as_json(doc.get("Contacts") if isinstance(doc.get("Contacts"), list) else [], default_val=[])
    addresses = as_json(doc.get("Addresses") if isinstance(doc.get("Addresses"), list) else [], default_val=[])
    tags = clean_string_list(doc.get("Tags"))
    attributes = as_json(doc.get("Attributes") if isinstance(doc.get("Attributes"), dict) else {}, default_val={})

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        staff_id,
        inst_id,
        doj,
        designations,
        status,
        employment_history,
        course_subject_list,
        alias,
        class_teacher,
        ref_id,
        user_id,
        salaries,
        payslips,
        first_name,
        middle_name,
        last_name,
        name,
        title,
        gender,
        dob,
        email,
        mobile,
        virtual_id,
        contacts,
        addresses,
        tags,
        attributes,
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
    """Create target enums and staff table without secondary indexes."""
    cur.execute(
        """
        -- 1. Create Enums
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'staff_gender_enum') THEN
                CREATE TYPE staff_gender_enum AS ENUM (
                    'Female',
                    'Male',
                    'Other',
                    'NoInfo'
                );
            ELSE
                BEGIN
                    ALTER TYPE staff_gender_enum ADD VALUE IF NOT EXISTS 'Other';
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END;
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'staff_status_enum') THEN
                CREATE TYPE staff_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Disabled'
                );
            END IF;
        END $$;

        -- 2. Create Target Table (No secondary indexes)
        CREATE TABLE IF NOT EXISTS staff (
            id UUID PRIMARY KEY,
            inst_id UUID,
            doj TIMESTAMPTZ,
            designations JSONB DEFAULT '[]'::jsonb,
            status staff_status_enum NOT NULL DEFAULT 'Active',
            employment_history JSONB DEFAULT '[]'::jsonb,
            course_subject_list JSONB DEFAULT '[]'::jsonb,
            alias VARCHAR(200),
            class_teacher JSONB DEFAULT '{}'::jsonb,
            ref_id VARCHAR(100),
            user_id UUID,
            salaries JSONB DEFAULT '[]'::jsonb,
            payslips JSONB DEFAULT '[]'::jsonb,
            first_name VARCHAR(150),
            middle_name VARCHAR(150),
            last_name VARCHAR(150),
            name VARCHAR(250),
            title VARCHAR(50),
            gender staff_gender_enum NOT NULL DEFAULT 'NoInfo',
            dob TIMESTAMPTZ,
            email VARCHAR(255),
            mobile VARCHAR(50),
            virtual_id VARCHAR(255),
            contacts JSONB DEFAULT '[]'::jsonb,
            addresses JSONB DEFAULT '[]'::jsonb,
            tags TEXT[] DEFAULT '{}'::text[],
            attributes JSONB DEFAULT '{}'::jsonb,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- Backward-compatibility view for plural 'staffs' query
        CREATE OR REPLACE VIEW staffs AS SELECT * FROM staff;
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operation
# -----------------------------------------------------------------------------


def upsert_staff(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> UpsertResult:
    """Idempotently upsert a Staff document."""
    fields = extract_staff_fields(doc)
    sql = """
        INSERT INTO staff (
            id, inst_id, doj, designations, status,
            employment_history, course_subject_list, alias, class_teacher,
            ref_id, user_id, salaries, payslips,
            first_name, middle_name, last_name, name, title, gender,
            dob, email, mobile, virtual_id,
            contacts, addresses, tags, attributes,
            owner_id, parent_id, created_on, created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            inst_id = EXCLUDED.inst_id,
            doj = EXCLUDED.doj,
            designations = EXCLUDED.designations,
            status = EXCLUDED.status,
            employment_history = EXCLUDED.employment_history,
            course_subject_list = EXCLUDED.course_subject_list,
            alias = EXCLUDED.alias,
            class_teacher = EXCLUDED.class_teacher,
            ref_id = EXCLUDED.ref_id,
            user_id = EXCLUDED.user_id,
            salaries = EXCLUDED.salaries,
            payslips = EXCLUDED.payslips,
            first_name = EXCLUDED.first_name,
            middle_name = EXCLUDED.middle_name,
            last_name = EXCLUDED.last_name,
            name = EXCLUDED.name,
            title = EXCLUDED.title,
            gender = EXCLUDED.gender,
            dob = EXCLUDED.dob,
            email = EXCLUDED.email,
            mobile = EXCLUDED.mobile,
            virtual_id = EXCLUDED.virtual_id,
            contacts = EXCLUDED.contacts,
            addresses = EXCLUDED.addresses,
            tags = EXCLUDED.tags,
            attributes = EXCLUDED.attributes,
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
    """Run the end-to-end migration for Staffs."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collection={cfg.staffs_collection}"
        )
        print("[1/4] Fetching RavenDB documents...")
        staff_docs = raven_query_collection(
            requests_session, cfg, cfg.staffs_collection
        )

        # Fallback to singular name if 0 docs fetched with default collection name
        if not staff_docs and cfg.staffs_collection == "Staffs":
            try:
                alt_docs = raven_query_collection(requests_session, cfg, "Staff")
                if alt_docs:
                    print(f"Fallback: Loaded {len(alt_docs)} docs from 'Staff'.")
                    staff_docs = alt_docs
            except Exception:
                pass

        print(f"Fetched staffs={len(staff_docs)}")

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

        loaded_staffs = 0
        new_staffs = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/4] Upserting staffs...")
                for d in staff_docs:
                    res = upsert_staff(cur, d)
                    loaded_staffs += 1
                    new_staffs += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collection": cfg.staffs_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "staffs_processed": loaded_staffs,
                "new_staffs_inserted": new_staffs,
            },
        }

        print("Migration completed.")
        print(f"staffs_processed: {loaded_staffs}")
        print(f"new_staffs_inserted: {new_staffs}")

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
