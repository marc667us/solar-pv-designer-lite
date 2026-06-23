#!/usr/bin/env python3
"""
patch_boq_rate_buildup_v2.py

Switches BOQ rate-buildup math from the buggy FLAT-additive formula to
the industry-standard COMPOUND formula (per Ghana GRA, Nigeria FIRS, and
the Building Cost Information Service practice).

OLD formula (bug):
    final = (supply + install) * (1 + (oh + prf + cnt + vat) / 100)

NEW formula:
    direct       = supply + install
    after_ohp    = direct      * (1 + (oh + prf) / 100)     # contractor markup
    after_cont   = after_ohp   * (1 + cnt / 100)            # contingency on marked-up subtotal
    final        = after_cont  * (1 + vat / 100)            # VAT on contingency-inclusive subtotal

For a typical 30% OH + 10% Profit + 5% Cont + 12.5% VAT chain on
$1300 direct cost:
    flat (old)     = 1300 * 1.575 = 2047.50
    compound (new) = 1300 * 1.40 * 1.05 * 1.125 = 2149.88   (~5% higher)

Three edits, all Pattern A (CRLF-preserved):
1. Replace the body of _boq_safe_rate with the compound formula.
2. Insert _boq_rate_breakdown right after, returning a per-step dict
   for use in the rate-buildup display + admin recalc audit log.
3. Insert a new /boq-projects/<pid>/recalc POST route immediately
   before boq_project_reset. Auth + CSRF + ownership guard;
   recomputes total_amount and final_built_up_rate for every item in
   the project using current rate_buildup percentages; updates both
   boq_floor_items and boq_floor_rate_buildup atomically; flashes
   summary (count of items + old grand total vs new grand total).
"""

from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()
orig = data

# --------------------------------------------------------------------------
# CHANGE 1 -- replace _boq_safe_rate body with compound formula.
# Pattern A: match the full function definition to keep CRLF + indentation.
# --------------------------------------------------------------------------
OLD_1 = (
    b'def _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat):\r\n'
    b'    """Spec rate build-up: final = (supply + install) * (1 + sum_pct/100).\r\n'
    b'    Supply defaults to basic; install defaults to 0."""\r\n'
    b'    b = max(0.0, float(basic or 0))\r\n'
    b'    s = max(0.0, float(supply if supply not in (None, "") else b))\r\n'
    b'    i = max(0.0, float(install if install not in (None, "") else 0))\r\n'
    b'    tot = (float(oh or 0) + float(prf or 0) + float(cnt or 0) + float(vat or 0))\r\n'
    b'    return (s + i) * (1.0 + tot / 100.0)\r\n'
)
NEW_1 = (
    b'def _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat):\r\n'
    b'    """Industry-standard rate build-up (compounded, tax-authority defensible).\r\n'
    b'\r\n'
    b'    Chain:\r\n'
    b'        direct      = supply_rate + install_rate\r\n'
    b'        (supply defaults to basic when blank; install defaults to 0)\r\n'
    b'        subtotal_1  = direct      * (1 + (overhead% + profit%) / 100)\r\n'
    b'        subtotal_2  = subtotal_1  * (1 + contingency% / 100)\r\n'
    b'        final       = subtotal_2  * (1 + VAT% / 100)\r\n'
    b'\r\n'
    b'    Each pct compounds on the running subtotal, NOT added flat to\r\n'
    b'    basic (the old buggy formula understated totals by ~5-10%).\r\n'
    b'    Matches GRA / FIRS / KRA tax-authority practice and the reviewer\r\n'
    b'    comments on the 1UGLS Auditorium sample.\r\n'
    b'    """\r\n'
    b'    b = max(0.0, float(basic or 0))\r\n'
    b'    s = max(0.0, float(supply if supply not in (None, "") else b))\r\n'
    b'    i = max(0.0, float(install if install not in (None, "") else 0))\r\n'
    b'    oh_f  = float(oh  or 0) / 100.0\r\n'
    b'    prf_f = float(prf or 0) / 100.0\r\n'
    b'    cnt_f = float(cnt or 0) / 100.0\r\n'
    b'    vat_f = float(vat or 0) / 100.0\r\n'
    b'    direct = s + i\r\n'
    b'    return direct * (1.0 + oh_f + prf_f) * (1.0 + cnt_f) * (1.0 + vat_f)\r\n'
    b'\r\n'
    b'\r\n'
    b'def _boq_rate_breakdown(basic, supply, install, oh, prf, cnt, vat):\r\n'
    b'    """Per-step breakdown of the rate build-up for audit display.\r\n'
    b'\r\n'
    b'    Returns a dict with each intermediate amount so the rate-buildup\r\n'
    b'    view can show how basic + supplier markup + contractor markup +\r\n'
    b'    contingency + VAT compound to the final built-up rate.\r\n'
    b'    """\r\n'
    b'    b = max(0.0, float(basic or 0))\r\n'
    b'    s = max(0.0, float(supply if supply not in (None, "") else b))\r\n'
    b'    i = max(0.0, float(install if install not in (None, "") else 0))\r\n'
    b'    oh_v  = float(oh  or 0)\r\n'
    b'    prf_v = float(prf or 0)\r\n'
    b'    cnt_v = float(cnt or 0)\r\n'
    b'    vat_v = float(vat or 0)\r\n'
    b'    direct = s + i\r\n'
    b'    after_ohp  = direct     * (1.0 + (oh_v + prf_v) / 100.0)\r\n'
    b'    after_cont = after_ohp  * (1.0 + cnt_v / 100.0)\r\n'
    b'    final      = after_cont * (1.0 + vat_v / 100.0)\r\n'
    b'    return {\r\n'
    b'        "basic_price": b,\r\n'
    b'        "supply_rate": s,\r\n'
    b'        "install_rate": i,\r\n'
    b'        "direct_cost": direct,\r\n'
    b'        "overhead_pct": oh_v,\r\n'
    b'        "profit_pct": prf_v,\r\n'
    b'        "overhead_profit_amt": after_ohp - direct,\r\n'
    b'        "after_overhead_profit": after_ohp,\r\n'
    b'        "contingency_pct": cnt_v,\r\n'
    b'        "contingency_amt": after_cont - after_ohp,\r\n'
    b'        "after_contingency": after_cont,\r\n'
    b'        "vat_pct": vat_v,\r\n'
    b'        "vat_amt": final - after_cont,\r\n'
    b'        "final_built_up_rate": final,\r\n'
    b'    }\r\n'
)

