#!/usr/bin/env python3
"""
Extract Artefacts and ArtefactTags data from RavenDB,
transform it to PostgreSQL schema, and load into PostgreSQL.

Handles:
- artefact_tag (ArtefactTags collection)
- artefact (Artefacts collection)
- Child/mapping tables:
    - artefact_tag_mapping
    - artefact_change_set
    - artefact_comment
    - artefact_video_link
    - artefact_data_attribute
    - artefact_public_url
    - artefact_thumbnail
- Backward-compatible views: artefacts, artefact_tags

Before running: set required configuration in .env or pass CLI arguments.
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

# ArtefactStatusEnum: Unknown=0, Active=1, Etl=60, Published=70,
# PublishedToPublic=75, Uploaded=80, Downloaded=90, Disabled=99
ARTEFACT_STATUS_MAP: Dict[str, int] = {
    "unknown": 0,
    "active": 1,
    "etl": 60,
    "published": 70,
    "publishedtopublic": 75,
    "published_to_public": 75,
    "uploaded": 80,
    "downloaded": 90,
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

# VideoTypeEnum: Record=10, Drive=20, Stream=30
VIDEO_TYPE_MAP: Dict[str, int] = {
    "record": 10,
    "recording": 10,
    "drive": 20,
    "googledrive": 20,
    "stream": 30,
    "streaming": 30,
    "live": 30,
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
    artefacts_collection: str
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
        description="Migrate Artefacts and ArtefactTags data from RavenDB to PostgreSQL"
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
        "--artefacts-collection",
        default=os.getenv("ARTEFACTS_COLLECTION", "Artefacts"),
        help="RavenDB collection name for artefacts (default: Artefacts)",
    )
    parser.add_argument(
        "--tags-collection",
        default=os.getenv("ARTEFACT_TAGS_COLLECTION", "ArtefactTags"),
        help="RavenDB collection name for artefact tags (default: ArtefactTags)",
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
            "ARTEFACTS_SUMMARY_JSON_PATH",
            os.path.join(script_dir, "..", "validation", "artefacts_migration_summary.json"),
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
        artefacts_collection=args.artefacts_collection,
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
    """Parse timestamp to ISO UTC string compatible with PostgreSQL TIMESTAMPTZ."""
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


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


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


def parse_artefact_status(value: Any) -> int:
    """
    Map ArtefactStatusEnum to int:
    Unknown=0, Active=1, Etl=60, Published=70, PublishedToPublic=75,
    Uploaded=80, Downloaded=90, Disabled=99
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
    return ARTEFACT_STATUS_MAP.get(text, 0)


