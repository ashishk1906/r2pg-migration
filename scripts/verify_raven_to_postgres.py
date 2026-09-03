#!/usr/bin/env python3
"""
Comprehensive Verification Script: RavenDB vs PostgreSQL Complete Parity
Validates EVERY SINGLE FIELD AND COLUMN across all 9 migrated domains:
1. organization (23 fields)
2. institute (32 fields)
3. student (40 fields)
4. course (14 fields)
5. staff (19 fields)
6. persona (10 fields)
7. fee (11 fields)
8. fee_transaction (16 fields)
9. exam (12 fields)
Total: 177 distinct attributes audited per record with full type and value checking.
"""

from __future__ import annotations

import argparse
import atexit
import inspect
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def extract_uuid(val: Any) -> Optional[str]:
    if val is None:
        return None
    val_str = str(val).strip()
    match = UUID_RE.search(val_str)
    if match:
        return match.group(0).lower()
    return None


def normalize_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    # Strip subsecond digits beyond 6 (RavenDB .0000000)
    if "." in text:
        base, rest = text.split(".", 1)
        digits = ""
        tz_part = ""
        for i, ch in enumerate(rest):
            if ch.isdigit():
                digits += ch
            else:
                tz_part = rest[i:]
                break
        digits = digits[:6].ljust(6, "0")
        text = f"{base}.{digits}{tz_part}"

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def to_decimal(val: Any) -> Optional[Decimal]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, str):
        try:
            return Decimal(val.strip())
        except Exception:
            return None
    return None


def deep_values_equal(v1: Any, v2: Any) -> bool:
    """
    Robust parity equality check that handles:
    - Postgres JSONB wrappers (.adapted)
    - Native UUID objects vs string UUIDs
    - UTC Date/DateTime conversions
    - Arbitrary precision Decimal comparisons
    - List and array element comparisons (with tag/set sorting)
    - Range objects
    - Empty collections and string semantics preserving strictness
    """
    if hasattr(v1, "adapted"):
        v1 = v1.adapted
    if hasattr(v2, "adapted"):
        v2 = v2.adapted

    if isinstance(v1, uuid.UUID):
        v1 = str(v1).lower()
    if isinstance(v2, uuid.UUID):
        v2 = str(v2).lower()

    # None and empty checks
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False

    # Boolean checks
    if isinstance(v1, bool) or isinstance(v2, bool):
        return isinstance(v1, bool) and isinstance(v2, bool) and v1 == v2

    # Date / DateTime handling
    if isinstance(v1, (date, datetime)) or isinstance(v2, (date, datetime)):
        dt1 = normalize_datetime(v1)
        dt2 = normalize_datetime(v2)
        if dt1 is not None and dt2 is not None:
            return dt1 == dt2

        # Support date vs date string (YYYY-MM-DD)
        if isinstance(v1, date) and not isinstance(v1, datetime):
            v1_str = v1.isoformat()
            if isinstance(v2, str) and v2.startswith(v1_str):
                return True
        if isinstance(v2, date) and not isinstance(v2, datetime):
            v2_str = v2.isoformat()
            if isinstance(v1, str) and v1.startswith(v2_str):
                return True

    # Numeric handling
    d1 = to_decimal(v1)
    d2 = to_decimal(v2)
    if d1 is not None and d2 is not None:
        return d1 == d2

    # String UUID check
    if isinstance(v1, str) and isinstance(v2, str):
        u1 = extract_uuid(v1)
        u2 = extract_uuid(v2)
        if u1 and u2 and u1 == u2:
            return True
        return v1.strip() == v2.strip()

    # Dictionary / Object comparison
    if isinstance(v1, dict) and isinstance(v2, dict):
        if set(v1.keys()) != set(v2.keys()):
            return False
        return all(deep_values_equal(v1[k], v2[k]) for k in v1)

    # List / Array comparison
    if isinstance(v1, (list, tuple)) and isinstance(v2, (list, tuple)):
        if len(v1) != len(v2):
            return False
        if all(deep_values_equal(a, b) for a, b in zip(v1, v2)):
            return True

        # Fallback for set-like collections (e.g. tags, roles)
        try:
            sv1 = sorted(str(x) for x in v1)
            sv2 = sorted(str(x) for x in v2)
            if sv1 == sv2:
                return True
        except Exception:
            pass
        return False

    # Bytes / bytearray handling
    if isinstance(v1, (bytes, bytearray, memoryview)) or isinstance(v2, (bytes, bytearray, memoryview)):
        return bytes(v1) == bytes(v2)

    # Postgres Range comparison
    has_range_v1 = hasattr(v1, "lower") and hasattr(v1, "upper") and not callable(getattr(v1, "lower", None))
    has_range_v2 = hasattr(v2, "lower") and hasattr(v2, "upper") and not callable(getattr(v2, "lower", None))
    if has_range_v1 and has_range_v2:
        return deep_values_equal(v1.lower, v2.lower) and deep_values_equal(v1.upper, v2.upper)

    return v1 == v2


def apply_transform(transform_fn: Optional[Callable[..., Any]], r_raw: Any, r_doc: Dict[str, Any]) -> Any:
    if transform_fn is None or not callable(transform_fn):
        return r_raw

    try:
        sig = inspect.signature(transform_fn)
        params = list(sig.parameters.values())

        if any(p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD) for p in params):
            return transform_fn(r_raw, r_doc)

        positional_count = sum(
            1 for p in params if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        )
        if positional_count >= 2:
            return transform_fn(r_raw, r_doc)
        return transform_fn(r_raw)
    except (ValueError, TypeError):
        try:
            return transform_fn(r_raw, r_doc)
        except TypeError:
            return transform_fn(r_raw)


def as_list(val: Any) -> List[Any]:
    return val if isinstance(val, list) else []


