"""
Extract Personas data from RavenDB and load it into PostgreSQL.

This script migrates Persona documents and also builds an API-shaped payload
from PostgreSQL for parity validation. The payload is generated dynamically
from loaded data (not hardcoded examples).

Before running: set all required configuration values in scripts/.env
(or pass them explicitly as command-line arguments).

Target tables:
- persona
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
from typing import Any, Dict, List, Optional, Sequence

import psycopg2
from psycopg2.extras import Json
import requests

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


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
    personas_collection: str
    page_size: int
    timeout_sec: int
    summary_json_path: Optional[str]
    write_summary_json: bool
    include_api_payload_validation: bool
    inspect_source_only: bool


@dataclass
class UpsertResult:
    persona_id: str
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
    for env_path in (
        os.path.join(script_dir, "..", "..", ".env"),
        os.path.join(script_dir, "..", ".env"),
        os.path.join(script_dir, ".env"),
    ):
        if os.path.exists(env_path):
            load_env_file(env_path)
            break

    parser = argparse.ArgumentParser(
        description="Migrate Personas data from RavenDB to PostgreSQL"
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
        "--personas-collection", default=os.getenv("PERSONAS_COLLECTION", "Personas")
    )
    parser.add_argument("--page-size", type=int, default=os.getenv("PAGE_SIZE"))
    parser.add_argument("--timeout-sec", type=int, default=os.getenv("TIMEOUT_SEC"))
    parser.add_argument(
        "--summary-json-path",
        default=os.getenv("MIGRATION_SUMMARY_JSON"),
        help=(
            "Optional output path for post-run JSON artifact. "
            "Default when omitted: validation/personas-migration-summary-<timestamp>.json"
        ),
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        help="Disable writing post-run summary JSON artifact.",
    )
    parser.add_argument(
        "--no-api-payload-validation",
        action="store_true",
        help="Disable API-shaped PostgreSQL payload generation in summary JSON.",
    )
    parser.add_argument(
        "--inspect-source-only",
        action="store_true",
        help="Fetch RavenDB Personas and print source shape/counts without writing PostgreSQL.",
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
    if not args.personas_collection:
        parser.error(
            "Missing collection config. Provide --personas-collection or set PERSONAS_COLLECTION."
        )
    if args.page_size is None:
        parser.error("Missing page size. Provide --page-size or set PAGE_SIZE.")
    if args.timeout_sec is None:
        parser.error("Missing timeout. Provide --timeout-sec or set TIMEOUT_SEC.")
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
        personas_collection=args.personas_collection,
        page_size=args.page_size,
        timeout_sec=args.timeout_sec,
        summary_json_path=args.summary_json_path,
        write_summary_json=not args.no_summary_json,
        include_api_payload_validation=not args.no_api_payload_validation,
        inspect_source_only=args.inspect_source_only,
    )


def write_summary_json(path_text: str, payload: Dict[str, Any]) -> str:
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path.resolve())


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


def as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def as_json(value: Any) -> Optional[Json]:
    if value is None:
        return None
    return Json(value)


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def iso_utc(value: Any) -> Optional[str]:
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


def as_string_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(x) for x in value if x is not None]
    return [str(value)]


def parse_persona_type(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    valid_names = (
        "0",
        "Anon",
        "Management",
        "Parent",
        "Staff",
        "Student",
        "External",
        "Dev",
        "35",
        "60",
        "70",
    )
    if val_str in valid_names:
        return val_str
    try:
        val_int = int(val_str)
        named = {
            0: "0",
            10: "Anon",
            20: "Management",
            30: "Parent",
            35: "35",
            40: "Staff",
            50: "Student",
            60: "60",
            70: "70",
            80: "External",
            90: "Dev",
        }.get(val_int)
        return named if named is not None else str(val_int)
    except (TypeError, ValueError):
        return val_str


def parse_persona_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    if value in ("Unknown", "Active", "Disabled"):
        return str(value)
    try:
        return {-1: "Unknown", 1: "Active", 99: "Disabled"}.get(int(value), None)
    except (TypeError, ValueError):
        return None


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
            raise RuntimeError(
                f"RavenDB returned a non-document result for {collection_name}"
            )
        if not results:
            break

        docs.extend(results)
        start += len(results)

    return docs


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


def derive_persona_id(doc: Dict[str, Any]) -> Optional[str]:
    return first_non_empty(
        extract_uuid_from_any(get_nested(doc, "@metadata", "@id")),
        extract_uuid_from_any(doc.get("PersonaId")),
        extract_uuid_from_any(doc.get("Id")),
    )


def ensure_target_schema(cur: psycopg2.extensions.cursor) -> None:
    """Create persona table and indexes with exact target schema."""
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'persona_type_enum') THEN
                CREATE TYPE persona_type_enum AS ENUM (
                    '0',
                    'Anon',
                    'Management',
                    'Parent',
                    'Staff',
                    'Student',
                    'External',
                    'Dev',
                    '35',
                    '60',
                    '70'
                );
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'persona_status_enum') THEN
                CREATE TYPE persona_status_enum AS ENUM (
                    'Unknown',
                    'Active',
                    'Disabled'
                );
            END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS persona (
            id UUID PRIMARY KEY,
            title VARCHAR(200),
            display_text VARCHAR(200),
            persona_type persona_type_enum,
            persona_type_as_string VARCHAR(64),
            scope TEXT[],
            named_scope TEXT[],
            status persona_status_enum,
            owner_id UUID,
            parent_id UUID,
            created_on TIMESTAMPTZ,
            created_by UUID,
            modified_on TIMESTAMPTZ,
            modified_by UUID
        );
        """
    )




