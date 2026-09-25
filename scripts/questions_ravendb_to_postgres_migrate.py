#!/usr/bin/env python3
"""
Extract Questions, QATags, and RandomQuestionSubmissions data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs and JSONBs,
and load into PostgreSQL.

Target tables:
- qa_tags
- questions
- random_question_submissions
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

UUID_NAMESPACE_QUESTIONS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


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
    qa_tags_collection: str
    questions_collection: str
    random_question_submissions_collection: str
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
        description="Migrate QATags, Questions, and RandomQuestionSubmissions from RavenDB to PostgreSQL"
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
        "--qa-tags-collection",
        default=os.getenv("QA_TAGS_COLLECTION", "QATags"),
        help="RavenDB collection name for QA tags (default: QATags)",
    )
    parser.add_argument(
        "--questions-collection",
        default=os.getenv("QUESTIONS_COLLECTION", "Questions"),
        help="RavenDB collection name for questions (default: Questions)",
    )
    parser.add_argument(
        "--random-question-submissions-collection",
        default=os.getenv(
            "RANDOM_QUESTION_SUBMISSIONS_COLLECTION", "RandomQuestionSubmissions"
        ),
        help="RavenDB collection name for random question submissions (default: RandomQuestionSubmissions)",
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
        qa_tags_collection=args.qa_tags_collection,
        questions_collection=args.questions_collection,
        random_question_submissions_collection=args.random_question_submissions_collection,
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


def clean_decimal(val: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Parse numeric/decimal value into Decimal(10, 2)."""
    if val is None:
        return default
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"))
    text = str(val).strip().replace(",", "")
    if not text:
        return default
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return default


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


def clean_sub_questions(raw_val: Any) -> List[Dict[str, Any]]:
    """Clean sub-questions ensuring DefaultWeightage is valid decimal/float in JSONB."""
    if not isinstance(raw_val, list):
        return []
    cleaned_list = []
    for item in raw_val:
        if isinstance(item, dict):
            cleaned_item = dict(item)
            if "DefaultWeightage" in cleaned_item and cleaned_item["DefaultWeightage"] is not None:
                try:
                    cleaned_item["DefaultWeightage"] = float(cleaned_item["DefaultWeightage"])
                except (ValueError, TypeError):
                    pass
            cleaned_list.append(cleaned_item)
    return cleaned_list


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

# TagStatusEnum: Unknown = 0, Active = 1, Disabled = 99
QA_TAG_STATUS_MAP: Dict[Any, str] = {
    0: "Unknown",
    1: "Active",
    99: "Disabled",
    "unknown": "Unknown",
    "active": "Active",
    "disabled": "Disabled",
    "inactive": "Disabled",
}

# QuestionStatusEnum: unknown = 0, active = 1, disabled = 99, published = 50, wip = 40, archived = 80
QUESTION_STATUS_MAP: Dict[Any, str] = {
    0: "unknown",
    1: "active",
    40: "wip",
    50: "published",
    80: "archived",
    99: "disabled",
    "unknown": "unknown",
    "active": "active",
    "wip": "wip",
    "published": "published",
    "archived": "archived",
    "disabled": "disabled",
    "inactive": "disabled",
}

# AnswerEnum: Text = 1, OneOf = 2, ManyOf = 3
QUESTION_ANSWER_TYPE_MAP: Dict[Any, str] = {
    1: "Text",
    2: "OneOf",
    3: "ManyOf",
    "text": "Text",
    "oneof": "OneOf",
    "manyof": "ManyOf",
}

# DifficultyEnum: low = 10, medium = 20, high = 30
QUESTION_DIFFICULTY_MAP: Dict[Any, str] = {
    10: "low",
    20: "medium",
    30: "high",
    "low": "low",
    "medium": "medium",
    "high": "high",
}


def map_qa_tag_status(val: Any) -> str:
    if val is None:
        return "Active"
    if isinstance(val, int):
        return QA_TAG_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return QA_TAG_STATUS_MAP.get(int(s), "Active")
    return QA_TAG_STATUS_MAP.get(s.lower(), "Active")


