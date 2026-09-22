#!/usr/bin/env python3
"""
Extract Assessments and AssessmentTags data from RavenDB,
transform it to PostgreSQL schema, and load into PostgreSQL.

Handles:
- assessment_tag (AssessmentTags collection)
- assessment (Assessments collection)
- Child/relational tables:
    - assessment_tag_mapping
    - assessment_section
    - assessment_question
    - assessment_question_option
    - assessment_question_hint
- Backward-compatible views: assessments, assessment_tags, assessment_questions

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

# AssessmentStatusEnum: Unknown=0, Active=1, WIP=40, Published=50, Archived=80, Disabled=99
ASSESSMENT_STATUS_MAP: Dict[str, int] = {
    "unknown": 0,
    "active": 1,
    "wip": 40,
    "published": 50,
    "archived": 80,
    "disabled": 99,
    "inactive": 99,
}

# TagStatusEnum: Unknown=0, Active=1, Disabled=99
TAG_STATUS_MAP: Dict[str, int] = {
    "unknown": 0,
    "active": 1,
    "disabled": 99,
    "inactive": 99,
}

# QuestionStatusEnum: unknown=0, active=1, wip=40, published=50, archived=80, disabled=99
QUESTION_STATUS_MAP: Dict[str, int] = {
    "unknown": 0,
    "active": 1,
    "wip": 40,
    "published": 50,
    "archived": 80,
    "disabled": 99,
    "inactive": 99,
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
    assessments_collection: str
    tags_collection: str
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
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
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
        description="Migrate Assessments and AssessmentTags from RavenDB to PostgreSQL"
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
    )
    parser.add_argument(
        "--pg-host", default=os.getenv("PG_HOST", "localhost")
    )
    parser.add_argument(
        "--pg-port",
        type=int,
        default=int(os.getenv("PG_PORT", "5432")),
    )
    parser.add_argument("--pg-db", default=os.getenv("PG_DB", "rpg"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER", "postgres"))
    parser.add_argument(
        "--pg-password", default=os.getenv("PG_PASSWORD", "")
    )
    parser.add_argument(
        "--assessments-collection",
        default=os.getenv("ASSESSMENTS_COLLECTION", "Assessments"),
        help="RavenDB collection name for assessments (default: Assessments)",
    )
    parser.add_argument(
        "--tags-collection",
        default=os.getenv("ASSESSMENT_TAGS_COLLECTION", "AssessmentTags"),
        help="RavenDB collection name for assessment tags (default: AssessmentTags)",
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
            "ASSESSMENTS_SUMMARY_JSON_PATH",
            os.path.join(script_dir, "..", "validation", "assessments_migration_summary.json"),
        ),
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--inspect-source-only",
        action="store_true",
        default=False,
        help="Inspect RavenDB collections only; do not write to PostgreSQL",
    )

    args = parser.parse_args()

    if not args.raven_url:
        parser.error("Missing RavenDB URL. Provide --raven-url or set RAVEN_URL.")
    if not args.raven_db:
        parser.error("Missing RavenDB database. Provide --raven-db or set RAVEN_DB.")

    if args.raven_cert_file:
        if not os.path.isfile(args.raven_cert_file):
            script_dir_cert = os.path.join(script_dir, args.raven_cert_file)
            if os.path.isfile(script_dir_cert):
                args.raven_cert_file = script_dir_cert
            else:
                parser.error(f"Raven cert file not found: {args.raven_cert_file}")

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
        assessments_collection=args.assessments_collection,
        tags_collection=args.tags_collection,
        page_size=args.page_size,
        timeout_sec=args.timeout_sec,
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
        inspect_source_only=args.inspect_source_only,
    )


# -----------------------------------------------------------------------------
# Extraction & Transformation Helpers
# -----------------------------------------------------------------------------

def get_nested(doc: Dict[str, Any], *path: str) -> Any:
    cur: Any = doc
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


def first_non_empty(*values: Any) -> Optional[Any]:
    for val in values:
        if val is None:
            continue
        if isinstance(val, str) and val.strip() == "":
            continue
        return val
    return None


def extract_uuid_from_any(value: Any) -> Optional[str]:
    if value is None:
        return None
    match = UUID_RE.search(str(value))
    return match.group(0).lower() if match else None


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


def parse_int(value: Any) -> Optional[int]:
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


def parse_assessment_status(value: Any) -> int:
    """
    AssessmentStatusEnum: Unknown=0, Active=1, WIP=40, Published=50, Archived=80, Disabled=99
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    return ASSESSMENT_STATUS_MAP.get(text, 0)


