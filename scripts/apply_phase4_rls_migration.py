"""
Apply migrations/003_rls_tenant.sql to the live Postgres + verify.

Phase 4 task 21 of docs/SECURITY_MIGRATION_KEYCLOAK.md.

Usage
-----

    # Dry-run -- prints the SQL it would run, no DB writes.
    python scripts/apply_phase4_rls_migration.py --dry-run

    # Real apply -- requires DATABASE_URL env to a postgres:// URL.
    # On a deployed environment, the URL comes from Render's env vars.
    python scripts/apply_phase4_rls_migration.py

    # Apply + skip the pre-flight backup. ONLY for staging.
    python scripts/apply_phase4_rls_migration.py --no-backup

Behaviour
---------

1. Detect DATABASE_URL. Refuse to run against a sqlite path -- the
   migration's PL/pgSQL bodies are Postgres-only.

2. Print the migration's section headers + line counts so the operator
   sees what is about to run.

3. Pre-flight: `pg_dump --schema-only` to `tmp/phase4_preflight_<ts>.sql`
   so a half-apply can be reverted without touching the rest of the
   schema. Skipped when `--no-backup` is passed.

4. Apply: `psql $DATABASE_URL -v ON_ERROR_STOP=1 -f migrations/003_rls_tenant.sql`.

5. Post-apply verification: run the same SELECTs documented at the
   bottom of the migration file. Print pass/fail per check.

Exit codes
----------

    0   apply + verification all green
    1   refused to run (config / wrong DB)
    2   pre-flight backup failed
    3   psql apply failed
    4   verification failed (apply may have succeeded; investigate)

The script is a thin wrapper around psql; it does NOT rewrite any SQL.
That keeps the migration file the single source of truth.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "migrations" / "003_rls_tenant.sql"


def _resolve_database_url() -> Optional[str]:
    url = os.environ.get("DATABASE_URL", "").strip()
    return url or None


def _refuse(msg: str, code: int = 1) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return code


def _print_migration_overview() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    print(f"=== {MIGRATION.name} ({len(text):,} chars) ===")
    for line in text.splitlines():
        if line.startswith("-- PART") or line.startswith("-- ==="):
            print(line)


def _require_tool(name: str) -> Optional[str]:
    path = shutil.which(name)
    if not path:
        return None
    return path


def _run_psql(args: list[str], database_url: str) -> subprocess.CompletedProcess:
    """psql wraps DATABASE_URL as positional arg so we don't have to
    explode it into PG* env vars."""
    return subprocess.run(
        ["psql", database_url, *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _pg_dump_schema(database_url: str) -> Optional[Path]:
    """Pre-flight: schema-only pg_dump. Returns the path to the dump
    file, or None if pg_dump is unavailable. The dump is informational
    only -- the migration's idempotent DDL means re-running it is safe."""
    if not _require_tool("pg_dump"):
        print("[warn] pg_dump not on PATH; skipping pre-flight backup.")
        return None
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = REPO_ROOT / "tmp" / f"phase4_preflight_{ts}.sql"
    out.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        ["pg_dump", "--schema-only", "--no-owner", "--file", str(out), database_url],
        text=True, capture_output=True, check=False,
    )
    if cp.returncode != 0:
        print(f"[FAIL] pg_dump exited {cp.returncode}:\n{cp.stderr}", file=sys.stderr)
        return None
    print(f"[ok] pre-flight dump written to {out}")
    return out


VERIFY_QUERIES: list[tuple[str, str, int]] = [
    # (label, sql, minimum_expected_rows)
    (
        "helpers present",
        "SELECT proname FROM pg_proc "
        "WHERE proname IN ('current_tenant_id','current_user_sub','_phase4_user_to_tenant')",
        3,
    ),
    (
        "tenant_id columns present",
        "SELECT table_name FROM information_schema.columns "
        "WHERE column_name = 'tenant_id' AND table_schema = 'public'",
        1,
    ),
    (
        "RLS policies installed",
        "SELECT tablename, policyname FROM pg_policies "
        "WHERE policyname LIKE '%_tenant_isolation'",
        1,
    ),
]


def _verify(database_url: str) -> int:
    """Returns 0 if every probe passes its minimum row threshold."""
    if not _require_tool("psql"):
        print("[FAIL] psql not on PATH; cannot verify.", file=sys.stderr)
        return 4
    failures = 0
    for label, sql, minimum in VERIFY_QUERIES:
        cp = _run_psql(["-Atc", sql], database_url)
        if cp.returncode != 0:
            print(f"[FAIL] verify '{label}': psql exited {cp.returncode}",
                  file=sys.stderr)
            print(cp.stderr, file=sys.stderr)
            failures += 1
            continue
        rows = [line for line in cp.stdout.splitlines() if line.strip()]
        if len(rows) < minimum:
            print(f"[FAIL] verify '{label}': got {len(rows)} rows, "
                  f"expected >= {minimum}")
            failures += 1
        else:
            print(f"[ok]  verify '{label}': {len(rows)} row(s)")
    return 0 if failures == 0 else 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the migration and exit; no DB writes.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip pre-flight pg_dump (staging only).")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Don't run the verification queries after apply.")
    args = parser.parse_args(argv)

    if not MIGRATION.exists():
        return _refuse(f"Migration file missing: {MIGRATION}")

    _print_migration_overview()

    if args.dry_run:
        print("\n[dry-run] no DB connection attempted.")
        return 0

    database_url = _resolve_database_url()
    if not database_url:
        return _refuse(
            "DATABASE_URL is not set. The migration is Postgres-only; "
            "run on a host where DATABASE_URL points at a postgresql:// URL."
        )
    if not database_url.startswith(("postgres://", "postgresql://")):
        return _refuse(
            f"DATABASE_URL must start with postgres:// or postgresql:// "
            f"(got {database_url[:30]!r}...)."
        )

    if not _require_tool("psql"):
        return _refuse("psql not on PATH. Install Postgres client tools.", code=3)

    if not args.no_backup:
        if _pg_dump_schema(database_url) is None:
            return _refuse("pre-flight backup did not complete; aborting.", code=2)

    print(f"\n[apply] psql -v ON_ERROR_STOP=1 -f {MIGRATION.name}")
    cp = _run_psql(["-v", "ON_ERROR_STOP=1", "-f", str(MIGRATION)], database_url)
    if cp.returncode != 0:
        print(f"[FAIL] psql exited {cp.returncode}:\n{cp.stderr}", file=sys.stderr)
        return 3
    print("[ok] psql apply succeeded.")
    if cp.stdout.strip():
        print(cp.stdout)

    if args.skip_verify:
        print("[skip] verification skipped (--skip-verify).")
        return 0

    print("\n[verify]")
    return _verify(database_url)


if __name__ == "__main__":
    sys.exit(main())
