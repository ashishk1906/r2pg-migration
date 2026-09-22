#!/usr/bin/env python3
"""
Extract Grading data from RavenDB, transform it to PostgreSQL schema,
and load into PostgreSQL.

Handles:
- grading table (Gradings collection)
- grading_rule table (GradingRules list in grading documents)
- Backward-compatible views: gradings, grading_rules

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

# GradingStatusEnum: Active = 1, Disabled = 99
GRADING_STATUS_MAP: Dict[str, int] = {
    "active": 1,
    "enabled": 1,
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
    gradings_collection: str
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
        description="Migrate Grading data from RavenDB to PostgreSQL"
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
        "--gradings-collection",
        default=os.getenv("GRADINGS_COLLECTION", "Gradings"),
        help="RavenDB collection name for gradings (default: Gradings)",
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
            "GRADINGS_SUMMARY_JSON_PATH",
            os.path.join(script_dir, "..", "validation", "gradings_migration_summary.json"),
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
        gradings_collection=args.gradings_collection,
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


def parse_grading_status(value: Any) -> int:
    """GradingStatusEnum: Active = 1, Disabled = 99 (default: 1)"""
    if value is None:
        return 1
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().replace(" ", "").replace("_", "")
    if not text:
        return 1
    if text.isdigit():
        return int(text)
    return GRADING_STATUS_MAP.get(text, 1)


def derive_grading_id(doc: Dict[str, Any]) -> Optional[str]:
    return first_non_empty(
        extract_uuid_from_any(get_nested(doc, "@metadata", "@id")),
        extract_uuid_from_any(doc.get("GradingId")),
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
    """Create all required grading and grading_rule tables and indexes."""
    cur.execute(
        """
        -- 1. Main Grading Table
        CREATE TABLE IF NOT EXISTS grading (
            id UUID PRIMARY KEY,
            status INTEGER,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID,
            grading_rules JSONB
        );

        -- 2. Grading Rules Child Table
        CREATE TABLE IF NOT EXISTS grading_rule (
            id BIGSERIAL PRIMARY KEY,
            grading_id UUID NOT NULL REFERENCES grading(id) ON DELETE CASCADE,
            marks NUMERIC(5, 2),
            grade VARCHAR(20),
            description VARCHAR(250),
            display_order INTEGER
        );

        -- Indexes for query performance
        CREATE INDEX IF NOT EXISTS idx_grading_status ON grading (status);
        CREATE INDEX IF NOT EXISTS idx_grading_owner_id ON grading (owner_id);
        CREATE INDEX IF NOT EXISTS idx_grading_rule_gid ON grading_rule (grading_id);
        CREATE INDEX IF NOT EXISTS idx_grading_rule_grade ON grading_rule (grade);

        -- Backward compatible views
        CREATE OR REPLACE VIEW gradings AS SELECT * FROM grading;
        CREATE OR REPLACE VIEW grading_rules AS SELECT * FROM grading_rule;
        """
    )


def assert_required_schema(cur: psycopg2.extensions.cursor) -> None:
    """Assert all required columns exist in grading and grading_rule tables."""
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_name IN ('grading', 'grading_rule')
        """
    )
    existing = {(row[0], row[1].lower()) for row in cur.fetchall()}

    req_grading = {
        "id", "status", "owner_id", "parent_id",
        "created_on", "created_by", "modified_on", "modified_by"
    }
    req_rules = {
        "id", "grading_id", "marks", "grade", "description", "display_order"
    }

    missing_grading = {col for col in req_grading if ("grading", col) not in existing}
    missing_rules = {col for col in req_rules if ("grading_rule", col) not in existing}

    if missing_grading or missing_rules:
        raise RuntimeError(
            f"Schema verification failed! Missing cols in grading: {missing_grading}, grading_rule: {missing_rules}"
        )


# -----------------------------------------------------------------------------
# Transform & Upsert: Grading and Rules
# -----------------------------------------------------------------------------

def transform_grading_doc(doc: Dict[str, Any]) -> Tuple[Tuple[Any, ...], List[Dict[str, Any]]]:
    grading_id = derive_grading_id(doc)
    if not grading_id:
        raise ValueError(f"Grading doc missing valid GUID: {doc.get('Id')}")

    status = parse_grading_status(doc.get("Status"))
    owner_id = extract_uuid_from_any(doc.get("OwnerId"))
    parent_id = extract_uuid_from_any(doc.get("ParentId"))
    created_on = parse_ts(doc.get("CreatedOn")) or datetime.now(timezone.utc).isoformat()
    created_by = extract_uuid_from_any(doc.get("CreatedBy"))
    modified_on = parse_ts(doc.get("ModifiedOn"))
    modified_by = extract_uuid_from_any(doc.get("ModifiedBy"))

    rules_raw = first_non_empty(doc.get("GradingRules"), doc.get("Rules"), doc.get("gradingRules")) or []
    rules_list = rules_raw if isinstance(rules_raw, list) else []

    main_row = (
        grading_id,
        status,
        owner_id,
        parent_id,
        created_on,
        created_by,
        modified_on,
        modified_by,
        as_json(rules_list),
    )

    return main_row, rules_list


