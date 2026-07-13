# patch_pg_insert_or_replace_fix.py
#
# THE BUG THE OWNER REPORTED
#   "in the procurement cost estimate when user clicks on the save labour button it
#    gives syntax errors"
#
# THE CAUSE
#   `INSERT OR REPLACE` is SQLite-only. Postgres has no such syntax -- it fails with
#   `syntax error at or near "OR"`. The app moved to Postgres on 2026-06-13, and
#   db_adapter._translate_sqlite_to_postgres translates `INSERT OR IGNORE` but NOT
#   `INSERT OR REPLACE` (db_adapter.py:105-119). So the statement reaches Postgres
#   verbatim and dies.
#
#   Worse, boms_save_rates then flashes the raw exception at the user:
#       flash(f"Could not save rates: {_e!s}. ...")
#   which is how a database syntax error became a message on the owner's screen.
#   (Directive s15: no raw errors leak.)
#
#   A comment in new_marketplace_boq_export_routes.py:152 asserts "db_adapter
#   translates INSERT OR REPLACE -> ON CONFLICT DO UPDATE". THAT IS FALSE, and it is
#   presumably why this shipped. The comment is corrected by the sibling patch note.
#
# WHY THE EXISTING try/except FALLBACK DID NOT SAVE IT
#   boms_save_rates wraps the 7-column upsert in a try/except whose fallback is the
#   SAME `INSERT OR REPLACE` with 6 columns -- so on Postgres BOTH arms are illegal.
#   And on Postgres a failed statement ABORTS THE WHOLE TRANSACTION, so even a valid
#   fallback could not have run inside the same `with get_db()` block. A try/except is
#   the wrong shape here; branching on the backend BEFORE executing is the right one,
#   and it is already the house pattern (web_app.py:22777, :28687, :29045).
#
# WHAT THIS PATCHES
#   (1) boms_save_rates            -- the reported button. Real ON CONFLICT upsert on PG.
#   (2) boms_save_rates flash      -- stop leaking the raw DB error to the user.
#   (3) _boq_record_override       -- the SAME defect, but wrapped in `except Exception:
#                                     pass`, so on live it has been SILENTLY discarding
#                                     every learned BOQ rate since the Postgres cutover.
#                                     Nobody saw an error; the library just never learned.
#
# web_app.py is CRLF + mojibake, so it is NEVER edited with a text editor -- byte
# replacement only (CLAUDE.md "CRITICAL -- Editing web_app.py").

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()
before = len(data)


def apply(old: bytes, new: bytes, label: str) -> None:
    global data
    if new in data:
        print(f"SKIP  {label} -- already applied")
        return
    if old not in data:
        raise SystemExit(f"FAIL  {label} -- anchor not found")
    if data.count(old) != 1:
        raise SystemExit(f"FAIL  {label} -- anchor matches {data.count(old)}x, need exactly 1")
    data = data.replace(old, new, 1)
    print(f"OK    {label}")


# ---------------------------------------------------------------- (1) the upsert
OLD_1 = (
    b'            try:\r\n'
    b'                c.execute(\r\n'
    b'                    "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'                    "(bom_id, labour_pct, overhead_pct, profit_pct, contingency_pct, vat_pct, labour_pct_client) "\r\n'
    b'                    "VALUES (?, ?, ?, ?, ?, ?, ?)",\r\n'
    b'                    (bom_id, lab, ovh, prf, cnt, vat, lab_client),\r\n'
    b'                )\r\n'
    b'            except Exception:\r\n'
    b'                # Column not migrated yet: fall back to legacy 6-col upsert.\r\n'
    b'                c.execute(\r\n'
    b'                    "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'                    "(bom_id, labour_pct, overhead_pct, profit_pct, contingency_pct, vat_pct) "\r\n'
    b'                    "VALUES (?, ?, ?, ?, ?, ?)",\r\n'
    b'                    (bom_id, lab, ovh, prf, cnt, vat),\r\n'
    b'                )\r\n'
)

NEW_1 = (
    b'            # Postgres has NO "INSERT OR REPLACE" -- it is a syntax error, and that\r\n'
    b'            # error is what the owner saw flashed back at them. Branch on the backend\r\n'
    b'            # BEFORE executing (the house pattern at :22777 / :28687 / :29045), because\r\n'
    b'            # on Postgres a failed statement aborts the whole transaction -- so a\r\n'
    b'            # try/except fallback could not have executed anyway.\r\n'
    b'            # bom_id is the PRIMARY KEY, so it is the conflict target.\r\n'
    b'            if bool(os.environ.get("DATABASE_URL")):\r\n'
    b'                c.execute(\r\n'
    b'                    "INSERT INTO marketplace_bom_rates "\r\n'
    b'                    "(bom_id, labour_pct, overhead_pct, profit_pct, contingency_pct, vat_pct, labour_pct_client) "\r\n'
    b'                    "VALUES (?, ?, ?, ?, ?, ?, ?) "\r\n'
    b'                    "ON CONFLICT (bom_id) DO UPDATE SET "\r\n'
    b'                    "labour_pct=EXCLUDED.labour_pct, "\r\n'
    b'                    "overhead_pct=EXCLUDED.overhead_pct, "\r\n'
    b'                    "profit_pct=EXCLUDED.profit_pct, "\r\n'
    b'                    "contingency_pct=EXCLUDED.contingency_pct, "\r\n'
    b'                    "vat_pct=EXCLUDED.vat_pct, "\r\n'
    b'                    "labour_pct_client=EXCLUDED.labour_pct_client, "\r\n'
    b'                    "updated_at=CURRENT_TIMESTAMP",\r\n'
    b'                    (bom_id, lab, ovh, prf, cnt, vat, lab_client),\r\n'
    b'                )\r\n'
    b'            else:\r\n'
    b'                # SQLite: a failed statement does NOT poison the transaction, so the\r\n'
    b'                # legacy 6-column fallback is still safe here if the column is missing.\r\n'
    b'                try:\r\n'
    b'                    c.execute(\r\n'
    b'                        "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'                        "(bom_id, labour_pct, overhead_pct, profit_pct, contingency_pct, vat_pct, labour_pct_client) "\r\n'
    b'                        "VALUES (?, ?, ?, ?, ?, ?, ?)",\r\n'
    b'                        (bom_id, lab, ovh, prf, cnt, vat, lab_client),\r\n'
    b'                    )\r\n'
    b'                except Exception:\r\n'
    b'                    c.execute(\r\n'
    b'                        "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'                        "(bom_id, labour_pct, overhead_pct, profit_pct, contingency_pct, vat_pct) "\r\n'
    b'                        "VALUES (?, ?, ?, ?, ?, ?)",\r\n'
    b'                        (bom_id, lab, ovh, prf, cnt, vat),\r\n'
    b'                    )\r\n'
)