def parse_tag_status(value: Any) -> int:
    """
    Map TagStatusEnum to int:
    Unknown=0, Active=1, Disabled=99
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


def parse_video_type(value: Any) -> int:
    """
    Map VideoTypeEnum to int:
    Record=10, Drive=20, Stream=30
    """
    if value is None:
        return 10
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 10
    if text.isdigit():
        return int(text)
    return VIDEO_TYPE_MAP.get(text, 10)


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
    """Create all required artefact and artefact_tag tables and indexes."""
    cur.execute(
        """
        -- 1. ArtefactTag Table
        CREATE TABLE IF NOT EXISTS artefact_tag (
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

        -- 2. Artefact Main Table
        CREATE TABLE IF NOT EXISTS artefact (
            id UUID PRIMARY KEY,
            url VARCHAR(1000),
            title VARCHAR(250),
            description TEXT,
            metadata JSONB,
            mime_type VARCHAR(100),
            file_name VARCHAR(255),
            file_size DOUBLE PRECISION,
            status INTEGER,
            sha1 VARCHAR(40),
            model TEXT,
            template TEXT,
            csv TEXT,
            published_on TIMESTAMPTZ,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID,
            tags TEXT[],
            change_set JSONB,
            comments JSONB,
            video_links JSONB,
            data_attributes JSONB,
            public_urls TEXT[],
            thumbnails TEXT[]
        );

        -- 3. ArtefactTags Mapping Table
        CREATE TABLE IF NOT EXISTS artefact_tag_mapping (
            artefact_id UUID NOT NULL REFERENCES artefact(id) ON DELETE CASCADE,
            tag_id UUID NOT NULL,
            PRIMARY KEY (artefact_id, tag_id)
        );

        -- 4. ArtefactChangeSet Table
        CREATE TABLE IF NOT EXISTS artefact_change_set (
            id BIGSERIAL PRIMARY KEY,
            artefact_id UUID NOT NULL REFERENCES artefact(id) ON DELETE CASCADE,
            "by" VARCHAR(100),
            "on" TIMESTAMPTZ,
            ref VARCHAR(500)
        );

        -- 5. ArtefactComments Table
        CREATE TABLE IF NOT EXISTS artefact_comment (
            id BIGSERIAL PRIMARY KEY,
            artefact_id UUID NOT NULL REFERENCES artefact(id) ON DELETE CASCADE,
            "by" VARCHAR(100),
            timestamp TIMESTAMPTZ,
            item_id BIGINT,
            text TEXT,
            html TEXT
        );

        -- 6. ArtefactVideoLinks Table
        CREATE TABLE IF NOT EXISTS artefact_video_link (
            id BIGSERIAL PRIMARY KEY,
            artefact_id UUID NOT NULL REFERENCES artefact(id) ON DELETE CASCADE,
            type INTEGER,
            url VARCHAR(1000),
            item_id BIGINT
        );

        -- 7. ArtefactDataAttributes Table
        CREATE TABLE IF NOT EXISTS artefact_data_attribute (
            id BIGSERIAL PRIMARY KEY,
            artefact_id UUID NOT NULL REFERENCES artefact(id) ON DELETE CASCADE,
            item_id BIGINT,
            attributes_json JSONB
        );

        -- 8. PublicUrls Table
        CREATE TABLE IF NOT EXISTS artefact_public_url (
            id BIGSERIAL PRIMARY KEY,
            artefact_id UUID NOT NULL REFERENCES artefact(id) ON DELETE CASCADE,
            url VARCHAR(1000)
        );

        -- 9. Thumbnails Table
        CREATE TABLE IF NOT EXISTS artefact_thumbnail (
            id BIGSERIAL PRIMARY KEY,
            artefact_id UUID NOT NULL REFERENCES artefact(id) ON DELETE CASCADE,
            url VARCHAR(1000)
        );

        -- Indexes for query performance
        CREATE INDEX IF NOT EXISTS idx_artefact_tag_name ON artefact_tag (name);
        CREATE INDEX IF NOT EXISTS idx_artefact_tag_status ON artefact_tag (status);
        CREATE INDEX IF NOT EXISTS idx_artefact_status ON artefact (status);
        CREATE INDEX IF NOT EXISTS idx_artefact_owner_id ON artefact (owner_id);
        CREATE INDEX IF NOT EXISTS idx_artefact_published_on ON artefact (published_on);
        CREATE INDEX IF NOT EXISTS idx_artefact_tag_map_tag ON artefact_tag_mapping (tag_id);

        -- Backward compatible views
        CREATE OR REPLACE VIEW artefacts AS SELECT * FROM artefact;
        CREATE OR REPLACE VIEW artefact_tags AS SELECT * FROM artefact_tag;
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    """Validate that core tables and columns exist."""
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_name IN ('artefact', 'artefact_tag')
        """
    )
    existing = {(row[0], row[1].lower()) for row in cur.fetchall()}

    req_artefact = {
        "id", "url", "title", "description", "metadata", "mime_type",
        "file_name", "file_size", "status", "sha1", "model", "template",
        "csv", "published_on", "owner_id", "parent_id", "created_on",
        "created_by", "modified_on", "modified_by"
    }
    req_tag = {
        "id", "name", "predefined", "csn", "meta", "status",
        "owner_id", "parent_id", "created_on", "created_by",
        "modified_on", "modified_by"
    }

    missing_artefact = {col for col in req_artefact if ("artefact", col) not in existing}
    missing_tag = {col for col in req_tag if ("artefact_tag", col) not in existing}

    if missing_artefact or missing_tag:
        raise RuntimeError(
            f"Schema verification failed! Missing artefact cols: {missing_artefact}, missing tag cols: {missing_tag}"
        )


# -----------------------------------------------------------------------------
# Transform & Upsert: ArtefactTag
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
    cur.execute("SELECT 1 FROM artefact_tag WHERE id = %s", (tag_id,))
    is_new = cur.fetchone() is None

    cur.execute(
        """
        INSERT INTO artefact_tag (
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
# Transform & Upsert: Artefact and Child Records
# -----------------------------------------------------------------------------

def transform_artefact_doc(doc: Dict[str, Any]) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
    artefact_id = derive_doc_id(doc, "ArtefactId")
    if not artefact_id:
        raise ValueError(f"Artefact doc missing valid GUID: {doc.get('Id')}")

    url = as_text(doc.get("Url"))
    url = url[:1000] if url else None
    title = as_text(doc.get("Title"))
    title = title[:250] if title else None
    description = as_text(doc.get("Description"))
    metadata = as_json(first_non_empty(doc.get("MetaData"), doc.get("Metadata")))
    mime_type = as_text(doc.get("MimeType"))
    mime_type = mime_type[:100] if mime_type else None
    file_name = as_text(doc.get("FileName"))
    file_name = file_name[:255] if file_name else None
    file_size = parse_float(doc.get("FileSize"))
    status = parse_artefact_status(doc.get("Status"))
    sha1 = as_text(doc.get("SHA1"))
    sha1 = sha1[:40] if sha1 else None
    model = as_text(doc.get("Model"))
    template = as_text(doc.get("Template"))
    csv = as_text(doc.get("Csv"))
    published_on = parse_ts(doc.get("PublishedOn"))
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))
    parent_id = extract_uuid_from_any(doc.get("ParentId"))
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))
    modified_on = parse_ts(doc.get("ModifiedOn"))
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

    # Child collections in document
    tags_raw = doc.get("Tags") or []
    tags_list = [str(t) for t in tags_raw if t] if isinstance(tags_raw, list) else []

    change_set_raw = doc.get("ChangeSet") or doc.get("ChangeSets") or []
    comments_raw = doc.get("Comments") or []
    video_links_raw = doc.get("VideoLinks") or []
    data_attrs_raw = doc.get("DataAttributes") or []
    public_urls_raw = doc.get("PublicUrls") or []
    thumbnails_raw = doc.get("Thumbnails") or []

    main_row = (
        artefact_id,
        url,
        title,
        description,
        metadata,
        mime_type,
        file_name,
        file_size,
        status,
        sha1,
        model,
        template,
        csv,
        published_on,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
        tags_list,
        as_json(change_set_raw),
        as_json(comments_raw),
        as_json(video_links_raw),
        as_json(data_attrs_raw),
        [str(u) for u in public_urls_raw] if isinstance(public_urls_raw, list) else [],
        [str(u) for u in thumbnails_raw] if isinstance(thumbnails_raw, list) else [],
    )

    child_data = {
        "tags": tags_list,
        "change_sets": change_set_raw if isinstance(change_set_raw, list) else [],
        "comments": comments_raw if isinstance(comments_raw, list) else [],
        "video_links": video_links_raw if isinstance(video_links_raw, list) else [],
        "data_attributes": data_attrs_raw if isinstance(data_attrs_raw, list) else [],
        "public_urls": public_urls_raw if isinstance(public_urls_raw, list) else [],
        "thumbnails": thumbnails_raw if isinstance(thumbnails_raw, list) else [],
    }

    return main_row, child_data


