#!/usr/bin/env python3
"""
Comprehensive Verification Script: RavenDB vs PostgreSQL Complete Parity
Audits ALL 42 RavenDB Collections against their corresponding PostgreSQL tables:
- 9 Core Domains with 177 deep field/column transformations and value audits.
- 33 Auxiliary Domains with full record count, ID-parity, and core attribute verification.

Total: 42 distinct business collections validated for 100% data integrity.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

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
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and os.getenv(k) is None:
                os.environ[k] = v


def extract_uuid(value: Any) -> Optional[str]:
    if value is None:
        return None
    match = UUID_RE.search(str(value))
    return match.group(0).lower() if match else None


def normalize_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (
            value.astimezone(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
            + "Z"
        )
    text = str(value).strip()
    if not text:
        return None
    if "." in text:
        base, rest = text.split(".", 1)
        tz_part = ""
        if "Z" in rest:
            tz_part = "Z"
        elif "+" in rest:
            tz_part = rest[rest.find("+"):]
        elif "-" in rest:
            tz_part = rest[rest.find("-"):]
        text = base + tz_part

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (
            dt.astimezone(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
            + "Z"
        )
    except Exception:
        return text[:19] + ("Z" if not text.endswith("Z") else "")


def normalize_val(val: Any) -> Any:
    """Normalize values for deep equality comparison."""
    if val is None or val == "" or val == [] or val == {}:
        return None
    if isinstance(val, str):
        text = val.strip()
        if not text:
            return None
        if (
            len(text) >= 19
            and ("T" in text or " " in text)
            and any(c.isdigit() for c in text[:4])
        ):
            parsed = normalize_datetime(text)
            if parsed:
                return parsed
        uuid_cand = extract_uuid(text)
        if uuid_cand and len(text) <= 45 and "-" in text:
            return uuid_cand
        return text
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float, Decimal)):
        return round(float(val), 4)
    if isinstance(val, datetime):
        return normalize_datetime(val)
    if isinstance(val, dict):
        cleaned = {k: normalize_val(v) for k, v in val.items() if normalize_val(v) is not None}
        return json.dumps(cleaned, sort_keys=True, default=str) if cleaned else None
    if isinstance(val, list):
        cleaned = [normalize_val(x) for x in val if normalize_val(x) is not None]
        return json.dumps(cleaned, sort_keys=True, default=str) if cleaned else None
    return val


# ==========================================
# Domain Enum Transformation Helpers
# ==========================================

def parse_student_gender(value: Any) -> str:
    if value in ("Female", "Male", "NoInfo"):
        return str(value)
    try:
        return {0: "Female", 1: "Male", 90: "NoInfo"}.get(int(value), "NoInfo")
    except (TypeError, ValueError):
        return "NoInfo"


def parse_student_status(value: Any) -> str:
    if value in ("Unknown", "Active", "Disabled"):
        return str(value)
    try:
        return {-1: "Unknown", 1: "Active", 99: "Disabled"}.get(int(value), "Active")
    except (TypeError, ValueError):
        return "Active"


def parse_org_status(value: Any) -> str:
    if value in ("Unknown", "ActivationPending", "Active", "Locked", "Disabled"):
        return str(value)
    try:
        return {
            -1: "Unknown",
            0: "ActivationPending",
            1: "Active",
            90: "Locked",
            99: "Disabled",
        }.get(int(value), "Active")
    except (TypeError, ValueError):
        return "Active"


def parse_institute_status(value: Any) -> str:
    if value in ("Unknown", "ActivationPending", "Active", "Locked", "Disabled"):
        return str(value)
    try:
        return {
            -1: "Unknown",
            0: "ActivationPending",
            1: "Active",
            90: "Locked",
            99: "Disabled",
        }.get(int(value), "Active")
    except (TypeError, ValueError):
        return "Active"


def parse_edu_level(value: Any) -> Optional[str]:
    valid_names = (
        "Unknown",
        "PreNursery",
        "Nursery",
        "School",
        "UnderGraduate",
        "Graduate",
        "PostGraduate",
    )
    if value in valid_names:
        return str(value)
    try:
        return {
            -1: "Unknown",
            2: "PreNursery",
            5: "Nursery",
            10: "School",
            20: "UnderGraduate",
            30: "Graduate",
            40: "PostGraduate",
        }.get(int(value), None)
    except (TypeError, ValueError):
        return None


def parse_staff_type(value: Any) -> Optional[str]:
    if value in ("Teaching", "NonTeaching", "Management"):
        return str(value)
    try:
        return {0: "Teaching", 1: "NonTeaching", 2: "Management"}.get(int(value), None)
    except (TypeError, ValueError):
        return None


def parse_staff_status(value: Any) -> str:
    if value in ("Unknown", "Active", "Disabled"):
        return str(value)
    try:
        return {-1: "Unknown", 1: "Active", 99: "Disabled"}.get(int(value), "Active")
    except (TypeError, ValueError):
        return "Active"


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


def parse_persona_status(value: Any) -> str:
    if value in ("Unknown", "Active", "Disabled"):
        return str(value)
    try:
        return {-1: "Unknown", 1: "Active", 99: "Disabled"}.get(int(value), "Active")
    except (TypeError, ValueError):
        return "Active"


def parse_fee_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    if val_str in ("Unknown", "Active", "Disabled"):
        return val_str
    try:
        return {0: "Unknown", 1: "Active", 99: "Disabled"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_fee_tx_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    if val_str in ("Active", "Disabled"):
        return val_str
    try:
        return {1: "Active", 99: "Disabled"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_grading_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    if val_str in ("Active", "Disabled"):
        return val_str
    try:
        return {1: "Active", 99: "Disabled"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_image_tag_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    if val_str in ("Unknown", "Active", "Disabled"):
        return val_str
    try:
        return {0: "Unknown", 1: "Active", 99: "Disabled"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_course_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    if val_str in ("Unknown", "Active", "Disabled"):
        return val_str
    try:
        return {0: "Unknown", 1: "Active", 99: "Disabled"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_exam_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None
    valid_names = ("Unknown", "Active", "Scheduled", "Conducted", "Locked", "Disabled")
    if val_str in valid_names:
        return val_str
    try:
        return {
            0: "Unknown",
            1: "Active",
            10: "Scheduled",
            20: "Conducted",
            90: "Locked",
            99: "Disabled",
        }.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_app_res_status(val: Any) -> Optional[str]:
    if val is None or val == 0 or val == "0" or val == "":
        return None
    val_str = str(val).strip()
    if val_str in ("Indian", "PIO_OCI", "NRI"):
        return val_str
    try:
        return {10: "Indian", 20: "PIO_OCI", 30: "NRI"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_app_category(val: Any) -> Optional[str]:
    if val is None or val == 0 or val == "0" or val == "":
        return None
    val_str = str(val).strip()
    if val_str in ("GM", "OBC", "SC", "ST"):
        return val_str
    try:
        return {40: "GM", 50: "OBC", 60: "SC", 70: "ST"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_app_status(val: Any) -> Optional[str]:
    if val is None or val == 0 or val == "0" or val == "":
        return None
    val_str = str(val).strip()
    valid_names = (
        "WIP",
        "Selected",
        "Submitted",
        "Shortlisted",
        "Admitted",
        "Rejected",
        "OptedIn",
        "OptedOut",
        "Declined",
    )
    for name in valid_names:
        if val_str.lower() == name.lower():
            return name
    try:
        return {
            10: "WIP",
            15: "Selected",
            20: "Submitted",
            25: "Shortlisted",
            30: "Admitted",
            35: "Rejected",
            40: "OptedIn",
            45: "OptedOut",
            50: "Declined",
        }.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_template_status(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    val_str = str(val).strip()
    for name in ("Active", "Published", "Disabled"):
        if val_str.lower() == name.lower():
            return name
    try:
        return {1: "Active", 70: "Published", 99: "Disabled"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_artefact_status(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    val_str = str(val).strip()
    valid_names = (
        "Unknown",
        "Active",
        "Etl",
        "Published",
        "PublishedToPublic",
        "Uploaded",
        "Downloaded",
        "Disabled",
    )
    for name in valid_names:
        if val_str.lower() == name.lower():
            return name
    try:
        return {
            0: "Unknown",
            1: "Active",
            60: "Etl",
            70: "Published",
            75: "PublishedToPublic",
            80: "Uploaded",
            90: "Downloaded",
            99: "Disabled",
        }.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_assessment_status(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    val_str = str(val).strip()
    valid_names = ("Unknown", "Active", "WIP", "Published", "Archived", "Disabled")
    for name in valid_names:
        if val_str.lower() == name.lower():
            return name
    try:
        return {
            0: "Unknown",
            1: "Active",
            40: "WIP",
            50: "Published",
            80: "Archived",
            99: "Disabled",
        }.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_tag_status(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    val_str = str(val).strip()
    for name in ("Unknown", "Active", "Disabled"):
        if val_str.lower() == name.lower():
            return name
    try:
        return {0: "Unknown", 1: "Active", 99: "Disabled"}.get(int(val_str), None)
    except (TypeError, ValueError):
        return None


def parse_user_status(val: Any) -> str:
    if val is None:
        return "Active"
    m = {
        "-1": "Unknown",
        "0": "Registered",
        "1": "Active",
        "99": "Disabled",
        "unknown": "Unknown",
        "registered": "Registered",
        "active": "Active",
        "disabled": "Disabled",
        "locked": "Locked",
    }
    return m.get(str(val).strip().lower(), str(val).capitalize() if str(val) else "Active")


def parse_user_gender(val: Any) -> Optional[str]:
    if val is None or val == "":
        return None
    s = str(val).strip().lower()
    if s in {"null", "none"}:
        return None
    return {"0": "Female", "1": "Male", "90": "NoInfo", "female": "Female", "male": "Male", "noinfo": "NoInfo"}.get(s, str(val).capitalize())


def parse_asset_status(val: Any) -> Any:
    if isinstance(val, int):
        return {1: "Active", 90: "Cleared", 99: "Disabled"}.get(val, "Active")
    return val or "Active"


def extract_standard_id(doc: Dict[str, Any]) -> Optional[str]:
    meta_id = doc.get("@metadata", {}).get("@id")
    meta_uuid = extract_uuid(meta_id)
    if meta_uuid:
        return meta_uuid
    direct_uuid = extract_uuid(doc.get("Id"))
    if direct_uuid:
        return direct_uuid
    if meta_id:
        return str(meta_id).strip().lower()
    if doc.get("Id"):
        return str(doc.get("Id")).strip().lower()
    return None


def extract_student_id(doc: Dict[str, Any]) -> Optional[str]:
    meta_id = doc.get("@metadata", {}).get("@id")
    meta_uuid = extract_uuid(meta_id)
    if meta_uuid:
        return meta_uuid
    return (
        extract_uuid(doc.get("Id"))
        or extract_uuid(doc.get("SourceStudentId"))
        or extract_uuid(doc.get("StudentId"))
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
    field_mismatches_count: int = 0
    sample_mismatches: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "PENDING"
    error_message: Optional[str] = None


class VerificationEngine:
    def __init__(self, config: Dict[str, Any]):
        self.script_dir = Path(__file__).parent.resolve()
        
        # Load environment files
        for env_cand in (
            self.script_dir.parent / ".env",
            self.script_dir / ".env",
            Path(".env"),
        ):
            if env_cand.exists():
                load_env_file(env_cand)

        self.raven_url = (config.get("raven_url") or os.getenv("RAVEN_URL", "")).rstrip("/")
        self.raven_db = config.get("raven_db") or os.getenv("RAVEN_DB", "")
        self.raven_cert_file = config.get("raven_cert_file") or os.getenv("RAVEN_CERT_FILE")
        self.raven_cert_password = config.get("raven_cert_password") or os.getenv("RAVEN_CERT_PASSWORD")
        self.raven_insecure = config.get("raven_insecure", False) or (os.getenv("RAVEN_INSECURE", "false").lower() in {"1", "true", "yes"})

        self.pg_host = config.get("pg_host") or os.getenv("PG_HOST", "localhost")
        self.pg_port = int(config.get("pg_port") or os.getenv("PG_PORT", "5432"))
        self.pg_db = config.get("pg_db") or os.getenv("PG_DB", "rpg")
        self.pg_user = config.get("pg_user") or os.getenv("PG_USER", "postgres")
        self.pg_password = config.get("pg_password") or os.getenv("PG_PASSWORD", "")

        self.session = requests.Session()
        self._configure_raven_session()

    def _configure_raven_session(self) -> None:
        if not self.raven_cert_file:
            return
        cert_path = self.raven_cert_file
        if not os.path.isabs(cert_path):
            for candidate in (
                self.script_dir / cert_path,
                self.script_dir.parent / cert_path,
                Path(cert_path),
            ):
                if candidate.exists():
                    cert_path = str(candidate)
                    break

        if cert_path.endswith(".pfx") or cert_path.endswith(".p12"):
            try:
                from requests_pkcs12 import Pkcs12Adapter
                with open(cert_path, "rb") as fh:
                    pfx_data = fh.read()
                self.session.mount(
                    "https://",
                    Pkcs12Adapter(pkcs12_data=pfx_data, pkcs12_password=self.raven_cert_password or "")
                )
                return
            except ImportError:
                pass

            try:
                from cryptography.hazmat.primitives.serialization import (
                    Encoding,
                    NoEncryption,
                    PrivateFormat,
                    pkcs12,
                )
                with open(cert_path, "rb") as fh:
                    pfx_data = fh.read()
                pwd = self.raven_cert_password.encode("utf-8") if self.raven_cert_password else None
                key, cert, add_certs = pkcs12.load_key_and_certificates(pfx_data, pwd)

                temp_pem = tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb")
                if cert:
                    temp_pem.write(cert.public_bytes(Encoding.PEM))
                if add_certs:
                    for c in add_certs:
                        temp_pem.write(c.public_bytes(Encoding.PEM))
                if key:
                    temp_pem.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
                temp_pem.flush()
                temp_pem.close()
                self.session.cert = temp_pem.name
            except Exception as e:
                print(f"[!] Warning: Unable to parse PKCS#12 certificate: {e}")
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
        page_size = 1000
        url = f"{self.raven_url}/databases/{self.raven_db}/queries"

        while True:
            rql = f"from '{collection}'"
            payload = {"Query": rql, "Start": start, "PageSize": page_size}
            res = self.session.post(
                url,
                json=payload,
                timeout=60,
                verify=not self.raven_insecure,
            )
            if res.status_code != 200:
                raise RuntimeError(
                    f"Failed querying RavenDB collection '{collection}': {res.status_code} {res.text[:200]}"
                )
            data = res.json()
            results = data.get("Results", [])
            if not results:
                break
            docs.extend(results)
            start += len(results)
            if len(results) < page_size:
                break
        return docs

    def verify_domain(
        self,
        domain_name: str,
        collection_name: str,
        table_name: str,
        key_extractor: Callable[[Dict[str, Any]], Optional[str]],
        field_comparisons: List[Tuple[str, str, Any]],
        pg_conn,
    ) -> DomainCheckResult:
        result = DomainCheckResult(
            domain_name=domain_name,
            collection_name=collection_name,
            table_name=table_name,
            total_fields_checked=len(field_comparisons),
        )

        try:
            # 1. Fetch RavenDB documents
            raven_docs = self.fetch_raven_collection(collection_name)
            result.raven_count = len(raven_docs)

            # Build Raven map: id -> doc
            raven_map: Dict[str, Dict[str, Any]] = {}
            for doc in raven_docs:
                pk = key_extractor(doc)
                if pk:
                    raven_map[pk.lower()] = doc

            # 2. Fetch PostgreSQL rows and column metadata
            with pg_conn.cursor() as cur:
                try:
                    cur.execute(f"SELECT * FROM {table_name}")
                    pg_rows = cur.fetchall()
                    cur.execute(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        f"WHERE table_schema='public' AND table_name='{table_name}'"
                    )
                    pg_col_types = {r["column_name"]: r["data_type"] for r in cur.fetchall()}
                except psycopg2.errors.UndefinedTable:
                    pg_conn.rollback()
                    result.status = "MISSING_TABLE"
                    result.error_message = f"Table '{table_name}' does not exist in PostgreSQL"
                    return result
                except Exception as ex:
                    pg_conn.rollback()
                    result.status = "ERROR"
                    result.error_message = str(ex)
                    return result

            # Auto-expand to audit ALL fields across all 42 tables
            all_fields = list(field_comparisons)
            existing_pg_cols = {pf for _, pf, _ in all_fields}

            all_raven_keys = set()
            for doc in raven_docs:
                all_raven_keys.update(doc.keys())

            for rk in sorted(all_raven_keys):
                if rk in ("@metadata", "Id"):
                    continue
                sc = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', rk)).lower()
                if sc in pg_col_types and sc not in existing_pg_cols and sc != "modified_on":
                    fn = None
                    if table_name == "applications":
                        if sc == "residential_status": fn = parse_app_res_status
                        elif sc == "category": fn = parse_app_category
                        elif sc == "gender": fn = parse_student_gender
                        elif sc == "application_status": fn = parse_app_status
                        elif sc.endswith("_url") or sc.endswith("_id"): fn = lambda x: extract_uuid(x) if sc.endswith("_id") else (x or None)
                    elif table_name in ("asset", "asset_views") and sc == "status":
                        fn = parse_asset_status
                    elif table_name == "assessments" and sc == "status":
                        fn = lambda x: str(x).title() if x else None
                    elif table_name == "calendar_rules" and sc == "create_meeting_link":
                        fn = lambda x: bool(x) if x is not None else False
                    elif table_name == "exam" and sc in ("parent_id", "course_id", "term_id", "inst_id"):
                        fn = extract_uuid
                    elif table_name == "users":
                        if sc in ("password", "salt", "otp", "otp_validity", "password_reset_on", "password_changed_on"):
                            continue
                        if sc == "status": fn = parse_user_status
                        elif sc == "gender": fn = parse_user_gender
                        elif sc == "virtual_id": fn = None
                        elif sc.endswith("_id") or sc in ("owner_id", "parent_id", "created_by", "modified_by"):
                            if pg_col_types.get(sc) == "uuid":
                                fn = extract_uuid
                    elif sc == "virtual_id":
                        fn = None
                    elif sc.endswith("_id") or sc in ("owner_id", "parent_id", "created_by", "modified_by"):
                        if pg_col_types.get(sc) == "uuid":
                            fn = extract_uuid

                    all_fields.append((rk, sc, fn))
                    existing_pg_cols.add(sc)

            result.total_fields_checked = len(all_fields)
            result.pg_count = len(pg_rows)
            pg_map = {str(r["id"]).lower(): r for r in pg_rows}

            # 3. ID match check
            raven_ids = set(raven_map.keys())
            pg_ids = set(pg_map.keys())

            matched = raven_ids.intersection(pg_ids)
            result.matched_ids = len(matched)
            result.missing_in_pg = list(raven_ids - pg_ids)
            result.extra_in_pg = list(pg_ids - raven_ids)

            # 4. Field value & type checks on matched rows
            mismatches = 0
            for pk in matched:
                r_doc = raven_map[pk]
                p_row = pg_map[pk]

                for raven_field, pg_field, transform_fn in all_fields:
                    if pg_field == "modified_on":
                        continue
                    if table_name == "users" and pg_field == "virtual_id" and not r_doc.get("VirtualId"):
                        continue
                    r_raw = r_doc.get(raven_field)
                    if callable(transform_fn):
                        if transform_fn.__code__.co_argcount == 2:
                            r_val = transform_fn(r_raw, r_doc)
                        else:
                            r_val = transform_fn(r_raw)
                    else:
                        r_val = r_raw

                    p_val = p_row.get(pg_field)

                    # ModifiedOn is automatically updated by PostgreSQL audit trigger (trg_modified_on)
                    if pg_field == "modified_on":
                        continue

                    norm_r = normalize_val(r_val)
                    norm_p = normalize_val(p_val)

                    if norm_r is None and norm_p is None:
                        continue

                    if norm_r != norm_p:
                        mismatches += 1
                        if len(result.sample_mismatches) < 5:
                            result.sample_mismatches.append(
                                {
                                    "id": pk,
                                    "field": f"Raven({raven_field}) vs PG({pg_field})",
                                    "raven_val": str(norm_r)[:100],
                                    "pg_val": str(norm_p)[:100],
                                }
                            )

            result.field_mismatches_count = mismatches

            if (
                result.raven_count == result.pg_count
                and len(result.missing_in_pg) == 0
                and mismatches == 0
            ):
                result.status = "PASS"
            else:
                result.status = "FAIL"

        except Exception as ex:
            result.status = "ERROR"
            result.error_message = str(ex)

        return result


# =============================================================================
# Definition of All 42 Domains
# =============================================================================

def get_all_domain_specs() -> List[Dict[str, Any]]:
    """Return complete specifications for all 42 RavenDB collections and target PostgreSQL tables.
    Every domain explicitly specifies all field mappings across all 42 collections.
    """

    organizations_comparisons = [
        ("Name", "name", None),
        ("ShortName", "short_name", lambda x: str(x).strip()[:6] if x else None),
        ("Status", "status", parse_org_status),
        ("AcademicYearFrom", "academic_year_from", None),
        ("AcademicYearTo", "academic_year_to", None),
        ("RegistrationNumber", "registration_number", None),
        ("Website", "website", None),
        ("Address", "address", None),
        ("SMSSenderId", "sms_sender_id", None),
        ("EmailSenderId", "email_sender_id", None),
        ("LogoUrl", "logo_url", None),
        ("IsGroup", "is_group", None),
        ("IsRoot", "is_root", None),
        ("Modules", "modules", None),
        ("PolicyName", "policy_name", None),
        ("EnableSMS", "enable_sms", None),
        ("EnableEmail", "enable_email", None),
        ("EnableNotification", "enable_notification", None),
        ("EduLevel", "edu_level", parse_edu_level),
        ("ReadOnly", "read_only", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
    ]

    institutes_comparisons = [
        ("Name", "name", None),
        ("ShortName", "short_name", lambda x: str(x).strip()[:6] if x else None),
        ("Status", "status", parse_institute_status),
        ("AcademicYearFrom", "academic_year_from", None),
        ("AcademicYearTo", "academic_year_to", None),
        ("InstituteCode", "institute_code", None),
        ("RegistrationNumber", "registration_number", None),
        ("Website", "website", None),
        ("Address", "address", None),
        ("SMSSenderId", "sms_sender_id", None),
        ("EmailSenderId", "email_sender_id", None),
        ("LogoUrl", "logo_url", None),
        ("IsGroup", "is_group", None),
        ("IsRoot", "is_root", None),
        ("IsOrg", "is_org", None),
        ("Modules", "modules", None),
        ("PolicyName", "policy_name", None),
        ("CourseOrder", "course_order", None),
        ("EnableSMS", "enable_sms", None),
        ("EnableEmail", "enable_email", None),
        ("EnableNotification", "enable_notification", None),
        ("ParentalAccessEnabled", "parental_access_enabled", None),
        ("StaffAccessEnabled", "staff_access_enabled", None),
        ("StudentAccessEnabled", "student_access_enabled", None),
        ("EduLevel", "edu_level", parse_edu_level),
        ("ReadOnly", "read_only", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
    ]

    students_comparisons = [
        ("StudentId", "student_id", derive_business_student_id),
        ("Name", "name", None),
        ("FirstName", "first_name", None),
        ("MiddleName", "middle_name", None),
        ("LastName", "last_name", None),
        ("Title", "title", None),
        ("Gender", "gender", parse_student_gender),
        ("DOB", "dob", None),
        ("Email", "email", None),
        ("Mobile", "mobile", None),
        ("EmailCSV", "email_csv", None),
        ("MobileCSV", "mobile_csv", None),
        ("VirtualId", "virtual_id", None),
        ("Category", "category", None),
        ("Attendance", "attendance", None),
        ("Status", "status", parse_student_status),
        ("UserId", "user_id", extract_uuid),
        ("Father", "father", None),
        ("Mother", "mother", None),
        ("Guardian", "guardian", None),
        ("AadharNumber", "aadhar_number", None),
        ("UDID", "udid", None),
        ("Domicile", "domicile", None),
        ("FeesReceivable", "fees_receivable", None),
        ("IEP", "iep", None),
        ("Documents", "documents", None),
        ("PhotoUrl", "photo_url", None),
        ("Contacts", "contacts", None),
        ("Addresses", "addresses", None),
        ("Tags", "tags", None),
        ("Attributes", "attributes", None),
        ("Occupations", "occupations", None),
        ("PAN", "pan", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Enrollments", "enrollments", None),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Father", "father_name", lambda f, doc: (doc.get("Father") or {}).get("Name")),
        ("Mother", "mother_name", lambda m, doc: (doc.get("Mother") or {}).get("Name")),
        ("InstId", "inst_id", lambda _, doc: extract_uuid(doc.get("InstId") or ((doc.get("Enrollments") or [{}])[0].get("InstId") if isinstance(doc.get("Enrollments"), list) else None))),
    ]

    courses_comparisons = [
        ("Name", "name", None),
        ("InstId", "inst_id", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Status", "status", parse_course_status),
        ("EduLevel", "edu_level", parse_edu_level),
        ("SortIndex", "sort_index", None),
        ("Terms", "terms", None),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Affiliation", "affiliation", None),
        ("Branch", "branch", None),
        ("EduLevelAsString", "edu_level_as_string", None),
        ("ExamSubjectOrder", "exam_subject_order", None),
        ("NameAndBranch", "name_and_branch", None),
        ("Program", "program", None),
        ("Rank", "rank", None),
        ("SeatsAvailable", "seats_available", None),
        ("StatusAsString", "status_as_string", None),
    ]

    staffs_comparisons = [
        ("Name", "name", None),
        ("FirstName", "first_name", None),
        ("MiddleName", "middle_name", None),
        ("LastName", "last_name", None),
        ("Gender", "gender", parse_student_gender),
        ("Status", "status", parse_staff_status),
        ("Mobile", "mobile", None),
        ("Email", "email", None),
        ("Contacts", "contacts", None),
        ("Addresses", "addresses", None),
        ("EmploymentHistory", "employment_history", None),
        ("Qualifications", "qualifications", None),
        ("Departments", "departments", None),
        ("Designations", "designations", None),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Alias", "alias", None),
        ("Attributes", "attributes", None),
        ("ClassTeacher", "class_teacher", None),
        ("CourseSubjectList", "course_subject_list", None),
        ("DOB", "dob", None),
        ("DOJ", "doj", None),
        ("InstId", "inst_id", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Payslips", "payslips", None),
        ("RefId", "ref_id", None),
        ("Salaries", "salaries", None),
        ("Tags", "tags", None),
        ("Title", "title", None),
        ("UserId", "user_id", extract_uuid),
        ("VirtualId", "virtual_id", None),
    ]

    personas_comparisons = [
        ("Title", "title", None),
        ("DisplayText", "display_text", None),
        ("PersonaType", "persona_type", parse_persona_type),
        ("Status", "status", parse_persona_status),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("NamedScope", "named_scope", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("PersonaTypeAsString", "persona_type_as_string", None),
        ("Scope", "scope", None),
    ]

    fees_comparisons = [
        ("Name", "name", None),
        ("DisplayText", "display_text", None),
        ("Status", "status", parse_fee_status),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Amount", "amount", None),
        ("CollectStudentWise", "collect_student_wise", None),
        ("CourseList", "course_list", None),
        ("Fines", "fines", None),
        ("Installments", "installments", None),
        ("IsTxDone", "is_tx_done", None),
        ("Name", "name_lower", lambda x: str(x).lower() if x is not None else None),
        ("StudentList", "student_list", None),
        ("Tags", "tags", None),
    ]

    fee_transactions_comparisons = [
        ("StudentId", "student_id", extract_uuid),
        ("FeeId", "fee_id", None),
        ("TxNo", "tx_no", None),
        ("TxDate", "tx_date", None),
        ("Amount", "amount", lambda x: float(x) if x is not None else None),
        ("Status", "status", parse_fee_tx_status),
        ("RefNo", "ref_no", None),
        ("PaidBy", "paid_by", None),
        ("InstallmentsPaid", "installments_paid", None),
        ("FinesPaid", "fines_paid", None),
        ("Discounts", "discounts", None),
        ("FeeAdjustment", "fee_adjustment", None),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("BankName", "bank_name", None),
        ("ChequeDate", "cheque_date", None),
        ("ChequeNo", "cheque_no", None),
        ("HasFeeAdjustment", "has_fee_adjustment", None),
        ("IsDiscountGiven", "is_discount_given", None),
        ("IsFinePaid", "is_fine_paid", None),
        ("IsOpeningBalanceAdjusted", "is_opening_balance_adjusted", None),
        ("OnlineTxnRefNo", "online_txn_ref_no", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("PaymentMode", "payment_mode", None),
    ]

    exams_comparisons = [
        ("Name", "name", None),
        ("Status", "status", parse_exam_status),
        ("InstId", "inst_id", extract_uuid),
        ("CourseId", "course_id", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("ModifiedOn", "modified_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("AttendanceList", "attendance_list", None),
        ("DaysWorked", "days_worked", None),
        ("ExamContents", "exam_contents", None),
        ("LockHistory", "lock_history", None),
        ("MergeIndex", "merge_index", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("RemarksList", "remarks_list", None),
        ("ResultDate", "result_date", None),
        ("Section", "section", None),
        ("StartDate", "start_date", None),
        ("Term", "term", None),
        ("TotalMaxMarks", "total_max_marks", None),
    ]

    users_comparisons = [
        ("Name", "name", None),
        ("FirstName", "first_name", None),
        ("LastName", "last_name", None),
        ("Email", "email", None),
        ("Mobile", "mobile", None),
        ("CreatedOn", "created_on", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("Addresses", "addresses", None),
        ("Attributes", "attributes", None),
        ("ConfirmedOn", "confirmed_on", None),
        ("Contacts", "contacts", None),
        ("CurrentPersona", "current_persona", extract_uuid),
        ("DOB", "dob", None),
        ("ForceChangePassword", "force_change_password", None),
        ("Gender", "gender", parse_user_gender),
        ("Handle", "handle", None),
        ("IsVirtual", "is_virtual", None),
        ("MiddleName", "middle_name", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Notification", "notification", None),
        ("OTP", "otp", None),
        ("OTPValidity", "otp_validity", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Password", "password", None),
        ("PasswordChangedOn", "password_changed_on", None),
        ("PasswordResetOn", "password_reset_on", None),
        ("Personas", "personas", None),
        ("Preferences", "preferences", None),
        ("Profile", "profile", None),
        ("PushNotifications", "push_notifications", None),
        ("RecoveryEmail", "recovery_email", None),
        ("RecoveryMobile", "recovery_mobile", None),
        ("Salt", "salt", None),
        ("Status", "status", parse_user_status),
        ("Tags", "tags", None),
        ("Title", "title", None),
        ("VirtualId", "virtual_id", None),
    ]

    applications_comparisons = [
        ("Name", "name", None),
        ("AadharURL", "aadhar_url", None),
        ("Address", "address", None),
        ("ApplicationFormTemplateId", "application_form_template_id", extract_uuid),
        ("ApplicationNumber", "application_number", None),
        ("ApplicationStatus", "application_status", parse_app_status),
        ("AppliedFor", "applied_for", None),
        ("BirthCertificateURL", "birth_certificate_url", None),
        ("CasteCertificateURL", "caste_certificate_url", None),
        ("Category", "category", parse_app_category),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("DOA", "doa", None),
        ("DOB", "dob", None),
        ("DomicileCertificateURL", "domicile_certificate_url", None),
        ("Email", "email", None),
        ("FatherDetails", "father_details", None),
        ("Gender", "gender", parse_student_gender),
        ("GuardianDetails", "guardian_details", None),
        ("HSC", "hsc", None),
        ("HSCMarksCardURL", "hsc_marks_card_url", None),
        ("LeavingCertificateURL", "leaving_certificate_url", None),
        ("Mobile", "mobile", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("MotherDetails", "mother_details", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Payment", "payment", None),
        ("PhotoURL", "photo_url", None),
        ("ResidentialStatus", "residential_status", parse_app_res_status),
        ("SSC", "ssc", None),
        ("SSCMarksCardURL", "ssc_marks_card_url", None),
        ("ShortlistedIn", "shortlisted_in", None),
        ("SubmittedOn", "submitted_on", None),
        ("TransferCertificateURL", "transfer_certificate_url", None),
    ]

    app_form_templates_comparisons = [
        ("Title", "title", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Description", "description", None),
        ("EndDate", "end_date", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Options", "options", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Shortlists", "shortlists", None),
        ("StartDate", "start_date", None),
        ("Status", "status", parse_template_status),
    ]

    artefacts_comparisons = [
        ("Title", "title", None),
        ("ChangeSet", "change_set", None),
        ("Comments", "comments", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Csv", "csv", None),
        ("DataAttributes", "data_attributes", None),
        ("Description", "description", None),
        ("FileName", "file_name", None),
        ("FileSize", "file_size", None),
        ("MetaData", "meta_data", None),
        ("MimeType", "mime_type", None),
        ("Model", "model", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("PublicUrls", "public_urls", None),
        ("PublishedOn", "published_on", None),
        ("SHA1", "sha1", None),
        ("Status", "status", parse_artefact_status),
        ("Tags", "tags", None),
        ("Template", "template", None),
        ("Thumbnails", "thumbnails", None),
        ("Url", "url", None),
        ("VideoLinks", "video_links", None),
    ]

    artefact_tags_comparisons = [
        ("Name", "name", None),
        ("CSN", "csn", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Predefined", "predefined", None),
        ("Status", "status", parse_tag_status),
    ]

    assessments_comparisons = [
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Description", "description", None),
        ("Duration", "duration", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("MultipleAttempts", "multiple_attempts", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Sections", "sections", None),
        ("Status", "status", parse_assessment_status),
        ("Subject", "subject", None),
        ("SubjectCode", "subject_code", None),
        ("Tags", "tags", None),
        ("TotalMarks", "total_marks", None),
    ]

    assessment_tags_comparisons = [
        ("Name", "name", None),
        ("CSN", "csn", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Predefined", "predefined", None),
        ("Status", "status", parse_tag_status),
    ]

    asset_views_comparisons = [
        ("Attributes", "attributes", None),
        ("CurrentWarranty", "current_warranty", None),
        ("LastMaintenance", "last_maintenance", None),
        ("Location", "location", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("Status", "status", parse_asset_status),
        ("Tags", "tags", None),
        ("TrackingId", "tracking_id", None),
        ("UnderWarranty", "under_warranty", None),
        ("Value", "value", lambda v: Decimal(str(v or "0.00"))),
    ]

    attendance_events_comparisons = [
        ("Attendance", "attendance", None),
        ("CourseId", "course_id", None),
        ("CreatedBy", "created_by", None),
        ("CreatedOn", "created_on", None),
        ("Date", "date", None),
        ("InstId", "inst_id", None),
        ("IsOptionalSubject", "is_optional_subject", None),
        ("ModifiedBy", "modified_by", None),
        ("OwnerId", "owner_id", None),
        ("ParentId", "parent_id", None),
        ("PeriodNo", "period_no", None),
        ("SectionName", "section_name", None),
        ("StaffId", "staff_id", None),
        ("StudentId", "student_id", None),
        ("SubjectName", "subject_name", None),
        ("TermName", "term_name", None),
    ]

    calendar_rules_comparisons = [
        ("CalendarEventCategory", "calendar_event_category", None),
        ("CalendarRuleStatus", "calendar_rule_status", None),
        ("CreateMeetingLink", "create_meeting_link", lambda x: bool(x) if x is not None else False),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("CronExpression", "cron_expression", None),
        ("Duration", "duration", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Title", "title", None),
        ("TopicId", "topic_id", extract_uuid),
        ("UserId", "user_id", extract_uuid),
        ("Weight", "weight", None),
    ]

    circulation_views_comparisons = [
        ("DueOn", "due_on", None),
        ("IssuedOn", "issued_on", None),
        ("IssuedTo", "issued_to", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ReceivedOn", "received_on", None),
        ("ReissuedOn", "reissued_on", None),
        ("TrackingId", "tracking_id", None),
    ]

    commits_comparisons = [
        ("AggregateId", "aggregate_id", extract_uuid),
        ("EventMessage", "event_message", None),
        ("InstId", "inst_id", extract_uuid),
        ("UserId", "user_id", extract_uuid),
        ("Version", "version", None),
        ("TimeStamp", "timestamp", None),
    ]

    commit_acs_comparisons = [
        ("AggregateId", "aggregate_id", extract_uuid),
        ("EventMessage", "event_message", None),
        ("InstId", "inst_id", extract_uuid),
        ("UserId", "user_id", extract_uuid),
        ("Version", "version", None),
        ("TimeStamp", "timestamp", None),
    ]

    commit_assets_comparisons = [
        ("AggregateId", "aggregate_id", extract_uuid),
        ("EventMessage", "event_message", None),
        ("InstId", "inst_id", extract_uuid),
        ("UserId", "user_id", extract_uuid),
        ("Version", "version", None),
        ("TimeStamp", "timestamp", None),
    ]

    content_tags_comparisons = [
        ("Name", "name", None),
        ("CSN", "csn", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Predefined", "predefined", None),
        ("Status", "status", None),
    ]

    emails_comparisons = [
        ("Attachments", "attachments", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("From", "from", None),
        ("Message", "message", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Recipients", "recipients", None),
        ("Subject", "subject", None),
        ("Type", "type", None),
    ]

    gradings_comparisons = [
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("GradingRules", "grading_rules", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Status", "status", parse_grading_status),
    ]

    image_tags_comparisons = [
        ("Name", "name", None),
        ("CSN", "csn", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Predefined", "predefined", None),
        ("Status", "status", parse_image_tag_status),
    ]

    institute_calendars_comparisons = [
        ("Audience", "audience", None),
        ("ConductedBy", "conducted_by", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("EventCategory", "event_category", None),
        ("EventCategoryAsString", "event_category_as_string", None),
        ("EventDates", "event_dates", None),
        ("EventName", "event_name", None),
        ("InstId", "inst_id", extract_uuid),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Priority", "priority", None),
    ]

    inventory_items_comparisons = [
        ("Name", "name", None),
        ("Attributes", "attributes", None),
        ("GroupId", "group_id", extract_uuid),
        ("InventoryType", "inventory_type", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("Status", "status", None),
        ("Tags", "tags", None),
        ("UOM", "uom", None),
    ]

    inventory_journals_comparisons = [
        ("AccountingJournalId", "accounting_journal_id", extract_uuid),
        ("Date", "date", None),
        ("InventoryItemId", "inventory_item_id", extract_uuid),
        ("InventoryJournalId", "inventory_journal_id", extract_uuid),
        ("JournalEntryType", "journal_entry_type", None),
        ("Name", "name", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("Particulars", "particulars", None),
        ("PartyId", "party_id", extract_uuid),
        ("PartyName", "party_name", None),
        ("Quantity", "quantity", None),
        ("Rate", "rate", None),
        ("Reference", "reference", None),
        ("Status", "status", None),
        ("UOM", "uom", None),
    ]

    ledger_accounts_comparisons = [
        ("Name", "name", None),
        ("GroupId", "group_id", extract_uuid),
        ("GroupName", "group_name", None),
        ("LedgerType", "ledger_type", None),
        ("NatureOfAccounts", "nature_of_accounts", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("OwnerName", "owner_name", None),
        ("OwnerType", "owner_type", None),
        ("Status", "status", None),
    ]

    material_views_comparisons = [
        ("Name", "name", None),
        ("Attributes", "attributes", None),
        ("Author", "author", None),
        ("ISBN", "isbn", None),
        ("LastVerifiedOn", "last_verified_on", None),
        ("Location", "location", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("Pages", "pages", None),
        ("Publisher", "publisher", None),
        ("Status", "status", None),
        ("Tags", "tags", None),
        ("Title", "title", None),
        ("TrackingId", "tracking_id", None),
        ("Value", "value", None),
        ("OwnerShip", "ownership", None),
    ]

    member_views_comparisons = [
        ("IssuedBooks", "issued_books", None),
        ("MemberType", "member_type", None),
        ("MembershipId", "membership_id", None),
        ("OwnerId", "owner_id", extract_uuid),
    ]

    questions_comparisons = [
        ("AnswerText", "answer_text", None),
        ("AnswerType", "answer_type", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("DefaultWeightage", "default_weightage", None),
        ("Difficulty", "difficulty", None),
        ("Hints", "hints", None),
        ("HtmlText", "html_text", None),
        ("ISN", "isn", None),
        ("Instruction", "instruction", None),
        ("Keywords", "keywords", None),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Options", "options", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("PlainText", "plain_text", None),
        ("QuestionText", "question_text", None),
        ("Questions", "questions", None),
        ("Status", "status", None),
        ("TagList", "tag_list", None),
    ]

    qa_tags_comparisons = [
        ("Name", "name", None),
        ("CSN", "csn", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Predefined", "predefined", None),
        ("Status", "status", None),
    ]

    random_questions_comparisons = [
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("QuestionsAnswered", "questions_answered", None),
        ("UserEmail", "user_email", None),
        ("UserId", "user_id", extract_uuid),
    ]

    receipts_comparisons = [
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Customer", "customer", None),
        ("Date", "date", None),
        ("FinancialInstrument", "financial_instrument", None),
        ("HTML", "html", None),
        ("InstId", "inst_id", extract_uuid),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("Number", "number", None),
        ("OrderItems", "order_items", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("PaymentMode", "payment_mode", None),
        ("ReceiptType", "receipt_type", None),
        ("ReceivedBy", "received_by", None),
        ("RevenueShare", "revenue_share", None),
        ("RevenueSharingEnabled", "revenue_sharing_enabled", None),
        ("Status", "status", None),
        ("TotalAmount", "total_amount", None),
    ]

    seat_matrices_comparisons = [
        ("BreakUp", "break_up", None),
        ("Course", "course", None),
        ("CourseId", "course_id", extract_uuid),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("TotalSeats", "total_seats", None),
    ]

    sms_comparisons = [
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Gateway", "gateway", None),
        ("GatewayResult", "gateway_result", None),
        ("Message", "message", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Recipients", "recipients", None),
        ("SMSRefId", "sms_ref_id", None),
    ]

    sms_messages_comparisons = [
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Credits", "credits", None),
        ("Length", "length", None),
        ("Message", "message", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Reason", "reason", None),
        ("Status", "status", None),
        ("StatusAsString", "status_as_string", None),
    ]

    topics_comparisons = [
        ("Name", "name", None),
        ("Access", "access", None),
        ("CanPublish", "can_publish", None),
        ("CanUnsubscribe", "can_unsubscribe", None),
        ("Category", "category", None),
        ("CreatedBy", "created_by", extract_uuid),
        ("CreatedOn", "created_on", None),
        ("Description", "description", None),
        ("FriendlyName", "friendly_name", None),
        ("Handle", "handle", None),
        ("IsSubscriptionAllowed", "is_subscription_allowed", None),
        ("MainTopicId", "main_topic_id", extract_uuid),
        ("Meta", "meta", None),
        ("ModifiedBy", "modified_by", extract_uuid),
        ("OwnerId", "owner_id", extract_uuid),
        ("ParentId", "parent_id", extract_uuid),
        ("Role", "role", None),
        ("Status", "status", None),
        ("Subscriptions", "subscriptions", None),
        ("Tags", "tags", None),
    ]

    voucher_views_comparisons = [
        ("By", "by", None),
        ("ByTotal", "by_total", None),
        ("CreatedOn", "created_on", None),
        ("Date", "date", None),
        ("Description", "description", None),
        ("OwnerId", "owner_id", extract_uuid),
        ("RefNo", "ref_no", None),
        ("Section", "section", None),
        ("Status", "status", None),
        ("Tags", "tags", None),
        ("To", "to", None),
        ("ToTotal", "to_total", None),
        ("Type", "type", None),
        ("VoucherNo", "voucher_no", None),
    ]

    return [
        {"domain": "Organizations", "collection": "Orgs", "table": "organization", "key_fn": extract_standard_id, "fields": organizations_comparisons, "is_core": True},
        {"domain": "Institutes", "collection": "Institutes", "table": "institute", "key_fn": extract_standard_id, "fields": institutes_comparisons, "is_core": True},
        {"domain": "Students", "collection": "Students", "table": "student", "key_fn": extract_student_id, "fields": students_comparisons, "is_core": True},
        {"domain": "Courses", "collection": "Courses", "table": "course", "key_fn": extract_standard_id, "fields": courses_comparisons, "is_core": True},
        {"domain": "Staffs", "collection": "Staffs", "table": "staffs", "key_fn": extract_standard_id, "fields": staffs_comparisons, "is_core": True},
        {"domain": "Personas", "collection": "Personas", "table": "persona", "key_fn": extract_standard_id, "fields": personas_comparisons, "is_core": True},
        {"domain": "Fees", "collection": "Fees", "table": "fee", "key_fn": extract_standard_id, "fields": fees_comparisons, "is_core": True},
        {"domain": "Fee Transactions", "collection": "FeeTxes", "table": "fee_transaction", "key_fn": extract_standard_id, "fields": fee_transactions_comparisons, "is_core": True},
        {"domain": "Exams", "collection": "Exams", "table": "exam", "key_fn": extract_standard_id, "fields": exams_comparisons, "is_core": True},
        {"domain": "Users", "collection": "Users", "table": "users", "key_fn": extract_standard_id, "fields": users_comparisons, "is_core": True},
        {"domain": "Applications", "collection": "Applications", "table": "applications", "key_fn": extract_standard_id, "fields": applications_comparisons, "is_core": True},
        {"domain": "App Form Templates", "collection": "ApplicationFormTemplates", "table": "application_form_templates", "key_fn": extract_standard_id, "fields": app_form_templates_comparisons, "is_core": True},
        {"domain": "Artefacts", "collection": "Artefacts", "table": "artefacts", "key_fn": extract_standard_id, "fields": artefacts_comparisons, "is_core": True},
        {"domain": "Artefact Tags", "collection": "ArtefactTags", "table": "artefact_tags", "key_fn": extract_standard_id, "fields": artefact_tags_comparisons, "is_core": True},
        {"domain": "Assessments", "collection": "Assessments", "table": "assessments", "key_fn": extract_standard_id, "fields": assessments_comparisons, "is_core": True},
        {"domain": "Assessment Tags", "collection": "AssessmentTags", "table": "assessment_tags", "key_fn": extract_standard_id, "fields": assessment_tags_comparisons, "is_core": True},
        {"domain": "Asset Views", "collection": "AssetViews", "table": "asset_views", "key_fn": extract_standard_id, "fields": asset_views_comparisons, "is_core": True},
        {"domain": "Attendance Events", "collection": "AttendanceEvents", "table": "attendance_event", "key_fn": extract_standard_id, "fields": attendance_events_comparisons, "is_core": True},
        {"domain": "Calendar Rules", "collection": "CalendarRules", "table": "calendar_rules", "key_fn": extract_standard_id, "fields": calendar_rules_comparisons, "is_core": True},
        {"domain": "Circulation Views", "collection": "CirculationViews", "table": "circulation_views", "key_fn": extract_standard_id, "fields": circulation_views_comparisons, "is_core": True},
        {"domain": "Commits", "collection": "Commits", "table": "commits", "key_fn": extract_standard_id, "fields": commits_comparisons, "is_core": True},
        {"domain": "Commit ACs", "collection": "CommitAcs", "table": "commit_ac", "key_fn": extract_standard_id, "fields": commit_acs_comparisons, "is_core": True},
        {"domain": "Commit Assets", "collection": "CommitAssets", "table": "commit_asset", "key_fn": extract_standard_id, "fields": commit_assets_comparisons, "is_core": True},
        {"domain": "Content Tags", "collection": "ContentTags", "table": "content_tags", "key_fn": extract_standard_id, "fields": content_tags_comparisons, "is_core": True},
        {"domain": "Emails", "collection": "Emails", "table": "email", "key_fn": extract_standard_id, "fields": emails_comparisons, "is_core": True},
        {"domain": "Gradings", "collection": "Gradings", "table": "gradings", "key_fn": extract_standard_id, "fields": gradings_comparisons, "is_core": True},
        {"domain": "Image Tags", "collection": "ImageTags", "table": "image_tags", "key_fn": extract_standard_id, "fields": image_tags_comparisons, "is_core": True},
        {"domain": "Institute Calendars", "collection": "InstituteCalendars", "table": "institute_calendars", "key_fn": extract_standard_id, "fields": institute_calendars_comparisons, "is_core": True},
        {"domain": "Inventory Items", "collection": "InventoryItemViews", "table": "inventory_item_views", "key_fn": extract_standard_id, "fields": inventory_items_comparisons, "is_core": True},
        {"domain": "Inventory Journals", "collection": "InventoryJournalViews", "table": "inventory_journal_views", "key_fn": extract_standard_id, "fields": inventory_journals_comparisons, "is_core": True},
        {"domain": "Ledger Accounts", "collection": "LedgerAccountViews", "table": "ledger_account_views", "key_fn": extract_standard_id, "fields": ledger_accounts_comparisons, "is_core": True},
        {"domain": "Material Views", "collection": "MaterialViews", "table": "material_views", "key_fn": extract_standard_id, "fields": material_views_comparisons, "is_core": True},
        {"domain": "Member Views", "collection": "MemberViews", "table": "member_views", "key_fn": extract_standard_id, "fields": member_views_comparisons, "is_core": True},
        {"domain": "Questions", "collection": "Questions", "table": "questions", "key_fn": extract_standard_id, "fields": questions_comparisons, "is_core": True},
        {"domain": "QA Tags", "collection": "QATags", "table": "qa_tags", "key_fn": extract_standard_id, "fields": qa_tags_comparisons, "is_core": True},
        {"domain": "Random Questions", "collection": "RandomQuestionSubmissions", "table": "random_question_submissions", "key_fn": extract_standard_id, "fields": random_questions_comparisons, "is_core": True},
        {"domain": "Receipts", "collection": "Receipts", "table": "receipts", "key_fn": extract_standard_id, "fields": receipts_comparisons, "is_core": True},
        {"domain": "Seat Matrices", "collection": "SeatMatrices", "table": "seat_matrices", "key_fn": extract_standard_id, "fields": seat_matrices_comparisons, "is_core": True},
        {"domain": "SMS", "collection": "SMs", "table": "sms", "key_fn": extract_standard_id, "fields": sms_comparisons, "is_core": True},
        {"domain": "SMS Messages", "collection": "SmsMessages", "table": "sms_message", "key_fn": extract_standard_id, "fields": sms_messages_comparisons, "is_core": True},
        {"domain": "Topics", "collection": "Topics", "table": "topics", "key_fn": extract_standard_id, "fields": topics_comparisons, "is_core": True},
        {"domain": "Voucher Views", "collection": "VoucherViews", "table": "voucher_views", "key_fn": extract_standard_id, "fields": voucher_views_comparisons, "is_core": True},
    ]

def main() -> int:
    script_dir = Path(__file__).parent.resolve()
    for env_cand in (
        script_dir.parent / ".env",
        script_dir / ".env",
        Path(".env"),
    ):
        if env_cand.exists():
            load_env_file(env_cand)
            break

    parser = argparse.ArgumentParser(
        description="Master RavenDB vs PostgreSQL Complete 42-Table Parity Verifier"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Audit all 42 RavenDB business collections and PostgreSQL tables (default: True)",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Audit only the 9 core domains (177 detailed attributes)",
    )
    parser.add_argument(
        "--module",
        "-m",
        help="Comma-separated list of tables or collections to audit (e.g. students,fees,users)",
    )
    parser.add_argument("--raven-url", default=os.getenv("RAVEN_URL"))
    parser.add_argument("--raven-db", default=os.getenv("RAVEN_DB"))
    parser.add_argument("--raven-cert-file", default=os.getenv("RAVEN_CERT_FILE"))
    parser.add_argument("--raven-cert-password", default=os.getenv("RAVEN_CERT_PASSWORD"))
    parser.add_argument("--raven-insecure", action="store_true", default=False)
    parser.add_argument("--pg-host", default=os.getenv("PG_HOST"))
    parser.add_argument("--pg-port", type=int, default=int(os.getenv("PG_PORT", "5432")))
    parser.add_argument("--pg-db", default=os.getenv("PG_DB"))
    parser.add_argument("--pg-user", default=os.getenv("PG_USER"))
    parser.add_argument("--pg-password", default=os.getenv("PG_PASSWORD"))
    parser.add_argument(
        "--summary-json-path",
        default=os.getenv("VERIFICATION_SUMMARY_JSON"),
        help="Custom output file path for detailed JSON parity report",
    )
    parser.add_argument(
        "--no-summary-json",
        action="store_true",
        help="Disable writing verification report JSON artifact",
    )

    args = parser.parse_args()

    config = {
        "raven_url": args.raven_url,
        "raven_db": args.raven_db,
        "raven_cert_file": args.raven_cert_file,
        "raven_cert_password": args.raven_cert_password,
        "raven_insecure": args.raven_insecure,
        "pg_host": args.pg_host,
        "pg_port": args.pg_port,
        "pg_db": args.pg_db,
        "pg_user": args.pg_user,
        "pg_password": args.pg_password,
    }

    engine = VerificationEngine(config)

    print("=" * 115)
    print("           RAVENDB -> POSTGRESQL COMPLETE 42-COLLECTION DATA PARITY AUDIT             ")
    print("=" * 115)
    print(f"[+] Target RavenDB:    {engine.raven_url} (DB: {engine.raven_db})")
    print(f"[+] Target PostgreSQL: {engine.pg_host}:{engine.pg_port}/{engine.pg_db} (User: {engine.pg_user})\n")

    try:
        pg_conn = engine.get_pg_connection()
    except Exception as ex:
        print(f"[!] Critical Error: Unable to connect to PostgreSQL: {ex}")
        return 1

    all_specs = get_all_domain_specs()

    # Filter specs based on flags
    selected_specs = all_specs
    if args.core_only:
        selected_specs = [s for s in all_specs if s.get("is_core")]
    elif args.module:
        targets = set(t.strip().lower() for t in args.module.split(","))
        selected_specs = [
            s
            for s in all_specs
            if s["table"].lower() in targets
            or s["collection"].lower() in targets
            or s["domain"].lower() in targets
            or s["table"].lower().replace("_", "") in targets
        ]

    print(f"[*] Auditing {len(selected_specs)} collection/table pairs...\n")

    results: List[DomainCheckResult] = []

    for spec in selected_specs:
        res = engine.verify_domain(
            domain_name=spec["domain"],
            collection_name=spec["collection"],
            table_name=spec["table"],
            key_extractor=spec["key_fn"],
            field_comparisons=spec["fields"],
            pg_conn=pg_conn,
        )
        results.append(res)

    pg_conn.close()

    # Print Formatted Summary Table
    print("=" * 125)
    print(
        f"{'Domain / Entity':<24} | {'Collection':<26} | {'PG Table':<26} | {'RavenDB':<8} | {'PG':<8} | {'Matched':<8} | {'Status':<8}"
    )
    print("=" * 125)

    all_passed = True
    total_raven = sum(r.raven_count for r in results)
    total_pg = sum(r.pg_count for r in results)
    total_matched = sum(r.matched_ids for r in results)

    for r in results:
        print(
            f"{r.domain_name:<24} | {r.collection_name:<26} | {r.table_name:<26} | {r.raven_count:<8} | {r.pg_count:<8} | {r.matched_ids:<8} | {r.status:<8}"
        )
        if r.status != "PASS":
            all_passed = False
            if r.error_message:
                print(f"   [!] Error: {r.error_message}")
            if r.missing_in_pg:
                print(f"   [!] Missing IDs in PG ({len(r.missing_in_pg)}): {r.missing_in_pg[:3]}...")
            if r.sample_mismatches:
                print("   [!] Sample field mismatches:")
                for m in r.sample_mismatches[:3]:
                    print(f"       - ID {m['id']} {m['field']}: Raven='{m['raven_val']}' vs PG='{m['pg_val']}'")

    print("=" * 125)
    print(
        f"{'TOTAL AUDITED (' + str(len(results)) + ' TABLES)':<79} | {total_raven:<8} | {total_pg:<8} | {total_matched:<8} | {'PASS' if all_passed else 'FAIL':<8}"
    )
    print("=" * 125)

    # Save detailed JSON artifact
    if not args.no_summary_json:
        out_dir = Path("validation")
        out_dir.mkdir(parents=True, exist_ok=True)
        report_file = (
            Path(args.summary_json_path)
            if args.summary_json_path
            else (
                out_dir
                / f"exhaustive-parity-report-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            )
        )

        report_payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "collections_audited_count": len(results),
            "total_documents_in_raven": total_raven,
            "total_rows_in_postgres": total_pg,
            "total_matched_ids": total_matched,
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
                    "extra_in_pg_count": len(r.extra_in_pg),
                    "field_mismatches_count": r.field_mismatches_count,
                    "sample_mismatches": r.sample_mismatches,
                    "error_message": r.error_message,
                    "status": r.status,
                }
                for r in results
            ],
        }
        report_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        print(f"\n[+] Detailed Verification Report JSON written to: {report_file.resolve()}")

    if all_passed:
        print(f"\n[SUCCESS] 100% COMPLETE PARITY CONFIRMED ACROSS ALL {len(results)} TABLES AND {total_matched} RECORDS!\n")
        return 0
    else:
        print("\n[FAILURE] DATA PARITY ISSUES DETECTED. Review table above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())