def upsert_grading_and_rules(
    cur: psycopg2.extensions.cursor,
    main_row: Tuple[Any, ...],
    rules_list: List[Dict[str, Any]],
) -> UpsertResult:
    grading_id = main_row[0]

    cur.execute("SELECT 1 FROM grading WHERE id = %s", (grading_id,))
    is_new = cur.fetchone() is None

    # 1. Upsert Grading
    cur.execute(
        """
        INSERT INTO grading (
            id, status, owner_id, parent_id,
            created_on, created_by, modified_on, modified_by,
            grading_rules
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id)
        DO UPDATE SET
            status = EXCLUDED.status,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by,
            grading_rules = EXCLUDED.grading_rules
        RETURNING id;
        """,
        main_row,
    )

    # 2. Clear existing child rules for this grading to ensure clean synchronization
    cur.execute("DELETE FROM grading_rule WHERE grading_id = %s", (grading_id,))

    # 3. Insert child grading rules
    for idx, rule in enumerate(rules_list, 1):
        if not isinstance(rule, dict):
            continue
        marks = parse_decimal(
            first_non_empty(rule.get("Marks"), rule.get("Percentage"), rule.get("Score")),
            default=Decimal("0.00"),
        )
        grade = as_text(rule.get("Grade"))
        grade = grade[:20] if grade else "N/A"
        desc = as_text(rule.get("Description"))
        desc = desc[:250] if desc else None
        order = parse_int(rule.get("DisplayOrder")) or idx

        cur.execute(
            """
            INSERT INTO grading_rule (grading_id, marks, grade, description, display_order)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (grading_id, marks, grade, desc, order),
        )

    return UpsertResult(record_id=str(grading_id), inserted=is_new)


# -----------------------------------------------------------------------------
# Main Routine
# -----------------------------------------------------------------------------

def main() -> None:
    cfg = parse_args()

    print("=" * 70)
    print("CT-RPG: RavenDB to PostgreSQL Migration — Gradings Module")
    print("=" * 70)
    print(f"[*] RavenDB URL:     {cfg.raven_url}")
    print(f"[*] RavenDB DB:      {cfg.raven_db}")
    print(f"[*] Collection:      {cfg.gradings_collection}")
    print(f"[*] PostgreSQL Host: {cfg.pg_host}:{cfg.pg_port}")
    print(f"[*] PostgreSQL DB:   {cfg.pg_db} (User: {cfg.pg_user})")
    print("=" * 70)

    session = requests.Session()
    configure_raven_session(session, cfg)

    # 1. Fetch Gradings
    docs: List[Dict[str, Any]] = []
    try:
        docs = raven_query_collection(session, cfg, cfg.gradings_collection)
    except requests.HTTPError as ex:
        if cfg.gradings_collection == "Gradings":
            print("[!] Collection 'Gradings' error. Trying fallback 'Grading'...")
            try:
                docs = raven_query_collection(session, cfg, "Grading")
            except Exception:
                pass
        else:
            raise ex

    if not docs and cfg.gradings_collection == "Gradings":
        try:
            docs = raven_query_collection(session, cfg, "Grading")
        except Exception:
            pass

    print(f"[+] Loaded {len(docs)} grading document(s) from RavenDB.")

    if cfg.inspect_source_only:
        print("\n[*] Inspect source only specified.")
        if docs:
            print("[*] Sample Grading keys:", list(docs[0].keys()))
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
            print("[*] Ensuring target table 'grading' and indexes exist...")
            ensure_target_schema(cur)
            assert_required_schema(cur)
            conn.commit()
            print("[+] Schema verified successfully.")

            # 3. Migrate Gradings
            print(f"\n[*] Migrating {len(docs)} Grading document(s)...")
            inserted_count = 0
            updated_count = 0
            error_count = 0
            errors: List[Dict[str, Any]] = []

            for idx, doc in enumerate(docs, 1):
                try:
                    main_row, rules_list = transform_grading_doc(doc)
                    res = upsert_grading_and_rules(cur, main_row, rules_list)
                    if res.inserted:
                        inserted_count += 1
                    else:
                        updated_count += 1
                except Exception as ex:
                    error_count += 1
                    doc_id = doc.get("Id") or f"index_{idx}"
                    errors.append({"id": str(doc_id), "error": str(ex)})
                    if error_count <= 5:
                        print(f"[!] Error migrating grading doc {doc_id}: {ex}")

                if idx % 500 == 0 or idx == len(docs):
                    conn.commit()
                    print(f"    - Processed gradings: {idx}/{len(docs)} (Inserted: {inserted_count}, Updated: {updated_count}, Errors: {error_count})")

            conn.commit()

            # 4. Verification counts
            cur.execute("SELECT COUNT(*) FROM grading")
            total_in_pg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM grading_rule")
            total_rules_pg = cur.fetchone()[0]

            print("\n" + "=" * 70)
            print("Migration Summary: Gradings")
            print("=" * 70)
            print(f"[+] Total RavenDB Documents:     {len(docs)}")
            print(f"[+] Records Inserted:            {inserted_count}")
            print(f"[+] Records Updated:             {updated_count}")
            print(f"[+] Records with Errors:         {error_count}")
            print(f"[+] Total Rows in 'grading':     {total_in_pg}")
            print(f"[+] Total Rows in 'grading_rule':{total_rules_pg}")
            print("=" * 70)

            # 5. Write Summary JSON
            if cfg.write_summary_json and cfg.summary_json_path:
                summary_data = {
                    "module": "gradings",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_count": len(docs),
                    "inserted_count": inserted_count,
                    "updated_count": updated_count,
                    "error_count": error_count,
                    "total_pg_records": total_in_pg,
                    "total_grading_rules": total_rules_pg,
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
        print("[+] Gradings migration completed successfully with 0 errors.")
        sys.exit(0)


if __name__ == "__main__":
    main()
