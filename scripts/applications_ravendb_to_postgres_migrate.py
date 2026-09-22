#!/usr/bin/env python3
"""
Extract ApplicationFormTemplate and Applications data from RavenDB,
transform it to PostgreSQL schema, and load into local PostgreSQL.

Before running: set all required configuration values in .env
(or pass them explicitly as command-line arguments).

Target tables:
- application_form_template
- application
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
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2.extras import Json
import requests

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# -----------------------------------------------------------------------------
# Enum Mappings
# -----------------------------------------------------------------------------

# ApplicationFormTemplateStatusEnum: Active = 1, Published = 70, Disabled = 99
TEMPLATE_STATUS_MAP: Dict[str, int] = {
    "active": 1,
    "enabled": 1,
    "published": 70,
    "disabled": 99,
    "inactive": 99,
}

# ApplicantCategoryEnum: GM = 40, OBC = 50, SC = 60, ST = 70 (0 is unset/default)
APPLICANT_CATEGORY_MAP: Dict[str, int] = {
    "gm": 40,
    "general": 40,
    "obc": 50,
    "sc": 60,
    "st": 70,
}

# ResidentialStatusEnum: Indian = 10, PIO_OCI = 20, NRI = 30 (0 is unset/default)
RESIDENTIAL_STATUS_MAP: Dict[str, int] = {
    "indian": 10,
    "pio_oci": 20,
    "piooci": 20,
    "pio": 20,
    "oci": 20,
    "nri": 30,
}

# PaymentStatusEnum: Pending = 10, Paid = 20 (0 is unset/default)
PAYMENT_STATUS_MAP: Dict[str, int] = {
    "pending": 10,
    "paid": 20,
    "success": 20,
    "completed": 20,
}

# CourseLevelEnum: PU = 1, UG = 2, PG = 3 (0 is unset/default)
COURSE_LEVEL_MAP: Dict[str, int] = {
    "pu": 1,
    "puc": 1,
    "ug": 2,
    "undergraduate": 2,
    "pg": 3,
    "postgraduate": 3,
}

# ApplicationStatusEnum:
# WIP = 10, Selected = 15, Submitted = 20, Shortlisted = 25, Admitted = 30,
# Rejected = 35, OptedIn = 40, OptedOut = 45, Declined = 50
APPLICATION_STATUS_MAP: Dict[str, int] = {
    "wip": 10,
    "selected": 15,
    "submitted": 20,
    "shortlisted": 25,
    "admitted": 30,
    "rejected": 35,
    "optedin": 40,
    "opted_in": 40,
    "optedout": 45,
    "opted_out": 45,
    "declined": 50,
}

# GenderEnum: Female = 0, Male = 1, NoInfo = 90
GENDER_MAP: Dict[str, int] = {
    "female": 0,
    "male": 1,
    "noinfo": 90,
    "no_info": 90,
    "other": 90,
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
    templates_collection: str
    applications_collection: str
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
        description="Migrate ApplicationFormTemplates and Applications from RavenDB to PostgreSQL"
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
    parser.add_argument("--pg-host", default=os.getenv("PG_HOST"))
    parser.add_argument("--pg-port", type=int, default=os.getenv("PG_PORT"))
    parser.add_argument("--pg-db", default=os.getenv("PG_DB"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER"))
    parser.add_argument("--pg-password", default=os.getenv("PG_PASSWORD"))

    parser.add_argument(
        "--templates-collection",
        default=os.getenv("APPLICATION_FORM_TEMPLATES_COLLECTION", "ApplicationFormTemplates"),
    )
    parser.add_argument(
        "--applications-collection",
        default=os.getenv("APPLICATIONS_COLLECTION", "Applications"),
    )
    parser.add_argument("--page-size", type=int, default=os.getenv("PAGE_SIZE"))
    parser.add_argument("--timeout-sec", type=int, default=os.getenv("TIMEOUT_SEC"))
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
        parser.error("Missing RavenDB config. Provide --raven-url/--raven-db or set RAVEN_URL/RAVEN_DB.")

    if not args.pg_password:
        parser.error("Missing PostgreSQL password. Provide --pg-password or set PG_PASSWORD.")

    if not args.pg_host or args.pg_port is None or not args.pg_db or not args.pg_user:
        parser.error(
            "Missing PostgreSQL config. Provide --pg-host/--pg-port/--pg-db/--pg-user or set PG_HOST/PG_PORT/PG_DB/PG_USER."
        )

    if args.page_size is None:
        args.page_size = 500
    if args.timeout_sec is None:
        args.timeout_sec = 30

    if args.page_size <= 0:
        parser.error("Invalid page size. --page-size must be greater than 0.")
    if args.timeout_sec <= 0:
        parser.error("Invalid timeout. --timeout-sec must be greater than 0.")

    if args.raven_cert_file:
        if not os.path.isfile(args.raven_cert_file):
            script_dir_cert = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.raven_cert_file)
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
        templates_collection=args.templates_collection,
        applications_collection=args.applications_collection,
        page_size=args.page_size,
        timeout_sec=args.timeout_sec,
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
    )


def write_summary_json(path_text: str, payload: Dict[str, Any]) -> str:
    """Write migration summary JSON artifact and return absolute path."""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path.resolve())


# -----------------------------------------------------------------------------
# Extraction Helpers
# -----------------------------------------------------------------------------

def extract_uuid_from_any(value: Any) -> Optional[str]:
    if not value:
        return None
    match = UUID_RE.search(str(value))
    return match.group(0).lower() if match else None


def first_non_empty(*values: Any) -> Optional[Any]:
    for val in values:
        if val is not None and str(val).strip():
            return val
    return None


def get_nested(data: Any, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def parse_ts(value: Any) -> Optional[str]:
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


def parse_doa(value: Any) -> Optional[str]:
    """Parse Date of Admission. Defaults like 0001-01-01 map to NULL."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.startswith("0001-01-01"):
        return None
    return parse_ts(value)