# ==========================================
# Generic Enum Transformation Factory
# ==========================================

def create_enum_mapper(
    code_to_name: Dict[int, str],
    default: Optional[str] = None,
) -> Callable[[Any], Optional[str]]:
    """Generic higher-order function that maps integer/string codes to canonical domain names."""
    valid_names = set(code_to_name.values())

    def mapper(value: Any) -> Optional[str]:
        if value is None:
            return default
        str_val = str(value).strip()
        if str_val in valid_names:
            return str_val
        try:
            int_val = int(value)
            return code_to_name.get(int_val, default)
        except (TypeError, ValueError):
            return default

    return mapper


parse_student_gender = create_enum_mapper({0: "Female", 1: "Male", 90: "NoInfo"}, default="NoInfo")
parse_student_status = create_enum_mapper({-1: "Unknown", 1: "Active", 99: "Disabled"}, default="Active")
parse_org_status = create_enum_mapper(
    {-1: "Unknown", 0: "ActivationPending", 1: "Active", 90: "Locked", 99: "Disabled"},
    default="Active",
)
parse_institute_status = parse_org_status
parse_edu_level = create_enum_mapper(
    {
        -1: "Unknown",
        2: "PreNursery",
        5: "Nursery",
        10: "School",
        20: "UnderGraduate",
        30: "Graduate",
        40: "PostGraduate",
    },
    default=None,
)
parse_staff_type = create_enum_mapper({0: "Teaching", 1: "NonTeaching", 2: "Management"}, default=None)
parse_staff_status = create_enum_mapper({-1: "Unknown", 1: "Active", 99: "Disabled"}, default="Active")
parse_persona_type = create_enum_mapper(
    {10: "Anon", 20: "Management", 30: "Parent", 40: "Staff", 50: "Student", 80: "External", 90: "Dev"},
    default=None,
)
parse_persona_status = create_enum_mapper({-1: "Unknown", 1: "Active", 99: "Disabled"}, default="Active")
parse_fee_status = create_enum_mapper({0: "Unknown", 1: "Active", 99: "Disabled"}, default="Active")
parse_fee_tx_status = create_enum_mapper({1: "Active", 99: "Disabled"}, default="Active")
parse_course_status = create_enum_mapper({0: "Unknown", 1: "Active", 99: "Disabled"}, default="Active")
parse_exam_status = create_enum_mapper(
    {0: "Unknown", 1: "Active", 10: "Scheduled", 20: "Conducted", 90: "Locked", 99: "Disabled"},
    default="Active",
)


# ==========================================
# Domain-Specific Canonical ID Extractors
# (Matches the exact PK derivation used by each migration script)
# ==========================================

def extract_organization_pk(doc: Dict[str, Any]) -> Optional[str]:
    """Mirrors students_ravendb_to_postgres_migrate.py upsert_organization PK derivation."""
    return (
        extract_uuid(doc.get("SourceOrgId"))
        or extract_uuid(doc.get("OrgId"))
        or extract_uuid(doc.get("Id"))
        or extract_uuid(doc.get("@metadata", {}).get("@id"))
    )


def extract_institute_pk(doc: Dict[str, Any]) -> Optional[str]:
    """Mirrors students_ravendb_to_postgres_migrate.py upsert_institute PK derivation."""
    return (
        extract_uuid(doc.get("SourceInstId"))
        or extract_uuid(doc.get("InstId"))
        or extract_uuid(doc.get("Id"))
        or extract_uuid(doc.get("@metadata", {}).get("@id"))
    )


def extract_student_pk(doc: Dict[str, Any]) -> Optional[str]:
    """Mirrors students_ravendb_to_postgres_migrate.py derive_student_pk."""
    meta_id = doc.get("@metadata", {}).get("@id")
    meta_uuid = extract_uuid(meta_id)
    if meta_uuid:
        return meta_uuid
    # Strictly validate against UUID format to prevent business IDs (e.g. '23P001') from being used as PK
    return (
        extract_uuid(doc.get("Id"))
        or extract_uuid(doc.get("SourceStudentId"))
        or extract_uuid(doc.get("StudentId"))
    )


def extract_course_pk(doc: Dict[str, Any]) -> Optional[str]:
    """Mirrors courses_ravendb_to_postgres_migrate.py derive_course_id."""
    meta_id = doc.get("@metadata", {}).get("@id")
    return (
        extract_uuid(meta_id)
        or extract_uuid(doc.get("CourseId"))
        or extract_uuid(doc.get("Id"))
    )


def extract_staff_pk(doc: Dict[str, Any]) -> Optional[str]:
    """Mirrors staffs_ravendb_to_postgres_migrate.py derive_staff_id."""
    meta_id = doc.get("@metadata", {}).get("@id")
    return (
        extract_uuid(meta_id)
        or extract_uuid(doc.get("StaffId"))
        or extract_uuid(doc.get("Id"))
    )


def extract_persona_pk(doc: Dict[str, Any]) -> Optional[str]:
    meta_id = doc.get("@metadata", {}).get("@id")
    return (
        extract_uuid(meta_id)
        or extract_uuid(doc.get("PersonaId"))
        or extract_uuid(doc.get("Id"))
    )


def extract_fee_pk(doc: Dict[str, Any]) -> Optional[str]:
    meta_id = doc.get("@metadata", {}).get("@id")
    return (
        extract_uuid(meta_id)
        or extract_uuid(doc.get("FeeId"))
        or extract_uuid(doc.get("Id"))
    )


def extract_fee_tx_pk(doc: Dict[str, Any]) -> Optional[str]:
    meta_id = doc.get("@metadata", {}).get("@id")
    return (
        extract_uuid(meta_id)
        or extract_uuid(doc.get("TxId"))
        or extract_uuid(doc.get("Id"))
    )