def map_question_status(val: Any) -> str:
    if val is None:
        return "wip"
    if isinstance(val, int):
        return QUESTION_STATUS_MAP.get(val, "wip")
    s = str(val).strip()
    if s.isdigit():
        return QUESTION_STATUS_MAP.get(int(s), "wip")
    return QUESTION_STATUS_MAP.get(s.lower(), "wip")


def map_question_answer_type(val: Any) -> str:
    if val is None:
        return "Text"
    if isinstance(val, int):
        return QUESTION_ANSWER_TYPE_MAP.get(val, "Text")
    s = str(val).strip()
    if s.isdigit():
        return QUESTION_ANSWER_TYPE_MAP.get(int(s), "Text")
    norm = s.lower().replace(" ", "").replace("_", "")
    return QUESTION_ANSWER_TYPE_MAP.get(norm, "Text")


def map_question_difficulty(val: Any) -> str:
    if val is None:
        return "low"
    if isinstance(val, int):
        return QUESTION_DIFFICULTY_MAP.get(val, "low")
    s = str(val).strip()
    if s.isdigit():
        return QUESTION_DIFFICULTY_MAP.get(int(s), "low")
    return QUESTION_DIFFICULTY_MAP.get(s.lower(), "low")


# -----------------------------------------------------------------------------
# Document Field Extractors (Only RavenDB fields, no metadata columns)
# -----------------------------------------------------------------------------


def extract_qa_tag_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for qa_tags table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    tag_id = clean_uuid(raw_id)
    if not tag_id and raw_id:
        tag_id = str(uuid.uuid5(UUID_NAMESPACE_QUESTIONS, str(raw_id).strip())).lower()
    if not tag_id:
        raise ValueError(f"QATag missing valid ID: {raw_id}")

    name = clean_str(doc.get("Name"), 255)
    predefined = clean_bool(doc.get("Predefined"), default=False)
    csn = clean_str(doc.get("CSN"), 50)
    meta = as_json(doc.get("Meta") if isinstance(doc.get("Meta"), dict) else {}, default_val={})
    status = map_qa_tag_status(doc.get("Status"))

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        tag_id,
        name,
        predefined,
        csn,
        meta,
        status,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


def extract_question_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for questions table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    question_id = clean_uuid(raw_id)
    if not question_id and raw_id:
        question_id = str(uuid.uuid5(UUID_NAMESPACE_QUESTIONS, str(raw_id).strip())).lower()
    if not question_id:
        raise ValueError(f"Question missing valid ID: {raw_id}")

    question_text = clean_str(doc.get("QuestionText"))
    plain_text = clean_str(doc.get("PlainText"))
    html_text = clean_str(doc.get("HtmlText"))
    tag_list = clean_string_list(doc.get("TagList"))

    options = as_json(doc.get("Options") if isinstance(doc.get("Options"), list) else [], default_val=[])
    meta = as_json(doc.get("Meta") if isinstance(doc.get("Meta"), dict) else {}, default_val={})
    status = map_question_status(doc.get("Status"))
    answer_type = map_question_answer_type(doc.get("AnswerType"))
    hints = as_json(doc.get("Hints") if isinstance(doc.get("Hints"), list) else [], default_val=[])
    instruction = clean_str(doc.get("Instruction"))
    default_weightage = clean_decimal(doc.get("DefaultWeightage"), default=Decimal("1.00"))
    sub_questions = as_json(clean_sub_questions(doc.get("Questions")), default_val=[])
    difficulty = map_question_difficulty(doc.get("Difficulty"))
    keywords = clean_string_list(doc.get("Keywords"))
    isn = clean_str(doc.get("ISN"), 50)
    answer_text = clean_str(doc.get("AnswerText"))

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        question_id,
        question_text,
        plain_text,
        html_text,
        tag_list,
        options,
        meta,
        status,
        answer_type,
        hints,
        instruction,
        default_weightage,
        sub_questions,
        difficulty,
        keywords,
        isn,
        answer_text,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
    )


