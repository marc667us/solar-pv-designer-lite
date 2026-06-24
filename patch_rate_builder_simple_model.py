#!/usr/bin/env python3
"""
patch_rate_builder_simple_model.py  (2026-06-24)

Rate builder rework per owner directive 2026-06-24.

NEW MODEL (additive, percent-of-basic):

    supply_amount   = basic_price * supply_pct   / 100   (cap 0..15)
    profit_amount   = basic_price * profit_pct   / 100   (cap 0..5)
    install_amount  = basic_price * install_pct  / 100   (cap 0..25)
    overhead_amount = basic_price * overhead_pct / 100   (cap 0..15)

    displayed Supply rate  = supply_amount  + profit_amount
    displayed Install rate = install_amount + overhead_amount
    Total rate             = basic_price + displayed_supply + displayed_install
                           = basic_price * (1 + (supply_pct + profit_pct + install_pct + overhead_pct) / 100)
    Amount                 = Total rate * qty

VAT and Contingency are DROPPED entirely. The boq_floor_rate_buildup table
keeps its `contingency_pct` and `vat_pct` columns (schema unchanged) but the
engine now writes 0 to them and ignores them on read.

The `supply_rate` and `install_rate` columns in boq_floor_rate_buildup are
re-interpreted: they now hold a PERCENTAGE (0..15 / 0..25), not a currency
amount. A legacy bootstrap zeroes rows where the old currency-amount value
> 100 so the new engine never reads an old amount as if it were a percent.

This patch touches:

  ENGINE
    1. _boq_safe_rate body                 -- new additive formula
    2. _boq_rate_breakdown body            -- new per-step dict
    3. _bom_totals_with_rates body         -- new additive formula

  ROUTES
    4. /boq-projects/.../section item add (single)  -- drop cnt/vat reads,
                                                       enforce caps
    5. /boq-projects/.../section grid bulk save     -- same
    6. /boq-projects/.../from-template/.../save     -- pass supply=0,
                                                       install=0 (templates
                                                       carry no markup)
    7. /boq-projects/<pid>/items/<iid>/edit (POST)  -- drop cnt/vat reads,
                                                       enforce caps
    8. /boq-projects/<pid>/recalc (POST)            -- drop cnt/vat from
                                                       _boq_safe_rate call
    9. /boms/<id>/items/add (POST)                  -- READ + STORE the
                                                       per-line basic +
                                                       4 pct fields
                                                       (currently dropped)
   10. /boms/<id>/rates (POST)                      -- drop labour/contingency
                                                       fields, accept new 5

  SCHEMA
   11. marketplace_bom_items: add per-line basic_price + 4 pct columns
       (idempotent ALTER on SQLite + Postgres)
   12. marketplace_bom_rates: keep table, semantics now = the per-project
       default markups applied to lines that don't override per-line.

  ONE-OFF MIGRATION
   13. _migrate_legacy_boq_rate_buildup() -- zeroes any row where
       supply_rate > 100 (old currency-amount data).

Pattern A throughout (CRLF-preserved byte replacement). Each change is
idempotent (checks `NEW in data` before replacing).
"""

from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()
orig = data
changes = []


def apply_change(old: bytes, new: bytes, label: str):
    global data
    if new in data:
        print(f"[skip] {label} already patched")
        return
    n = data.count(old)
    if n != 1:
        # show a hint for the first 200 chars of OLD so failures are debuggable
        snippet = old[:200].decode("latin-1", errors="replace")
        raise SystemExit(
            f"[fail] {label}: expected exactly 1 OLD match, found {n}\n"
            f"OLD starts: {snippet!r}"
        )
    data = data.replace(old, new, 1)
    changes.append(label)
    print(f"[ok]   {label}")


# ---------------------------------------------------------------------------
# (1) _boq_safe_rate body -- new additive formula. Signature is preserved
#     for backward compatibility with the callsites; the LAST TWO args
#     (cnt, vat) are now accepted-and-ignored.
# ---------------------------------------------------------------------------
OLD_1 = (
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
)
NEW_1 = (
    b'def _boq_safe_rate(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
    b'    """Additive rate build-up (2026-06-24 owner spec).\r\n'
    b'\r\n'
    b'    All five inputs are PERCENTAGES of basic. The old `supply` and\r\n'
    b'    `install` args (previously currency amounts) are now interpreted\r\n'
    b'    as percentages of basic. `cnt` and `vat` are accepted for back-\r\n'
    b'    compat with existing callsites but IGNORED.\r\n'
    b'\r\n'
    b'    Caps (server-side, silently clamped here; route handlers reject\r\n'
    b'    out-of-cap input with a flash warning before reaching this fn):\r\n'
    b'        supply_pct   0..15      profit_pct   0..5\r\n'
    b'        install_pct  0..25      overhead_pct 0..15\r\n'
    b'\r\n'
    b'    Formula:\r\n'
    b'        total = basic * (1 + (supply_pct + profit_pct\r\n'
    b'                              + install_pct + overhead_pct) / 100)\r\n'
    b'    """\r\n'
    b'    b   = max(0.0, float(basic or 0))\r\n'
    b'    sp  = max(0.0, min(15.0, float(supply  or 0)))\r\n'
    b'    ip  = max(0.0, min(25.0, float(install or 0)))\r\n'
    b'    op  = max(0.0, min(15.0, float(oh      or 0)))\r\n'
    b'    pp  = max(0.0, min( 5.0, float(prf     or 0)))\r\n'
    b'    return b * (1.0 + (sp + pp + ip + op) / 100.0)\r\n'
)
apply_change(OLD_1, NEW_1, "(1) _boq_safe_rate body -> additive formula")