# --------------------------------------------------------------------------
# CHANGE 2 -- insert recalc route immediately before boq_project_reset.
# Pattern A: anchor on the exact boq_project_reset @app.route line so the
# insertion lands deterministically.
# --------------------------------------------------------------------------
OLD_2 = (
    b'@app.route("/boq-projects/<int:pid>/reset", methods=["POST"])\r\n'
    b'@login_required\r\n'
    b'def boq_project_reset(pid):\r\n'
)
NEW_2 = (
    b'@app.route("/boq-projects/<int:pid>/recalc", methods=["POST"])\r\n'
    b'@login_required\r\n'
    b'def boq_project_recalc(pid):\r\n'
    b'    """Recompute total_amount + final_built_up_rate for every item in\r\n'
    b'    the project using the current compound rate-buildup formula.\r\n'
    b'\r\n'
    b'    Idempotent. Reads basic/supply/install/oh/prf/cnt/vat from\r\n'
    b'    boq_floor_rate_buildup, calls _boq_safe_rate, writes the new\r\n'
    b'    final_built_up_rate + total_amount back to BOTH boq_floor_items\r\n'
    b'    and boq_floor_rate_buildup. Flashes count + old vs new grand\r\n'
    b'    total so the owner sees the delta from the math fix.\r\n'
    b'    """\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    project = _boq_project_owned_or_404(pid, uid)\r\n'
    b'    csrf_protect()\r\n'
    b'    confirm = (request.form.get("confirm") or "").strip()\r\n'
    b'    if confirm != "RECALC":\r\n'
    b'        flash("Type RECALC to confirm recomputing all rates.", "warning")\r\n'
    b'        return redirect(url_for("boq_project_overview", pid=pid))\r\n'
    b'    updated = 0\r\n'
    b'    old_grand = 0.0\r\n'
    b'    new_grand = 0.0\r\n'
    b'    with get_db() as c:\r\n'
    b'        rows = c.execute(\r\n'
    b'            "SELECT i.id AS item_id, i.qty, i.total_amount AS old_total, "\r\n'
    b'            "       rb.basic_price, rb.supply_rate, rb.install_rate, "\r\n'
    b'            "       rb.overhead_pct, rb.profit_pct, "\r\n'
    b'            "       rb.contingency_pct, rb.vat_pct "\r\n'
    b'            "FROM boq_floor_items i "\r\n'
    b'            "LEFT JOIN boq_floor_rate_buildup rb ON rb.floor_item_id=i.id "\r\n'
    b'            "WHERE i.project_id=?",\r\n'
    b'            (pid,),\r\n'
    b'        ).fetchall()\r\n'
    b'        for r in rows:\r\n'
    b'            qty = float(r["qty"] or 0)\r\n'
    b'            old_total = float(r["old_total"] or 0)\r\n'
    b'            old_grand += old_total\r\n'
    b'            new_rate = _boq_safe_rate(\r\n'
    b'                r["basic_price"], r["supply_rate"], r["install_rate"],\r\n'
    b'                r["overhead_pct"], r["profit_pct"],\r\n'
    b'                r["contingency_pct"], r["vat_pct"],\r\n'
    b'            )\r\n'
    b'            new_total = qty * new_rate\r\n'
    b'            new_grand += new_total\r\n'
    b'            c.execute(\r\n'
    b'                "UPDATE boq_floor_items SET final_built_up_rate=?, "\r\n'
    b'                "       total_amount=? WHERE id=?",\r\n'
    b'                (new_rate, new_total, r["item_id"]),\r\n'
    b'            )\r\n'
    b'            c.execute(\r\n'
    b'                "UPDATE boq_floor_rate_buildup SET final_built_up_rate=?, "\r\n'
    b'                "       total_amount=? WHERE floor_item_id=?",\r\n'
    b'                (new_rate, new_total, r["item_id"]),\r\n'
    b'            )\r\n'
    b'            updated += 1\r\n'
    b'        c.execute(\r\n'
    b'            "UPDATE boq_projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?",\r\n'
    b'            (pid,),\r\n'
    b'        )\r\n'
    b'    try:\r\n'
    b'        from new_boq_hierarchy_schema import boq_audit\r\n'
    b'        boq_audit(get_db, uid, "boq_project_recalc", "boq_project", pid,\r\n'
    b'                  "items=" + str(updated) + " old_grand=" + str(round(old_grand, 2))\r\n'
    b'                  + " new_grand=" + str(round(new_grand, 2)))\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
    b'    delta = new_grand - old_grand\r\n'
    b'    sign = "+" if delta >= 0 else ""\r\n'
    b'    flash(\r\n'
    b'        "Recalculated " + str(updated) + " item(s). "\r\n'
    b'        "Grand total " + str(round(old_grand, 2)) + " -> "\r\n'
    b'        + str(round(new_grand, 2)) + " (" + sign + str(round(delta, 2)) + ")."\r\n'
    b'        " Using compound rate-buildup formula.",\r\n'
    b'        "success",\r\n'
    b'    )\r\n'
    b'    return redirect(url_for("boq_project_overview", pid=pid))\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.route("/boq-projects/<int:pid>/reset", methods=["POST"])\r\n'
    b'@login_required\r\n'
    b'def boq_project_reset(pid):\r\n'
)


def apply_change(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    if new in data:
        print(f"[skip] {label} already patched")
        return data
    n = data.count(old)
    if n != 1:
        raise SystemExit(f"[fail] {label}: expected exactly 1 OLD match, found {n}")
    print(f"[ok]   {label}: applied (+{len(new) - len(old)} bytes)")
    return data.replace(old, new, 1)


data = apply_change(data, OLD_1, NEW_1, "_boq_safe_rate compound formula + _boq_rate_breakdown")
data = apply_change(data, OLD_2, NEW_2, "boq_project_recalc route")

if data == orig:
    print("[noop] file unchanged")
else:
    P.write_bytes(data)
    print(f"[done] web_app.py: {len(orig)} -> {len(data)} bytes ({len(data)-len(orig):+d})")
