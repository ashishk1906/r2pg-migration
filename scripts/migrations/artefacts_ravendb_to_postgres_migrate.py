#!/usr/bin/env python3
"""
Extract Artefacts and ArtefactTags data from RavenDB,
transform it to PostgreSQL schema with native PostgreSQL ENUMs and JSONBs,
and load into local PostgreSQL.

Target tables:
- artefact_tags
- artefacts
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
    artefacts_collection: str
    tags_collection: str
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
    for env_path in (
        os.path.join(script_dir, "..", "..", ".env"),
        os.path.join(script_dir, "..", ".env"),
        os.path.join(script_dir, ".env"),
    ):
        if os.path.exists(env_path):
            load_env_file(env_path)
            break

    parser = argparse.ArgumentParser(
        description="Migrate Artefacts and ArtefactTags from RavenDB to PostgreSQL"
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
        "--artefacts-collection",
        default=os.getenv("ARTEFACTS_COLLECTION", "Artefacts"),
    )
    parser.add_argument(
        "--tags-collection",
        default=os.getenv("ARTEFACT_TAGS_COLLECTION", "ArtefactTags"),
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
            for cert_dir in (
                os.path.join(script_dir, ".."),
                os.path.join(script_dir, "..", ".."),
                script_dir,
            ):
                cand = os.path.join(cert_dir, args.raven_cert_file)
                if os.path.isfile(cand):
                    args.raven_cert_file = cand
                    break
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
        artefacts_collection=args.artefacts_collection,
        tags_collection=args.tags_collection,
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


def clean_bool(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "1", "yes"}


def clean_decimal(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val).strip().replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
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

# TagStatusEnum: Unknown = 0, Active = 1, Disabled = 99
TAG_STATUS_MAP: Dict[Any, str] = {
    0: "Unknown",
    1: "Active",
    99: "Disabled",
    "unknown": "Unknown",
    "active": "Active",
    "disabled": "Disabled",
}


def map_tag_status(val: Any) -> str:
    if val is None:
        return "Active"
    if isinstance(val, int):
        return TAG_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return TAG_STATUS_MAP.get(int(s), "Active")
    return TAG_STATUS_MAP.get(s.lower(), "Active")


# ArtefactStatusEnum: Unknown=0, Active=1, Etl=60, Published=70, PublishedToPublic=75, Uploaded=80, Downloaded=90, Disabled=99
ARTEFACT_STATUS_MAP: Dict[Any, str] = {
    0: "Unknown",
    1: "Active",
    60: "Etl",
    70: "Published",
    75: "PublishedToPublic",
    80: "Uploaded",
    90: "Downloaded",
    99: "Disabled",
    "unknown": "Unknown",
    "active": "Active",
    "etl": "Etl",
    "published": "Published",
    "publishedtopublic": "PublishedToPublic",
    "published_to_public": "PublishedToPublic",
    "uploaded": "Uploaded",
    "downloaded": "Downloaded",
    "disabled": "Disabled",
}


def map_artefact_status(val: Any) -> str:
    if val is None:
        return "Active"
    if isinstance(val, int):
        return ARTEFACT_STATUS_MAP.get(val, "Active")
    s = str(val).strip()
    if s.isdigit():
        return ARTEFACT_STATUS_MAP.get(int(s), "Active")
    norm = s.lower().replace(" ", "").replace("_", "")
    return ARTEFACT_STATUS_MAP.get(norm, "Active")


# -----------------------------------------------------------------------------
# Document Field Extractors
# -----------------------------------------------------------------------------


def extract_tag_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform all fields for artefact_tags table."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    tag_id = clean_uuid(raw_id)
    if not tag_id:
        raise ValueError(f"ArtefactTag missing valid UUID: {raw_id}")

    name = clean_str(doc.get("Name"), 150)
    predefined = clean_bool(doc.get("Predefined"))
    csn = clean_str(doc.get("CSN"), 100)
    meta = as_json(doc.get("Meta") or {})
    status = map_tag_status(doc.get("Status"))

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


def extract_artefact_fields(doc: Dict[str, Any]) -> Tuple:
    """Extract and transform all fields for artefacts table using JSONBs and TEXT[]."""
    metadata = doc.get("@metadata") or {}
    raw_id = metadata.get("@id") or doc.get("Id") or doc.get("id")
    art_id = clean_uuid(raw_id)
    if not art_id:
        raise ValueError(f"Artefact missing valid UUID: {raw_id}")

    url = clean_str(doc.get("Url"))
    title = clean_str(doc.get("Title"), 250)
    description = clean_str(doc.get("Description"))
    meta_data = as_json(doc.get("MetaData") or {})

    tags = clean_string_list(doc.get("Tags"))

    mime_type = clean_str(doc.get("MimeType"), 100)
    file_name = clean_str(doc.get("FileName"), 250)
    raw_fs = doc.get("FileSize")
    file_size = float(raw_fs) if raw_fs is not None else None
    status = map_artefact_status(doc.get("Status"))
    sha1 = clean_str(doc.get("SHA1"), 100)

    model = clean_str(doc.get("Model"))
    template = clean_str(doc.get("Template"))
    csv_val = clean_str(doc.get("Csv"))

    change_set = as_json(doc.get("ChangeSet") if isinstance(doc.get("ChangeSet"), list) else [])
    comments = as_json(doc.get("Comments") if isinstance(doc.get("Comments"), list) else [])
    video_links = as_json(doc.get("VideoLinks") if isinstance(doc.get("VideoLinks"), list) else [])
    data_attributes = as_json(doc.get("DataAttributes") if isinstance(doc.get("DataAttributes"), list) else [])

    published_on = parse_iso_timestamp(doc.get("PublishedOn"))
    public_urls = clean_string_list(doc.get("PublicUrls"))
    thumbnails = clean_string_list(doc.get("Thumbnails"))

    owner_id = clean_uuid(doc.get("OwnerId"))
    parent_id = clean_uuid(doc.get("ParentId"))
    created_on = parse_iso_timestamp(
        doc.get("CreatedOn") or metadata.get("@last-modified")
    ) or datetime.now(timezone.utc)
    created_by = clean_uuid(doc.get("CreatedBy"))
    modified_on = parse_iso_timestamp(doc.get("ModifiedOn"))
    modified_by = clean_uuid(doc.get("ModifiedBy"))

    return (
        art_id,
        url,
        title,
        description,
        meta_data,
        tags,
        mime_type,
        file_name,
        file_size,
        status,
        sha1,
        model,
        template,
        csv_val,
        change_set,
        comments,
        video_links,
        data_attributes,
        published_on,
        public_urls,
        thumbnails,
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
    """Create target enums, artefact_tags and artefacts tables."""
    cur.execute(
        """
        -- 1. Create Enums
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tag_status_enum') THEN
                CREATE TYPE tag_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Disabled'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'artefact_status_enum') THEN
                CREATE TYPE artefact_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Etl',
                    'Published',
                    'PublishedToPublic',
                    'Uploaded',
                    'Downloaded',
                    'Disabled'
                );
            END IF;
        END $$;

        -- 2. ArtefactTags Table
        CREATE TABLE IF NOT EXISTS artefact_tags (
            id UUID PRIMARY KEY,
            name VARCHAR(150),
            predefined BOOLEAN DEFAULT FALSE,
            csn VARCHAR(100),
            meta JSONB DEFAULT '{}'::jsonb,
            status tag_status_enum NOT NULL DEFAULT 'Active',
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ NOT NULL,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );

        -- 3. Artefacts Table
        CREATE TABLE IF NOT EXISTS artefacts (
            id UUID PRIMARY KEY,
            url TEXT,
            title VARCHAR(250),
            description TEXT,
            meta_data JSONB DEFAULT '{}'::jsonb,
            tags TEXT[] DEFAULT '{}'::text[],
            mime_type VARCHAR(100),
            file_name VARCHAR(250),
            file_size DOUBLE PRECISION,
            status artefact_status_enum NOT NULL DEFAULT 'Active',
            sha1 VARCHAR(100),
            model TEXT,
            template TEXT,
            csv TEXT,
            change_set JSONB DEFAULT '[]'::jsonb,
            comments JSONB DEFAULT '[]'::jsonb,
            video_links JSONB DEFAULT '[]'::jsonb,
            data_attributes JSONB DEFAULT '[]'::jsonb,
            published_on TIMESTAMPTZ,
            public_urls TEXT[] DEFAULT '{}'::text[],
            thumbnails TEXT[] DEFAULT '{}'::text[],
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


def upsert_tag(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> UpsertResult:
    """Idempotently upsert an ArtefactTag."""
    fields = extract_tag_fields(doc)
    sql = """
        INSERT INTO artefact_tags (
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


def upsert_artefact(cur: psycopg2.extensions.cursor, doc: Dict[str, Any]) -> UpsertResult:
    """Idempotently upsert an Artefact."""
    fields = extract_artefact_fields(doc)
    sql = """
        INSERT INTO artefacts (
            id, url, title, description, meta_data, tags, mime_type, file_name, file_size,
            status, sha1, model, template, csv, change_set, comments, video_links,
            data_attributes, published_on, public_urls, thumbnails,
            owner_id, parent_id, created_on, created_by, modified_on, modified_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            url = EXCLUDED.url,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            meta_data = EXCLUDED.meta_data,
            tags = EXCLUDED.tags,
            mime_type = EXCLUDED.mime_type,
            file_name = EXCLUDED.file_name,
            file_size = EXCLUDED.file_size,
            status = EXCLUDED.status,
            sha1 = EXCLUDED.sha1,
            model = EXCLUDED.model,
            template = EXCLUDED.template,
            csv = EXCLUDED.csv,
            change_set = EXCLUDED.change_set,
            comments = EXCLUDED.comments,
            video_links = EXCLUDED.video_links,
            data_attributes = EXCLUDED.data_attributes,
            published_on = EXCLUDED.published_on,
            public_urls = EXCLUDED.public_urls,
            thumbnails = EXCLUDED.thumbnails,
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
    """Run the end-to-end migration for artefact tags and artefacts."""
    cfg = parse_args()

    requests_session = requests.Session()
    conn = None
    try:
        configure_raven_session(requests_session, cfg)

        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, "
            f"collections=({cfg.tags_collection}, {cfg.artefacts_collection})"
        )
        print("[1/5] Fetching RavenDB documents...")
        tag_docs = raven_query_collection(
            requests_session, cfg, cfg.tags_collection
        )
        art_docs = raven_query_collection(
            requests_session, cfg, cfg.artefacts_collection
        )
        print(
            f"Fetched artefact_tags={len(tag_docs)}, artefacts={len(art_docs)}"
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

        loaded_tags = 0
        new_tags = 0
        loaded_arts = 0
        new_arts = 0

        with conn:
            with conn.cursor() as cur:
                print("[3/5] Ensuring target schema...")
                ensure_target_schema(cur)

                print("[4/5] Upserting artefact tags...")
                for d in tag_docs:
                    res = upsert_tag(cur, d)
                    loaded_tags += 1
                    new_tags += int(res.inserted)

                print("[5/5] Upserting artefacts...")
                for d in art_docs:
                    res = upsert_artefact(cur, d)
                    loaded_arts += 1
                    new_arts += int(res.inserted)

        # Post-load verification counts
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM artefact_tags")
            total_tags = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM artefacts")
            total_artefacts = int(cur.fetchone()[0])

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "tags_collection": cfg.tags_collection,
                "artefacts_collection": cfg.artefacts_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "tags_processed": loaded_tags,
                "new_tags_inserted": new_tags,
                "artefacts_processed": loaded_arts,
                "new_artefacts_inserted": new_arts,
            },
            "post_load_counts": {
                "artefact_tags": total_tags,
                "artefacts": total_artefacts,
            },
        }

        print("Migration completed.")
        print(f"artefacts_tags_processed: {loaded_tags}")
        print(f"new_artefacts_tags_inserted: {new_tags}")
        print(f"artefacts_processed: {loaded_arts}")
        print(f"new_artefacts_inserted: {new_arts}")

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