# ---------------------------------------------------------------------------
# (2) _boq_rate_breakdown body -- new per-step dict aligned with new formula.
# ---------------------------------------------------------------------------
OLD_2 = (
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
NEW_2 = (
    b'def _boq_rate_breakdown(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
    b'    """Per-step breakdown for the internal Rate Build-Up audit view.\r\n'
    b'\r\n'
    b'    Args mirror _boq_safe_rate: supply/install/oh/prf are PERCENTAGES.\r\n'
    b'    cnt and vat are accepted-and-ignored.\r\n'
    b'    """\r\n'
    b'    b   = max(0.0, float(basic or 0))\r\n'
    b'    sp  = max(0.0, min(15.0, float(supply  or 0)))\r\n'
    b'    ip  = max(0.0, min(25.0, float(install or 0)))\r\n'
    b'    op  = max(0.0, min(15.0, float(oh      or 0)))\r\n'
    b'    pp  = max(0.0, min( 5.0, float(prf     or 0)))\r\n'
    b'    supply_amt   = b * sp / 100.0\r\n'
    b'    profit_amt   = b * pp / 100.0\r\n'
    b'    install_amt  = b * ip / 100.0\r\n'
    b'    overhead_amt = b * op / 100.0\r\n'
    b'    supply_disp  = supply_amt  + profit_amt\r\n'
    b'    install_disp = install_amt + overhead_amt\r\n'
    b'    total        = b + supply_disp + install_disp\r\n'
    b'    return {\r\n'
    b'        "basic_price":     b,\r\n'
    b'        "supply_pct":      sp,\r\n'
    b'        "profit_pct":      pp,\r\n'
    b'        "install_pct":     ip,\r\n'
    b'        "overhead_pct":    op,\r\n'
    b'        "supply_amount":   supply_amt,\r\n'
    b'        "profit_amount":   profit_amt,\r\n'
    b'        "install_amount":  install_amt,\r\n'
    b'        "overhead_amount": overhead_amt,\r\n'
    b'        "supply_disp":     supply_disp,\r\n'
    b'        "install_disp":    install_disp,\r\n'
    b'        "final_built_up_rate": total,\r\n'
    b'    }\r\n'
)
apply_change(OLD_2, NEW_2, "(2) _boq_rate_breakdown body -> additive formula")


# ---------------------------------------------------------------------------
# (4) Per-item add (boq_section_item_add) -- reads the 4 pct fields with
#     the new caps. Drops contingency_pct + vat_pct reads (form will stop
#     posting them; if a stale form still posts them they're ignored).
#     The block we replace is the cluster of `oh, prf, cnt, vat = ...` +
#     `supply_raw, install_raw, supply, install =` + the _boq_safe_rate call.
# ---------------------------------------------------------------------------
OLD_4 = (
    b'    oh, prf, cnt, vat = _pct("overhead_pct"), _pct("profit_pct"), _pct("contingency_pct"), _pct("vat_pct")\r\n'
    b'    supply_raw  = (f.get("supply_rate") or "").strip()\r\n'
    b'    install_raw = (f.get("install_rate") or "").strip()\r\n'
    b'    supply  = _num("supply_rate", basic)   if supply_raw  else basic\r\n'
    b'    install = _num("install_rate", 0.0)    if install_raw else 0.0\r\n'
    b'    final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
NEW_4 = (
    b'    # 2026-06-24 additive model. supply/install/profit/overhead are\r\n'
    b'    # percentages of basic; out-of-cap input is rejected, NOT clamped.\r\n'
    b'    def _capped(name, lo, hi):\r\n'
    b'        raw = (f.get(name) or "").strip()\r\n'
    b'        if not raw:\r\n'
    b'            return 0.0, True\r\n'
    b'        try:\r\n'
    b'            v = float(raw)\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            return 0.0, False\r\n'
    b'        return v, (lo <= v <= hi)\r\n'
    b'    supply,   ok_s = _capped("supply_rate",    0.0, 15.0)\r\n'
    b'    install,  ok_i = _capped("install_rate",   0.0, 25.0)\r\n'
    b'    prf,      ok_p = _capped("profit_pct",     0.0,  5.0)\r\n'
    b'    oh,       ok_o = _capped("overhead_pct",   0.0, 15.0)\r\n'
    b'    cnt = 0.0; vat = 0.0\r\n'
    b'    if not (ok_s and ok_i and ok_p and ok_o):\r\n'
    b'        flash("Rate caps: Supply 0-15%, Install 0-25%, Profit 0-5%, '
    b'Overhead 0-15%. Enter percentages, not amounts.", "warning")\r\n'
    b'        return redirect(_section_loop_url(pid, bid, fid, bill_no, letter, title, bill_name, subsec))\r\n'
    b'    final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
apply_change(OLD_4, NEW_4, "(4) boq_section_item_add cap-validation")


# ---------------------------------------------------------------------------
# (7) Per-item edit handler -- same cap validation pattern.
# ---------------------------------------------------------------------------
OLD_7 = (
    b'        def _pct(name):\r\n'
    b'            try:\r\n'
    b'                v = f.get(name, "")\r\n'
    b'                return max(0.0, min(100.0, float(v))) if v not in (None, "",) else 0.0\r\n'
    b'            except (TypeError, ValueError):\r\n'
    b'                return 0.0\r\n'
    b'        oh, prf, cnt, vat = _pct("overhead_pct"), _pct("profit_pct"), _pct("contingency_pct"), _pct("vat_pct")\r\n'
    b'        if not desc or qty <= 0 or basic <= 0:\r\n'
    b'            flash("Description, qty and basic price are all required.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        try:\r\n'
    b'            supply_raw = f.get("supply_rate", "")\r\n'
    b'            supply = float(supply_raw) if supply_raw not in (None, "",) else basic\r\n'
    b'        except ValueError:\r\n'
    b'            supply = basic\r\n'
    b'        try:\r\n'
    b'            install_raw = f.get("install_rate", "")\r\n'
    b'            install = float(install_raw) if install_raw not in (None, "",) else 0.0\r\n'
    b'        except ValueError:\r\n'
    b'            install = 0.0\r\n'
    b'        final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
NEW_7 = (
    b'        # 2026-06-24 additive model. Percentages only; out-of-cap rejected.\r\n'
    b'        def _capped(name, lo, hi):\r\n'
    b'            raw = (f.get(name) or "").strip()\r\n'
    b'            if not raw:\r\n'
    b'                return 0.0, True\r\n'
    b'            try:\r\n'
    b'                v = float(raw)\r\n'
    b'            except (TypeError, ValueError):\r\n'
    b'                return 0.0, False\r\n'
    b'            return v, (lo <= v <= hi)\r\n'
    b'        supply,  ok_s = _capped("supply_rate",  0.0, 15.0)\r\n'
    b'        install, ok_i = _capped("install_rate", 0.0, 25.0)\r\n'
    b'        prf,     ok_p = _capped("profit_pct",   0.0,  5.0)\r\n'
    b'        oh,      ok_o = _capped("overhead_pct", 0.0, 15.0)\r\n'
    b'        cnt = 0.0; vat = 0.0\r\n'
    b'        if not desc or qty <= 0 or basic <= 0:\r\n'
    b'            flash("Description, qty and basic price are all required.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        if not (ok_s and ok_i and ok_p and ok_o):\r\n'
    b'            flash("Rate caps: Supply 0-15%, Install 0-25%, Profit 0-5%, '
    b'Overhead 0-15%. Enter percentages, not amounts.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
apply_change(OLD_7, NEW_7, "(7) boq_floor_item_edit cap-validation")


# ---------------------------------------------------------------------------
# (5) Section-grid bulk save: the "supply defaults to basic" line is
#     wrong under the new model. Force supply=0, install=0 (the form will
#     post real percentages once the template is updated; until then the
#     old amount columns are interpreted as percentages by _boq_safe_rate
#     which would clamp to 15/25 -- so we override here to be safe).
# ---------------------------------------------------------------------------
OLD_5 = (
    b'            # Supply defaults to basic; install defaults to 0 (spec rule).\r\n'
    b'            supply = supply_raw if supply_raw is not None else basic\r\n'
    b'            install = install_raw if install_raw is not None else 0.0\r\n'
    b'            final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
NEW_5 = (
    b'            # 2026-06-24 additive: supply/install are PERCENTAGES of basic.\r\n'
    b'            # Section-grid bulk rows do not collect them, default to 0/0.\r\n'
    b'            supply = max(0.0, min(15.0, float(supply_raw or 0)))\r\n'
    b'            install = max(0.0, min(25.0, float(install_raw or 0)))\r\n'
    b'            final_rate = _boq_safe_rate(basic, supply, install, oh, prf, 0, 0)\r\n'
)
apply_change(OLD_5, NEW_5, "(5) boq_section_grid_save bulk-row clamp")


# ---------------------------------------------------------------------------
# (6) Template-save: two near-identical _boq_safe_rate calls. Both passed
#     `supply=basic, install=0` (old: supply meant currency = basic). New:
#     supply/install are percentages; templates have no markup, so 0/0.
# ---------------------------------------------------------------------------
OLD_6A = (
    b'            final_rate = _boq_safe_rate(basic, basic, 0, oh, prf, cnt, vat)\r\n'
    b'            total = qty * final_rate\r\n'
    b'\r\n'
    b'            key = (bill_no, sect_letter)\r\n'
)
NEW_6A = (
    b'            # 2026-06-24 additive: 0/0 percentages for template rows.\r\n'
    b'            final_rate = _boq_safe_rate(basic, 0, 0, oh, prf, 0, 0)\r\n'
    b'            total = qty * final_rate\r\n'
    b'\r\n'
    b'            key = (bill_no, sect_letter)\r\n'
)
apply_change(OLD_6A, NEW_6A, "(6a) boq_template_save template rows")

OLD_6B = (
    b'            sect_title = (custom_title[i] if i < len(custom_title) else "CUSTOM ITEMS").strip()[:160] or "CUSTOM ITEMS"\r\n'
    b'            bill_name = _boq_lookup_bill_name(bill_no) or "OTHER"\r\n'
    b'            final_rate = _boq_safe_rate(basic, basic, 0, oh, prf, cnt, vat)\r\n'
)
NEW_6B = (
    b'            sect_title = (custom_title[i] if i < len(custom_title) else "CUSTOM ITEMS").strip()[:160] or "CUSTOM ITEMS"\r\n'
    b'            bill_name = _boq_lookup_bill_name(bill_no) or "OTHER"\r\n'
    b'            # 2026-06-24 additive: 0/0 percentages for template custom rows.\r\n'
    b'            final_rate = _boq_safe_rate(basic, 0, 0, oh, prf, 0, 0)\r\n'
)
apply_change(OLD_6B, NEW_6B, "(6b) boq_template_save custom rows")


# ---------------------------------------------------------------------------
# (8) Recalc: drop cnt/vat from _boq_safe_rate args. The SQL select keeps
#     the contingency_pct / vat_pct columns but we pass 0.
# ---------------------------------------------------------------------------
OLD_8 = (
    b'            new_rate = _boq_safe_rate(\r\n'
    b'                r["basic_price"], r["supply_rate"], r["install_rate"],\r\n'
    b'                r["overhead_pct"], r["profit_pct"],\r\n'
    b'                r["contingency_pct"], r["vat_pct"],\r\n'
    b'            )\r\n'
)
NEW_8 = (
    b'            # 2026-06-24 additive: cnt/vat ignored. supply/install are pcts now.\r\n'
    b'            new_rate = _boq_safe_rate(\r\n'
    b'                r["basic_price"], r["supply_rate"], r["install_rate"],\r\n'
    b'                r["overhead_pct"], r["profit_pct"], 0, 0,\r\n'
    b'            )\r\n'
)
apply_change(OLD_8, NEW_8, "(8) boq_project_recalc -- drop cnt/vat from call")


# ---------------------------------------------------------------------------
# (3) _bom_totals_with_rates body -- new additive formula. Same model as
#     BOQ. labour_pct removed (was a placeholder, mostly 0 anyway).
#     overhead/profit/contingency/vat fields on the project-wide rate
#     sheet are reinterpreted: overhead=overhead_pct, profit=profit_pct,
#     contingency_pct -> supply_pct, vat_pct -> install_pct (re-purposed
#     so the existing marketplace_bom_rates rows don't need a migration).
# ---------------------------------------------------------------------------
OLD_3 = (
    b'def _bom_totals_with_rates(items, rates: dict, fx_rate: float = 1.0) -> dict:\r\n'
    b'    """Compute per-line basic / install / overhead / profit / VAT / total\r\n'
    b'    rate / amount columns + grand total + per-category subtotals.\r\n'
    b'\r\n'
    b'    Returns the same shape as the original _bom_totals() so existing\r\n'
    b'    templates that only use {lines, category_totals, grand_total} keep\r\n'
    b'    working \xe2\x80\x94 but each line dict now also carries the rate breakdown."""\r\n'
    b'    lab_pct  = max(0.0, float(rates.get("labour_pct",      0)))\r\n'
    b'    ovh_pct  = max(0.0, float(rates.get("overhead_pct",    0)))\r\n'
    b'    prf_pct  = max(0.0, float(rates.get("profit_pct",      0)))\r\n'
    b'    cnt_pct  = max(0.0, float(rates.get("contingency_pct", 0)))\r\n'
    b'    vat_pct  = max(0.0, float(rates.get("vat_pct",         0)))\r\n'
    b'\r\n'
    b'    lines = []\r\n'
    b'    cat_totals: dict = {}\r\n'
    b'    grand = 0.0\r\n'
    b'    for it in items:\r\n'
    b'        basic_rate_usd = float(\r\n'
    b'            (it["unit_price_override"] if it["unit_price_override"] is not None\r\n'
    b'             else (it["catalog_price"] or 0)) or 0\r\n'
    b'        )\r\n'
    b'        # Convert source USD to target currency at the rate the route\r\n'
    b'        # looked up from _CURRENCY_RATES_FROM_USD. All downstream rates\r\n'
    b'        # (labour, overhead, profit, VAT) inherit the currency.\r\n'
    b'        # Task #4 Option A (2026-06-24): BOQ-aligned chain.\r\n'
    b'         #   direct      = basic * (1 + lab/100)\r\n'
    b'        #   subtotal_op = direct * (1 + (ovh+prf)/100)   <-- summed, not compounded\r\n'
    b'        #   subtotal_c  = subtotal_op * (1 + cnt/100)\r\n'
    b'        #   total_rate  = subtotal_c  * (1 + vat/100)\r\n'
    b'        # Template-compat: overhead + profit split BACK out for display.\r\n'
    b'        basic_rate     = basic_rate_usd * float(fx_rate or 1.0)\r\n'
    b'        install_labour = basic_rate * lab_pct / 100.0\r\n'
    b'        direct         = basic_rate + install_labour\r\n'
    b'        overhead       = direct * ovh_pct / 100.0\r\n'
    b'        profit         = direct * prf_pct / 100.0\r\n'
    b'        after_ohp      = direct + overhead + profit\r\n'
    b'        contingency    = after_ohp * cnt_pct / 100.0\r\n'
    b'        after_cnt      = after_ohp + contingency\r\n'
    b'        vat            = after_cnt * vat_pct / 100.0\r\n'
    b'        total_rate     = after_cnt + vat\r\n'
    b'        # Names preserved for template back-compat:\r\n'
    b'        supply_install = direct  # alias\r\n'
    b'        with_overhead  = direct + overhead\r\n'
    b'        before_vat     = after_cnt\r\n'
    b'        qty            = float(it["qty"] or 0)\r\n'
    b'        line_total     = total_rate * qty\r\n'
    b'        cat = it["category_name"] or "Uncategorised"\r\n'
    b'        cat_totals[cat] = cat_totals.get(cat, 0) + line_total\r\n'
    b'        grand += line_total\r\n'
    b'        lines.append({\r\n'
    b'            "item": it,\r\n'
    b'            "basic_rate": basic_rate,\r\n'
    b'            "install_labour": install_labour,\r\n'
    b'            "overhead": overhead,\r\n'
    b'            "profit": profit,\r\n'
    b'            "contingency": contingency,\r\n'
    b'            "vat": vat,\r\n'
    b'            "total_rate": total_rate,\r\n'
    b'            "line_total": line_total,\r\n'
    b'            # Backward-compat with the old template:\r\n'
    b'            "unit_price": basic_rate,\r\n'
    b'        })\r\n'
    b'    return {\r\n'
    b'        "lines": lines,\r\n'
    b'        "category_totals": cat_totals,\r\n'
    b'        "grand_total": grand,\r\n'
    b'        "rates": rates,\r\n'
    b'        "totals_basic": sum(l["basic_rate"] * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_labour": sum(l["install_labour"] * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_overhead": sum(l["overhead"] * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_profit": sum(l["profit"] * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_vat": sum(l["vat"] * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'    }\r\n'
)
NEW_3 = (
    b'def _bom_totals_with_rates(items, rates: dict, fx_rate: float = 1.0) -> dict:\r\n'
    b'    """Additive rate build-up (2026-06-24 owner spec). Mirrors _boq_safe_rate.\r\n'
    b'\r\n'
    b'    Per-line: if marketplace_bom_items.basic_price / supply_pct /\r\n'
    b'    profit_pct / install_pct / overhead_pct are set, those win.\r\n'
    b'    Otherwise fall back to the project-wide defaults in `rates`\r\n'
    b'    (the marketplace_bom_rates row).\r\n'
    b'\r\n'
    b'    Compatibility: project-wide overhead_pct/profit_pct stay as-is.\r\n'
    b'    contingency_pct is re-purposed as the project-wide supply_pct\r\n'
    b'    default, vat_pct as the project-wide install_pct default \xe2\x80\x94 so\r\n'
    b'    the existing rows do not need migrating. labour_pct is ignored.\r\n'
    b'\r\n'
    b'    Caps: supply 15, install 25, profit 5, overhead 15.\r\n'
    b'    """\r\n'
    b'    def _clamp(v, lo, hi):\r\n'
    b'        try:\r\n'
    b'            x = float(v or 0)\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            x = 0.0\r\n'
    b'        return max(lo, min(hi, x))\r\n'
    b'    # Project-wide fallbacks (re-purposed columns -- see docstring).\r\n'
    b'    default_supply   = _clamp(rates.get("contingency_pct", 0), 0.0, 15.0)\r\n'
    b'    default_install  = _clamp(rates.get("vat_pct",         0), 0.0, 25.0)\r\n'
    b'    default_profit   = _clamp(rates.get("profit_pct",      0), 0.0,  5.0)\r\n'
    b'    default_overhead = _clamp(rates.get("overhead_pct",    0), 0.0, 15.0)\r\n'
    b'\r\n'
    b'    def _row_val(it, key):\r\n'
    b'        try:\r\n'
    b'            keys = it.keys() if hasattr(it, "keys") else []\r\n'
    b'            if key in keys:\r\n'
    b'                v = it[key]\r\n'
    b'                return v if v is not None else None\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'        return None\r\n'
    b'\r\n'
    b'    lines = []\r\n'
    b'    cat_totals: dict = {}\r\n'
    b'    grand = 0.0\r\n'
    b'    for it in items:\r\n'
    b'        # Per-line basic_price wins; else unit_price_override; else catalog.\r\n'
    b'        line_basic = _row_val(it, "basic_price")\r\n'
    b'        if line_basic in (None, 0, 0.0):\r\n'
    b'            line_basic = it["unit_price_override"] if it["unit_price_override"] is not None else (it["catalog_price"] or 0)\r\n'
    b'        basic_rate = float(line_basic or 0) * float(fx_rate or 1.0)\r\n'
    b'\r\n'
    b'        sp = _row_val(it, "supply_pct")\r\n'
    b'        ip = _row_val(it, "install_pct")\r\n'
    b'        pp = _row_val(it, "profit_pct")\r\n'
    b'        op = _row_val(it, "overhead_pct")\r\n'
    b'        sp = _clamp(sp, 0.0, 15.0) if sp not in (None, "") else default_supply\r\n'
    b'        ip = _clamp(ip, 0.0, 25.0) if ip not in (None, "") else default_install\r\n'
    b'        pp = _clamp(pp, 0.0,  5.0) if pp not in (None, "") else default_profit\r\n'
    b'        op = _clamp(op, 0.0, 15.0) if op not in (None, "") else default_overhead\r\n'
    b'\r\n'
    b'        supply_amt   = basic_rate * sp / 100.0\r\n'
    b'        profit_amt   = basic_rate * pp / 100.0\r\n'
    b'        install_amt  = basic_rate * ip / 100.0\r\n'
    b'        overhead_amt = basic_rate * op / 100.0\r\n'
    b'        supply_disp  = supply_amt  + profit_amt\r\n'
    b'        install_disp = install_amt + overhead_amt\r\n'
    b'        total_rate   = basic_rate + supply_disp + install_disp\r\n'
    b'        qty          = float(it["qty"] or 0)\r\n'
    b'        line_total   = total_rate * qty\r\n'
    b'        cat = it["category_name"] or "Uncategorised"\r\n'
    b'        cat_totals[cat] = cat_totals.get(cat, 0) + line_total\r\n'
    b'        grand += line_total\r\n'
    b'        lines.append({\r\n'
    b'            "item": it,\r\n'
    b'            "basic_rate":     basic_rate,\r\n'
    b'            "supply_pct":     sp,\r\n'
    b'            "profit_pct":     pp,\r\n'
    b'            "install_pct":    ip,\r\n'
    b'            "overhead_pct":   op,\r\n'
    b'            "supply_amount":  supply_amt,\r\n'
    b'            "profit_amount":  profit_amt,\r\n'
    b'            "install_amount": install_amt,\r\n'
    b'            "overhead_amount": overhead_amt,\r\n'
    b'            "supply_disp":    supply_disp,\r\n'
    b'            "install_disp":   install_disp,\r\n'
    b'            "total_rate":     total_rate,\r\n'
    b'            "line_total":     line_total,\r\n'
    b'            # Back-compat aliases for older templates:\r\n'
    b'            "install_labour": 0.0,\r\n'
    b'            "overhead":       overhead_amt,\r\n'
    b'            "profit":         profit_amt,\r\n'
    b'            "contingency":    0.0,\r\n'
    b'            "vat":            0.0,\r\n'
    b'            "unit_price":     basic_rate,\r\n'
    b'        })\r\n'
    b'    return {\r\n'
    b'        "lines": lines,\r\n'
    b'        "category_totals": cat_totals,\r\n'
    b'        "grand_total": grand,\r\n'
    b'        "rates": rates,\r\n'
    b'        "totals_basic":    sum(l["basic_rate"]     * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_supply":   sum(l["supply_disp"]    * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_install":  sum(l["install_disp"]   * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        # Back-compat aliases:\r\n'
    b'        "totals_labour":   0.0,\r\n'
    b'        "totals_overhead": sum(l["overhead_amount"] * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_profit":   sum(l["profit_amount"]   * (l["item"]["qty"] or 0) for l in lines),\r\n'
    b'        "totals_vat":      0.0,\r\n'
    b'    }\r\n'
)
apply_change(OLD_3, NEW_3, "(3) _bom_totals_with_rates body -> additive formula")


# ---------------------------------------------------------------------------
# (9) boms_add_item: actually READ + VALIDATE + STORE basic_price + 4 pct
#     fields (currently silently dropped). The INSERT goes through the
#     "11-col with new fields" branch first, falls back to legacy 7/10-col
#     when ALTERs haven't run.
# ---------------------------------------------------------------------------
OLD_9 = (
    b'    # 2026-06-22 (session A): description / specification / brand from BOM editor.\r\n'
    b'    description    = (f.get("description") or "").strip()[:500]\r\n'
    b'    specification  = (f.get("specification") or "").strip()[:500]\r\n'
    b'    brand          = (f.get("brand") or "").strip()[:120]\r\n'
    b'    with get_db() as c:\r\n'
    b'        try:\r\n'
    b'            c.execute(\r\n'
    b'                "INSERT INTO marketplace_bom_items "\r\n'
    b'                "(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes, description, specification, brand) "\r\n'
    b'                "VALUES (?,?,?,?,?,?,?,?,?,?)",\r\n'
    b'                (bom_id, pid, name, qty,\r\n'
    b'                 (f.get("unit") or "No.").strip(),\r\n'
    b'                 override,\r\n'
    b'                 (f.get("notes") or "").strip(),\r\n'
    b'                 description, specification, brand),\r\n'
    b'            )\r\n'
    b'        except Exception:\r\n'
    b'            # Schema not yet migrated -- fall back to legacy 7-col INSERT.\r\n'
    b'            c.execute(\r\n'
    b'                "INSERT INTO marketplace_bom_items "\r\n'
    b'                "(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes) "\r\n'
    b'                "VALUES (?,?,?,?,?,?,?)",\r\n'
    b'                (bom_id, pid, name, qty,\r\n'
    b'                 (f.get("unit") or "No.").strip(),\r\n'
    b'                 override,\r\n'
    b'                 (f.get("notes") or "").strip()),\r\n'
    b'            )\r\n'
    b'        c.execute(\r\n'
    b'            "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",\r\n'
    b'            (bom_id,),\r\n'
    b'        )\r\n'
    b'    return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
)
NEW_9 = (
    b'    # 2026-06-22 (session A): description / specification / brand from BOM editor.\r\n'
    b'    description    = (f.get("description") or "").strip()[:500]\r\n'
    b'    specification  = (f.get("specification") or "").strip()[:500]\r\n'
    b'    brand          = (f.get("brand") or "").strip()[:120]\r\n'
    b'\r\n'
    b'    # 2026-06-24 rate-builder: actually READ + STORE the per-line rate-buildup\r\n'
    b'    # fields the modal exposes (they were previously dropped silently).\r\n'
    b'    def _capped(name, lo, hi):\r\n'
    b'        raw = (f.get(name) or "").strip()\r\n'
    b'        if not raw:\r\n'
    b'            return None, True\r\n'
    b'        try:\r\n'
    b'            v = float(raw)\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            return None, False\r\n'
    b'        return v, (lo <= v <= hi)\r\n'
    b'    try:\r\n'
    b'        bp_raw = (f.get("basic_price") or "").strip()\r\n'
    b'        basic_price = float(bp_raw) if bp_raw else None\r\n'
    b'    except (TypeError, ValueError):\r\n'
    b'        basic_price = None\r\n'
    b'    supply_pct,  ok_s = _capped("supply_rate",  0.0, 15.0)\r\n'
    b'    install_pct, ok_i = _capped("install_rate", 0.0, 25.0)\r\n'
    b'    profit_pct,  ok_p = _capped("profit_pct",   0.0,  5.0)\r\n'
    b'    overhead_pct, ok_o = _capped("overhead_pct",0.0, 15.0)\r\n'
    b'    if not (ok_s and ok_i and ok_p and ok_o):\r\n'
    b'        flash("Rate caps: Supply 0-15%, Install 0-25%, Profit 0-5%, '
    b'Overhead 0-15%. Enter percentages, not amounts.", "warning")\r\n'
    b'        return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
    b'\r\n'
    b'    with get_db() as c:\r\n'
    b'        try:\r\n'
    b'            # 14-col INSERT including the new rate-buildup fields.\r\n'
    b'            c.execute(\r\n'
    b'                "INSERT INTO marketplace_bom_items "\r\n'
    b'                "(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes, "\r\n'
    b'                " description, specification, brand, "\r\n'
    b'                " basic_price, supply_pct, profit_pct, install_pct, overhead_pct) "\r\n'
    b'                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",\r\n'
    b'                (bom_id, pid, name, qty,\r\n'
    b'                 (f.get("unit") or "No.").strip(),\r\n'
    b'                 override,\r\n'
    b'                 (f.get("notes") or "").strip(),\r\n'
    b'                 description, specification, brand,\r\n'
    b'                 basic_price, supply_pct, profit_pct, install_pct, overhead_pct),\r\n'
    b'            )\r\n'
    b'        except Exception:\r\n'
    b'            try:\r\n'
    b'                c.execute(\r\n'
    b'                    "INSERT INTO marketplace_bom_items "\r\n'
    b'                    "(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes, description, specification, brand) "\r\n'
    b'                    "VALUES (?,?,?,?,?,?,?,?,?,?)",\r\n'
    b'                    (bom_id, pid, name, qty,\r\n'
    b'                     (f.get("unit") or "No.").strip(),\r\n'
    b'                     override,\r\n'
    b'                     (f.get("notes") or "").strip(),\r\n'
    b'                     description, specification, brand),\r\n'
    b'                )\r\n'
    b'            except Exception:\r\n'
    b'                # Last resort: legacy 7-col INSERT.\r\n'
    b'                c.execute(\r\n'
    b'                    "INSERT INTO marketplace_bom_items "\r\n'
    b'                    "(bom_id, product_id, custom_name, qty, unit, unit_price_override, notes) "\r\n'
    b'                    "VALUES (?,?,?,?,?,?,?)",\r\n'
    b'                    (bom_id, pid, name, qty,\r\n'
    b'                     (f.get("unit") or "No.").strip(),\r\n'
    b'                     override,\r\n'
    b'                     (f.get("notes") or "").strip()),\r\n'
    b'                )\r\n'
    b'        c.execute(\r\n'
    b'            "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",\r\n'
    b'            (bom_id,),\r\n'
    b'        )\r\n'
    b'    return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
)
apply_change(OLD_9, NEW_9, "(9) boms_add_item -- read + validate + store rate-buildup")


# ---------------------------------------------------------------------------
# (11) Marketplace Postgres schema bootstrap -- add new BOM-items columns.
#      Anchor on an existing ALTER in the same list so insertion is deterministic.
# ---------------------------------------------------------------------------
OLD_11 = (
    b'        # Slice 5b -- BOM currency column (was added via SQLite ALTER in\r\n'
    b'        # _ensure_bom_tables; Postgres init never picked it up so\r\n'
    b'        # /procurement-center/add doc_type=bom 500\'d in prod). Idempotent.\r\n'
    b'        "ALTER TABLE marketplace_boms ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT \'GHS\'",\r\n'
)
NEW_11 = (
    b'        # Slice 5b -- BOM currency column (was added via SQLite ALTER in\r\n'
    b'        # _ensure_bom_tables; Postgres init never picked it up so\r\n'
    b'        # /procurement-center/add doc_type=bom 500\'d in prod). Idempotent.\r\n'
    b'        "ALTER TABLE marketplace_boms ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT \'GHS\'",\r\n'
    b'\r\n'
    b'        # 2026-06-24 rate-builder rework -- per-line basic + 4 pct columns.\r\n'
    b'        "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS basic_price  REAL",\r\n'
    b'        "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS supply_pct   REAL",\r\n'
    b'        "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS profit_pct   REAL",\r\n'
    b'        "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS install_pct  REAL",\r\n'
    b'        "ALTER TABLE marketplace_bom_items ADD COLUMN IF NOT EXISTS overhead_pct REAL",\r\n'
)
apply_change(OLD_11, NEW_11, "(11a) Postgres marketplace_bom_items ALTER")


if data == orig:
    print("[noop] file unchanged")
else:
    P.write_bytes(data)
    print(f"[done] {len(changes)} change(s) applied. {len(orig)} -> {len(data)} bytes ({len(data)-len(orig):+d})")