def parse_int(value: Any) -> Optional[int]:
    """Parse an integer-like value; return None when invalid or blank."""
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


def as_json(value: Any) -> Optional[Json]:
    """Wrap values for JSONB writes while preserving SQL NULL semantics."""
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


def parse_template_status(value: Any) -> int:
    """ApplicationFormTemplateStatusEnum: Active = 1, Published = 70, Disabled = 99 (default: 1)"""
    if value is None:
        return 1
    if isinstance(value, int):
        return value if value in (1, 70, 99) else 1
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 1
    if text.isdigit():
        val = int(text)
        return val if val in (1, 70, 99) else 1
    return TEMPLATE_STATUS_MAP.get(text, 1)


def parse_category(value: Any) -> Optional[int]:
    """ApplicantCategoryEnum: GM = 40, OBC = 50, SC = 60, ST = 70 (0 is unset/default)"""
    if value is None:
        return None
    if isinstance(value, int):
        if value == 0:
            return None
        return value if value in (40, 50, 60, 70) else None
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text or text == "0":
        return None
    if text.isdigit():
        val = int(text)
        return val if val in (40, 50, 60, 70) else None
    return APPLICANT_CATEGORY_MAP.get(text)


def parse_residential_status(value: Any) -> Optional[int]:
    """ResidentialStatusEnum: Indian = 10, PIO_OCI = 20, NRI = 30 (0 is unset/default)"""
    if value is None:
        return None
    if isinstance(value, int):
        if value == 0:
            return None
        return value if value in (10, 20, 30) else None
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text or text == "0":
        return None
    if text.isdigit():
        val = int(text)
        return val if val in (10, 20, 30) else None
    return RESIDENTIAL_STATUS_MAP.get(text)


def parse_payment_status(value: Any) -> Optional[int]:
    """PaymentStatusEnum: Pending = 10, Paid = 20 (0 is unset/default)"""
    if value is None:
        return None
    if isinstance(value, int):
        if value == 0:
            return None
        return value if value in (10, 20) else None
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text or text == "0":
        return None
    if text.isdigit():
        val = int(text)
        return val if val in (10, 20) else None
    return PAYMENT_STATUS_MAP.get(text)


def parse_course_level(value: Any) -> Optional[int]:
    """CourseLevelEnum: PU = 1, UG = 2, PG = 3 (0 is unset/default)"""
    if value is None:
        return None
    if isinstance(value, int):
        if value == 0:
            return None
        return value if value in (1, 2, 3) else None
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text or text == "0":
        return None
    if text.isdigit():
        val = int(text)
        return val if val in (1, 2, 3) else None
    return COURSE_LEVEL_MAP.get(text)


def parse_application_status(value: Any) -> int:
    """ApplicationStatusEnum: WIP=10, Selected=15, Submitted=20, Shortlisted=25, Admitted=30, ..."""
    if value is None:
        return 10
    if isinstance(value, int):
        return value if value in (10, 15, 20, 25, 30, 35, 40, 45, 50) else 10
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 10
    if text.isdigit():
        val = int(text)
        return val if val in (10, 15, 20, 25, 30, 35, 40, 45, 50) else 10
    return APPLICATION_STATUS_MAP.get(text, 10)


def parse_gender(value: Any) -> int:
    """GenderEnum: Female = 0, Male = 1, NoInfo = 90 (0 is Female!)"""
    if value is None:
        return 90
    if isinstance(value, int):
        return value if value in (0, 1, 90) else 90
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 90
    if text.isdigit():
        val = int(text)
        return val if val in (0, 1, 90) else 90
    return GENDER_MAP.get(text, 90)


def derive_doc_id(doc: Dict[str, Any], id_key: str = "Id") -> Optional[str]:
    return first_non_empty(
        extract_uuid_from_any(get_nested(doc, "@metadata", "@id")),
        extract_uuid_from_any(doc.get(id_key)),
        extract_uuid_from_any(doc.get("Id")),
    )


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

        if any(not isinstance(result, dict) for result in results):
            raise RuntimeError(f"RavenDB returned a non-document result for {collection_name}")

        if not results:
            break

        docs.extend(results)
        start += len(results)

    return docs


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup
# -----------------------------------------------------------------------------

