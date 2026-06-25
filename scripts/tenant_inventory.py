#!/usr/bin/env python3
"""SOC 2 M1.5 -- tenant column / RLS / query inventory.

Walks the codebase + (optionally) the live Postgres schema to produce:

  1. A markdown table of every CREATE TABLE found in source, with:
        - has_tenant_id          (column declared in the CREATE)
        - rls_policy_in_migration (covered by migrations/003_rls_tenant.sql)
        - source_file:line
        - suggested_action       (per the SOC 2 plan -- add column / add RLS / OK)

  2. A counter summary: % of tables with tenant_id, % with RLS, gaps.

Output: docs/tenant_inventory_<DATE>.md   (relative to repo root)

The intent isn't a perfect SQL parser -- it's a high-signal action list
fed by simple regex over the source.  Sections marked TODO in the output
are the bits a human (or a follow-up M1.6 task) has to resolve.
"""
from __future__ import annotations
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Source files to walk -- web_app.py is the main one but many new_*.py
# files also CREATE TABLE.  Tests + scratch are excluded.
SOURCES = [
    "web_app.py",
    *[str(p.relative_to(ROOT)) for p in ROOT.glob("new_*.py")],
    *[str(p.relative_to(ROOT)) for p in ROOT.glob("migrations/*.sql")],
]

# Heuristic regexes.
RE_CREATE = re.compile(
    r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+([a-zA-Z_][\w]*)\s*\((.*?)\)",
    re.IGNORECASE | re.DOTALL,
)
RE_TENANT_COL = re.compile(r"\btenant_id\b", re.IGNORECASE)
RE_USER_ID_COL = re.compile(r"\buser_id\b", re.IGNORECASE)


def discover_tables():
    """Yield (table_name, has_tenant_id, has_user_id, source_file, source_line)."""
    seen = {}  # table_name -> dict (first wins; second-seen ignored)
    for rel in SOURCES:
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Build a line-number index so we can map char-offset back to a line.
        line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                line_starts.append(i + 1)

        def char_to_line(offset):
            # Binary search would be faster but this is fine for ~10K-line files.
            for i, s in enumerate(line_starts):
                if s > offset:
                    return i
            return len(line_starts)

        for m in RE_CREATE.finditer(text):
            name = m.group(1).lower()
            if name in seen:
                continue
            body = m.group(2)
            seen[name] = {
                "table": name,
                "has_tenant_id": bool(RE_TENANT_COL.search(body)),
                "has_user_id": bool(RE_USER_ID_COL.search(body)),
                "file": rel,
                "line": char_to_line(m.start()),
            }
    return seen


def discover_rls_policies():
    """Return the set of table names covered by an RLS policy in migrations/."""
    covered = set()
    pat = re.compile(
        r"(?:CREATE\s+POLICY|ALTER\s+TABLE)\s+([a-zA-Z_][\w]*)",
        re.IGNORECASE,
    )
    # Find tables mentioned in CREATE POLICY / ALTER TABLE ... ROW LEVEL SECURITY.
    for sql_path in ROOT.glob("migrations/*.sql"):
        try:
            txt = sql_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Only consider tables that appear in a "_tenant_isolation" policy line
        # OR that have ALTER TABLE ... ENABLE ROW LEVEL SECURITY.
        for line in txt.splitlines():
            if "ENABLE ROW LEVEL SECURITY" in line.upper():
                m = pat.search(line)
                if m:
                    covered.add(m.group(1).lower())
            elif "_tenant_isolation" in line or "_tenant_policy" in line:
                m = pat.search(line)
                if m:
                    covered.add(m.group(1).lower())
    return covered


