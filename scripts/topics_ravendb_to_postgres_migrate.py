#!/usr/bin/env python3
"""
Extract Topics data from RavenDB, transform it to PostgreSQL schema,
and load into PostgreSQL.

Handles:
- topic table (Topics collection)
- topic_tag_mapping table (Tags list in topic documents)
- Backward-compatible views: topics, topic_tags

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

# RoleEnum: Admin = 10, Member = 20
ROLE_MAP: Dict[str, int] = {
    "admin": 10,
    "administrator": 10,
    "member": 20,
    "user": 20,
}

# CategoryEnum: PrivateToInstitue = 30, Public = 40
# Note: Code spelling is PrivateToInstitue, support both spellings
CATEGORY_MAP: Dict[str, int] = {
    "privatetoinstitue": 30,
    "privatetoinstitute": 30,
    "private_to_institute": 30,
    "private": 30,
    "public": 40,
}

# AccessEnum: Open = 50, Restricted = 60
ACCESS_MAP: Dict[str, int] = {
    "open": 50,
    "public": 50,
    "restricted": 60,
    "private": 60,
}

# TopicStatusEnum: Unknown = 0, Active = 1, Disabled = 99
TOPIC_STATUS_MAP: Dict[str, int] = {
    "unknown": 0,
    "active": 1,
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
    topics_collection: str
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
        description="Migrate Topics data from RavenDB to PostgreSQL"
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
        "--topics-collection",
        default=os.getenv("TOPICS_COLLECTION", "Topics"),
        help="RavenDB collection name for topics (default: Topics)",
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
            "TOPICS_SUMMARY_JSON_PATH",
            os.path.join(script_dir, "..", "validation", "topics_migration_summary.json"),
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
        topics_collection=args.topics_collection,
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


def parse_role(value: Any) -> Optional[int]:
    """RoleEnum: Admin = 10, Member = 20"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return ROLE_MAP.get(text)


def parse_category(value: Any) -> Optional[int]:
    """CategoryEnum: PrivateToInstitue = 30, Public = 40"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return CATEGORY_MAP.get(text)


def parse_access(value: Any) -> Optional[int]:
    """AccessEnum: Open = 50, Restricted = 60"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return ACCESS_MAP.get(text)


def parse_topic_status(value: Any) -> int:
    """TopicStatusEnum: Unknown = 0, Active = 1, Disabled = 99"""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 0
    if text.isdigit():
        return int(text)
    return TOPIC_STATUS_MAP.get(text, 0)


