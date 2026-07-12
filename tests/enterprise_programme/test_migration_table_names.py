"""The rebuild's migrations must not collide with what is already ON LIVE.

WHY THIS TEST EXISTS
--------------------
Migration 027 declared `CREATE TABLE IF NOT EXISTS enterprise_beneficiaries` -- a name
migration 024 already owns, and 024 IS APPLIED TO THE LIVE DATABASE. On live, that CREATE
would have been silently skipped (that is what IF NOT EXISTS does), leaving 024's completely
different shape in place: no `tenant_id`, no `code`, no `status`. The very next statement --

    CREATE UNIQUE INDEX ux_ent_beneficiary_code
        ON enterprise_beneficiaries (tenant_id, programme_id, code)

-- would have failed with `column "tenant_id" does not exist`, rolling back the whole
migration inside its BEGIN. Slices 5, 6, 7, 8 and 9 would have landed NO SCHEMA AT ALL, and
the first anyone would have known is the apply failing against production.

Nothing in the test suite could see it. The `.sql` migrations never run on SQLite, and the
SQLite mirror in `beneficiaries.py` builds the NEW shape in a database that has never met
migration 024. Every test stayed green. It took a human reading the two files side by side.

So the check becomes a test. It is cheap, it is exact, and it runs on every commit.
"""

from __future__ import annotations

import pathlib
import re

MIGRATIONS = pathlib.Path(__file__).resolve().parents[2] / "migrations"

# Applied to the live Postgres (2026-07-11, commit d42097a). Its tables are SUPERSEDED by the
# rebuild but never dropped -- owner decision D1 -- so their names stay taken, forever.
LIVE = "024_enterprise_programme_foundation.sql"

# The rebuild. None of these has been applied yet.
REBUILD = [
    "025_enterprise_tenancy_rbac.sql",
    "026_enterprise_programme_lifecycle.sql",
    "027_enterprise_beneficiaries_import.sql",
]

_CREATE = re.compile(r"^\s*CREATE TABLE IF NOT EXISTS\s+(\w+)", re.MULTILINE | re.IGNORECASE)


def _tables(filename: str) -> set[str]:
    return set(_CREATE.findall((MIGRATIONS / filename).read_text(encoding="utf-8")))


def test_no_rebuild_migration_reuses_a_live_table_name():
    live = _tables(LIVE)
    assert "enterprise_beneficiaries" in live, \
        "the fixture is wrong if 024 no longer owns this name"

    for filename in REBUILD:
        clash = _tables(filename) & live
        assert not clash, (
            f"{filename} re-declares table(s) already on live: {sorted(clash)}. "
            f"CREATE TABLE IF NOT EXISTS will SILENTLY SKIP them, leave 024's shape in "
            f"place, and kill the apply at the first index or foreign key that expects the "
            f"new columns. Rename, as enterprise_programme_registry / _phase_states / "
            f"enterprise_beneficiary_register already were."
        )


def test_the_rebuild_still_owns_the_names_the_code_actually_queries():
    """The rename is only safe if the CODE was renamed with the migration. If a query still
    said `enterprise_beneficiaries`, it would silently read 024's abandoned table on live --
    which has no tenant_id, so control C13 would have nothing to scope by."""
    declared: set[str] = set()
    for filename in REBUILD:
        declared |= _tables(filename)

    for name in ("enterprise_beneficiary_register", "enterprise_site_qualifications",
                 "enterprise_import_batches", "enterprise_project_links"):
        assert name in declared, f"{name} is queried by the code but declared by no migration"

    src = pathlib.Path(__file__).resolve().parents[2] / "app" / "enterprise_programme"
    for module in ("beneficiaries.py", "imports.py", "site_qualification.py", "gates.py"):
        text = (src / module).read_text(encoding="utf-8")
        assert "enterprise_beneficiaries" not in text, (
            f"{module} still names 024's live table. On Postgres it would read the wrong "
            f"table -- one with no tenant_id at all."
        )
