#!/usr/bin/env python3
"""patch_rate_builder_schema_and_migrate.py (2026-06-24)

Final two pieces of the rate-builder rework:

1. SQLite-side ALTERs for marketplace_bom_items: add the 5 per-line
   rate-buildup columns mirroring the Postgres init in
   _ensure_marketplace_schema_postgres.

2. _migrate_legacy_boq_rate_buildup() -- one-time idempotent backfill
   that zeroes any boq_floor_rate_buildup row where supply_rate > 100
   (old currency-amount data). Runs once at startup (guarded by a
   module-level flag), logs a single line with the count.
"""

from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()
orig = data
changes = []


def apply(old: bytes, new: bytes, label: str):
    global data
    if new in data:
        print(f"[skip] {label} already patched")
        return
    n = data.count(old)
    if n != 1:
        snippet = old[:200].decode("latin-1", errors="replace")
        raise SystemExit(
            f"[fail] {label}: expected exactly 1 OLD match, found {n}\n"
            f"OLD starts: {snippet!r}"
        )
    data = data.replace(old, new, 1)
    changes.append(label)
    print(f"[ok]   {label}")


# ----- (a) SQLite ALTERs for the 5 new BOM rate-buildup columns -----------
OLD_A = (
    b'        # New 2026-06-22 (session A): description / specification / brand on BOM lines.\r\n'
    b'        # Idempotent for SQLite + Postgres (psycopg accepts ADD COLUMN IF NOT EXISTS).\r\n'
    b'        for _ddl in (\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN description TEXT DEFAULT \'\'",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN specification TEXT DEFAULT \'\'",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN brand TEXT DEFAULT \'\'",\r\n'
    b'        ):\r\n'
    b'            try:\r\n'
    b'                with get_db() as _c:\r\n'
    b'                    _c.execute(_ddl)\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
)
NEW_A = (
    b'        # New 2026-06-22 (session A): description / specification / brand on BOM lines.\r\n'
    b'        # Idempotent for SQLite + Postgres (psycopg accepts ADD COLUMN IF NOT EXISTS).\r\n'
    b'        for _ddl in (\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN description TEXT DEFAULT \'\'",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN specification TEXT DEFAULT \'\'",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN brand TEXT DEFAULT \'\'",\r\n'
    b'            # 2026-06-24 rate-builder rework -- per-line basic + 4 pct columns.\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN basic_price  REAL",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN supply_pct   REAL",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN profit_pct   REAL",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN install_pct  REAL",\r\n'
    b'            "ALTER TABLE marketplace_bom_items ADD COLUMN overhead_pct REAL",\r\n'
    b'        ):\r\n'
    b'            try:\r\n'
    b'                with get_db() as _c:\r\n'
    b'                    _c.execute(_ddl)\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
)
apply(OLD_A, NEW_A, "(a) SQLite ALTERs for new BOM rate-buildup columns")