def upsert_persona(
    cur: psycopg2.extensions.cursor, doc: Dict[str, Any]
) -> Optional[UpsertResult]:
    persona_id = derive_persona_id(doc)
    if not persona_id:
        return None

    cur.execute(
        """
        INSERT INTO persona (
            id,
            title,
            display_text,
            persona_type,
            persona_type_as_string,
            scope,
            named_scope,
            status,
            owner_id,
            parent_id,
            created_on,
            created_by,
            modified_on,
            modified_by
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (id)
        DO UPDATE SET
            title = EXCLUDED.title,
            display_text = EXCLUDED.display_text,
            persona_type = EXCLUDED.persona_type,
            persona_type_as_string = EXCLUDED.persona_type_as_string,
            scope = EXCLUDED.scope,
            named_scope = EXCLUDED.named_scope,
            status = EXCLUDED.status,
            owner_id = EXCLUDED.owner_id,
            parent_id = EXCLUDED.parent_id,
            created_on = EXCLUDED.created_on,
            created_by = EXCLUDED.created_by,
            modified_on = EXCLUDED.modified_on,
            modified_by = EXCLUDED.modified_by
        RETURNING (xmax = 0);
        """,
        (
            persona_id,
            as_text(doc.get("Title")),
            as_text(doc.get("DisplayText")),
            parse_persona_type(
                first_non_empty(
                    doc.get("PersonaTypeAsString"), doc.get("PersonaType")
                )
            ),
            as_text(doc.get("PersonaTypeAsString")),
            as_string_list(doc.get("Scope")),
            as_string_list(doc.get("NamedScope")),
            parse_persona_status(doc.get("Status")),
            extract_uuid_from_any(doc.get("OwnerId")),
            extract_uuid_from_any(doc.get("ParentId")),
            parse_ts(doc.get("CreatedOn")),
            extract_uuid_from_any(doc.get("CreatedBy")),
            parse_ts(doc.get("ModifiedOn")),
            extract_uuid_from_any(doc.get("ModifiedBy")),
        ),
    )

    row = cur.fetchone()
    if not row:
        return None
    return UpsertResult(persona_id, bool(row[0]))


def build_source_profile(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    profile = {
        "persona_documents": len(docs),
        "with_persona_id": 0,
        "scope_items": 0,
        "named_scope_items": 0,
        "first_persona": None,
    }

    for doc in docs:
        if derive_persona_id(doc):
            profile["with_persona_id"] += 1
        profile["scope_items"] += len(as_list(doc.get("Scope")))
        profile["named_scope_items"] += len(as_list(doc.get("NamedScope")))

    if docs:
        first = docs[0]
        profile["first_persona"] = {
            "id": derive_persona_id(first),
            "title": first.get("Title"),
            "persona_type": first.get("PersonaType"),
            "status": first.get("Status"),
            "owner_id": first.get("OwnerId"),
            "scope_items": len(as_list(first.get("Scope"))),
            "named_scope_items": len(as_list(first.get("NamedScope"))),
        }

    return profile


def main() -> int:
    cfg = parse_args()
    requests_session = requests.Session()
    conn = None

    try:
        configure_raven_session(requests_session, cfg)
        print(
            f"RavenDB target: url={cfg.raven_url}, db={cfg.raven_db}, collection={cfg.personas_collection}"
        )
        print("[1/3] Fetching RavenDB persona documents...")
        persona_docs = raven_query_collection(
            requests_session, cfg, cfg.personas_collection
        )
        print(f"Fetched personas={len(persona_docs)}")

        if cfg.inspect_source_only:
            print(json.dumps(build_source_profile(persona_docs), indent=2))
            return 0

        print("[2/3] Connecting PostgreSQL...")
        print(
            f"PostgreSQL target: host={cfg.pg_host}, port={cfg.pg_port}, db={cfg.pg_db}, user={cfg.pg_user}"
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

        personas_processed = 0
        personas_inserted = 0
        skipped_personas_missing_id = 0

        with conn:
            with conn.cursor() as cur:
                ensure_target_schema(cur)

                print("[3/3] Upserting personas...")
                for doc in persona_docs:
                    result = upsert_persona(cur, doc)
                    if result is None:
                        skipped_personas_missing_id += 1
                        continue
                    personas_processed += 1
                    personas_inserted += int(result.inserted)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "source": {
                "raven_url": cfg.raven_url,
                "raven_db": cfg.raven_db,
                "personas_collection": cfg.personas_collection,
            },
            "target": {
                "pg_host": cfg.pg_host,
                "pg_port": cfg.pg_port,
                "pg_db": cfg.pg_db,
                "pg_user": cfg.pg_user,
            },
            "run_stats": {
                "personas_processed": personas_processed,
                "new_personas_inserted": personas_inserted,
                "skipped_personas_missing_id": skipped_personas_missing_id,
            },
        }

        print("Migration completed.")
        print(f"personas_processed: {personas_processed}")
        print(f"new_personas_inserted: {personas_inserted}")

        if cfg.write_summary_json:
            output_path = cfg.summary_json_path
            if not output_path:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                output_path = f"validation/personas-migration-summary-{timestamp}.json"
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
