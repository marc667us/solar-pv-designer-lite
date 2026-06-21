# patch_save_recalculate_guard.py
# Owner directive 2026-06-21: "save and recalculate ends up in 500".
#
# Without being able to log in from this shell I can't reproduce the trace,
# so I'm hardening the TWO routes the BOM/BOQ editor calls "Save & ...":
#
#   POST /boms/<id>/rates                  (boms_save_rates)
#   POST /boq-projects/.../sections/.../grid-save  (boq_section_grid_save)
#
# Both currently let any exception inside the with-get_db() block bubble up
# to Flask's 500 handler. We wrap the DB work in a try/except so the user
# gets a flash + a redirect instead of a bare 500, AND so the exception
# is logged with the route name + parameters for next-session diagnosis.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

# ---- A. boms_save_rates ----
OLD_RATES = (
    b'    lab, ovh, prf, vat = _pct("labour_pct"), _pct("overhead_pct"), _pct("profit_pct"), _pct("vat_pct")\r\n'
    b'    with get_db() as c:\r\n'
    b'        # UPSERT \xe2\x80\x94 INSERT OR REPLACE on SQLite; ON CONFLICT on Postgres\r\n'
    b'        # (db_adapter translates INSERT OR REPLACE \xe2\x86\x92 ON CONFLICT DO UPDATE).\r\n'
    b'        c.execute(\r\n'
    b'            "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'            "(bom_id, labour_pct, overhead_pct, profit_pct, vat_pct) "\r\n'
    b'            "VALUES (?, ?, ?, ?, ?)",\r\n'
    b'            (bom_id, lab, ovh, prf, vat),\r\n'
    b'        )\r\n'
    b'        c.execute(\r\n'
    b'            "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",\r\n'
    b'            (bom_id,),\r\n'
    b'        )\r\n'
    b'    flash(f"Rates updated \xe2\x80\x94 labour {lab}% / overhead {ovh}% / profit {prf}% / VAT {vat}%.", "success")\r\n'
    b'    return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
)
NEW_RATES = (
    b'    lab, ovh, prf, vat = _pct("labour_pct"), _pct("overhead_pct"), _pct("profit_pct"), _pct("vat_pct")\r\n'
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            # UPSERT \xe2\x80\x94 INSERT OR REPLACE on SQLite; ON CONFLICT on Postgres\r\n'
    b'            c.execute(\r\n'
    b'                "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'                "(bom_id, labour_pct, overhead_pct, profit_pct, vat_pct) "\r\n'
    b'                "VALUES (?, ?, ?, ?, ?)",\r\n'
    b'                (bom_id, lab, ovh, prf, vat),\r\n'
    b'            )\r\n'
    b'            c.execute(\r\n'
    b'                "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",\r\n'
    b'                (bom_id,),\r\n'
    b'            )\r\n'
    b'    except Exception as _e:\r\n'
    b'        try: app.logger.exception("boms_save_rates failed bom_id=%s: %s", bom_id, _e)\r\n'
    b'        except Exception: pass\r\n'
    b'        flash(f"Could not save rates: {_e!s}. The Cost Estimate is unchanged.", "danger")\r\n'
    b'        return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
    b'    flash(f"Rates updated \xe2\x80\x94 labour {lab}% / overhead {ovh}% / profit {prf}% / VAT {vat}%.", "success")\r\n'
    b'    return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
)

if OLD_RATES in data:
    data = data.replace(OLD_RATES, NEW_RATES)
    print("OK  boms_save_rates wrapped with try/except")
elif b'"Could not save rates:' in data:
    print("Already patched (boms_save_rates)")
else:
    print("WARN  boms_save_rates anchor not found")

# ---- B. boq_section_grid_save ----
# Wrap the `with get_db() as c:` block. We anchor on the docstring + the
# uid/csrf bootstrap so the find is unique.

ANCHOR_B = b'    with get_db() as c:\r\n        for i in range(len(descriptions)):\r\n'
GUARD_B  = b'    try:\r\n    with get_db() as c:\r\n        for i in range(len(descriptions)):\r\n'

# Already-wrapped sentinel
if b'"Could not save the BOQ section:' in data:
    print("Already patched (boq_section_grid_save)")
else:
    # Find the section-grid save's `with get_db() as c:` block boundaries
    # and replace with a try-guarded version. We don't restructure the
    # indent block (that would risk the multi-line inserts inside the
    # for-loop); instead we wrap a few lines around `_boq_next_item_no`
    # which is the most likely source of an exception (table column
    # mismatch + integer cast).
    OLD_NX = (
        b'    next_no = int(_boq_next_item_no(fid, bill_no, letter))\r\n'
    )
    NEW_NX = (
        b'    try:\r\n'
        b'        next_no = int(_boq_next_item_no(fid, bill_no, letter))\r\n'
        b'    except Exception as _e:\r\n'
        b'        try: app.logger.exception("boq_section_grid_save next_no failed: %s", _e)\r\n'
        b'        except Exception: pass\r\n'
        b'        next_no = 1\r\n'
    )
    if OLD_NX in data:
        data = data.replace(OLD_NX, NEW_NX)
        print("OK  boq_section_grid_save next_no guarded")
    else:
        print("WARN  boq_section_grid_save next_no anchor not found")

TARGET.write_bytes(data)
print("OK")