def derive_topic_id(doc: Dict[str, Any]) -> Optional[str]:
    return first_non_empty(
        extract_uuid_from_any(get_nested(doc, "@metadata", "@id")),
        extract_uuid_from_any(doc.get("TopicId")),
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
    """Create all required topic and topic_tag tables and indexes."""
    cur.execute(
        """
        -- 1. Main Topic Table
        CREATE TABLE IF NOT EXISTS topic (
            id UUID PRIMARY KEY,
            main_topic_id UUID,
            name VARCHAR(150),
            friendly_name VARCHAR(150),
            description TEXT,
            role INTEGER,
            category INTEGER,
            access INTEGER,
            subscriptions JSONB,
            status INTEGER,
            meta JSONB,
            can_unsubscribe BOOLEAN,
            can_publish BOOLEAN,
            is_subscription_allowed BOOLEAN,
            handle VARCHAR(150),
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID,
            tags TEXT[]
        );

        -- 2. Topic Tags Mapping Table
        CREATE TABLE IF NOT EXISTS topic_tag_mapping (
            topic_id UUID NOT NULL REFERENCES topic(id) ON DELETE CASCADE,
            tag_id VARCHAR(100) NOT NULL,
            PRIMARY KEY (topic_id, tag_id)
        );

        -- Indexes for query performance
        CREATE INDEX IF NOT EXISTS idx_topic_name ON topic (name);
        CREATE INDEX IF NOT EXISTS idx_topic_friendly_name ON topic (friendly_name);
        CREATE INDEX IF NOT EXISTS idx_topic_handle ON topic (handle);
        CREATE INDEX IF NOT EXISTS idx_topic_status ON topic (status);
        CREATE INDEX IF NOT EXISTS idx_topic_category ON topic (category);
        CREATE INDEX IF NOT EXISTS idx_topic_role ON topic (role);
        CREATE INDEX IF NOT EXISTS idx_topic_access ON topic (access);
        CREATE INDEX IF NOT EXISTS idx_topic_owner_id ON topic (owner_id);
        CREATE INDEX IF NOT EXISTS idx_topic_main_topic_id ON topic (main_topic_id);
        CREATE INDEX IF NOT EXISTS idx_topic_tag_map_tag ON topic_tag_mapping (tag_id);

        -- Backward compatible views
        CREATE OR REPLACE VIEW topics AS SELECT * FROM topic;
        CREATE OR REPLACE VIEW topic_tags AS SELECT * FROM topic_tag_mapping;
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    """Assert all required columns exist in topic table."""
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'topic'
        """
    )
    existing = {row[0].lower() for row in cur.fetchall()}

    req_cols = {
        "id", "main_topic_id", "name", "friendly_name", "description",
        "role", "category", "access", "subscriptions", "status", "meta",
        "can_unsubscribe", "can_publish", "is_subscription_allowed",
        "handle", "owner_id", "parent_id", "created_on", "created_by",
        "modified_on", "modified_by"
    }

    missing = req_cols - existing
    if missing:
        raise RuntimeError(f"Schema verification failed! Missing columns in 'topic': {sorted(missing)}")


# -----------------------------------------------------------------------------
# Transform & Upsert: Topic
# -----------------------------------------------------------------------------

def transform_topic_doc(doc: Dict[str, Any]) -> Tuple[Tuple[Any, ...], List[str]]:
    topic_id = derive_topic_id(doc)
    if not topic_id:
        raise ValueError(f"Topic doc missing valid GUID: {doc.get('Id')}")

    main_topic_id = extract_uuid_from_any(doc.get("MainTopicId"))
    name = as_text(doc.get("Name"))
    name = name[:150] if name else None
    friendly_name = as_text(doc.get("FriendlyName"))
    friendly_name = friendly_name[:150] if friendly_name else None
    description = as_text(doc.get("Description"))
    role = parse_role(doc.get("Role"))
    category = parse_category(doc.get("Category"))
    access = parse_access(doc.get("Access"))
    subscriptions = as_json(doc.get("Subscriptions"))
    status = parse_topic_status(doc.get("Status"))
    meta = as_json(first_non_empty(doc.get("Meta"), doc.get("MetaData")))
    can_unsubscribe = parse_bool(doc.get("CanUnsubscribe"), default=True)
    can_publish = parse_bool(doc.get("CanPublish"), default=True)
    is_subscription_allowed = parse_bool(doc.get("IsSubscriptionAllowed"), default=True)
    handle = as_text(doc.get("Handle"))
    handle = handle[:150] if handle else None
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))
    parent_id = extract_uuid_from_any(doc.get("ParentId"))
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))
    modified_on = parse_ts(doc.get("ModifiedOn"))
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

    tags_raw = doc.get("Tags") or []
    tags_list = [str(t).strip() for t in tags_raw if str(t).strip()] if isinstance(tags_raw, list) else []

    main_row = (
        topic_id,
        main_topic_id,
        name,
        friendly_name,
        description,
        role,
        category,
        access,
        subscriptions,
        status,
        meta,
        can_unsubscribe,
        can_publish,
        is_subscription_allowed,
        handle,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
        tags_list,
    )

    return main_row, tags_list


def upsert_topic_and_tags(
    cur: psycopg2.extensions.cursor,
    main_row: Tuple[Any, ...],
    tags_list: List[str],
) -> UpsertResult:
    topic_id = main_row[0]

    cur.execute("SELECT 1 FROM topic WHERE id = %s", (topic_id,))
    is_new = cur.fetchone() is None

    # 1. Upsert Topic
    cur.execute(
        """
        INSERT INTO topic (
            id, main_topic_id, name, friendly_name, description,
            role, category, access, subscriptions, status, meta,
            can_unsubscribe, can_publish, is_subscription_allowed,
            handle, owner_id, parent_id, created_on, created_by,
            modified_on, modified_by, tags
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (id)
        DO UPDATE SET
            main_topic_id = EXCLUDED.main_topic_id,
            name = EXCLUDED.name,
            friendly_name = EXCLUDED.friendly_name,
            description = EXCLUDED.description,
            role = EXCLUDED.role,
            category = EXCLUDED.category,
            access = EXCLUDED.access,
            subscriptions = EXCLUDED.subscriptions,
            status = EXCLUDED.status,
            meta = EXCLUDED.meta,
            can_unsubscribe = EXCLUDED.can_unsubscribe,
            can_publish = EXCLUDED.can_publish,
            is_subscription_allowed = EXCLUDED.is_subscription_allowed,
            handle = EXCLUDED.handle,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by,
            tags = EXCLUDED.tags
        RETURNING id;
        """,
        main_row,
    )

    # 2. Sync topic tags mapping
    cur.execute("DELETE FROM topic_tag_mapping WHERE topic_id = %s", (topic_id,))
    for tag in tags_list:
        tag_val = tag[:100]
        cur.execute(
            """
            INSERT INTO topic_tag_mapping (topic_id, tag_id)
            VALUES (%s, %s)
            ON CONFLICT (topic_id, tag_id) DO NOTHING
            """,
            (topic_id, tag_val),
        )

    return UpsertResult(record_id=str(topic_id), inserted=is_new)