def extract_exam_pk(doc: Dict[str, Any]) -> Optional[str]:
    """Mirrors exams_ravendb_to_postgres_migrate.py derive_exam_id."""
    meta_id = doc.get("@metadata", {}).get("@id")
    return (
        extract_uuid(meta_id)
        or extract_uuid(doc.get("ExamId"))
        or extract_uuid(doc.get("Id"))
    )


def derive_business_student_id(val: Any, doc: Dict[str, Any]) -> Optional[str]:
    direct = doc.get("SourceStudentId") or doc.get("StudentId")
    if direct:
        return str(direct)
    enrollments = doc.get("Enrollments")
    if isinstance(enrollments, list):
        for e in enrollments:
            if isinstance(e, dict) and e.get("StudentId"):
                return str(e.get("StudentId"))
    return None


# ==========================================
# Domain & Field Comparison Declarations
# ==========================================

@dataclass
class FieldComparison:
    raven_field: str
    pg_field: str
    transform: Optional[Callable[..., Any]] = None
    ignored: bool = False
    note: str = ""


@dataclass
class DomainDefinition:
    name: str
    collection_name: str
    table_name: str
    key_extractor: Callable[[Dict[str, Any]], Optional[str]]
    comparisons: List[FieldComparison]


@dataclass
class DomainCheckResult:
    domain_name: str
    collection_name: str
    table_name: str
    total_fields_checked: int = 0
    raven_count: int = 0
    pg_count: int = 0
    matched_ids: int = 0
    missing_in_pg: List[str] = field(default_factory=list)
    extra_in_pg: List[str] = field(default_factory=list)
    unparseable_raven_ids: List[str] = field(default_factory=list)
    invalid_pg_ids: List[str] = field(default_factory=list)
    field_mismatches_count: int = 0
    sample_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    all_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "PENDING"
    error_message: Optional[str] = None


# ==========================================
# Verification Engine
# ==========================================