def extract_random_question_submission_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform fields for random_question_submissions table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    submission_id = clean_uuid(raw_id)
    if not submission_id and raw_id:
        submission_id = str(uuid.uuid5(UUID_NAMESPACE_QUESTIONS, str(raw_id).strip())).lower()
    if not submission_id:
        raise ValueError(f"RandomQuestionSubmission missing valid ID: {raw_id}")

    user_id = clean_uuid(doc.get("UserId"))
    user_email = clean_str(doc.get("UserEmail"), 255)
    questions_answered = as_json(
        doc.get("QuestionsAnswered") if isinstance(doc.get("QuestionsAnswered"), list) else [],
        default_val=[],
    )

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        submission_id,
        user_id,
        user_email,
        questions_answered,
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
    """Create target enums and tables without secondary indexes."""
    cur.execute(
        """
        -- 1. Create or extend Enums
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'qa_tag_status_enum') THEN
                CREATE TYPE qa_tag_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Disabled'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'question_status_enum') THEN
                CREATE TYPE question_status_enum AS ENUM (
                    'unknown',
                    'active',
                    'disabled',
                    'published',
                    'wip',
                    'archived'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'question_answer_type_enum') THEN
                CREATE TYPE question_answer_type_enum AS ENUM (
                    'Text',
                    'OneOf',
                    'ManyOf'
                );
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'question_difficulty_enum') THEN
                CREATE TYPE question_difficulty_enum AS ENUM (
                    'low',
                    'medium',
                    'high'
                );
            END IF;
        END $$;

        -- 2. Create Target Tables (No secondary indexes)
        CREATE TABLE IF NOT EXISTS qa_tags (
            id UUID PRIMARY KEY,
            name VARCHAR(255),
            predefined BOOLEAN DEFAULT FALSE,
            csn VARCHAR(50),
            meta JSONB DEFAULT '{}'::jsonb,
            status qa_tag_status_enum NOT NULL DEFAULT 'Active',
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        CREATE TABLE IF NOT EXISTS questions (
            id UUID PRIMARY KEY,
            question_text TEXT,
            plain_text TEXT,
            html_text TEXT,
            tag_list TEXT[] DEFAULT '{}'::text[],
            options JSONB DEFAULT '[]'::jsonb,
            meta JSONB DEFAULT '{}'::jsonb,
            status question_status_enum NOT NULL DEFAULT 'wip',
            answer_type question_answer_type_enum NOT NULL DEFAULT 'Text',
            hints JSONB DEFAULT '[]'::jsonb,
            instruction TEXT,
            default_weightage NUMERIC(10, 2) DEFAULT 1.00,
            questions JSONB DEFAULT '[]'::jsonb,
            difficulty question_difficulty_enum NOT NULL DEFAULT 'low',
            keywords TEXT[] DEFAULT '{}'::text[],
            isn VARCHAR(50),
            answer_text TEXT,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        CREATE TABLE IF NOT EXISTS random_question_submissions (
            id UUID PRIMARY KEY,
            user_id UUID,
            user_email VARCHAR(255),
            questions_answered JSONB DEFAULT '[]'::jsonb,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );
        """
    )


# -----------------------------------------------------------------------------
# Database Upsert Operations
# -----------------------------------------------------------------------------