def upsert_artefact_and_children(
    cur: psycopg2.extensions.cursor,
    main_row: Tuple[Any, ...],
    child_data: Dict[str, Any],
) -> UpsertResult:
    artefact_id = main_row[0]

    cur.execute("SELECT 1 FROM artefact WHERE id = %s", (artefact_id,))
    is_new = cur.fetchone() is None

    # 1. Upsert main artefact row
    cur.execute(
        """
        INSERT INTO artefact (
            id, url, title, description, metadata, mime_type, file_name, file_size,
            status, sha1, model, template, csv, published_on, owner_id, parent_id,
            created_on, created_by, modified_on, modified_by,
            tags, change_set, comments, video_links, data_attributes, public_urls, thumbnails
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id)
        DO UPDATE SET
            url = EXCLUDED.url,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            metadata = EXCLUDED.metadata,
            mime_type = EXCLUDED.mime_type,
            file_name = EXCLUDED.file_name,
            file_size = EXCLUDED.file_size,
            status = EXCLUDED.status,
            sha1 = EXCLUDED.sha1,
            model = EXCLUDED.model,
            template = EXCLUDED.template,
            csv = EXCLUDED.csv,
            published_on = EXCLUDED.published_on,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by,
            tags = EXCLUDED.tags,
            change_set = EXCLUDED.change_set,
            comments = EXCLUDED.comments,
            video_links = EXCLUDED.video_links,
            data_attributes = EXCLUDED.data_attributes,
            public_urls = EXCLUDED.public_urls,
            thumbnails = EXCLUDED.thumbnails
        RETURNING id;
        """,
        main_row,
    )

    # 2. Sync child tables (clear existing child records for this artefact)
    cur.execute("DELETE FROM artefact_tag_mapping WHERE artefact_id = %s", (artefact_id,))
    cur.execute("DELETE FROM artefact_change_set WHERE artefact_id = %s", (artefact_id,))
    cur.execute("DELETE FROM artefact_comment WHERE artefact_id = %s", (artefact_id,))
    cur.execute("DELETE FROM artefact_video_link WHERE artefact_id = %s", (artefact_id,))
    cur.execute("DELETE FROM artefact_data_attribute WHERE artefact_id = %s", (artefact_id,))
    cur.execute("DELETE FROM artefact_public_url WHERE artefact_id = %s", (artefact_id,))
    cur.execute("DELETE FROM artefact_thumbnail WHERE artefact_id = %s", (artefact_id,))

    # Insert ArtefactTags Mapping
    for tag in child_data.get("tags", []):
        tag_uuid = extract_uuid_from_any(tag)
        if tag_uuid:
            cur.execute(
                """
                INSERT INTO artefact_tag_mapping (artefact_id, tag_id)
                VALUES (%s, %s)
                ON CONFLICT (artefact_id, tag_id) DO NOTHING
                """,
                (artefact_id, tag_uuid),
            )

    # Insert ChangeSets
    for cs in child_data.get("change_sets", []):
        if isinstance(cs, dict):
            by_val = as_text(cs.get("By"))[:100] if cs.get("By") else None
            on_val = parse_ts(cs.get("On") or cs.get("TimeStamp") or cs.get("Date"))
            ref_val = as_text(cs.get("Ref") or cs.get("Reference"))[:500] if cs.get("Ref") else None
            cur.execute(
                """
                INSERT INTO artefact_change_set (artefact_id, "by", "on", ref)
                VALUES (%s, %s, %s, %s)
                """,
                (artefact_id, by_val, on_val, ref_val),
            )

    # Insert Comments
    for cm in child_data.get("comments", []):
        if isinstance(cm, dict):
            by_val = as_text(cm.get("By"))[:100] if cm.get("By") else None
            ts_val = parse_ts(cm.get("TimeStamp") or cm.get("Date"))
            item_id = parse_int(cm.get("ItemId") or cm.get("Id")) or 0
            text_val = as_text(cm.get("Text"))
            html_val = as_text(cm.get("Html") or cm.get("HTML"))
            cur.execute(
                """
                INSERT INTO artefact_comment (artefact_id, "by", timestamp, item_id, text, html)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (artefact_id, by_val, ts_val, item_id, text_val, html_val),
            )

    # Insert VideoLinks
    for vl in child_data.get("video_links", []):
        if isinstance(vl, dict):
            v_type = parse_video_type(vl.get("Type"))
            v_url = as_text(vl.get("Url"))[:1000] if vl.get("Url") else None
            item_id = parse_int(vl.get("ItemId") or vl.get("Id")) or 0
            cur.execute(
                """
                INSERT INTO artefact_video_link (artefact_id, type, url, item_id)
                VALUES (%s, %s, %s, %s)
                """,
                (artefact_id, v_type, v_url, item_id),
            )

    # Insert DataAttributes
    for da in child_data.get("data_attributes", []):
        if isinstance(da, dict):
            item_id = parse_int(da.get("ItemId") or da.get("Id")) or 0
            attrs_json = as_json(da.get("AttributesJson") or da.get("Attributes") or da)
            cur.execute(
                """
                INSERT INTO artefact_data_attribute (artefact_id, item_id, attributes_json)
                VALUES (%s, %s, %s)
                """,
                (artefact_id, item_id, attrs_json),
            )

    # Insert PublicUrls
    for pu in child_data.get("public_urls", []):
        p_url = as_text(pu)[:1000] if pu else None
        if p_url:
            cur.execute(
                """
                INSERT INTO artefact_public_url (artefact_id, url)
                VALUES (%s, %s)
                """,
                (artefact_id, p_url),
            )

    # Insert Thumbnails
    for tn in child_data.get("thumbnails", []):
        t_url = as_text(tn)[:1000] if tn else None
        if t_url:
            cur.execute(
                """
                INSERT INTO artefact_thumbnail (artefact_id, url)
                VALUES (%s, %s)
                """,
                (artefact_id, t_url),
            )

    return UpsertResult(record_id=str(artefact_id), inserted=is_new)


# -----------------------------------------------------------------------------
# Main Orchestrator
# -----------------------------------------------------------------------------

def main() -> None:
    cfg = parse_args()

    print("=" * 70)
    print("CT-RPG: RavenDB to PostgreSQL Migration — Artefacts & Tags Module")
    print("=" * 70)
    print(f"[*] RavenDB URL:     {cfg.raven_url}")
    print(f"[*] RavenDB DB:      {cfg.raven_db}")
    print(f"[*] Tags Col:        {cfg.tags_collection}")
    print(f"[*] Artefacts Col:   {cfg.artefacts_collection}")
    print(f"[*] PostgreSQL Host: {cfg.pg_host}:{cfg.pg_port}")
    print(f"[*] PostgreSQL DB:   {cfg.pg_db} (User: {cfg.pg_user})")
    print("=" * 70)

    session = requests.Session()
    configure_raven_session(session, cfg)

    # 1. Fetch ArtefactTags
    tag_docs: List[Dict[str, Any]] = []
    try:
        tag_docs = raven_query_collection(session, cfg, cfg.tags_collection)
    except requests.HTTPError as ex:
        if cfg.tags_collection == "ArtefactTags":
            print("[!] Collection 'ArtefactTags' error. Trying fallback 'ArtefactTag'...")
            try:
                tag_docs = raven_query_collection(session, cfg, "ArtefactTag")
            except Exception:
                pass
        else:
            raise ex

    if not tag_docs and cfg.tags_collection == "ArtefactTags":
        try:
            tag_docs = raven_query_collection(session, cfg, "ArtefactTag")
        except Exception:
            pass

    # 2. Fetch Artefacts
    artefact_docs: List[Dict[str, Any]] = []
    try:
        artefact_docs = raven_query_collection(session, cfg, cfg.artefacts_collection)
    except requests.HTTPError as ex:
        if cfg.artefacts_collection == "Artefacts":
            print("[!] Collection 'Artefacts' error. Trying fallback 'Artefact'...")
            try:
                artefact_docs = raven_query_collection(session, cfg, "Artefact")
            except Exception:
                pass
        else:
            raise ex

    if not artefact_docs and cfg.artefacts_collection == "Artefacts":
        try:
            artefact_docs = raven_query_collection(session, cfg, "Artefact")
        except Exception:
            pass

    print(f"\n[+] Loaded {len(tag_docs)} ArtefactTag(s) and {len(artefact_docs)} Artefact(s) from RavenDB.")

    if cfg.inspect_source_only:
        print("\n[*] Inspect source only specified.")
        if tag_docs:
            print("[*] Sample ArtefactTag keys:", list(tag_docs[0].keys()))
        if artefact_docs:
            print("[*] Sample Artefact keys:", list(artefact_docs[0].keys()))
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

            # 4. Migrate ArtefactTags
            print(f"\n[*] Migrating {len(tag_docs)} ArtefactTag document(s)...")
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

            # 5. Migrate Artefacts & Children
            print(f"\n[*] Migrating {len(artefact_docs)} Artefact document(s)...")
            art_inserted = 0
            art_updated = 0
            art_errors = 0
            for idx, doc in enumerate(artefact_docs, 1):
                try:
                    main_row, child_data = transform_artefact_doc(doc)
                    res = upsert_artefact_and_children(cur, main_row, child_data)
                    if res.inserted:
                        art_inserted += 1
                    else:
                        art_updated += 1
                except Exception as ex:
                    art_errors += 1
                    doc_id = doc.get("Id") or f"index_{idx}"
                    if art_errors <= 5:
                        print(f"[!] Error migrating artefact doc {doc_id}: {ex}")

                if idx % 500 == 0 or idx == len(artefact_docs):
                    conn.commit()
                    print(f"    - Processed artefacts: {idx}/{len(artefact_docs)}")

            conn.commit()
            print(f"[+] Artefacts migration complete. Inserted: {art_inserted}, Updated: {art_updated}, Errors: {art_errors}")

            # 6. Verification counts
            cur.execute("SELECT COUNT(*) FROM artefact_tag")
            total_tags_pg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM artefact")
            total_art_pg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM artefact_tag_mapping")
            total_tag_maps = cur.fetchone()[0]

            print("\n" + "=" * 70)
            print("Migration Summary: Artefacts & ArtefactTags")
            print("=" * 70)
            print(f"[+] Total RavenDB ArtefactTags: {len(tag_docs)}")
            print(f"[+] Total Rows in 'artefact_tag':  {total_tags_pg}")
            print(f"[+] Total RavenDB Artefacts:     {len(artefact_docs)}")
            print(f"[+] Total Rows in 'artefact':      {total_art_pg}")
            print(f"[+] Tag Mappings Created:          {total_tag_maps}")
            print("=" * 70)

            # 7. Write Summary JSON
            if cfg.write_summary_json and cfg.summary_json_path:
                summary_data = {
                    "module": "artefacts",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "artefact_tags": {
                        "source_count": len(tag_docs),
                        "inserted": tags_inserted,
                        "updated": tags_updated,
                        "errors": tags_errors,
                        "total_pg_records": total_tags_pg,
                    },
                    "artefacts": {
                        "source_count": len(artefact_docs),
                        "inserted": art_inserted,
                        "updated": art_updated,
                        "errors": art_errors,
                        "total_pg_records": total_art_pg,
                        "tag_mappings_created": total_tag_maps,
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

    total_errors = tags_errors + art_errors
    if total_errors > 0:
        print(f"[!] Completed with {total_errors} error(s).")
        sys.exit(1)
    else:
        print("[+] Artefacts and ArtefactTags migration completed successfully with 0 errors.")
        sys.exit(0)


if __name__ == "__main__":
    main()