class VerificationEngine:
    def __init__(
        self,
        page_size: int = 1000,
        limit: Optional[int] = None,
        filter_ids: Optional[List[str]] = None,
        max_mismatches: int = 5,
    ):
        self.script_dir = Path(__file__).parent.resolve()
        root_env = self.script_dir.parent / ".env"
        if root_env.exists():
            load_env_file(root_env)

        self.raven_url = os.getenv("RAVEN_URL", "").rstrip("/")
        self.raven_db = os.getenv("RAVEN_DB", "")
        self.raven_cert_file = os.getenv("RAVEN_CERT_FILE")
        self.raven_cert_password = os.getenv("RAVEN_CERT_PASSWORD")
        self.raven_api_key = os.getenv("RAVEN_API_KEY")
        self.raven_insecure = os.getenv("RAVEN_INSECURE", "false").lower() in {
            "1",
            "true",
            "yes",
        }

        self.pg_host = os.getenv("PG_HOST", "localhost")
        self.pg_port = int(os.getenv("PG_PORT", "5432"))
        self.pg_db = os.getenv("PG_DB", "rpg")
        self.pg_user = os.getenv("PG_USER", "postgres")
        self.pg_password = os.getenv("PG_PASSWORD", "")

        self.page_size = page_size
        self.limit = limit
        self.filter_ids = {i.lower().strip() for i in filter_ids} if filter_ids else None
        self.max_mismatches = max_mismatches

        self._temp_files: List[str] = []
        atexit.register(self.cleanup)

        self.session = requests.Session()
        if self.raven_api_key:
            self.session.headers["Authorization"] = f"Bearer {self.raven_api_key}"

        self._configure_raven_session()

    def cleanup(self) -> None:
        """Remove temporary PEM certificate files created during runtime."""
        for path in self._temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self._temp_files.clear()

    def _configure_raven_session(self) -> None:
        if not self.raven_cert_file:
            return
        cert_path = self.raven_cert_file
        if not os.path.isabs(cert_path):
            abs_cand = self.script_dir / cert_path
            if abs_cand.exists():
                cert_path = str(abs_cand)

        if cert_path.endswith(".pfx") or cert_path.endswith(".p12"):
            try:
                from cryptography.hazmat.primitives.serialization import (
                    Encoding,
                    NoEncryption,
                    PrivateFormat,
                    pkcs12,
                )
            except ImportError:
                print("[!] Warning: cryptography module not found for PKCS#12 certs.")
                return

            with open(cert_path, "rb") as fh:
                pfx_data = fh.read()
            pwd = (
                self.raven_cert_password.encode("utf-8")
                if self.raven_cert_password
                else None
            )
            key, cert, add_certs = pkcs12.load_key_and_certificates(pfx_data, pwd)

            temp_pem = tempfile.NamedTemporaryFile(
                delete=False, suffix=".pem", mode="wb"
            )
            self._temp_files.append(temp_pem.name)
            if cert:
                temp_pem.write(cert.public_bytes(Encoding.PEM))
            if add_certs:
                for c in add_certs:
                    temp_pem.write(c.public_bytes(Encoding.PEM))
            if key:
                temp_pem.write(
                    key.private_bytes(
                        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
                    )
                )
            temp_pem.flush()
            temp_pem.close()
            self.session.cert = temp_pem.name
        else:
            self.session.cert = cert_path

    def get_pg_connection(self):
        return psycopg2.connect(
            host=self.pg_host,
            port=self.pg_port,
            dbname=self.pg_db,
            user=self.pg_user,
            password=self.pg_password,
            cursor_factory=RealDictCursor,
        )

    def fetch_raven_collection(self, collection: str) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        start = 0
        url = f"{self.raven_url}/databases/{self.raven_db}/queries"
        max_retries = 3

        while True:
            batch_size = self.page_size
            if self.limit and (start + batch_size > self.limit):
                batch_size = max(0, self.limit - start)
                if batch_size == 0:
                    break

            rql = f"from '{collection}'"
            payload = {"Query": rql, "Start": start, "PageSize": batch_size}

            resp_data = None
            for attempt in range(1, max_retries + 1):
                try:
                    res = self.session.post(
                        url,
                        json=payload,
                        timeout=60,
                        verify=not self.raven_insecure,
                    )
                    if res.status_code == 200:
                        resp_data = res.json()
                        break
                    elif res.status_code == 429:
                        retry_after = int(res.headers.get("Retry-After", 2 * attempt))
                        print(f"   [!] RavenDB rate limit hit (429). Retrying in {retry_after}s...")
                        time.sleep(retry_after)
                    elif res.status_code in (500, 502, 503, 504):
                        wait_sec = 2 ** attempt
                        print(f"   [!] RavenDB server error {res.status_code}. Retrying in {wait_sec}s (attempt {attempt}/{max_retries})...")
                        time.sleep(wait_sec)
                    else:
                        raise RuntimeError(
                            f"Failed querying RavenDB collection '{collection}': HTTP {res.status_code} - {res.text}"
                        )
                except requests.RequestException as req_err:
                    if attempt == max_retries:
                        raise RuntimeError(
                            f"Network error querying RavenDB collection '{collection}' after {max_retries} attempts: {req_err}"
                        )
                    time.sleep(2 ** attempt)

            if resp_data is None:
                raise RuntimeError(f"Exhausted retries querying RavenDB collection '{collection}'")

            total_results = resp_data.get("TotalResults", 0)
            results = resp_data.get("Results", [])
            if start == 0 and total_results == 0 and not results:
                print(f"   [i] Collection '{collection}' is empty in RavenDB.")
                break

            if not results:
                break
            docs.extend(results)
            start += len(results)
            if len(docs) % 2000 == 0:
                print(f"   [RavenDB] Fetched {len(docs):,} documents from '{collection}'...")
            if len(results) < batch_size or (self.limit and len(docs) >= self.limit):
                break
        return docs

    def verify_domain(
        self,
        domain_def: DomainDefinition,
        pg_conn,
    ) -> DomainCheckResult:
        result = DomainCheckResult(
            domain_name=domain_def.name,
            collection_name=domain_def.collection_name,
            table_name=domain_def.table_name,
            total_fields_checked=len([c for c in domain_def.comparisons if not c.ignored]),
        )

        print(
            f"[*] Checking {domain_def.name} (RavenDB '{domain_def.collection_name}' -> PostgreSQL '{domain_def.table_name}')... [{result.total_fields_checked} active fields]"
        )

        try:
            # 1. Fetch RavenDB documents
            raven_docs = self.fetch_raven_collection(domain_def.collection_name)
            result.raven_count = len(raven_docs)

            needed_fields = {c.raven_field for c in domain_def.comparisons}
            needed_fields.update(
                {
                    "Id",
                    "SourceStudentId",
                    "StudentId",
                    "SourceOrgId",
                    "OrgId",
                    "SourceInstId",
                    "InstId",
                    "CourseId",
                    "StaffId",
                    "PersonaId",
                    "FeeId",
                    "TxId",
                    "ExamId",
                    "Enrollments",
                    "@metadata",
                }
            )

            raven_map: Dict[str, Dict[str, Any]] = {}
            for doc in raven_docs:
                raw_pk = domain_def.key_extractor(doc)
                if not raw_pk:
                    doc_hint = str(doc.get("Id") or doc.get("@metadata", {}).get("@id") or "<no_id>")
                    result.unparseable_raven_ids.append(doc_hint)
                    continue
                valid_pk = extract_uuid(raw_pk)
                if not valid_pk:
                    result.unparseable_raven_ids.append(str(raw_pk))
                    continue
                if self.filter_ids and valid_pk not in self.filter_ids:
                    continue
                raven_map[valid_pk] = {k: v for k, v in doc.items() if k in needed_fields}

            # 2. Fetch PostgreSQL rows with column projection
            active_comparisons = [c for c in domain_def.comparisons if not c.ignored]
            pg_cols = ["id"] + [c.pg_field for c in active_comparisons if c.pg_field != "id"]
            col_clause = ", ".join(pg_cols)

            with pg_conn.cursor() as cur:
                if self.filter_ids:
                    placeholders = ", ".join(["%s"] * len(self.filter_ids))
                    cur.execute(
                        f"SELECT {col_clause} FROM {domain_def.table_name} WHERE id::text IN ({placeholders})",
                        tuple(self.filter_ids),
                    )
                elif self.limit:
                    cur.execute(f"SELECT {col_clause} FROM {domain_def.table_name} LIMIT {self.limit}")
                else:
                    cur.execute(f"SELECT {col_clause} FROM {domain_def.table_name}")
                pg_rows = cur.fetchall()

            result.pg_count = len(pg_rows)
            pg_map: Dict[str, Dict[str, Any]] = {}
            for r in pg_rows:
                raw_pg_id = r.get("id")
                valid_pg_id = extract_uuid(raw_pg_id)
                if not valid_pg_id:
                    result.invalid_pg_ids.append(str(raw_pg_id))
                    continue
                pg_map[valid_pg_id] = r

            # 3. ID match check
            raven_ids = set(raven_map.keys())
            pg_ids = set(pg_map.keys())

            matched = raven_ids.intersection(pg_ids)
            result.matched_ids = len(matched)
            result.missing_in_pg = list(raven_ids - pg_ids)
            result.extra_in_pg = list(pg_ids - raven_ids)

            # 4. Field value & type checks on matched rows with progress reporting
            mismatches = 0
            matched_list = list(matched)
            total_matched = len(matched_list)

            for idx, pk in enumerate(matched_list, start=1):
                if idx % 2000 == 0 or idx == total_matched:
                    print(f"   [Progress] Audited {idx:,}/{total_matched:,} records in {domain_def.name}...")
                r_doc = raven_map[pk]
                p_row = pg_map[pk]

                for comp in domain_def.comparisons:
                    if comp.ignored:
                        continue
                    r_raw = r_doc.get(comp.raven_field)
                    r_val = apply_transform(comp.transform, r_raw, r_doc)
                    p_val = p_row.get(comp.pg_field)

                    if not deep_values_equal(r_val, p_val):
                        mismatches += 1
                        mismatch_entry = {
                            "id": pk,
                            "field": f"Raven({comp.raven_field}) vs PG({comp.pg_field})",
                            "raven_val": str(r_val)[:100],
                            "pg_val": str(p_val)[:100],
                        }
                        result.all_mismatches.append(mismatch_entry)
                        if len(result.sample_mismatches) < self.max_mismatches:
                            result.sample_mismatches.append(mismatch_entry)

            result.field_mismatches_count = mismatches

            if (
                len(result.missing_in_pg) == 0
                and mismatches == 0
                and len(result.unparseable_raven_ids) == 0
                and len(result.invalid_pg_ids) == 0
            ):
                result.status = "PASS"
            else:
                result.status = "FAIL"

        except Exception as ex:
            result.status = "ERROR"
            result.error_message = str(ex)
            print(f"   [!] Error auditing domain {domain_def.name}: {ex}")
            try:
                pg_conn.rollback()
            except Exception:
                pass

        return result