def suggested_action(row, rls_covered):
    t = row["table"]
    has_tid = row["has_tenant_id"]
    has_uid = row["has_user_id"]
    has_rls = t in rls_covered

    # Tables we KNOW are not multi-tenant (single global truth).
    GLOBAL = {
        "users", "tenants", "organizations",
        "equipment_catalog", "categories", "brands",
        "marketplace_categories", "marketplace_brands",
        "marketplace_settings", "actions_log",
        "fx_rates", "regions", "country_regions",
        "schema_migrations", "alembic_version",
        # error_logs is global ops data -- tenant_id is captured but RLS
        # isn't needed because admin-only.
        "error_logs",
    }
    if t in GLOBAL:
        return "OK -- intentionally global"

    if has_tid and has_rls:
        return "OK -- column + RLS"
    if has_tid and not has_rls:
        return f"M1.6 -- add RLS policy to migrations/006_rls_full.sql"
    if not has_tid and has_uid:
        return ("M3.1 -- table is user-scoped, not tenant-scoped. Add tenant_id, "
                "backfill from owning user's tenant, then M1.6 RLS.")
    return "M3.1 -- add tenant_id column + M1.6 RLS"


def main():
    tables = discover_tables()
    rls_covered = discover_rls_policies()

    today = date(2026, 6, 25).isoformat()
    out_path = ROOT / "docs" / f"tenant_inventory_{today}.md"

    n_total = len(tables)
    n_with_tid = sum(1 for r in tables.values() if r["has_tenant_id"])
    n_with_rls = sum(1 for r in tables.values() if r["table"] in rls_covered)

    lines = []
    lines.append(f"# Tenant inventory — {today}")
    lines.append("")
    lines.append("Source-grep snapshot of CREATE TABLE statements across "
                 "`web_app.py`, `new_*.py`, and `migrations/*.sql`. "
                 "Action column maps each gap to the SOC 2 plan milestone "
                 "(`docs/SOC2_IMPLEMENTATION_PLAN.md`).")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Tables found**: {n_total}")
    lines.append(f"- **With tenant_id column**: {n_with_tid} ({100.0*n_with_tid/max(n_total,1):.1f}%)")
    lines.append(f"- **With RLS policy in migrations/**: {n_with_rls} ({100.0*n_with_rls/max(n_total,1):.1f}%)")
    lines.append(f"- **Gap to close in M1.6**: {n_total - n_with_rls} tables need an RLS policy "
                 "(excluding the intentionally-global rows below).")
    lines.append("")
    lines.append("## Per-table action list")
    lines.append("")
    lines.append("| Table | tenant_id col | RLS in migrations/ | Source | Action |")
    lines.append("|---|---|---|---|---|")
    for name in sorted(tables):
        r = tables[name]
        tid = "yes" if r["has_tenant_id"] else "no"
        rls = "yes" if r["table"] in rls_covered else "no"
        src = f"`{r['file']}:{r['line']}`"
        act = suggested_action(r, rls_covered)
        lines.append(f"| `{r['table']}` | {tid} | {rls} | {src} | {act} |")
    lines.append("")
    lines.append("## How the action column maps to milestones")
    lines.append("")
    lines.append("- **M1.6** — extend `migrations/003_rls_tenant.sql` (or land `migrations/006_rls_full.sql`) so every tenant-owned table has `ENABLE ROW LEVEL SECURITY` + a `<table>_tenant_isolation` policy.")
    lines.append("- **M3.1** — when a table lacks `tenant_id`, the schema change comes first (Alembic migration adds the column, backfills from owning user / project / parent, then `NOT NULL` + index).")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append("- **CREATE TABLE only.** This walks the CREATE TABLE statements in source -- it does NOT see `ALTER TABLE ADD COLUMN tenant_id` (which `migrations/003_rls_tenant.sql` ran to add 14 columns to live Postgres). So a table that shows `tenant_id col: no` here may already carry the column at runtime. Confirm against Postgres before doing M3.1 work on it.")
    lines.append("- Source-grep -- a CREATE TABLE that has been since dropped or renamed without removing the source line still shows up.")
    lines.append("- Doesn't yet enumerate every `SELECT ... FROM <table>` callsite to flag missing `WHERE tenant_id=?` predicates -- that's the Phase 2 follow-up (M3.1 task list driver).")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"  Tables found: {n_total}")
    print(f"  With tenant_id: {n_with_tid}")
    print(f"  With RLS: {n_with_rls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