def parse_tag_status(value: Any) -> int:
    """
    TagStatusEnum: Unknown=0, Active=1, Disabled=99
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    return TAG_STATUS_MAP.get(text, 0)


def parse_question_status(value: Any) -> int:
    """
    QuestionStatusEnum: unknown=0, active=1, wip=40, published=50, archived=80, disabled=99
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    return QUESTION_STATUS_MAP.get(text, 0)


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
        print("[!] Warning: RavenDB TLS verification is disabled (--raven-insecure).")


def raven_query_collection(
    session: requests.Session, cfg: Config, collection_name: str
) -> List[Dict[str, Any]]:
    url = f"{cfg.raven_url}/databases/{cfg.raven_db}/queries"
    start = 0
    docs: List[Dict[str, Any]] = []
    escaped = collection_name.replace("\\", "\\\\").replace('"', '\\"')

    print(f"[*] Querying RavenDB collection: '{collection_name}'...")
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
        print(f"    - Retrieved {len(docs)} documents so far...")

    print(f"[+] Total documents fetched from '{collection_name}': {len(docs)}")
    return docs


# -----------------------------------------------------------------------------
# PostgreSQL Schema Setup
# -----------------------------------------------------------------------------

def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create all required assessment and assessment_tag tables and indexes."""
    cur.execute(
        """
        -- 1. AssessmentTag Table
        CREATE TABLE IF NOT EXISTS assessment_tag (
            id UUID PRIMARY KEY,
            name VARCHAR(100),
            predefined BOOLEAN,
            csn VARCHAR(50),
            meta JSONB,
            status INTEGER,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- 2. Assessment Main Table
        CREATE TABLE IF NOT EXISTS assessment (
            id UUID PRIMARY KEY,
            total_marks NUMERIC(18, 2),
            description TEXT,
            subject VARCHAR(150),
            subject_code VARCHAR(50),
            duration INTEGER,
            status INTEGER,
            multiple_attempts BOOLEAN,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID,
            tags TEXT[],
            sections JSONB
        );

        -- 3. AssessmentTags Mapping Table
        CREATE TABLE IF NOT EXISTS assessment_tag_mapping (
            assessment_id UUID NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
            assessment_tag_id UUID NOT NULL,
            PRIMARY KEY (assessment_id, assessment_tag_id)
        );

        -- 4. AssessmentSections Table
        CREATE TABLE IF NOT EXISTS assessment_section (
            id BIGSERIAL PRIMARY KEY,
            assessment_id UUID NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
            instruction TEXT,
            instruction_html TEXT,
            display_order INTEGER
        );

        -- 5. AssessmentQuestions Table
        CREATE TABLE IF NOT EXISTS assessment_question (
            id UUID PRIMARY KEY,
            assessment_id UUID NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
            section_id BIGINT,
            question_text TEXT,
            html_text TEXT,
            meta JSONB,
            status INTEGER,
            answer_type VARCHAR(30),
            instruction TEXT,
            default_weightage NUMERIC(18, 2),
            display_order INTEGER
        );

        -- 6. AssessmentQuestionOptions Table
        CREATE TABLE IF NOT EXISTS assessment_question_option (
            id BIGSERIAL PRIMARY KEY,
            option_id INTEGER,
            assessment_question_id UUID NOT NULL REFERENCES assessment_question(id) ON DELETE CASCADE,
            option_type VARCHAR(50),
            value TEXT,
            answer BOOLEAN,
            html_string TEXT
        );

        -- 7. AssessmentQuestionHints Table
        CREATE TABLE IF NOT EXISTS assessment_question_hint (
            id BIGSERIAL PRIMARY KEY,
            assessment_question_id UUID NOT NULL REFERENCES assessment_question(id) ON DELETE CASCADE,
            value TEXT,
            hint_type VARCHAR(50)
        );

        -- Indexes for query performance
        CREATE INDEX IF NOT EXISTS idx_assessment_tag_name ON assessment_tag (name);
        CREATE INDEX IF NOT EXISTS idx_assessment_tag_status ON assessment_tag (status);
        CREATE INDEX IF NOT EXISTS idx_assessment_status ON assessment (status);
        CREATE INDEX IF NOT EXISTS idx_assessment_subject ON assessment (subject);
        CREATE INDEX IF NOT EXISTS idx_assessment_subject_code ON assessment (subject_code);
        CREATE INDEX IF NOT EXISTS idx_assessment_owner_id ON assessment (owner_id);
        CREATE INDEX IF NOT EXISTS idx_assessment_section_aid ON assessment_section (assessment_id);
        CREATE INDEX IF NOT EXISTS idx_assessment_question_aid ON assessment_question (assessment_id);
        CREATE INDEX IF NOT EXISTS idx_assessment_question_sid ON assessment_question (section_id);
        CREATE INDEX IF NOT EXISTS idx_assessment_q_option_qid ON assessment_question_option (assessment_question_id);
        CREATE INDEX IF NOT EXISTS idx_assessment_q_hint_qid ON assessment_question_hint (assessment_question_id);

        -- Backward compatible views
        CREATE OR REPLACE VIEW assessments AS SELECT * FROM assessment;
        CREATE OR REPLACE VIEW assessment_tags AS SELECT * FROM assessment_tag;
        CREATE OR REPLACE VIEW assessment_questions AS SELECT * FROM assessment_question;
        CREATE OR REPLACE VIEW assessment_sections AS SELECT * FROM assessment_section;
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    """Assert all required columns exist in assessment and assessment_tag."""
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_name IN ('assessment', 'assessment_tag', 'assessment_question')
        """
    )
    existing = {(row[0], row[1].lower()) for row in cur.fetchall()}

    req_assessment = {
        "id", "total_marks", "description", "subject", "subject_code",
        "duration", "status", "multiple_attempts", "owner_id", "parent_id",
        "created_on", "created_by", "modified_on", "modified_by"
    }
    req_tag = {
        "id", "name", "predefined", "csn", "meta", "status",
        "owner_id", "parent_id", "created_on", "created_by",
        "modified_on", "modified_by"
    }
    req_question = {
        "id", "assessment_id", "section_id", "question_text", "html_text",
        "meta", "status", "answer_type", "instruction", "default_weightage",
        "display_order"
    }

    missing_assessment = {col for col in req_assessment if ("assessment", col) not in existing}
    missing_tag = {col for col in req_tag if ("assessment_tag", col) not in existing}
    missing_q = {col for col in req_question if ("assessment_question", col) not in existing}

    if missing_assessment or missing_tag or missing_q:
        raise RuntimeError(
            f"Schema verification failed! Missing cols in assessment: {missing_assessment}, tag: {missing_tag}, question: {missing_q}"
        )


# -----------------------------------------------------------------------------
# Transform & Upsert: AssessmentTag
# -----------------------------------------------------------------------------

def transform_tag_doc(doc: Dict[str, Any]) -> Tuple[Any, ...]:
    tag_id = derive_doc_id(doc, "TagId")
    if not tag_id:
        raise ValueError(f"Tag doc missing valid GUID: {doc.get('Id')}")

    name = as_text(doc.get("Name"))
    name = name[:100] if name else None
    predefined = parse_bool(doc.get("Predefined"), default=False)
    csn = as_text(doc.get("CSN"))
    csn = csn[:50] if csn else None
    meta = as_json(first_non_empty(doc.get("Meta"), doc.get("MetaData")))
    status = parse_tag_status(doc.get("Status"))
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))
    parent_id = extract_uuid_from_any(doc.get("ParentId"))
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))
    modified_on = parse_ts(doc.get("ModifiedOn"))
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

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


def upsert_tag(cur: psycopg2.extensions.cursor, row: Tuple[Any, ...]) -> UpsertResult:
    tag_id = row[0]
    cur.execute("SELECT 1 FROM assessment_tag WHERE id = %s", (tag_id,))
    is_new = cur.fetchone() is None

    cur.execute(
        """
        INSERT INTO assessment_tag (
            id, name, predefined, csn, meta, status,
            owner_id, parent_id, created_on, created_by, modified_on, modified_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id)
        DO UPDATE SET
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
        RETURNING id;
        """,
        row,
    )
    return UpsertResult(record_id=str(tag_id), inserted=is_new)


# -----------------------------------------------------------------------------
# Transform & Upsert: Assessment, Sections, Questions, Options, Hints
# -----------------------------------------------------------------------------

def transform_assessment_doc(doc: Dict[str, Any]) -> Tuple[Tuple[Any, ...], List[Dict[str, Any]], List[str]]:
    assessment_id = derive_doc_id(doc, "AssessmentId")
    if not assessment_id:
        raise ValueError(f"Assessment doc missing valid GUID: {doc.get('Id')}")

    total_marks = parse_decimal(
        first_non_empty(doc.get("TotalMarks"), doc.get("Marks"), doc.get("Total")),
        default=Decimal("0.00"),
    )
    description = as_text(doc.get("Description"))
    subject = as_text(doc.get("Subject"))
    subject = subject[:150] if subject else None
    subject_code = as_text(doc.get("SubjectCode"))
    subject_code = subject_code[:50] if subject_code else None
    duration = parse_int(doc.get("Duration")) or 0
    status = parse_assessment_status(doc.get("Status"))
    multiple_attempts = parse_bool(doc.get("MultipleAttempts"), default=False)
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))
    parent_id = extract_uuid_from_any(doc.get("ParentId"))
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))
    modified_on = parse_ts(doc.get("ModifiedOn"))
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

    tags_raw = doc.get("Tags") or []
    tags_list = [str(t) for t in tags_raw if t] if isinstance(tags_raw, list) else []

    sections_raw = doc.get("Sections") or []
    sections_list = sections_raw if isinstance(sections_raw, list) else []

    main_row = (
        assessment_id,
        total_marks,
        description,
        subject,
        subject_code,
        duration,
        status,
        multiple_attempts,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
        tags_list,
        as_json(sections_list),
    )

    return main_row, sections_list, tags_list


def upsert_assessment_and_children(
    cur: psycopg2.extensions.cursor,
    doc: Dict[str, Any],
    main_row: Tuple[Any, ...],
    sections_list: List[Dict[str, Any]],
    tags_list: List[str],
) -> UpsertResult:
    assessment_id = main_row[0]

    cur.execute("SELECT 1 FROM assessment WHERE id = %s", (assessment_id,))
    is_new = cur.fetchone() is None

    # 1. Upsert Assessment
    cur.execute(
        """
        INSERT INTO assessment (
            id, total_marks, description, subject, subject_code,
            duration, status, multiple_attempts, owner_id, parent_id,
            created_on, created_by, modified_on, modified_by,
            tags, sections
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (id)
        DO UPDATE SET
            total_marks = EXCLUDED.total_marks,
            description = EXCLUDED.description,
            subject = EXCLUDED.subject,
            subject_code = EXCLUDED.subject_code,
            duration = EXCLUDED.duration,
            status = EXCLUDED.status,
            multiple_attempts = EXCLUDED.multiple_attempts,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by,
            tags = EXCLUDED.tags,
            sections = EXCLUDED.sections
        RETURNING id;
        """,
        main_row,
    )

    # 2. Clear previous child data for this assessment to ensure idempotency
    cur.execute("DELETE FROM assessment_tag_mapping WHERE assessment_id = %s", (assessment_id,))
    cur.execute("DELETE FROM assessment_section WHERE assessment_id = %s", (assessment_id,))
    cur.execute("DELETE FROM assessment_question WHERE assessment_id = %s", (assessment_id,))

    # 3. Insert AssessmentTags Mapping
    for tag in tags_list:
        tag_uuid = extract_uuid_from_any(tag)
        if tag_uuid:
            cur.execute(
                """
                INSERT INTO assessment_tag_mapping (assessment_id, assessment_tag_id)
                VALUES (%s, %s)
                ON CONFLICT (assessment_id, assessment_tag_id) DO NOTHING
                """,
                (assessment_id, tag_uuid),
            )

    # 4. Insert Sections and Questions
    # Process sections if present
    standalone_questions: List[Dict[str, Any]] = doc.get("Questions") or []

    for s_idx, sec in enumerate(sections_list, 1):
        if not isinstance(sec, dict):
            continue
        instruction = as_text(sec.get("Instruction"))
        instruction_html = as_text(sec.get("InstructionHtml"))
        display_order = parse_int(sec.get("DisplayOrder")) or s_idx

        cur.execute(
            """
            INSERT INTO assessment_section (assessment_id, instruction, instruction_html, display_order)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (assessment_id, instruction, instruction_html, display_order),
        )
        sec_id = cur.fetchone()[0]

        # Questions inside section
        sec_questions = sec.get("Questions") or []
        for q_idx, q in enumerate(sec_questions, 1):
            if isinstance(q, dict):
                insert_question_and_children(cur, assessment_id, sec_id, q, q_idx)

    # Standalone questions directly attached to assessment
    if isinstance(standalone_questions, list):
        for q_idx, q in enumerate(standalone_questions, 1):
            if isinstance(q, dict):
                insert_question_and_children(cur, assessment_id, None, q, q_idx)

    return UpsertResult(record_id=str(assessment_id), inserted=is_new)


def insert_question_and_children(
    cur: psycopg2.extensions.cursor,
    assessment_id: str,
    section_id: Optional[int],
    q: Dict[str, Any],
    default_order: int,
) -> None:
    q_id = derive_doc_id(q, "QuestionId")
    if not q_id:
        return

    q_text = as_text(first_non_empty(q.get("QuestionText"), q.get("Text"), q.get("Title")))
    html_text = as_text(first_non_empty(q.get("HtmlText"), q.get("Html")))
    meta = as_json(q.get("Meta"))
    status = parse_question_status(q.get("Status"))
    answer_type = as_text(q.get("AnswerType")) or "Text"
    answer_type = answer_type[:30]
    instruction = as_text(q.get("Instruction"))
    weightage = parse_decimal(
        first_non_empty(q.get("DefaultWeightage"), q.get("Weightage"), q.get("Marks")),
        default=Decimal("1.00"),
    )
    display_order = parse_int(q.get("DisplayOrder")) or default_order

    cur.execute(
        """
        INSERT INTO assessment_question (
            id, assessment_id, section_id, question_text, html_text,
            meta, status, answer_type, instruction, default_weightage, display_order
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            assessment_id = EXCLUDED.assessment_id,
            section_id = EXCLUDED.section_id,
            question_text = EXCLUDED.question_text,
            html_text = EXCLUDED.html_text,
            meta = EXCLUDED.meta,
            status = EXCLUDED.status,
            answer_type = EXCLUDED.answer_type,
            instruction = EXCLUDED.instruction,
            default_weightage = EXCLUDED.default_weightage,
            display_order = EXCLUDED.display_order;
        """,
        (
            q_id,
            assessment_id,
            section_id,
            q_text,
            html_text,
            meta,
            status,
            answer_type,
            instruction,
            weightage,
            display_order,
        ),
    )

    # Options
    options = q.get("Options") or []
    if isinstance(options, list):
        for o_idx, opt in enumerate(options, 1):
            if isinstance(opt, dict):
                opt_id = parse_int(opt.get("Id")) or o_idx
                opt_type = as_text(opt.get("OptionType")) or "Option"
                opt_type = opt_type[:50]
                opt_val = as_text(first_non_empty(opt.get("Value"), opt.get("Text")))
                opt_ans = parse_bool(opt.get("Answer"), default=False)
                opt_html = as_text(first_non_empty(opt.get("HtmlString"), opt.get("Html")))

                cur.execute(
                    """
                    INSERT INTO assessment_question_option (
                        option_id, assessment_question_id, option_type, value, answer, html_string
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (opt_id, q_id, opt_type, opt_val, opt_ans, opt_html),
                )

    # Hints
    hints = q.get("Hints") or []
    if isinstance(hints, list):
        for hint in hints:
            if isinstance(hint, dict):
                h_val = as_text(hint.get("Value"))
                h_type = as_text(hint.get("HintType")) or "General"
                h_type = h_type[:50]
                cur.execute(
                    """
                    INSERT INTO assessment_question_hint (
                        assessment_question_id, value, hint_type
                    )
                    VALUES (%s, %s, %s)
                    """,
                    (q_id, h_val, h_type),
                )


# -----------------------------------------------------------------------------
# Main Migration Routine
# -----------------------------------------------------------------------------

def main() -> None:
    cfg = parse_args()

    print("=" * 70)
    print("CT-RPG: RavenDB to PostgreSQL Migration — Assessments Module")
    print("=" * 70)
    print(f"[*] RavenDB URL:     {cfg.raven_url}")
    print(f"[*] RavenDB DB:      {cfg.raven_db}")
    print(f"[*] Tags Col:        {cfg.tags_collection}")
    print(f"[*] Assessments Col: {cfg.assessments_collection}")
    print(f"[*] PostgreSQL Host: {cfg.pg_host}:{cfg.pg_port}")
    print(f"[*] PostgreSQL DB:   {cfg.pg_db} (User: {cfg.pg_user})")
    print("=" * 70)

    session = requests.Session()
    configure_raven_session(session, cfg)

    # 1. Fetch AssessmentTags
    tag_docs: List[Dict[str, Any]] = []
    try:
        tag_docs = raven_query_collection(session, cfg, cfg.tags_collection)
    except requests.HTTPError as ex:
        if cfg.tags_collection == "AssessmentTags":
            print("[!] Collection 'AssessmentTags' error. Trying fallback 'AssessmentTag'...")
            try:
                tag_docs = raven_query_collection(session, cfg, "AssessmentTag")
            except Exception:
                pass
        else:
            raise ex

    if not tag_docs and cfg.tags_collection == "AssessmentTags":
        try:
            tag_docs = raven_query_collection(session, cfg, "AssessmentTag")
        except Exception:
            pass

    # 2. Fetch Assessments
    assessment_docs: List[Dict[str, Any]] = []
    try:
        assessment_docs = raven_query_collection(session, cfg, cfg.assessments_collection)
    except requests.HTTPError as ex:
        if cfg.assessments_collection == "Assessments":
            print("[!] Collection 'Assessments' error. Trying fallback 'Assessment'...")
            try:
                assessment_docs = raven_query_collection(session, cfg, "Assessment")
            except Exception:
                pass
        else:
            raise ex

    if not assessment_docs and cfg.assessments_collection == "Assessments":
        try:
            assessment_docs = raven_query_collection(session, cfg, "Assessment")
        except Exception:
            pass

    print(f"\n[+] Loaded {len(tag_docs)} AssessmentTag(s) and {len(assessment_docs)} Assessment(s) from RavenDB.")

    if cfg.inspect_source_only:
        print("\n[*] Inspect source only specified.")
        if tag_docs:
            print("[*] Sample AssessmentTag keys:", list(tag_docs[0].keys()))
        if assessment_docs:
            print("[*] Sample Assessment keys:", list(assessment_docs[0].keys()))
        sys.exit(0)

    # 3. Connect to PostgreSQL
    print("\n[*] Connecting to PostgreSQL...")
    conn = psycopg2.connect(
        host=cfg.pg_host,
        port=cfg.pg_port,
        dbname=cfg.pg_db,
        user=cfg.pg_user,
        password=cfg.pg_password,
    )
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print("[*] Ensuring target tables and indexes exist...")
            ensure_target_schema(cur)
            assert_required_schema(cur)
            conn.commit()
            print("[+] Schema verified successfully.")

            # 4. Migrate AssessmentTags
            print(f"\n[*] Migrating {len(tag_docs)} AssessmentTag document(s)...")
            tags_inserted = 0
            tags_updated = 0
            tags_errors = 0
            for idx, doc in enumerate(tag_docs, 1):
                try:
                    row = transform_tag_doc(doc)
                    res = upsert_tag(cur, row)
                    if res.inserted:
                        tags_inserted += 1
                    else:
                        tags_updated += 1
                except Exception as ex:
                    tags_errors += 1
                    doc_id = doc.get("Id") or f"index_{idx}"
                    if tags_errors <= 5:
                        print(f"[!] Error migrating tag doc {doc_id}: {ex}")

                if idx % 500 == 0 or idx == len(tag_docs):
                    conn.commit()
                    print(f"    - Processed tags: {idx}/{len(tag_docs)}")

            conn.commit()
            print(f"[+] Tags migration complete. Inserted: {tags_inserted}, Updated: {tags_updated}, Errors: {tags_errors}")

            # 5. Migrate Assessments & Children
            print(f"\n[*] Migrating {len(assessment_docs)} Assessment document(s)...")
            ass_inserted = 0
            ass_updated = 0
            ass_errors = 0
            for idx, doc in enumerate(assessment_docs, 1):
                try:
                    main_row, sections_list, tags_list = transform_assessment_doc(doc)
                    res = upsert_assessment_and_children(cur, doc, main_row, sections_list, tags_list)
                    if res.inserted:
                        ass_inserted += 1
                    else:
                        ass_updated += 1
                except Exception as ex:
                    ass_errors += 1
                    doc_id = doc.get("Id") or f"index_{idx}"
                    if ass_errors <= 5:
                        print(f"[!] Error migrating assessment doc {doc_id}: {ex}")

                if idx % 500 == 0 or idx == len(assessment_docs):
                    conn.commit()
                    print(f"    - Processed assessments: {idx}/{len(assessment_docs)}")

            conn.commit()
            print(f"[+] Assessments migration complete. Inserted: {ass_inserted}, Updated: {ass_updated}, Errors: {ass_errors}")

            # 6. Verification counts
            cur.execute("SELECT COUNT(*) FROM assessment_tag")
            total_tags_pg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM assessment")
            total_ass_pg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM assessment_section")
            total_sections_pg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM assessment_question")
            total_questions_pg = cur.fetchone()[0]

            print("\n" + "=" * 70)
            print("Migration Summary: Assessments & AssessmentTags")
            print("=" * 70)
            print(f"[+] Total RavenDB AssessmentTags: {len(tag_docs)}")
            print(f"[+] Total Rows in 'assessment_tag':     {total_tags_pg}")
            print(f"[+] Total RavenDB Assessments:        {len(assessment_docs)}")
            print(f"[+] Total Rows in 'assessment':         {total_ass_pg}")
            print(f"[+] Total Sections Created:             {total_sections_pg}")
            print(f"[+] Total Questions Created:            {total_questions_pg}")
            print("=" * 70)

            # 7. Write Summary JSON
            if cfg.write_summary_json and cfg.summary_json_path:
                summary_data = {
                    "module": "assessments",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "assessment_tags": {
                        "source_count": len(tag_docs),
                        "inserted": tags_inserted,
                        "updated": tags_updated,
                        "errors": tags_errors,
                        "total_pg_records": total_tags_pg,
                    },
                    "assessments": {
                        "source_count": len(assessment_docs),
                        "inserted": ass_inserted,
                        "updated": ass_updated,
                        "errors": ass_errors,
                        "total_pg_records": total_ass_pg,
                        "total_sections": total_sections_pg,
                        "total_questions": total_questions_pg,
                    },
                }
                summary_file = Path(cfg.summary_json_path)
                summary_file.parent.mkdir(parents=True, exist_ok=True)
                summary_file.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
                print(f"[+] Summary written to: {summary_file.resolve()}")

    except Exception as ex:
        conn.rollback()
        print(f"[!] Fatal error during migration: {ex}")
        conn.close()
        sys.exit(1)
    finally:
        conn.close()

    total_errors = tags_errors + ass_errors
    if total_errors > 0:
        print(f"[!] Completed with {total_errors} error(s).")
        sys.exit(1)
    else:
        print("[+] Assessments and AssessmentTags migration completed successfully with 0 errors.")
        sys.exit(0)


if __name__ == "__main__":
    main()