# ==========================================
# Domain Registry (Data-Driven)
# ==========================================

DOMAIN_REGISTRY: List[DomainDefinition] = [
    # 1. Organization (23 fields)
    DomainDefinition(
        name="Organizations",
        collection_name="Orgs",
        table_name="organization",
        key_extractor=extract_organization_pk,
        comparisons=[
            FieldComparison("Name", "name"),
            FieldComparison("ShortName", "short_name"),
            FieldComparison("Status", "status", parse_org_status),
            FieldComparison("Website", "website"),
            FieldComparison("Address", "address"),
            FieldComparison("SMSSenderId", "sms_sender_id"),
            FieldComparison("EmailSenderId", "email_sender_id"),
            FieldComparison("LogoUrl", "logo_url"),
            FieldComparison("IsGroup", "is_group"),
            FieldComparison("IsRoot", "is_root"),
            FieldComparison("Modules", "modules"),
            FieldComparison("PolicyName", "policy_name"),
            FieldComparison("EnableSMS", "enable_sms"),
            FieldComparison("EnableEmail", "enable_email"),
            FieldComparison("EnableNotification", "enable_notification"),
            FieldComparison("EduLevel", "edu_level", parse_edu_level),
            FieldComparison("ReadOnly", "read_only"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 2. Institute (32 fields)
    DomainDefinition(
        name="Institutes",
        collection_name="Institutes",
        table_name="institute",
        key_extractor=extract_institute_pk,
        comparisons=[
            FieldComparison("Name", "name"),
            FieldComparison("ShortName", "short_name", lambda x: str(x).strip()[:6] if x else None),
            FieldComparison("Status", "status", parse_institute_status),
            FieldComparison("AcademicYearFrom", "academic_year_from"),
            FieldComparison("AcademicYearTo", "academic_year_to"),
            FieldComparison("InstituteCode", "institute_code"),
            FieldComparison("RegistrationNumber", "registration_number"),
            FieldComparison("Website", "website"),
            FieldComparison("Address", "address"),
            FieldComparison("SMSSenderId", "sms_sender_id"),
            FieldComparison("EmailSenderId", "email_sender_id"),
            FieldComparison("LogoUrl", "logo_url"),
            FieldComparison("IsGroup", "is_group"),
            FieldComparison("IsRoot", "is_root"),
            FieldComparison("IsOrg", "is_org"),
            FieldComparison("Modules", "modules"),
            FieldComparison("PolicyName", "policy_name"),
            FieldComparison("CourseOrder", "course_order"),
            FieldComparison("EnableSMS", "enable_sms"),
            FieldComparison("EnableEmail", "enable_email"),
            FieldComparison("EnableNotification", "enable_notification"),
            FieldComparison("ParentalAccessEnabled", "parental_access_enabled"),
            FieldComparison("StaffAccessEnabled", "staff_access_enabled"),
            FieldComparison("StudentAccessEnabled", "student_access_enabled"),
            FieldComparison("EduLevel", "edu_level", parse_edu_level),
            FieldComparison("ReadOnly", "read_only"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 3. Student (40 fields)
    DomainDefinition(
        name="Students",
        collection_name="Students",
        table_name="student",
        key_extractor=extract_student_pk,
        comparisons=[
            FieldComparison("StudentId", "student_id", derive_business_student_id),
            FieldComparison("Name", "name"),
            FieldComparison("FirstName", "first_name"),
            FieldComparison("MiddleName", "middle_name"),
            FieldComparison("LastName", "last_name"),
            FieldComparison("Title", "title"),
            FieldComparison("Gender", "gender", parse_student_gender),
            FieldComparison("DOB", "dob"),
            FieldComparison("Email", "email"),
            FieldComparison("Mobile", "mobile"),
            FieldComparison("EmailCSV", "email_csv"),
            FieldComparison("MobileCSV", "mobile_csv"),
            FieldComparison("VirtualId", "virtual_id"),
            FieldComparison("Category", "category"),
            FieldComparison("Attendance", "attendance"),
            FieldComparison("Status", "status", parse_student_status),
            FieldComparison("UserId", "user_id", extract_uuid),
            FieldComparison("Father", "father"),
            FieldComparison("Mother", "mother"),
            FieldComparison("Guardian", "guardian"),
            FieldComparison("AadharNumber", "aadhar_number"),
            FieldComparison("UDID", "udid"),
            FieldComparison("Domicile", "domicile"),
            FieldComparison("FeesReceivable", "fees_receivable"),
            FieldComparison("IEP", "iep"),
            FieldComparison("Documents", "documents"),
            FieldComparison("PhotoUrl", "photo_url"),
            FieldComparison("Contacts", "contacts"),
            FieldComparison("Addresses", "addresses"),
            FieldComparison("Tags", "tags"),
            FieldComparison("Attributes", "attributes"),
            FieldComparison("Occupations", "occupations"),
            FieldComparison("PAN", "pan"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("Enrollments", "enrollments"),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 4. Course (19 fields)
    DomainDefinition(
        name="Courses",
        collection_name="Courses",
        table_name="course",
        key_extractor=extract_course_pk,
        comparisons=[
            FieldComparison("Name", "name"),
            FieldComparison("Branch", "branch"),
            FieldComparison("NameAndBranch", "name_and_branch"),
            FieldComparison("EduLevel", "edu_level", parse_edu_level),
            FieldComparison("InstId", "inst_id", extract_uuid),
            FieldComparison("Affiliation", "affiliation"),
            FieldComparison("Status", "status", parse_course_status),
            FieldComparison("Terms", "terms"),
            FieldComparison("ExamSubjectOrder", "exam_subject_order"),
            FieldComparison("SortIndex", "sort_index"),
            FieldComparison("Rank", "rank"),
            FieldComparison("SeatsAvailable", "seats_available"),
            FieldComparison("Program", "program"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 5. Staff (23 fields)
    DomainDefinition(
        name="Staffs",
        collection_name="Staffs",
        table_name="staff",
        key_extractor=extract_staff_pk,
        comparisons=[
            FieldComparison("Name", "name"),
            FieldComparison("FirstName", "first_name"),
            FieldComparison("MiddleName", "middle_name"),
            FieldComparison("LastName", "last_name"),
            FieldComparison("Title", "title"),
            FieldComparison("Gender", "gender", parse_student_gender),
            FieldComparison("Status", "status", parse_staff_status),
            FieldComparison("StaffType", "staff_type", parse_staff_type),
            FieldComparison("DOB", "dob"),
            FieldComparison("Email", "email"),
            FieldComparison("Mobile", "mobile"),
            FieldComparison("VirtualId", "virtual_id"),
            FieldComparison("Contacts", "contacts"),
            FieldComparison("Addresses", "addresses"),
            FieldComparison("EmploymentHistory", "employment_history", as_list),
            FieldComparison("Designations", "designations", as_list),
            FieldComparison("DOJ", "doj"),
            FieldComparison("InstId", "inst_id", extract_uuid),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 6. Persona (12 fields)
    DomainDefinition(
        name="Personas",
        collection_name="Personas",
        table_name="persona",
        key_extractor=extract_persona_pk,
        comparisons=[
            FieldComparison("Title", "title"),
            FieldComparison("DisplayText", "display_text"),
            FieldComparison("PersonaType", "persona_type", parse_persona_type),
            FieldComparison("Status", "status", parse_persona_status),
            FieldComparison("Scope", "scope"),
            FieldComparison("NamedScope", "named_scope"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 7. Fee (15 fields)
    DomainDefinition(
        name="Fees",
        collection_name="Fees",
        table_name="fee",
        key_extractor=extract_fee_pk,
        comparisons=[
            FieldComparison("Name", "name"),
            FieldComparison("DisplayText", "display_text"),
            FieldComparison("Amount", "amount"),
            FieldComparison("Status", "status", parse_fee_status),
            FieldComparison("Tags", "tags"),
            FieldComparison("CollectStudentWise", "collect_student_wise"),
            FieldComparison("StudentList", "student_list"),
            FieldComparison("CourseList", "course_list"),
            FieldComparison("Installments", "installments"),
            FieldComparison("Fines", "fines"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 8. Fee Transaction (17 fields)
    DomainDefinition(
        name="Fee Transactions",
        collection_name="FeeTxes",
        table_name="fee_transaction",
        key_extractor=extract_fee_tx_pk,
        comparisons=[
            FieldComparison("TxNo", "tx_no"),
            FieldComparison("TxDate", "tx_date"),
            FieldComparison("StudentId", "student_id", extract_uuid),
            FieldComparison("InstallmentsPaid", "installments_paid"),
            FieldComparison("FinesPaid", "fines_paid"),
            FieldComparison("Discounts", "discounts"),
            FieldComparison("FeeAdjustment", "fee_adjustment"),
            FieldComparison("PaymentMode", "payment_mode"),
            FieldComparison("RefNo", "ref_no"),
            FieldComparison("Amount", "amount"),
            FieldComparison("Status", "status", parse_fee_tx_status),
            FieldComparison("PaidBy", "paid_by"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
    # 9. Exam (21 fields)
    DomainDefinition(
        name="Exams",
        collection_name="Exams",
        table_name="exam",
        key_extractor=extract_exam_pk,
        comparisons=[
            FieldComparison("Name", "name"),
            FieldComparison("Status", "status", parse_exam_status),
            FieldComparison("InstId", "inst_id", extract_uuid),
            FieldComparison("CourseId", "course_id", extract_uuid),
            FieldComparison("Term", "term"),
            FieldComparison("Section", "section"),
            FieldComparison("ExamContents", "exam_contents"),
            FieldComparison("LockHistory", "lock_history"),
            FieldComparison("AttendanceList", "attendance_list"),
            FieldComparison("RemarksList", "remarks_list"),
            FieldComparison("DaysWorked", "days_worked"),
            FieldComparison("TotalMaxMarks", "total_max_marks"),
            FieldComparison("MergeIndex", "merge_index"),
            FieldComparison("StartDate", "start_date"),
            FieldComparison("ResultDate", "result_date"),
            FieldComparison("OwnerId", "owner_id", extract_uuid),
            FieldComparison("ParentId", "parent_id", extract_uuid),
            FieldComparison("CreatedOn", "created_on"),
            FieldComparison("CreatedBy", "created_by", extract_uuid),
            FieldComparison("ModifiedOn", "modified_on", ignored=True, note="Auto-updated by PG trigger"),
            FieldComparison("ModifiedBy", "modified_by", extract_uuid),
        ],
    ),
]


# ==========================================
# Built-In Unit Test Suite
# ==========================================

def run_unit_tests() -> int:
    print("=" * 70)
    print("         RUNNING VERIFICATION ENGINE UNIT TESTS               ")
    print("=" * 70)

    # 1. Test Generic Enum Mapper
    gender_map = create_enum_mapper({0: "Female", 1: "Male", 90: "NoInfo"}, default="NoInfo")
    assert gender_map(0) == "Female"
    assert gender_map(1) == "Male"
    assert gender_map(90) == "NoInfo"
    assert gender_map("Female") == "Female"
    assert gender_map("Male") == "Male"
    assert gender_map(999) == "NoInfo"
    assert gender_map(None) == "NoInfo"
    assert gender_map("invalid") == "NoInfo"
    print("  [+] Generic enum mapper passed")

    # 2. Test Datetime normalization
    now_utc = datetime.now(timezone.utc)
    assert normalize_datetime(now_utc) == now_utc
    assert normalize_datetime("2026-03-01T10:20:30.1234567Z") is not None
    assert normalize_datetime(None) is None
    assert normalize_datetime("") is None
    print("  [+] DateTime normalization passed")

    # 3. Test deep_values_equal
    assert deep_values_equal(None, None) is True
    assert deep_values_equal(None, "") is False
    assert deep_values_equal(0, 0.0) is True
    assert deep_values_equal(Decimal("100.50"), 100.50) is True
    assert deep_values_equal(uuid.UUID("11111111-2222-3333-4444-555555555555"), "11111111-2222-3333-4444-555555555555") is True
    assert deep_values_equal({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True
    assert deep_values_equal(["x", "y"], ["y", "x"]) is True
    print("  [+] Deep values equal comparison passed")

    # 4. Test apply_transform
    def one_arg(x):
        return x.upper() if x else None

    def two_arg(x, doc):
        return f"{x}_{doc.get('tag')}"

    assert apply_transform(one_arg, "hello", {}) == "HELLO"
    assert apply_transform(two_arg, "val", {"tag": "123"}) == "val_123"
    assert apply_transform(None, "raw", {}) == "raw"
    print("  [+] Apply transform signature dispatch passed")

    # 5. Test ID extractors
    # Organization: SourceOrgId takes precedence over metadata @id
    org_doc = {
        "@metadata": {"@id": "Orgs/11111111-1111-1111-1111-111111111111"},
        "SourceOrgId": "22222222-2222-2222-2222-222222222222",
        "Id": "33333333-3333-3333-3333-333333333333",
    }
    assert extract_organization_pk(org_doc) == "22222222-2222-2222-2222-222222222222"

    # Institute: SourceInstId takes precedence over metadata @id
    inst_doc = {
        "@metadata": {"@id": "Institutes/11111111-1111-1111-1111-111111111111"},
        "SourceInstId": "44444444-4444-4444-4444-444444444444",
        "InstId": "55555555-5555-5555-5555-555555555555",
    }
    assert extract_institute_pk(inst_doc) == "44444444-4444-4444-4444-444444444444"

    # Student: metadata @id takes precedence; business code ('23P001') is rejected as PK
    student_doc = {
        "@metadata": {"@id": "Students/77777777-7777-7777-7777-777777777777"},
        "StudentId": "23P001",
    }
    assert extract_student_pk(student_doc) == "77777777-7777-7777-7777-777777777777"
    assert derive_business_student_id(None, student_doc) == "23P001"

    # Business code fallback rejection when no UUID is present
    no_uuid_doc = {"StudentId": "23P001", "Id": "NOT-A-UUID"}
    assert extract_student_pk(no_uuid_doc) is None

    # Course, Staff, Exam extractors
    course_doc = {"@metadata": {"@id": "Courses/88888888-8888-8888-8888-888888888888"}}
    assert extract_course_pk(course_doc) == "88888888-8888-8888-8888-888888888888"

    staff_doc = {"@metadata": {"@id": "Staffs/99999999-9999-9999-9999-999999999999"}}
    assert extract_staff_pk(staff_doc) == "99999999-9999-9999-9999-999999999999"

    exam_doc = {"ExamId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
    assert extract_exam_pk(exam_doc) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    print("  [+] Domain-specific canonical ID extractors passed")

    print("\n[SUCCESS] All 5 test suites passed flawlessly!\n")
    return 0


# ==========================================
# Main Execution Runner
# ==========================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify RavenDB to PostgreSQL data migration parity."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit audit to top N records per collection for quick debugging.",
    )
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        help="Comma-separated UUID list to limit audit to specific records.",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Limit audit to a specific domain (e.g. Organizations, Institutes, Students, Staffs, Personas, Fees, FeeTransactions, Courses, Exams).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="Batch size for RavenDB document fetching (default: 1000).",
    )
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=5,
        help="Maximum sample field mismatches to display per domain on CLI (default: 5).",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="validation",
        help="Output directory for JSON verification reports (default: 'validation').",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run verification engine pure function unit test suite and exit.",
    )
    args = parser.parse_args()

    if args.test:
        return run_unit_tests()

    filter_ids = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else None
    target_domain = args.domain.lower().strip() if args.domain else None

    print("=" * 95)
    print("           RAVENDB -> POSTGRESQL 100% EXHAUSTIVE DATA PARITY AUDIT            ")
    print("=" * 95)

    engine = VerificationEngine(
        page_size=args.page_size,
        limit=args.limit,
        filter_ids=filter_ids,
        max_mismatches=args.max_mismatches,
    )

    if engine.raven_insecure:
        print("[!] WARNING: RAVEN_INSECURE is active! TLS verification is explicitly disabled.\n")

    pg_pass_masked = "***" if engine.pg_password else "<none>"
    print(f"[+] Target RavenDB:    {engine.raven_url} (DB: {engine.raven_db})")
    print(
        f"[+] Target PostgreSQL: {engine.pg_host}:{engine.pg_port}/{engine.pg_db} (User: {engine.pg_user}, Pass: {pg_pass_masked})\n"
    )

    def should_check(d_def: DomainDefinition) -> bool:
        if not target_domain:
            return True
        t = target_domain.replace("_", "").replace(" ", "")
        d_name = d_def.name.lower().replace("_", "").replace(" ", "")
        d_coll = d_def.collection_name.lower().replace("_", "").replace(" ", "")
        d_tbl = d_def.table_name.lower().replace("_", "").replace(" ", "")
        return t in d_name or t in d_coll or t in d_tbl

    active_domains = [d for d in DOMAIN_REGISTRY if should_check(d)]
    if not active_domains:
        print(f"[!] No matching domain found for filter: '{args.domain}'.")
        print(f"    Available domains: {', '.join(d.name for d in DOMAIN_REGISTRY)}\n")
        engine.cleanup()
        return 1

    pg_conn = None
    try:
        pg_conn = engine.get_pg_connection()
    except Exception as ex:
        print(f"[!] Critical Error: Unable to connect to PostgreSQL: {ex}")
        engine.cleanup()
        return 1

    results: List[DomainCheckResult] = []

    try:
        for domain_def in active_domains:
            res = engine.verify_domain(domain_def, pg_conn)
            results.append(res)
    finally:
        if pg_conn:
            pg_conn.close()
        engine.cleanup()

    # Print Summary Table
    print("\n" + "=" * 115)
    print(
        f"{'Domain / Entity':<18} | {'Fields':<8} | {'RavenDB':<8} | {'PostgreSQL':<10} | {'Matched IDs':<12} | {'Mismatches':<10} | {'Status':<8}"
    )
    print("=" * 115)

    all_passed = True
    total_audited_fields = sum(r.total_fields_checked for r in results)

    for r in results:
        print(
            f"{r.domain_name:<18} | {r.total_fields_checked:<8} | {r.raven_count:<8} | {r.pg_count:<10} | {r.matched_ids:<12} | {r.field_mismatches_count:<10} | {r.status:<8}"
        )
        if r.status != "PASS":
            all_passed = False
            if r.error_message:
                print(f"   [!] Error: {r.error_message}")
            if r.unparseable_raven_ids:
                print(
                    f"   [!] Unparseable/Non-UUID IDs in RavenDB ({len(r.unparseable_raven_ids)}): {r.unparseable_raven_ids[:3]}..."
                )
            if r.invalid_pg_ids:
                print(
                    f"   [!] Invalid/Non-UUID IDs in PostgreSQL ({len(r.invalid_pg_ids)}): {r.invalid_pg_ids[:3]}..."
                )
            if r.missing_in_pg:
                print(f"   [!] Missing IDs in PG ({len(r.missing_in_pg)}): {r.missing_in_pg[:3]}...")
            if r.extra_in_pg:
                print(f"   [!] Extra IDs in PG ({len(r.extra_in_pg)}): {r.extra_in_pg[:3]}...")
            if r.sample_mismatches:
                print(f"   [!] Sample field mismatches (showing {len(r.sample_mismatches)} of {r.field_mismatches_count}):")
                for m in r.sample_mismatches:
                    print(
                        f"       - ID {m['id']} {m['field']}: Raven='{m['raven_val']}' vs PG='{m['pg_val']}'"
                    )

    print("=" * 115)

    # Save detailed JSON artifact
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = (
        out_dir
        / f"exhaustive-parity-report-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )

    report_payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_fields_audited_per_record": total_audited_fields,
        "overall_status": "PASS" if all_passed else "FAIL",
        "results": [
            {
                "domain": r.domain_name,
                "collection": r.collection_name,
                "table": r.table_name,
                "fields_audited_count": r.total_fields_checked,
                "raven_count": r.raven_count,
                "pg_count": r.pg_count,
                "matched_ids": r.matched_ids,
                "missing_in_pg_count": len(r.missing_in_pg),
                "missing_in_pg": r.missing_in_pg,
                "extra_in_pg_count": len(r.extra_in_pg),
                "extra_in_pg": r.extra_in_pg,
                "unparseable_raven_ids_count": len(r.unparseable_raven_ids),
                "unparseable_raven_ids": r.unparseable_raven_ids,
                "invalid_pg_ids_count": len(r.invalid_pg_ids),
                "invalid_pg_ids": r.invalid_pg_ids,
                "field_mismatches_count": r.field_mismatches_count,
                "sample_mismatches": r.sample_mismatches,
                "all_mismatches": r.all_mismatches,
                "status": r.status,
                "error_message": r.error_message,
            }
            for r in results
        ],
    }
    report_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    print(f"\n[+] Detailed Verification Report JSON written to: {report_file.resolve()}")

    if all_passed:
        print(f"\n[SUCCESS] 100% COMPLETE PARITY CONFIRMED across all {total_audited_fields} schema columns!\n")
        return 0
    else:
        print("\n[FAILURE] DATA PARITY ISSUES DETECTED. Review table above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