apply(OLD_1, NEW_1, "(1) boms_save_rates -- real ON CONFLICT upsert on Postgres")


# ------------------------------------------------- (2) stop leaking the raw DB error
# The user is not the audience for `syntax error at or near "OR"`. Log it, show a
# sentence they can act on. Directive s15.
OLD_2 = (
    b'        flash(f"Could not save rates: {_e!s}. The Cost Estimate is unchanged.", "danger")\r\n'
)
NEW_2 = (
    b'        flash("Could not save the labour and markup rates -- the Cost Estimate is "\r\n'
    b'              "unchanged. The problem has been logged; please try again.", "danger")\r\n'
)
apply(OLD_2, NEW_2, "(2) boms_save_rates -- do not flash the raw database error at the user")


# ------------------------------------- (3) the same bug, but silent, in the BOQ library
# `_boq_record_override` is non-raising by contract (`except Exception: pass`), so on
# Postgres the syntax error has been swallowed on EVERY call since the cutover: the
# rate library silently learns nothing. A bug you cannot see is still a bug.
# UNIQUE(user_id, description_key) exists on PG (_BOQ_USER_OVERRIDES_DDL_PG:33791),
# so it is the conflict target.
OLD_3 = (
    b'        with get_db() as c:\r\n'
    b'            c.execute(\r\n'
    b'                "INSERT OR REPLACE INTO boq_user_item_overrides "\r\n'
    b'                "(user_id, description_key, unit, basic_price, last_description, "\r\n'
    b'                " supply_pct, install_pct, last_qty) "\r\n'
    b'                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",\r\n'
    b'                (int(uid), key, (unit or "").strip()[:20],\r\n'
    b'                 float(basic or 0), (desc or "").strip()[:500],\r\n'
    b'                 float(supply_pct or 0), float(install_pct or 0),\r\n'
    b'                 float(qty or 0)),\r\n'
    b'            )\r\n'
)
NEW_3 = (
    b'        _vals = (int(uid), key, (unit or "").strip()[:20],\r\n'
    b'                 float(basic or 0), (desc or "").strip()[:500],\r\n'
    b'                 float(supply_pct or 0), float(install_pct or 0),\r\n'
    b'                 float(qty or 0))\r\n'
    b'        with get_db() as c:\r\n'
    b'            # Postgres has no INSERT OR REPLACE. Because this function is non-raising\r\n'
    b'            # (`except Exception: pass` below), the syntax error was swallowed on every\r\n'
    b'            # call since the Postgres cutover -- the rate library silently learned\r\n'
    b'            # NOTHING on live, with no error anywhere to say so.\r\n'
    b'            if bool(os.environ.get("DATABASE_URL")):\r\n'
    b'                c.execute(\r\n'
    b'                    "INSERT INTO boq_user_item_overrides "\r\n'
    b'                    "(user_id, description_key, unit, basic_price, last_description, "\r\n'
    b'                    " supply_pct, install_pct, last_qty) "\r\n'
    b'                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "\r\n'
    b'                    "ON CONFLICT (user_id, description_key) DO UPDATE SET "\r\n'
    b'                    "unit=EXCLUDED.unit, "\r\n'
    b'                    "basic_price=EXCLUDED.basic_price, "\r\n'
    b'                    "last_description=EXCLUDED.last_description, "\r\n'
    b'                    "supply_pct=EXCLUDED.supply_pct, "\r\n'
    b'                    "install_pct=EXCLUDED.install_pct, "\r\n'
    b'                    "last_qty=EXCLUDED.last_qty, "\r\n'
    b'                    "updated_at=CURRENT_TIMESTAMP",\r\n'
    b'                    _vals,\r\n'
    b'                )\r\n'
    b'            else:\r\n'
    b'                c.execute(\r\n'
    b'                    "INSERT OR REPLACE INTO boq_user_item_overrides "\r\n'
    b'                    "(user_id, description_key, unit, basic_price, last_description, "\r\n'
    b'                    " supply_pct, install_pct, last_qty) "\r\n'
    b'                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",\r\n'
    b'                    _vals,\r\n'
    b'                )\r\n'
)
apply(OLD_3, NEW_3, "(3) _boq_record_override -- the same bug, silently discarding learned rates")


TARGET.write_bytes(data)
print(f"\nwrote web_app.py  ({before} -> {len(data)} bytes, +{len(data) - before})")