def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target tables: application_form_template and application (no indexes)."""
    cur.execute(
        """
        -- Clean up any prior child tables/views if they exist
        DROP TABLE IF EXISTS application_form_template_course CASCADE;
        DROP TABLE IF EXISTS application_form_template_shortlist CASCADE;
        DROP VIEW IF EXISTS application_form_template_courses CASCADE;
        DROP VIEW IF EXISTS application_form_template_shortlists CASCADE;

        -- 1. ApplicationFormTemplate Table
        CREATE TABLE IF NOT EXISTS application_form_template (
            id UUID PRIMARY KEY,
            title VARCHAR(200),
            description TEXT,
            start_date TIMESTAMPTZ,
            end_date TIMESTAMPTZ,
            status INTEGER,
            shortlists JSONB DEFAULT '[]'::jsonb,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID,
            -- Options
            options_json JSONB,
            upload_photo BOOLEAN,
            upload_aadhar_card BOOLEAN,
            upload_ssc_marksheet BOOLEAN,
            upload_hsc_marksheet BOOLEAN,
            upload_caste_certificate BOOLEAN,
            upload_domicile_certificate BOOLEAN,
            upload_birth_certificate BOOLEAN,
            upload_transfer_certificate BOOLEAN,
            upload_leaving_certificate BOOLEAN,
            collect_parent_details BOOLEAN,
            display_labels_json JSONB,
            application_fee NUMERIC(18, 2),
            ssc_board VARCHAR(100),
            ssc_year_of_passing INTEGER,
            ssc_medium VARCHAR(50),
            ssc_percentage NUMERIC(5, 2),
            ssc_show BOOLEAN,
            hsc_board VARCHAR(100),
            hsc_year_of_passing INTEGER,
            hsc_medium VARCHAR(50),
            hsc_percentage NUMERIC(5, 2),
            hsc_show BOOLEAN,
            -- ApplyFor courses array
            apply_for TEXT[]
        );

        -- Ensure shortlists column exists if table was created earlier
        ALTER TABLE application_form_template ADD COLUMN IF NOT EXISTS shortlists JSONB DEFAULT '[]'::jsonb;

        -- 2. Applications Table
        CREATE TABLE IF NOT EXISTS application (
            id UUID PRIMARY KEY,
            name VARCHAR(150),
            email VARCHAR(254),
            mobile VARCHAR(20),
            dob TIMESTAMPTZ,
            residential_status INTEGER,
            category INTEGER,
            gender INTEGER,
            application_form_template_id UUID,
            submitted_on TIMESTAMPTZ,
            application_number INTEGER,
            shortlisted_in INTEGER,
            doa TIMESTAMPTZ,
            application_status INTEGER,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID,
            -- Flattened address
            address_line1 VARCHAR(250),
            address_line2 VARCHAR(250),
            address_city VARCHAR(100),
            address_state VARCHAR(100),
            address_country VARCHAR(100),
            address_pincode VARCHAR(20),
            -- Academic (HSC)
            hsc_year_of_passing INTEGER,
            hsc_board VARCHAR(100),
            hsc_percentage NUMERIC(5, 2),
            hsc_medium VARCHAR(50),
            -- Academic (SSC)
            ssc_year_of_passing INTEGER,
            ssc_board VARCHAR(100),
            ssc_percentage NUMERIC(5, 2),
            ssc_medium VARCHAR(50),
            -- Parents / Guardian
            father_name VARCHAR(150),
            father_email VARCHAR(254),
            father_mobile VARCHAR(20),
            mother_name VARCHAR(150),
            mother_email VARCHAR(254),
            mother_mobile VARCHAR(20),
            guardian_name VARCHAR(150),
            guardian_email VARCHAR(254),
            guardian_mobile VARCHAR(20),
            -- Course Applied (AppliedFor)
            applied_course_level INTEGER,
            applied_course_id UUID,
            applied_course VARCHAR(100),
            applied_stream VARCHAR(100),
            applied_combination VARCHAR(100),
            -- Payment
            payment_status INTEGER,
            payment_ref VARCHAR(100),
            amount_paid NUMERIC(18, 2),
            -- Upload URLs
            photo_url VARCHAR(1000),
            aadhar_url VARCHAR(1000),
            hsc_marks_card_url VARCHAR(1000),
            ssc_marks_card_url VARCHAR(1000),
            caste_certificate_url VARCHAR(1000),
            domicile_certificate_url VARCHAR(1000),
            birth_certificate_url VARCHAR(1000),
            transfer_certificate_url VARCHAR(1000),
            leaving_certificate_url VARCHAR(1000)
        );

        -- Backward compatible views
        CREATE OR REPLACE VIEW application_form_templates AS SELECT * FROM application_form_template;
        CREATE OR REPLACE VIEW applications AS SELECT * FROM application;
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_name IN ('application_form_template', 'application')
        """
    )
    existing = {(row[0], row[1].lower()) for row in cur.fetchall()}

    req_template = {
        "id", "title", "status", "start_date", "end_date", "shortlists", "owner_id",
        "options_json", "upload_photo", "application_fee", "apply_for"
    }
    req_app = {
        "id", "name", "email", "mobile", "application_status",
        "application_form_template_id", "address_line1", "applied_course"
    }

    missing_tpl = {col for col in req_template if ("application_form_template", col) not in existing}
    missing_app = {col for col in req_app if ("application", col) not in existing}

    if missing_tpl or missing_app:
        raise RuntimeError(
            f"Schema verification failed! Missing template cols: {missing_tpl}, app cols: {missing_app}"
        )


# -----------------------------------------------------------------------------
# Upsert: ApplicationFormTemplate
# -----------------------------------------------------------------------------

def upsert_template(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> Optional[UpsertResult]:
    tpl_id = derive_doc_id(doc, "ApplicationFormTemplateId")
    if not tpl_id:
        return None

    cur.execute("SELECT 1 FROM application_form_template WHERE id = %s", (tpl_id,))
    is_new = cur.fetchone() is None

    title = as_text(doc.get("Title"))
    title = title[:200] if title else None
    description = as_text(doc.get("Description"))
    start_date = parse_ts(doc.get("StartDate"))
    end_date = parse_ts(doc.get("EndDate"))
    status = parse_template_status(doc.get("Status"))
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))
    parent_id = extract_uuid_from_any(doc.get("ParentId"))
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))
    modified_on = parse_ts(doc.get("ModifiedOn"))
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

    # Options & Flattened Sub-objects
    options = doc.get("Options") or {}
    options_json = as_json(options) if isinstance(options, dict) else None

    uploads = options.get("Uploads") if isinstance(options, dict) and isinstance(options.get("Uploads"), dict) else {}
    acad = options.get("AcademicHistory") if isinstance(options, dict) and isinstance(options.get("AcademicHistory"), dict) else {}
    ssc_opt = acad.get("SSC") if isinstance(acad.get("SSC"), dict) else {}
    hsc_opt = acad.get("HSC") if isinstance(acad.get("HSC"), dict) else {}

    upload_photo = parse_bool(uploads.get("Photo") if "Photo" in uploads else options.get("UploadPhoto"))
    upload_aadhar_card = parse_bool(uploads.get("AadharCard") if "AadharCard" in uploads else options.get("UploadAadharCard"))
    upload_ssc_marksheet = parse_bool(uploads.get("SSCMarksheet") if "SSCMarksheet" in uploads else options.get("UploadSSCMarksheet"))
    upload_hsc_marksheet = parse_bool(uploads.get("HSCMarksheet") if "HSCMarksheet" in uploads else options.get("UploadHSCMarksheet"))
    upload_caste_cert = parse_bool(uploads.get("CasteCertificate") if "CasteCertificate" in uploads else options.get("UploadCasteCertificate"))
    upload_domicile_cert = parse_bool(uploads.get("DomicileCertificate") if "DomicileCertificate" in uploads else options.get("UploadDomicileCertificate"))
    upload_birth_cert = parse_bool(uploads.get("BirthCertificate") if "BirthCertificate" in uploads else options.get("UploadBirthCertificate"))
    upload_transfer_cert = parse_bool(uploads.get("TransferCertificate") if "TransferCertificate" in uploads else options.get("UploadTransferCertificate"))
    upload_leaving_cert = parse_bool(uploads.get("LeavingCertificate") if "LeavingCertificate" in uploads else options.get("UploadLeavingCertificate"))
    
    collect_parent_details = parse_bool(options.get("CollectParentDetails") if isinstance(options, dict) else None)
    display_labels = options.get("DisplayLabels") if isinstance(options, dict) else None
    display_labels_json = as_json(display_labels)
    application_fee = parse_decimal(options.get("ApplicationFee") if isinstance(options, dict) else None)

    ssc_board = as_text(ssc_opt.get("Board") or (options.get("SSCBoard") if isinstance(options, dict) else None))
    ssc_board = ssc_board[:100] if ssc_board else None
    ssc_year = parse_int(ssc_opt.get("YearOfPassing") or (options.get("SSCYearOfPassing") if isinstance(options, dict) else None))
    ssc_medium = as_text(ssc_opt.get("Medium") or (options.get("SSCMedium") if isinstance(options, dict) else None))
    ssc_medium = ssc_medium[:50] if ssc_medium else None
    ssc_percentage = parse_decimal(ssc_opt.get("Percentage") or (options.get("SSCPercentage") if isinstance(options, dict) else None))
    ssc_show = parse_bool(ssc_opt.get("Show") if "Show" in ssc_opt else (options.get("SSCShow") if isinstance(options, dict) else None))

    hsc_board = as_text(hsc_opt.get("Board") or (options.get("HSCBoard") if isinstance(options, dict) else None))
    hsc_board = hsc_board[:100] if hsc_board else None
    hsc_year = parse_int(hsc_opt.get("YearOfPassing") or (options.get("HSCYearOfPassing") if isinstance(options, dict) else None))
    hsc_medium = as_text(hsc_opt.get("Medium") or (options.get("HSCMedium") if isinstance(options, dict) else None))
    hsc_medium = hsc_medium[:50] if hsc_medium else None
    hsc_percentage = parse_decimal(hsc_opt.get("Percentage") or (options.get("HSCPercentage") if isinstance(options, dict) else None))
    hsc_show = parse_bool(hsc_opt.get("Show") if "Show" in hsc_opt else (options.get("HSCShow") if isinstance(options, dict) else None))

    apply_for_raw = options.get("ApplyFor") if isinstance(options, dict) and options.get("ApplyFor") else doc.get("ApplyFor")
    apply_for = [str(c).strip() for c in apply_for_raw if str(c).strip()] if isinstance(apply_for_raw, list) else []

    shortlists_raw = doc.get("Shortlists") or []
    shortlists_json = as_json(shortlists_raw if isinstance(shortlists_raw, list) else [])

    cur.execute(
        """
        INSERT INTO application_form_template (
            id, title, description, start_date, end_date, status, shortlists,
            owner_id, parent_id, created_on, created_by, modified_on, modified_by,
            options_json, upload_photo, upload_aadhar_card, upload_ssc_marksheet,
            upload_hsc_marksheet, upload_caste_certificate, upload_domicile_certificate,
            upload_birth_certificate, upload_transfer_certificate, upload_leaving_certificate,
            collect_parent_details, display_labels_json, application_fee,
            ssc_board, ssc_year_of_passing, ssc_medium, ssc_percentage, ssc_show,
            hsc_board, hsc_year_of_passing, hsc_medium, hsc_percentage, hsc_show,
            apply_for
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            status = EXCLUDED.status,
            shortlists = EXCLUDED.shortlists,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by,
            options_json = EXCLUDED.options_json,
            upload_photo = EXCLUDED.upload_photo,
            upload_aadhar_card = EXCLUDED.upload_aadhar_card,
            upload_ssc_marksheet = EXCLUDED.upload_ssc_marksheet,
            upload_hsc_marksheet = EXCLUDED.upload_hsc_marksheet,
            upload_caste_certificate = EXCLUDED.upload_caste_certificate,
            upload_domicile_certificate = EXCLUDED.upload_domicile_certificate,
            upload_birth_certificate = EXCLUDED.upload_birth_certificate,
            upload_transfer_certificate = EXCLUDED.upload_transfer_certificate,
            upload_leaving_certificate = EXCLUDED.upload_leaving_certificate,
            collect_parent_details = EXCLUDED.collect_parent_details,
            display_labels_json = EXCLUDED.display_labels_json,
            application_fee = EXCLUDED.application_fee,
            ssc_board = EXCLUDED.ssc_board,
            ssc_year_of_passing = EXCLUDED.ssc_year_of_passing,
            ssc_medium = EXCLUDED.ssc_medium,
            ssc_percentage = EXCLUDED.ssc_percentage,
            ssc_show = EXCLUDED.ssc_show,
            hsc_board = EXCLUDED.hsc_board,
            hsc_year_of_passing = EXCLUDED.hsc_year_of_passing,
            hsc_medium = EXCLUDED.hsc_medium,
            hsc_percentage = EXCLUDED.hsc_percentage,
            hsc_show = EXCLUDED.hsc_show,
            apply_for = EXCLUDED.apply_for
        RETURNING id;
        """,
        (
            tpl_id,
            title,
            description,
            start_date,
            end_date,
            status,
            shortlists_json,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by,
            options_json,
            upload_photo,
            upload_aadhar_card,
            upload_ssc_marksheet,
            upload_hsc_marksheet,
            upload_caste_cert,
            upload_domicile_cert,
            upload_birth_cert,
            upload_transfer_cert,
            upload_leaving_cert,
            collect_parent_details,
            display_labels_json,
            application_fee,
            ssc_board,
            ssc_year,
            ssc_medium,
            ssc_percentage,
            ssc_show,
            hsc_board,
            hsc_year,
            hsc_medium,
            hsc_percentage,
            hsc_show,
            apply_for,
        ),
    )
    row = cur.fetchone()
    record_id = str(row[0]) if row else str(tpl_id)
    return UpsertResult(record_id, is_new)


# -----------------------------------------------------------------------------
# Upsert: Application
# -----------------------------------------------------------------------------

def upsert_application(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> Optional[UpsertResult]:
    app_id = derive_doc_id(doc, "ApplicationId")
    if not app_id:
        return None

    cur.execute("SELECT 1 FROM application WHERE id = %s", (app_id,))
    is_new = cur.fetchone() is None

    name = as_text(doc.get("Name"))[:150] if doc.get("Name") else None
    email = as_text(doc.get("Email"))[:254] if doc.get("Email") else None
    mobile = as_text(doc.get("Mobile"))[:20] if doc.get("Mobile") else None
    dob = parse_ts(doc.get("DOB"))
    residential_status = parse_residential_status(doc.get("ResidentialStatus"))
    category = parse_category(doc.get("Category"))
    gender = parse_gender(doc.get("Gender"))
    tpl_id = extract_uuid_from_any(doc.get("ApplicationFormTemplateId"))
    submitted_on = parse_ts(doc.get("SubmittedOn"))
    app_no = parse_int(doc.get("ApplicationNumber"))
    shortlisted_in = parse_int(doc.get("ShortlistedIn"))
    doa = parse_doa(doc.get("DOA"))
    app_status = parse_application_status(doc.get("ApplicationStatus"))
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))
    parent_id = extract_uuid_from_any(doc.get("ParentId"))
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))
    modified_on = parse_ts(doc.get("ModifiedOn"))
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

    # Flattened address
    addr = doc.get("Address") if isinstance(doc.get("Address"), dict) else {}
    addr_line1 = as_text(addr.get("Line1") or addr.get("AddressLine1") or doc.get("AddressLine1"))
    addr_line1 = addr_line1[:250] if addr_line1 else None
    addr_line2 = as_text(addr.get("Line2") or addr.get("AddressLine2") or doc.get("AddressLine2"))
    addr_line2 = addr_line2[:250] if addr_line2 else None
    addr_city = as_text(addr.get("City") or doc.get("AddressCity"))
    addr_city = addr_city[:100] if addr_city else None
    addr_state = as_text(addr.get("State") or doc.get("AddressState"))
    addr_state = addr_state[:100] if addr_state else None
    addr_country = as_text(addr.get("Country") or doc.get("AddressCountry"))
    addr_country = addr_country[:100] if addr_country else None
    addr_pincode = as_text(addr.get("Pincode") or doc.get("AddressPincode"))
    addr_pincode = addr_pincode[:20] if addr_pincode else None

    # Academic: HSC
    hsc = doc.get("HSC") if isinstance(doc.get("HSC"), dict) else {}
    hsc_year = parse_int(hsc.get("YearOfPassing") or doc.get("HSCYearOfPassing"))
    hsc_board = as_text(hsc.get("Board") or doc.get("HSCBoard"))
    hsc_board = hsc_board[:100] if hsc_board else None
    hsc_percentage = parse_decimal(hsc.get("Percentage") or doc.get("HSCPercentage"))
    hsc_medium = as_text(hsc.get("Medium") or doc.get("HSCMedium"))
    hsc_medium = hsc_medium[:50] if hsc_medium else None

    # Academic: SSC
    ssc = doc.get("SSC") if isinstance(doc.get("SSC"), dict) else {}
    ssc_year = parse_int(ssc.get("YearOfPassing") or doc.get("SSCYearOfPassing"))
    ssc_board = as_text(ssc.get("Board") or doc.get("SSCBoard"))
    ssc_board = ssc_board[:100] if ssc_board else None
    ssc_percentage = parse_decimal(ssc.get("Percentage") or doc.get("SSCPercentage"))
    ssc_medium = as_text(ssc.get("Medium") or doc.get("SSCMedium"))
    ssc_medium = ssc_medium[:50] if ssc_medium else None

    # Parents / Guardian
    f_det = doc.get("FatherDetails") if isinstance(doc.get("FatherDetails"), dict) else {}
    m_det = doc.get("MotherDetails") if isinstance(doc.get("MotherDetails"), dict) else {}
    g_det = doc.get("GuardianDetails") if isinstance(doc.get("GuardianDetails"), dict) else {}
    p_fallback = doc.get("ParentDetails") if isinstance(doc.get("ParentDetails"), dict) else {}

    f_name = as_text(f_det.get("Name") or f_det.get("FatherName") or p_fallback.get("FatherName") or doc.get("FatherName"))
    f_name = f_name[:150] if f_name else None
    f_email = as_text(f_det.get("Email") or f_det.get("FatherEmail") or p_fallback.get("FatherEmail") or doc.get("FatherEmail"))
    f_email = f_email[:254] if f_email else None
    f_mobile = as_text(f_det.get("Mobile") or f_det.get("FatherMobile") or p_fallback.get("FatherMobile") or doc.get("FatherMobile"))
    f_mobile = f_mobile[:20] if f_mobile else None

    m_name = as_text(m_det.get("Name") or m_det.get("MotherName") or p_fallback.get("MotherName") or doc.get("MotherName"))
    m_name = m_name[:150] if m_name else None
    m_email = as_text(m_det.get("Email") or m_det.get("MotherEmail") or p_fallback.get("MotherEmail") or doc.get("MotherEmail"))
    m_email = m_email[:254] if m_email else None
    m_mobile = as_text(m_det.get("Mobile") or m_det.get("MotherMobile") or p_fallback.get("MotherMobile") or doc.get("MotherMobile"))
    m_mobile = m_mobile[:20] if m_mobile else None

    g_name = as_text(g_det.get("Name") or g_det.get("GuardianName") or p_fallback.get("GuardianName") or doc.get("GuardianName"))
    g_name = g_name[:150] if g_name else None
    g_email = as_text(g_det.get("Email") or g_det.get("GuardianEmail") or p_fallback.get("GuardianEmail") or doc.get("GuardianEmail"))
    g_email = g_email[:254] if g_email else None
    g_mobile = as_text(g_det.get("Mobile") or g_det.get("GuardianMobile") or p_fallback.get("GuardianMobile") or doc.get("GuardianMobile"))
    g_mobile = g_mobile[:20] if g_mobile else None

    # Applied Course (AppliedFor in C# / RavenDB)
    applied = doc.get("AppliedFor") if isinstance(doc.get("AppliedFor"), dict) else (
        doc.get("AppliedCourseDetails") if isinstance(doc.get("AppliedCourseDetails"), dict) else (
            doc.get("CourseDetails") if isinstance(doc.get("CourseDetails"), dict) else {}
        )
    )
    applied_course_level = parse_course_level(applied.get("CourseLevel") or doc.get("AppliedCourseLevel"))
    applied_course_id = extract_uuid_from_any(applied.get("CourseId") or doc.get("AppliedCourseId"))
    applied_course = as_text(applied.get("Course") or doc.get("AppliedCourse"))
    applied_course = applied_course[:100] if applied_course else None
    applied_stream = as_text(applied.get("Stream") or doc.get("AppliedStream"))
    applied_stream = applied_stream[:100] if applied_stream else None
    applied_comb = as_text(applied.get("Combination") or doc.get("AppliedCombination"))
    applied_comb = applied_comb[:100] if applied_comb else None

    # Payment
    payment = doc.get("Payment") if isinstance(doc.get("Payment"), dict) else {}
    payment_status = parse_payment_status(payment.get("PaymentStatus") or payment.get("Status") or doc.get("PaymentStatus"))
    payment_ref = as_text(payment.get("PaymentRef") or payment.get("Ref") or doc.get("PaymentRef"))
    payment_ref = payment_ref[:100] if payment_ref else None
    amount_paid = parse_decimal(payment.get("AmountPaid") or doc.get("AmountPaid"))

    # Uploads (URLs stored directly on Application)
    uploads = doc.get("Uploads") if isinstance(doc.get("Uploads"), dict) else (
        doc.get("Documents") if isinstance(doc.get("Documents"), dict) else {}
    )
    photo_url = as_text(doc.get("PhotoURL") or uploads.get("PhotoURL"))
    photo_url = photo_url[:1000] if photo_url else None
    aadhar_url = as_text(doc.get("AadharURL") or uploads.get("AadharURL"))
    aadhar_url = aadhar_url[:1000] if aadhar_url else None
    hsc_marks_card_url = as_text(doc.get("HSCMarksCardURL") or uploads.get("HSCMarksCardURL"))
    hsc_marks_card_url = hsc_marks_card_url[:1000] if hsc_marks_card_url else None
    ssc_marks_card_url = as_text(doc.get("SSCMarksCardURL") or uploads.get("SSCMarksCardURL"))
    ssc_marks_card_url = ssc_marks_card_url[:1000] if ssc_marks_card_url else None
    caste_cert_url = as_text(doc.get("CasteCertificateURL") or uploads.get("CasteCertificateURL"))
    caste_cert_url = caste_cert_url[:1000] if caste_cert_url else None
    domicile_cert_url = as_text(doc.get("DomicileCertificateURL") or uploads.get("DomicileCertificateURL"))
    domicile_cert_url = domicile_cert_url[:1000] if domicile_cert_url else None
    birth_cert_url = as_text(doc.get("BirthCertificateURL") or uploads.get("BirthCertificateURL"))
    birth_cert_url = birth_cert_url[:1000] if birth_cert_url else None
    transfer_cert_url = as_text(doc.get("TransferCertificateURL") or uploads.get("TransferCertificateURL"))
    transfer_cert_url = transfer_cert_url[:1000] if transfer_cert_url else None
    leaving_cert_url = as_text(doc.get("LeavingCertificateURL") or uploads.get("LeavingCertificateURL"))
    leaving_cert_url = leaving_cert_url[:1000] if leaving_cert_url else None

    cur.execute(
        """
        INSERT INTO application (
            id, name, email, mobile, dob, residential_status, category, gender,
            application_form_template_id, submitted_on, application_number, shortlisted_in,
            doa, application_status, owner_id, parent_id, created_on, created_by, modified_on, modified_by,
            address_line1, address_line2, address_city, address_state, address_country, address_pincode,
            hsc_year_of_passing, hsc_board, hsc_percentage, hsc_medium,
            ssc_year_of_passing, ssc_board, ssc_percentage, ssc_medium,
            father_name, father_email, father_mobile, mother_name, mother_email, mother_mobile,
            guardian_name, guardian_email, guardian_mobile,
            applied_course_level, applied_course_id, applied_course, applied_stream, applied_combination,
            payment_status, payment_ref, amount_paid,
            photo_url, aadhar_url, hsc_marks_card_url, ssc_marks_card_url,
            caste_certificate_url, domicile_certificate_url, birth_certificate_url,
            transfer_certificate_url, leaving_certificate_url
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            mobile = EXCLUDED.mobile,
            dob = EXCLUDED.dob,
            residential_status = EXCLUDED.residential_status,
            category = EXCLUDED.category,
            gender = EXCLUDED.gender,
            application_form_template_id = EXCLUDED.application_form_template_id,
            submitted_on = EXCLUDED.submitted_on,
            application_number = EXCLUDED.application_number,
            shortlisted_in = EXCLUDED.shortlisted_in,
            doa = EXCLUDED.doa,
            application_status = EXCLUDED.application_status,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by,
            address_line1 = EXCLUDED.address_line1,
            address_line2 = EXCLUDED.address_line2,
            address_city = EXCLUDED.address_city,
            address_state = EXCLUDED.address_state,
            address_country = EXCLUDED.address_country,
            address_pincode = EXCLUDED.address_pincode,
            hsc_year_of_passing = EXCLUDED.hsc_year_of_passing,
            hsc_board = EXCLUDED.hsc_board,
            hsc_percentage = EXCLUDED.hsc_percentage,
            hsc_medium = EXCLUDED.hsc_medium,
            ssc_year_of_passing = EXCLUDED.ssc_year_of_passing,
            ssc_board = EXCLUDED.ssc_board,
            ssc_percentage = EXCLUDED.ssc_percentage,
            ssc_medium = EXCLUDED.ssc_medium,
            father_name = EXCLUDED.father_name,
            father_email = EXCLUDED.father_email,
            father_mobile = EXCLUDED.father_mobile,
            mother_name = EXCLUDED.mother_name,
            mother_email = EXCLUDED.mother_email,
            mother_mobile = EXCLUDED.mother_mobile,
            guardian_name = EXCLUDED.guardian_name,
            guardian_email = EXCLUDED.guardian_email,
            guardian_mobile = EXCLUDED.guardian_mobile,
            applied_course_level = EXCLUDED.applied_course_level,
            applied_course_id = EXCLUDED.applied_course_id,
            applied_course = EXCLUDED.applied_course,
            applied_stream = EXCLUDED.applied_stream,
            applied_combination = EXCLUDED.applied_combination,
            payment_status = EXCLUDED.payment_status,
            payment_ref = EXCLUDED.payment_ref,
            amount_paid = EXCLUDED.amount_paid,
            photo_url = EXCLUDED.photo_url,
            aadhar_url = EXCLUDED.aadhar_url,
            hsc_marks_card_url = EXCLUDED.hsc_marks_card_url,
            ssc_marks_card_url = EXCLUDED.ssc_marks_card_url,
            caste_certificate_url = EXCLUDED.caste_certificate_url,
            domicile_certificate_url = EXCLUDED.domicile_certificate_url,
            birth_certificate_url = EXCLUDED.birth_certificate_url,
            transfer_certificate_url = EXCLUDED.transfer_certificate_url,
            leaving_certificate_url = EXCLUDED.leaving_certificate_url
        RETURNING id;
        """,
        (
            app_id,
            name,
            email,
            mobile,
            dob,
            residential_status,
            category,
            gender,
            tpl_id,
            submitted_on,
            app_no,
            shortlisted_in,
            doa,
            app_status,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by,
            addr_line1,
            addr_line2,
            addr_city,
            addr_state,
            addr_country,
            addr_pincode,
            hsc_year,
            hsc_board,
            hsc_percentage,
            hsc_medium,
            ssc_year,
            ssc_board,
            ssc_percentage,
            ssc_medium,
            f_name,
            f_email,
            f_mobile,
            m_name,
            m_email,
            m_mobile,
            g_name,
            g_email,
            g_mobile,
            applied_course_level,
            applied_course_id,
            applied_course,
            applied_stream,
            applied_comb,
            payment_status,
            payment_ref,
            amount_paid,
            photo_url,
            aadhar_url,
            hsc_marks_card_url,
            ssc_marks_card_url,
            caste_cert_url,
            domicile_cert_url,
            birth_cert_url,
            transfer_cert_url,
            leaving_cert_url,
        ),
    )
    row = cur.fetchone()
    return UpsertResult(str(row[0]), is_new) if row else None


# -----------------------------------------------------------------------------
# Main Routine
# -----------------------------------------------------------------------------

def main() -> int:
    """Run the end-to-end migration for application form templates and applications."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collections=({cfg.templates_collection}, {cfg.applications_collection})"
        )
        print("[1/5] Fetching RavenDB documents...")
        tpl_docs = raven_query_collection(requests_session, cfg, cfg.templates_collection)
        app_docs = raven_query_collection(requests_session, cfg, cfg.applications_collection)
        print(
            f"Fetched templates={len(tpl_docs)}, applications={len(app_docs)}"
        )

        print("[2/5] Connecting PostgreSQL...")
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

        loaded_tpls = 0
        new_tpls = 0
        loaded_apps = 0
        new_apps = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/5] Ensuring target schema...")
                ensure_target_schema(cur)
                assert_required_schema(cur)

                print("[4/5] Upserting application form templates...")
                for d in tpl_docs:
                    result = upsert_template(cur, d)
                    if result is not None:
                        loaded_tpls += 1
                        new_tpls += int(result.inserted)

                print("[5/5] Upserting applications...")
                for d in app_docs:
                    result = upsert_application(cur, d)
                    if result is not None:
                        loaded_apps += 1
                        new_apps += int(result.inserted)

        # Post-load counts used by validation and operational sign-off.
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM application_form_template")
            total_templates = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM application")
            total_applications = int(cur.fetchone()[0])

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "templates_collection": cfg.templates_collection,
                "applications_collection": cfg.applications_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "templates_processed": loaded_tpls,
                "new_templates_inserted": new_tpls,
                "applications_processed": loaded_apps,
                "new_applications_inserted": new_apps,
            },
            "post_load_counts": {
                "application_form_template": total_templates,
                "application": total_applications,
            },
        }

        print("Migration completed.")
        print(f"templates_processed: {loaded_tpls}")
        print(f"new_templates_inserted: {new_tpls}")
        print(f"applications_processed: {loaded_apps}")
        print(f"new_applications_inserted: {new_apps}")

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