# ----- (b) legacy BOQ rate-buildup migration -----------------------------
# Insert right BEFORE `def _boq_safe_rate(` so it lives with the engine.
OLD_B = (
    b'def _boq_safe_rate(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
)
NEW_B = (
    b'_BOQ_LEGACY_MIGRATION_DONE = {"v": False}\r\n'
    b'\r\n'
    b'def _migrate_legacy_boq_rate_buildup():\r\n'
    b'    """One-time backfill (2026-06-24): under the new additive model,\r\n'
    b'    `boq_floor_rate_buildup.supply_rate` and `install_rate` hold\r\n'
    b'    percentages (0..15 / 0..25). Any row with supply_rate > 100 is\r\n'
    b'    legacy data where those columns stored currency amounts. Zero\r\n'
    b'    those percentage fields and reset final_built_up_rate=basic_price\r\n'
    b'    so the owner sees the basic-only number until they re-enter rates.\r\n'
    b'\r\n'
    b'    Idempotent (guarded by _BOQ_LEGACY_MIGRATION_DONE + the WHERE\r\n'
    b'    clause itself only matches old rows). Non-raising.\r\n'
    b'    """\r\n'
    b'    if _BOQ_LEGACY_MIGRATION_DONE["v"]:\r\n'
    b'        return\r\n'
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            try:\r\n'
    b'                # Count affected rows first so the log is informative.\r\n'
    b'                n_row = c.execute(\r\n'
    b'                    "SELECT COUNT(*) AS n FROM boq_floor_rate_buildup "\r\n'
    b'                    "WHERE supply_rate > 100 OR install_rate > 100"\r\n'
    b'                ).fetchone()\r\n'
    b'                n = int((n_row["n"] if n_row else 0) or 0)\r\n'
    b'            except Exception:\r\n'
    b'                n = -1\r\n'
    b'            if n != 0:\r\n'
    b'                try:\r\n'
    b'                    c.execute(\r\n'
    b'                        "UPDATE boq_floor_rate_buildup "\r\n'
    b'                        "SET supply_rate=0, install_rate=0, overhead_pct=0, "\r\n'
    b'                        "    profit_pct=0, contingency_pct=0, vat_pct=0, "\r\n'
    b'                        "    final_built_up_rate=basic_price, "\r\n'
    b'                        "    total_amount=basic_price * COALESCE("\r\n'
    b'                        "      (SELECT qty FROM boq_floor_items i "\r\n'
    b'                        "       WHERE i.id=boq_floor_rate_buildup.floor_item_id), 0) "\r\n'
    b'                        "WHERE supply_rate > 100 OR install_rate > 100"\r\n'
    b'                    )\r\n'
    b'                    # Mirror the per-item table so the owner sees the same number.\r\n'
    b'                    c.execute(\r\n'
    b'                        "UPDATE boq_floor_items SET "\r\n'
    b'                        "  final_built_up_rate = COALESCE("\r\n'
    b'                        "    (SELECT basic_price FROM boq_floor_rate_buildup rb "\r\n'
    b'                        "     WHERE rb.floor_item_id=boq_floor_items.id), 0), "\r\n'
    b'                        "  total_amount = qty * COALESCE("\r\n'
    b'                        "    (SELECT basic_price FROM boq_floor_rate_buildup rb "\r\n'
    b'                        "     WHERE rb.floor_item_id=boq_floor_items.id), 0) "\r\n'
    b'                        "WHERE id IN ("\r\n'
    b'                        "  SELECT floor_item_id FROM boq_floor_rate_buildup "\r\n'
    b'                        "  WHERE supply_rate = 0 AND install_rate = 0 AND overhead_pct = 0"\r\n'
    b'                        ")"\r\n'
    b'                    )\r\n'
    b'                except Exception as _e:\r\n'
    b'                    try:\r\n'
    b'                        app.logger.warning(\r\n'
    b'                            "legacy boq rate-buildup migration update failed: %s", _e)\r\n'
    b'                    except Exception:\r\n'
    b'                        pass\r\n'
    b'        try:\r\n'
    b'            app.logger.info(\r\n'
    b'                "legacy boq rate-buildup migration: zeroed %s row(s)",\r\n'
    b'                "?" if n < 0 else n)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    except Exception as _e:\r\n'
    b'        try:\r\n'
    b'            app.logger.warning("legacy boq rate-buildup migration skipped: %s", _e)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    _BOQ_LEGACY_MIGRATION_DONE["v"] = True\r\n'
    b'\r\n'
    b'\r\n'
    b'def _boq_safe_rate(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
)
apply(OLD_B, NEW_B, "(b) legacy BOQ rate-buildup migration helper")


# ----- (c) call the migration once at startup, alongside other inits ----
# Hook into ensure_boq_hierarchy_schema if it exists; otherwise wire into
# the first request via before_first_request equivalent. We add a small
# guarded call inside _boq_project_owned_or_404 which gates the BOQ surface.
OLD_C = (
    b'def _boq_project_owned_or_404(pid, user_id):\r\n'
)
NEW_C = (
    b'def _boq_project_owned_or_404(pid, user_id):\r\n'
    b'    # 2026-06-24: lazy one-shot migration of legacy rate-buildup rows.\r\n'
    b'    try:\r\n'
    b'        _migrate_legacy_boq_rate_buildup()\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
)
apply(OLD_C, NEW_C, "(c) invoke migration from _boq_project_owned_or_404")


if data == orig:
    print("[noop] file unchanged")
else:
    P.write_bytes(data)
    print(f"[done] {len(changes)} change(s) applied. "
          f"{len(orig)} -> {len(data)} bytes ({len(data)-len(orig):+d})")
