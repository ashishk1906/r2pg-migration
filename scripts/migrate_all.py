#!/usr/bin/env python3
"""
Master Migration Orchestrator: RavenDB to PostgreSQL
1. Runs data migration scripts (extract from RavenDB, create tables dynamically, load data).
2. Applies post-migration SQL (views, performance indexes, and triggers).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
import psycopg2

MODULE_SCRIPTS = [
    ("users", "users_ravendb_to_postgres_migrate.py"),
    ("personas", "personas_ravendb_to_postgres_migrate.py"),
    ("courses", "courses_ravendb_to_postgres_migrate.py"),
    ("staffs", "staffs_ravendb_to_postgres_migrate.py"),
    ("students", "students_ravendb_to_postgres_migrate.py"),
    ("fees", "fees_ravendb_to_postgres_migrate.py"),
    ("exams", "exams_ravendb_to_postgres_migrate.py"),
    ("applications", "applications_ravendb_to_postgres_migrate.py"),
    ("assets", "assets_ravendb_to_postgres_migrate.py"),
    ("attendance_events", "attendance_events_ravendb_to_postgres_migrate.py"),
    ("commits", "commits_ravendb_to_postgres_migrate.py"),
    ("emails", "emails_ravendb_to_postgres_migrate.py"),
    ("sms", "sms_ravendb_to_postgres_migrate.py"),
    ("artefacts", "artefacts_ravendb_to_postgres_migrate.py"),
    ("assessments", "assessments_ravendb_to_postgres_migrate.py"),
    ("topics", "topics_ravendb_to_postgres_migrate.py"),
    ("voucher_views", "voucher_views_ravendb_to_postgres_migrate.py"),
    ("seat_matrices", "seat_matrices_ravendb_to_postgres_migrate.py"),
    ("receipts", "receipts_ravendb_to_postgres_migrate.py"),
    ("questions", "questions_ravendb_to_postgres_migrate.py"),
    ("member_views", "member_views_ravendb_to_postgres_migrate.py"),
    ("material_views", "material_views_ravendb_to_postgres_migrate.py"),
    ("ledger_account_views", "ledger_account_views_ravendb_to_postgres_migrate.py"),
    ("inventory", "inventory_ravendb_to_postgres_migrate.py"),
    ("institute_calendars", "institute_calendars_ravendb_to_postgres_migrate.py"),
    ("image_tags", "image_tags_ravendb_to_postgres_migrate.py"),
    ("gradings", "gradings_ravendb_to_postgres_migrate.py"),
    ("content_tags", "content_tags_ravendb_to_postgres_migrate.py"),
    ("circulation_views", "circulation_views_ravendb_to_postgres_migrate.py"),
    ("calendar_rules", "calendar_rules_ravendb_to_postgres_migrate.py"),
]

def load_env_file(env_path: Path):
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

def run_script(script_path: Path, extra_args: list[str]) -> bool:
    print("\n" + "=" * 65)
    print(f"[*] Starting Migration: {script_path.name}")
    print("=" * 65)
    cmd = [sys.executable, str(script_path)] + extra_args
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[!] Error: {script_path.name} failed with exit code {result.returncode}")
        return False
    print(f"[+] Success: {script_path.name} completed successfully.")
    return True

def apply_post_migration_sql(scripts_dir: Path):
    print("\n" + "=" * 65)
    print("[*] Applying Post-Migration Views, Indexes & Triggers")
    print("=" * 65)
    
    # Try finding sql directory
    sql_dirs = [
        scripts_dir.parent / "student-fee-poc" / "sql",
        scripts_dir.parent / "sql",
        scripts_dir / "sql"
    ]
    sql_dir = next((d for d in sql_dirs if d.exists()), None)
    
    if not sql_dir:
        print("[!] Warning: sql directory not found for post-migration views. Skipping.")
        return

    pg_host = os.getenv("PG_HOST")
    pg_port = int(os.getenv("PG_PORT", "5432")) if os.getenv("PG_PORT") else 5432
    pg_db = os.getenv("PG_DB")
    pg_user = os.getenv("PG_USER")
    pg_password = os.getenv("PG_PASSWORD")

    sql_files = ["01_student_fee_view.sql", "02_trigger.sql"]
    
    try:
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            dbname=pg_db,
            user=pg_user,
            password=pg_password
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            for sql_file in sql_files:
                file_path = sql_dir / sql_file
                if file_path.exists():
                    print(f"Applying SQL: {sql_file}...")
                    sql_content = file_path.read_text(encoding="utf-8")
                    cur.execute(sql_content)
                    print(f"[+] Applied {sql_file} successfully.")
                else:
                    print(f"[!] SQL file {sql_file} not found in {sql_dir}.")
        conn.close()
    except Exception as ex:
        print(f"[!] Warning during post-migration SQL execution: {ex}")

def main():
    scripts_dir = Path(__file__).parent.resolve()
    # Load central root .env
    root_env = scripts_dir.parent / ".env"
    if root_env.exists():
        load_env_file(root_env)

    parser = argparse.ArgumentParser(description="Master RavenDB -> PostgreSQL Migration Runner")
    parser.add_argument("--all", action="store_true", help="Run all migrations in order")
    parser.add_argument("--module", "-m", help="Comma-separated list of modules to migrate (e.g., student,fees)")
    parser.add_argument("--skip-post-sql", action="store_true", help="Skip applying post-migration views & triggers")
    
    args, unknown = parser.parse_known_args()

    selected_modules = []
    if args.all or not args.module:
        selected_modules = [m[0] for m in MODULE_SCRIPTS]
    else:
        raw_modules = [m.strip().lower() for m in args.module.split(",")]
        ALIASES = {
            "student": "students",
            "user": "users",
            "topic": "topics",
            "assessment": "assessments",
            "artefact": "artefacts",
            "artifact": "artefacts",
            "artifacts": "artefacts",
            "voucher": "voucher_views",
            "vouchers": "voucher_views",
            "voucherview": "voucher_views",
            "voucherviews": "voucher_views",
            "voucher_view": "voucher_views",
            "seatmatrix": "seat_matrices",
            "seatmatrices": "seat_matrices",
            "seat_matrix": "seat_matrices",
            "receipt": "receipts",
            "question": "questions",
            "questions": "questions",
            "qatag": "questions",
            "qatags": "questions",
            "randomquestionsubmission": "questions",
            "randomquestionsubmissions": "questions",
            "memberview": "member_views",
            "memberviews": "member_views",
            "member_view": "member_views",
            "member_views": "member_views",
            "material": "material_views",
            "materials": "material_views",
            "materialview": "material_views",
            "materialviews": "material_views",
            "material_view": "material_views",
            "material_views": "material_views",
            "ledger": "ledger_account_views",
            "ledgers": "ledger_account_views",
            "ledgeraccount": "ledger_account_views",
            "ledgeraccounts": "ledger_account_views",
            "ledgeraccountview": "ledger_account_views",
            "ledgeraccountviews": "ledger_account_views",
            "ledger_account_view": "ledger_account_views",
            "ledger_account_views": "ledger_account_views",
            "inventory": "inventory",
            "inventories": "inventory",
            "inventoryitem": "inventory",
            "inventoryitems": "inventory",
            "inventoryitemview": "inventory",
            "inventoryitemviews": "inventory",
            "inventory_item_views": "inventory",
            "inventoryjournal": "inventory",
            "inventoryjournals": "inventory",
            "inventoryjournalview": "inventory",
            "inventoryjournalviews": "inventory",
            "inventory_journal_views": "inventory",
            "institutecalendar": "institute_calendars",
            "institutecalendars": "institute_calendars",
            "institute_calendar": "institute_calendars",
            "institute_calendars": "institute_calendars",
            "calendar": "institute_calendars",
            "calendars": "institute_calendars",
            "imagetag": "image_tags",
            "imagetags": "image_tags",
            "image_tag": "image_tags",
            "image_tags": "image_tags",
            "grading": "gradings",
            "gradings": "gradings",
            "contenttag": "content_tags",
            "contenttags": "content_tags",
            "content_tag": "content_tags",
            "content_tags": "content_tags",
            "circulation": "circulation_views",
            "circulations": "circulation_views",
            "circulationview": "circulation_views",
            "circulationviews": "circulation_views",
            "circulation_view": "circulation_views",
            "circulation_views": "circulation_views",
            "calendarrule": "calendar_rules",
            "calendarrules": "calendar_rules",
            "calendar_rule": "calendar_rules",
            "calendar_rules": "calendar_rules",
            "application": "applications",
            "admission": "applications",
            "admissions": "applications",
            "asset": "assets",
            "assetview": "assets",
            "assetviews": "assets",
            "attendance": "attendance_events",
            "attendanceevent": "attendance_events",
            "attendanceevents": "attendance_events",
            "attendance_event": "attendance_events",
            "commit": "commits",
            "commitassets": "commits",
            "commitacs": "commits",
            "commit_asset": "commits",
            "commit_ac": "commits",
            "email": "emails",
            "smsmessages": "sms",
            "sms_messages": "sms",
            "sms_message": "sms",
        }
        selected_modules = [ALIASES.get(m, m) for m in raw_modules]

    print(f"[*] Queued migration modules: {', '.join(selected_modules)}")
    
    success_count = 0
    failure_count = 0

    for name, script_file in MODULE_SCRIPTS:
        if name in selected_modules:
            script_full_path = scripts_dir / script_file
            if not script_full_path.exists():
                print(f"[!] Warning: Script {script_file} not found. Skipping.")
                failure_count += 1
                continue
            
            ok = run_script(script_full_path, unknown)
            if ok:
                success_count += 1
            else:
                failure_count += 1

    print("\n" + "=" * 65)
    print(f"[=] MIGRATION SUMMARY: {success_count} succeeded, {failure_count} failed")
    print("=" * 65)

    if success_count > 0 and not args.skip_post_sql:
        apply_post_migration_sql(scripts_dir)

    if failure_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
