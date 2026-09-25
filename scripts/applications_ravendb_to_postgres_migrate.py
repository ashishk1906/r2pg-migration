#!/usr/bin/env python3
"""
Extract ApplicationFormTemplates and Applications data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs and JSONBs,
and load into local PostgreSQL.

Target tables:
- application_form_templates
- applications
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import sys
from dataclasses import dataclass
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
    parser.add_argument("--pg-host", default=os.getenv("PG_HOST", "localhost"))
    parser.add_argument("--pg-port", type=int, default=int(os.getenv("PG_PORT", "5432")))
    parser.add_argument("--pg-db", default=os.getenv("PG_DB", "rpg"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    parser.add_argument("--pg-password", default=os.getenv("PG_PASSWORD"))

    parser.add_argument(
        "--templates-collection",
        default=os.getenv(
            "APPLICATION_FORM_TEMPLATES_COLLECTION", "ApplicationFormTemplates"
        ),
    )
    parser.add_argument(
        "--applications-collection",
        default=os.getenv("APPLICATIONS_COLLECTION", "Applications"),
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
        templates_collection=args.templates_collection,
        applications_collection=args.applications_collection,
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


def clean_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def as_json(value: Any) -> Optional[Json]:
    """Wrap dict/list for JSONB writes while preserving SQL NULL semantics."""
    if value is None:
        return None
    return Json(value)


def parse_iso_timestamp(val: Any) -> Optional[datetime]:
    """Parse ISO timestamp safely."""
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

# ApplicationFormTemplateStatusEnum: Active = 1, Published = 70, Disabled = 99
TEMPLATE_STATUS_MAP: Dict[Any, str] = {
    1: "Active",
    70: "Published",
    99: "Disabled",
    "active": "Active",
    "published": "Published",
    "disabled": "Disabled",
}


def map_template_status(val: Any) -> str:
    if val is None:
        return "Active"
    if isinstance(val, int):
        return TEMPLATE_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return TEMPLATE_STATUS_MAP.get(int(s), "Active")
    return TEMPLATE_STATUS_MAP.get(s.lower(), "Active")


# ResidentialStatusEnum: Indian = 10, PIO_OCI = 20, NRI = 30
RESIDENTIAL_STATUS_MAP: Dict[Any, str] = {
    10: "Indian",
    20: "PIO_OCI",
    30: "NRI",
    "indian": "Indian",
    "pio_oci": "PIO_OCI",
    "piooci": "PIO_OCI",
    "nri": "NRI",
}


def map_residential_status(val: Any) -> Optional[str]:
    if not val or val == 0 or val == "0":
        return None
    if isinstance(val, int):
        return RESIDENTIAL_STATUS_MAP.get(val)
    s = str(val).strip()
    if s.isdigit():
        return RESIDENTIAL_STATUS_MAP.get(int(s))
    return RESIDENTIAL_STATUS_MAP.get(s.lower(), s if s in {"Indian", "PIO_OCI", "NRI"} else None)


# ApplicantCategoryEnum: GM = 40, OBC = 50, SC = 60, ST = 70
CATEGORY_MAP: Dict[Any, str] = {
    40: "GM",
    50: "OBC",
    60: "SC",
    70: "ST",
    "gm": "GM",
    "general": "GM",
    "obc": "OBC",
    "sc": "SC",
    "st": "ST",
}


def map_category(val: Any) -> Optional[str]:
    if not val or val == 0 or val == "0":
        return None
    if isinstance(val, int):
        return CATEGORY_MAP.get(val)
    s = str(val).strip()
    if s.isdigit():
        return CATEGORY_MAP.get(int(s))
    return CATEGORY_MAP.get(s.lower(), s.upper() if s.upper() in {"GM", "OBC", "SC", "ST"} else None)


# GenderEnum: Female = 0, Male = 1, NoInfo = 90
GENDER_MAP: Dict[Any, str] = {
    0: "Female",
    1: "Male",
    90: "NoInfo",
    "female": "Female",
    "male": "Male",
    "noinfo": "NoInfo",
}


def map_gender(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    if isinstance(val, int):
        return GENDER_MAP.get(val)
    s = str(val).strip()
    if s.isdigit():
        return GENDER_MAP.get(int(s))
    norm = s.lower().replace(" ", "").replace("_", "")
    return GENDER_MAP.get(norm, "NoInfo" if norm in {"unknown", "other"} else None)


# ApplicationStatusEnum:
# WIP = 10, Selected = 15, Submitted = 20, Shortlisted = 25,
# Admitted = 30, Rejected = 35, OptedIn = 40, OptedOut = 45, Declined = 50
APPLICATION_STATUS_MAP: Dict[Any, str] = {
    10: "WIP",
    15: "Selected",
    20: "Submitted",
    25: "Shortlisted",
    30: "Admitted",
    35: "Rejected",
    40: "OptedIn",
    45: "OptedOut",
    50: "Declined",
    "wip": "WIP",
    "selected": "Selected",
    "submitted": "Submitted",
    "shortlisted": "Shortlisted",
    "admitted": "Admitted",
    "rejected": "Rejected",
    "optedin": "OptedIn",
    "optedout": "OptedOut",
    "declined": "Declined",
}


def map_application_status(val: Any) -> str:
    if val is None:
        return "WIP"
    if isinstance(val, int):
        return APPLICATION_STATUS_MAP.get(val, "WIP")
    s = str(val).strip()
    if s.isdigit():
        return APPLICATION_STATUS_MAP.get(int(s), "WIP")
    norm = s.lower().replace(" ", "").replace("_", "")
    return APPLICATION_STATUS_MAP.get(norm, "WIP")


# -----------------------------------------------------------------------------
# Document Field Extractors
# -----------------------------------------------------------------------------


def extract_template_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform all fields for application_form_templates table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    tpl_id = clean_uuid(raw_id)
    if not tpl_id:
        raise ValueError(f"ApplicationFormTemplate missing valid UUID: {raw_id}")

    title = clean_str(doc.get("Title"), 200)
    description = clean_str(doc.get("Description"))
    options = as_json(doc.get("Options"))
    start_date = parse_iso_timestamp(doc.get("StartDate"))
    end_date = parse_iso_timestamp(doc.get("EndDate"))
    status = map_template_status(doc.get("Status"))

    shortlists_raw = doc.get("Shortlists")
    shortlists = as_json(shortlists_raw if isinstance(shortlists_raw, list) else [])

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))

    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        tpl_id,
        title,
        description,
        options,
        start_date,
        end_date,
        status,
        shortlists,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


def extract_application_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform all fields for applications table using JSONB for composite structures."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    app_id = clean_uuid(raw_id)
    if not app_id:
        raise ValueError(f"Application missing valid UUID: {raw_id}")

    name = clean_str(doc.get("Name"), 150)
    email = clean_str(doc.get("Email"), 254)
    mobile = clean_str(doc.get("Mobile"), 20)
    dob = parse_iso_timestamp(doc.get("DOB"))
    residential_status = map_residential_status(doc.get("ResidentialStatus"))
    category = map_category(doc.get("Category"))
    gender = map_gender(doc.get("Gender"))

    # Composite objects as JSONB
    address = as_json(doc.get("Address"))
    hsc = as_json(doc.get("HSC"))
    ssc = as_json(doc.get("SSC"))
    father_details = as_json(doc.get("FatherDetails"))
    mother_details = as_json(doc.get("MotherDetails"))
    guardian_details = as_json(doc.get("GuardianDetails"))
    applied_for = as_json(doc.get("AppliedFor"))
    payment = as_json(doc.get("Payment"))

    # S3 Upload URLs
    photo_url = clean_str(doc.get("PhotoURL"))
    aadhar_url = clean_str(doc.get("AadharURL"))
    hsc_marks_card_url = clean_str(doc.get("HSCMarksCardURL"))
    ssc_marks_card_url = clean_str(doc.get("SSCMarksCardURL"))
    caste_cert_url = clean_str(doc.get("CasteCertificateURL"))
    domicile_cert_url = clean_str(doc.get("DomicileCertificateURL"))
    birth_cert_url = clean_str(doc.get("BirthCertificateURL"))
    transfer_cert_url = clean_str(doc.get("TransferCertificateURL"))
    leaving_cert_url = clean_str(doc.get("LeavingCertificateURL"))

    tpl_id = clean_uuid(doc.get("ApplicationFormTemplateId"))
    submitted_on = parse_iso_timestamp(doc.get("SubmittedOn"))
    app_no = clean_int(doc.get("ApplicationNumber"))
    shortlisted_in = clean_int(doc.get("ShortlistedIn"))
    doa = parse_iso_timestamp(doc.get("DOA"))
    app_status = map_application_status(doc.get("ApplicationStatus"))

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        app_id,
        name,
        email,
        mobile,
        dob,
        residential_status,
        category,
        gender,
        address,
        hsc,
        ssc,
        father_details,
        mother_details,
        guardian_details,
        applied_for,
        payment,
        photo_url,
        aadhar_url,
        hsc_marks_card_url,
        ssc_marks_card_url,
        caste_cert_url,
        domicile_cert_url,
        birth_cert_url,
        transfer_cert_url,
        leaving_cert_url,
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
    )


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup
# -----------------------------------------------------------------------------


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create target enums, application_form_templates and applications tables."""
    cur.execute(
        """
        -- 1. Create Enums
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'application_form_template_status_enum') THEN
                CREATE TYPE application_form_template_status_enum AS ENUM (
                    'Active',
                    'Published',
                    'Disabled'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'residential_status_enum') THEN
                CREATE TYPE residential_status_enum AS ENUM (
                    'Indian',
                    'PIO_OCI',
                    'NRI'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'applicant_category_enum') THEN
                CREATE TYPE applicant_category_enum AS ENUM (
                    'GM',
                    'OBC',
                    'SC',
                    'ST'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'applicant_gender_enum') THEN
                CREATE TYPE applicant_gender_enum AS ENUM (
                    'Female',
                    'Male',
                    'NoInfo'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'application_status_enum') THEN
                CREATE TYPE application_status_enum AS ENUM (
                    'WIP',
                    'Selected',
                    'Submitted',
                    'Shortlisted',
                    'Admitted',
                    'Rejected',
                    'OptedIn',
                    'OptedOut',
                    'Declined'
                );
            END IF;
        END $$;

        -- Drop old views if any exist
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'applications') THEN
                DROP VIEW applications CASCADE;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.views WHERE table_name = 'application_form_templates') THEN
                DROP VIEW application_form_templates CASCADE;
            END IF;
        END $$;

        -- Drop previous tables to recreate with clean JSONB and ENUM columns
        DROP TABLE IF EXISTS applications CASCADE;
        DROP TABLE IF EXISTS application_form_templates CASCADE;
        DROP TABLE IF EXISTS application CASCADE;
        DROP TABLE IF EXISTS application_form_template CASCADE;

        -- 2. ApplicationFormTemplates Table
        CREATE TABLE IF NOT EXISTS application_form_templates (
            id UUID PRIMARY KEY,
            title VARCHAR(200),
            description TEXT,
            options JSONB,
            start_date TIMESTAMPTZ,
            end_date TIMESTAMPTZ,
            status application_form_template_status_enum NOT NULL DEFAULT 'Active',
            shortlists JSONB NOT NULL DEFAULT '[]'::jsonb,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- 3. Applications Table
        CREATE TABLE IF NOT EXISTS applications (
            id UUID PRIMARY KEY,
            name VARCHAR(150),
            email VARCHAR(254),
            mobile VARCHAR(20),
            dob TIMESTAMPTZ,
            residential_status residential_status_enum,
            category applicant_category_enum,
            gender applicant_gender_enum,
            -- Composite / Nested structures stored as JSONB
            address JSONB,
            hsc JSONB,
            ssc JSONB,
            father_details JSONB,
            mother_details JSONB,
            guardian_details JSONB,
            applied_for JSONB,
            payment JSONB,
            -- Upload S3 URLs
            photo_url TEXT,
            aadhar_url TEXT,
            hsc_marks_card_url TEXT,
            ssc_marks_card_url TEXT,
            caste_certificate_url TEXT,
            domicile_certificate_url TEXT,
            birth_certificate_url TEXT,
            transfer_certificate_url TEXT,
            leaving_certificate_url TEXT,
            -- Template reference & Application lifecycle
            application_form_template_id UUID REFERENCES application_form_templates(id),
            submitted_on TIMESTAMPTZ,
            application_number INTEGER,
            shortlisted_in INTEGER,
            doa TIMESTAMPTZ,
            application_status application_status_enum NOT NULL DEFAULT 'WIP',
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS application_form_templates_owner_id_idx ON application_form_templates (owner_id);
        CREATE INDEX IF NOT EXISTS application_form_templates_created_on_idx ON application_form_templates (created_on);
        CREATE INDEX IF NOT EXISTS applications_template_id_idx ON applications (application_form_template_id);
        CREATE INDEX IF NOT EXISTS applications_owner_id_idx ON applications (owner_id);
        CREATE INDEX IF NOT EXISTS applications_created_on_idx ON applications (created_on);
        CREATE INDEX IF NOT EXISTS applications_status_idx ON applications (application_status);
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operations
# -----------------------------------------------------------------------------


def upsert_template(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> UpsertResult:
    """Idempotently upsert an ApplicationFormTemplate."""
    fields = extract_template_fields(doc)
    sql = """
        INSERT INTO application_form_templates (
            id, title, description, options, start_date, end_date,
            status, shortlists, owner_id, parent_id, created_on,
            created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            options = EXCLUDED.options,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            status = EXCLUDED.status,
            shortlists = EXCLUDED.shortlists,
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


def upsert_application(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> UpsertResult:
    """Idempotently upsert an Application."""
    fields = extract_application_fields(doc)
    sql = """
        INSERT INTO applications (
            id, name, email, mobile, dob, residential_status, category, gender,
            address, hsc, ssc, father_details, mother_details, guardian_details,
            applied_for, payment,
            photo_url, aadhar_url, hsc_marks_card_url, ssc_marks_card_url,
            caste_certificate_url, domicile_certificate_url, birth_certificate_url,
            transfer_certificate_url, leaving_certificate_url,
            application_form_template_id, submitted_on, application_number, shortlisted_in,
            doa, application_status, owner_id, parent_id, created_on, created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            mobile = EXCLUDED.mobile,
            dob = EXCLUDED.dob,
            residential_status = EXCLUDED.residential_status,
            category = EXCLUDED.category,
            gender = EXCLUDED.gender,
            address = EXCLUDED.address,
            hsc = EXCLUDED.hsc,
            ssc = EXCLUDED.ssc,
            father_details = EXCLUDED.father_details,
            mother_details = EXCLUDED.mother_details,
            guardian_details = EXCLUDED.guardian_details,
            applied_for = EXCLUDED.applied_for,
            payment = EXCLUDED.payment,
            photo_url = EXCLUDED.photo_url,
            aadhar_url = EXCLUDED.aadhar_url,
            hsc_marks_card_url = EXCLUDED.hsc_marks_card_url,
            ssc_marks_card_url = EXCLUDED.ssc_marks_card_url,
            caste_certificate_url = EXCLUDED.caste_certificate_url,
            domicile_certificate_url = EXCLUDED.domicile_certificate_url,
            birth_certificate_url = EXCLUDED.birth_certificate_url,
            transfer_certificate_url = EXCLUDED.transfer_certificate_url,
            leaving_certificate_url = EXCLUDED.leaving_certificate_url,
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
        tpl_docs = raven_query_collection(
            requests_session, cfg, cfg.templates_collection
        )
        app_docs = raven_query_collection(
            requests_session, cfg, cfg.applications_collection
        )
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

                print("[4/5] Upserting application form templates...")
                for d in tpl_docs:
                    res = upsert_template(cur, d)
                    loaded_tpls += 1
                    new_tpls += int(res.inserted)

                print("[5/5] Upserting applications...")
                for d in app_docs:
                    res = upsert_application(cur, d)
                    loaded_apps += 1
                    new_apps += int(res.inserted)

        # Post-load verification counts
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM application_form_templates")
            total_templates = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM applications")
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
                "application_form_templates": total_templates,
                "applications": total_applications,
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