# -----------------------------------------------------------------------------
# Main Routine
# -----------------------------------------------------------------------------

def main() -> None:
    cfg = parse_args()

    print("=" * 70)
    print("CT-RPG: RavenDB to PostgreSQL Migration — Topics Module")
    print("=" * 70)
    print(f"[*] RavenDB URL:     {cfg.raven_url}")
    print(f"[*] RavenDB DB:      {cfg.raven_db}")
    print(f"[*] Collection:      {cfg.topics_collection}")
    print(f"[*] PostgreSQL Host: {cfg.pg_host}:{cfg.pg_port}")
    print(f"[*] PostgreSQL DB:   {cfg.pg_db} (User: {cfg.pg_user})")
    print("=" * 70)

    session = requests.Session()
    configure_raven_session(session, cfg)

    # 1. Fetch Topics
    docs: List[Dict[str, Any]] = []
    try:
        docs = raven_query_collection(session, cfg, cfg.topics_collection)
    except requests.HTTPError as ex:
        if cfg.topics_collection == "Topics":
            print("[!] Collection 'Topics' error. Trying fallback 'Topic'...")
            try:
                docs = raven_query_collection(session, cfg, "Topic")
            except Exception:
                pass
        else:
            raise ex

    if not docs and cfg.topics_collection == "Topics":
        try:
            docs = raven_query_collection(session, cfg, "Topic")
        except Exception:
            pass

    print(f"[+] Loaded {len(docs)} topic document(s) from RavenDB.")

    if cfg.inspect_source_only:
        print("\n[*] Inspect source only specified.")
        if docs:
            print("[*] Sample Topic keys:", list(docs[0].keys()))
            print("[*] Sample doc:\n", json.dumps(docs[0], indent=2, default=str)[:500])
        sys.exit(0)

    # 2. Connect to PostgreSQL
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
            print("[*] Ensuring target table 'topic' and indexes exist...")
            ensure_target_schema(cur)
            assert_required_schema(cur)
            conn.commit()
            print("[+] Schema verified successfully.")

            # 3. Migrate Topics
            print(f"\n[*] Migrating {len(docs)} Topic document(s)...")
            inserted_count = 0
            updated_count = 0
            error_count = 0
            errors: List[Dict[str, Any]] = []

            for idx, doc in enumerate(docs, 1):
                try:
                    main_row, tags_list = transform_topic_doc(doc)
                    res = upsert_topic_and_tags(cur, main_row, tags_list)
                    if res.inserted:
                        inserted_count += 1
                    else:
                        updated_count += 1
                except Exception as ex:
                    error_count += 1
                    doc_id = doc.get("Id") or f"index_{idx}"
                    errors.append({"id": str(doc_id), "error": str(ex)})
                    if error_count <= 5:
                        print(f"[!] Error migrating topic doc {doc_id}: {ex}")

                if idx % 500 == 0 or idx == len(docs):
                    conn.commit()
                    print(f"    - Processed topics: {idx}/{len(docs)} (Inserted: {inserted_count}, Updated: {updated_count}, Errors: {error_count})")

            conn.commit()

            # 4. Verification counts
            cur.execute("SELECT COUNT(*) FROM topic")
            total_in_pg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM topic_tag_mapping")
            total_tags_pg = cur.fetchone()[0]

            print("\n" + "=" * 70)
            print("Migration Summary: Topics")
            print("=" * 70)
            print(f"[+] Total RavenDB Documents:     {len(docs)}")
            print(f"[+] Records Inserted:            {inserted_count}")
            print(f"[+] Records Updated:             {updated_count}")
            print(f"[+] Records with Errors:         {error_count}")
            print(f"[+] Total Rows in 'topic':       {total_in_pg}")
            print(f"[+] Total Tag Mappings Created:  {total_tags_pg}")
            print("=" * 70)

            # 5. Write Summary JSON
            if cfg.write_summary_json and cfg.summary_json_path:
                summary_data = {
                    "module": "topics",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_count": len(docs),
                    "inserted_count": inserted_count,
                    "updated_count": updated_count,
                    "error_count": error_count,
                    "total_pg_records": total_in_pg,
                    "total_tag_mappings": total_tags_pg,
                    "errors": errors[:50],
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

    if error_count > 0:
        print(f"[!] Completed with {error_count} error(s).")
        sys.exit(1)
    else:
        print("[+] Topics migration completed successfully with 0 errors.")
        sys.exit(0)


if __name__ == "__main__":
    main()