def upsert_qa_tag(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert a QATag document."""
    fields = extract_qa_tag_fields(doc)
    sql = """
        INSERT INTO qa_tags (
            id, name, predefined, csn, meta, status,
            owner_id, parent_id, created_on, created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            predefined = EXCLUDED.predefined,
            csn = EXCLUDED.csn,
            meta = EXCLUDED.meta,
            status = EXCLUDED.status,
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


def upsert_question(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert a Question document."""
    fields = extract_question_fields(doc)
    sql = """
        INSERT INTO questions (
            id, question_text, plain_text, html_text, tag_list, options, meta,
            status, answer_type, hints, instruction, default_weightage,
            questions, difficulty, keywords, isn, answer_text,
            owner_id, parent_id, created_on, created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            question_text = EXCLUDED.question_text,
            plain_text = EXCLUDED.plain_text,
            html_text = EXCLUDED.html_text,
            tag_list = EXCLUDED.tag_list,
            options = EXCLUDED.options,
            meta = EXCLUDED.meta,
            status = EXCLUDED.status,
            answer_type = EXCLUDED.answer_type,
            hints = EXCLUDED.hints,
            instruction = EXCLUDED.instruction,
            default_weightage = EXCLUDED.default_weightage,
            questions = EXCLUDED.questions,
            difficulty = EXCLUDED.difficulty,
            keywords = EXCLUDED.keywords,
            isn = EXCLUDED.isn,
            answer_text = EXCLUDED.answer_text,
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


def upsert_random_question_submission(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> UpsertResult:
    """Idempotently upsert a RandomQuestionSubmission document."""
    fields = extract_random_question_submission_fields(doc)
    sql = """
        INSERT INTO random_question_submissions (
            id, user_id, user_email, questions_answered,
            owner_id, parent_id, created_on, created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            user_email = EXCLUDED.user_email,
            questions_answered = EXCLUDED.questions_answered,
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
    """Run the end-to-end migration for Questions module."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}")
        print("[1/4] Fetching RavenDB documents for all 3 collections...")

        # 1. Fetch QATags
        qa_tag_docs = raven_query_collection(
            requests_session, cfg, cfg.qa_tags_collection
        )
        if not qa_tag_docs and cfg.qa_tags_collection == "QATags":
            try:
                alt = raven_query_collection(requests_session, cfg, "QATag")
                if alt:
                    qa_tag_docs = alt
            except Exception:
                pass
        print(f"Fetched qa_tags={len(qa_tag_docs)}")

        # 2. Fetch Questions
        question_docs = raven_query_collection(
            requests_session, cfg, cfg.questions_collection
        )
        if not question_docs and cfg.questions_collection == "Questions":
            try:
                alt = raven_query_collection(requests_session, cfg, "Question")
                if alt:
                    question_docs = alt
            except Exception:
                pass
        print(f"Fetched questions={len(question_docs)}")

        # 3. Fetch RandomQuestionSubmissions
        submission_docs = raven_query_collection(
            requests_session, cfg, cfg.random_question_submissions_collection
        )
        if not submission_docs and cfg.random_question_submissions_collection == "RandomQuestionSubmissions":
            try:
                alt = raven_query_collection(requests_session, cfg, "RandomQuestionSubmission")
                if alt:
                    submission_docs = alt
            except Exception:
                pass
        print(f"Fetched random_question_submissions={len(submission_docs)}")

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

        loaded_tags = 0
        new_tags = 0
        loaded_questions = 0
        new_questions = 0
        loaded_submissions = 0
        new_submissions = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/4] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/4] Upserting documents...")
                # 1. Upsert QATags
                for d in qa_tag_docs:
                    res = upsert_qa_tag(cur, d)
                    loaded_tags += 1
                    new_tags += int(res.inserted)

                # 2. Upsert Questions
                for d in question_docs:
                    res = upsert_question(cur, d)
                    loaded_questions += 1
                    new_questions += int(res.inserted)

                # 3. Upsert RandomQuestionSubmissions
                for d in submission_docs:
                    res = upsert_random_question_submission(cur, d)
                    loaded_submissions += 1
                    new_submissions += int(res.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "collections": {
                    "qa_tags": cfg.qa_tags_collection,
                    "questions": cfg.questions_collection,
                    "random_question_submissions": cfg.random_question_submissions_collection,
                },
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "qa_tags_processed": loaded_tags,
                "new_qa_tags_inserted": new_tags,
                "questions_processed": loaded_questions,
                "new_questions_inserted": new_questions,
                "random_question_submissions_processed": loaded_submissions,
                "new_random_question_submissions_inserted": new_submissions,
            },
        }

        print("Migration completed.")
        print(f"qa_tags_processed: {loaded_tags}, new_inserted: {new_tags}")
        print(f"questions_processed: {loaded_questions}, new_inserted: {new_questions}")
        print(
            f"random_question_submissions_processed: {loaded_submissions}, new_inserted: {new_submissions}"
        )

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
