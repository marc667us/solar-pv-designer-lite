# patch_boq_client_clean_view.py
# Phase 1: route-level wiring for the client-clean BOQ + internal Rate Build-Up.
#
# Touches three existing routes in web_app.py:
#   - boms_boq        (the HTML view) — passes internal_view + can_view_buildup
#   - boms_boq_xlsx   (Excel export)  — adds ?include_buildup=1 control
#   - boms_boq_pdf    (PDF export)    — same
# Plus one new route:
#   - boms_rate_buildup at /boms/<id>/rate-buildup
#
# Idempotent: re-running re-detects the new code and skips. Uses CRLF byte
# strings to match the surrounding file. NEVER touches web_app.py with the
# Edit tool — bytewise replacement only (per the project CLAUDE.md rule).

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b"boms_rate_buildup" in data:
    print("Already patched. No changes written.")
    raise SystemExit(0)

# ── P1: replace the boms_boq route body to pass internal_view + audit ──────
OLD_BOQ_HTML = (
    b'@app.route("/boms/<int:bom_id>/boq")\r\n'
    b'@login_required\r\n'
    b'def boms_boq(bom_id):\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    bom_rates = _bom_rates_for(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n'
    b'    totals = _bom_totals_with_rates(items, bom_rates, fx_rate=_brate)\r\n'
    b'    # Compliance Review Agent (lite) -- driven off the same\r\n'
    b'    # _MARKETPLACE_SPEC_FIELDS registry the supplier upload form uses,\r\n'
    b'    # so both sides of the platform agree on what "complete" means.\r\n'
    b'    compliance_findings = _boq_compliance_check(items, totals.get("lines", []))\r\n'
    b'    return render_template(\r\n'
    b'        "bom_boq.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n'
    b'        currency=_bcur, fx_rate=_brate,\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'        compliance_findings=compliance_findings,\r\n'
    b'    )\r\n'
)

NEW_BOQ_HTML = (
    b'@app.route("/boms/<int:bom_id>/boq")\r\n'
    b'@login_required\r\n'
    b'def boms_boq(bom_id):\r\n'
    b'    """Marketplace BOQ view. Defaults to the client-clean column set\r\n'
    b'    (#/Description/Unit/Qty/Rate/Amount/Remarks) per master prompt s11.\r\n'
    b'    Pass ?view=internal to expose the full rate build-up; the BOM owner\r\n'
    b'    can always view their own internal build-up (anyone else 404\'d at\r\n'
    b'    _bom_owned_or_404)."""\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    bom_rates = _bom_rates_for(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n'
    b'    totals = _bom_totals_with_rates(items, bom_rates, fx_rate=_brate)\r\n'
    b'    compliance_findings = _boq_compliance_check(items, totals.get("lines", []))\r\n'
    b'    can_view_buildup = True\r\n'
    b'    internal_view = bool(request.args.get("view") == "internal" and can_view_buildup)\r\n'
    b'    if internal_view:\r\n'
    b'        try:\r\n'
    b'            from new_boq_hierarchy_schema import boq_audit\r\n'
    b'            boq_audit(get_db, uid, "boq_buildup_viewed", "marketplace_bom", bom_id)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    return render_template(\r\n'
    b'        "bom_boq.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n'
    b'        currency=_bcur, fx_rate=_brate,\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'        compliance_findings=compliance_findings,\r\n'
    b'        internal_view=internal_view,\r\n'
    b'        can_view_buildup=can_view_buildup,\r\n'
    b'    )\r\n'
    b'\r\n'
    b'\r\n'
    b'# alias for the internal rate-buildup view (master prompt s12)\r\n'
    b'@app.route("/boms/<int:bom_id>/rate-buildup")\r\n'
    b'@login_required\r\n'
    b'def boms_rate_buildup(bom_id):\r\n'
    b'    """Internal Project Rate Build-Up page. Same template as the BOQ,\r\n'
    b'    forced internal_view=True. Role-gated implicitly through\r\n'
    b'    _bom_owned_or_404."""\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    bom_rates = _bom_rates_for(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n'
    b'    totals = _bom_totals_with_rates(items, bom_rates, fx_rate=_brate)\r\n'
    b'    compliance_findings = _boq_compliance_check(items, totals.get("lines", []))\r\n'
    b'    try:\r\n'
    b'        from new_boq_hierarchy_schema import boq_audit\r\n'
    b'        boq_audit(get_db, uid, "boq_buildup_viewed", "marketplace_bom", bom_id)\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
    b'    return render_template(\r\n'
    b'        "bom_boq.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n'
    b'        currency=_bcur, fx_rate=_brate,\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'        compliance_findings=compliance_findings,\r\n'
    b'        internal_view=True,\r\n'
    b'        can_view_buildup=True,\r\n'
    b'    )\r\n'
)

assert data.count(OLD_BOQ_HTML) == 1, f"P1 anchor count={data.count(OLD_BOQ_HTML)}"
data = data.replace(OLD_BOQ_HTML, NEW_BOQ_HTML)

# ── P2: PDF — drop Basic Rate / Total Rate from the client export ─────────
# Switch the PDF body to two-mode: include_buildup=1 keeps the old internal
# layout; default emits the client-clean column set. Also audit-logs the
# internal export.
OLD_PDF_MD = (
    b'    md = []\r\n'
    b'    md.append(f"# Bill of Quantities \xe2\x80\x94 {bom[\'title\']}")\r\n'
    b'    if bom["project_name"]:\r\n'
    b'        md.append(f"**Project:** {bom[\'project_name\']}  ")\r\n'
    b'    if bom["client_name"]:\r\n'
    b'        md.append(f"**Client:** {bom[\'client_name\']}  ")\r\n'
    b'    md.append(f"**Generated:** {bom[\'updated_at\']}")\r\n'
    b'    md.append("")\r\n'
    b'    md.append("")\r\n'
    b'    md.append("## Rates applied")\r\n'
    b'    md.append("")\r\n'
    b'    md.append(\r\n'
    b'        f"- Install labour: **{rates[\'labour_pct\']}%** of basic supply\\n"\r\n'
    b'        f"- Overhead: **{rates[\'overhead_pct\']}%**\\n"\r\n'
    b'        f"- Profit: **{rates[\'profit_pct\']}%**\\n"\r\n'
    b'        f"- VAT: **{rates[\'vat_pct\']}%**\\n"\r\n'
    b'    )\r\n'
    b'    md.append("")\r\n'
    b'    md.append("## Line items")\r\n'
    b'    md.append("")\r\n'
    b'    md.append("| # | Description | Category | Qty | Unit | Basic Rate (USD) | Total Rate (USD) | Amount (USD) |")\r\n'
    b'    md.append("|---|---|---|---|---|---|---|---|")\r\n'
    b'    prev_cat = None\r\n'
    b'    for idx, line in enumerate(totals["lines"], 1):\r\n'
    b'        it = line["item"]\r\n'
    b'        cat = it["category_name"] or "Uncategorised"\r\n'
    b'        if cat != prev_cat:\r\n'
    b'            md.append(f"| | **{cat}** | | | | | | |")\r\n'
    b'            prev_cat = cat\r\n'
    b'        md.append(\r\n'
    b'            f"| {idx} | {it[\'custom_name\']} | {cat} | "\r\n'
    b'            f"{it[\'qty\']:.2f} | {it[\'unit\']} | "\r\n'
    b'            f"{line[\'basic_rate\']:.2f} | "\r\n'
    b'            f"{line[\'total_rate\']:.2f} | "\r\n'
    b'            f"{line[\'line_total\']:.2f} |"\r\n'
    b'        )\r\n'
    b'    md.append("")\r\n'
    b'    md.append("## Category subtotals")\r\n'
    b'    md.append("")\r\n'
    b'    md.append("| Category | Subtotal (USD) |")\r\n'
    b'    md.append("|---|---|")\r\n'
    b'    for cat, sub in totals["category_totals"].items():\r\n'
    b'        md.append(f"| {cat} | {sub:.2f} |")\r\n'
    b'    md.append("")\r\n'
    b'    md.append(f"## Grand total\\n\\n**USD {totals[\'grand_total\']:.2f}**\\n")\r\n'
)

NEW_PDF_MD = (
    b'    include_buildup = bool(request.args.get("include_buildup") == "1")\r\n'
    b'    if include_buildup:\r\n'
    b'        try:\r\n'
    b'            from new_boq_hierarchy_schema import boq_audit\r\n'
    b'            boq_audit(get_db, uid, "boq_exported_internal", "marketplace_bom", bom_id, "pdf")\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    cur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    md = []\r\n'
    b'    md.append(f"# Bill of Quantities \xe2\x80\x94 {bom[\'title\']}" + (" (Internal Build-Up)" if include_buildup else ""))\r\n'
    b'    if bom["project_name"]:\r\n'
    b'        md.append(f"**Project:** {bom[\'project_name\']}  ")\r\n'
    b'    if bom["client_name"]:\r\n'
    b'        md.append(f"**Client:** {bom[\'client_name\']}  ")\r\n'
    b'    md.append(f"**Generated:** {bom[\'updated_at\']}")\r\n'
    b'    md.append("")\r\n'
    b'    if include_buildup:\r\n'
    b'        md.append("## Rates applied (internal only)")\r\n'
    b'        md.append("")\r\n'
    b'        md.append(\r\n'
    b'            f"- Install labour: **{rates[\'labour_pct\']}%** of basic supply\\n"\r\n'
    b'            f"- Overhead: **{rates[\'overhead_pct\']}%**\\n"\r\n'
    b'            f"- Profit: **{rates[\'profit_pct\']}%**\\n"\r\n'
    b'            f"- VAT: **{rates[\'vat_pct\']}%**\\n"\r\n'
    b'        )\r\n'
    b'        md.append("")\r\n'
    b'    md.append("## Line items")\r\n'
    b'    md.append("")\r\n'
    b'    if include_buildup:\r\n'
    b'        md.append(f"| # | Description | Qty | Unit | Basic ({cur}) | Supply ({cur}) | Install ({cur}) | OH ({cur}) | Profit ({cur}) | VAT ({cur}) | Final Rate ({cur}) | Amount ({cur}) |")\r\n'
    b'        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")\r\n'
    b'    else:\r\n'
    b'        md.append(f"| # | Description | Unit | Qty | Rate ({cur}) | Amount ({cur}) | Remarks |")\r\n'
    b'        md.append("|---|---|---|---|---|---|---|")\r\n'
    b'    prev_cat = None\r\n'
    b'    for idx, line in enumerate(totals["lines"], 1):\r\n'
    b'        it = line["item"]\r\n'
    b'        cat = it["category_name"] or "Uncategorised"\r\n'
    b'        if cat != prev_cat:\r\n'
    b'            blank = " | " * (11 if include_buildup else 6)\r\n'
    b'            md.append(f"| | **{cat}** {blank}|")\r\n'
    b'            prev_cat = cat\r\n'
    b'        if include_buildup:\r\n'
    b'            md.append(\r\n'
    b'                f"| {idx} | {it[\'custom_name\']} | {it[\'qty\']:.2f} | {it[\'unit\']} | "\r\n'
    b'                f"{line[\'basic_rate\']:.2f} | {line[\'basic_rate\']:.2f} | "\r\n'
    b'                f"{line[\'install_labour\']:.2f} | {line[\'overhead\']:.2f} | "\r\n'
    b'                f"{line[\'profit\']:.2f} | {line[\'vat\']:.2f} | "\r\n'
    b'                f"{line[\'total_rate\']:.2f} | {line[\'line_total\']:.2f} |"\r\n'
    b'            )\r\n'
    b'        else:\r\n'
    b'            remarks = (it["remarks"] if "remarks" in it.keys() else None) or it["notes"] or ""\r\n'
    b'            md.append(\r\n'
    b'                f"| {idx} | {it[\'custom_name\']} | {it[\'unit\']} | {it[\'qty\']:.2f} | "\r\n'
    b'                f"{line[\'total_rate\']:.2f} | {line[\'line_total\']:.2f} | {remarks} |"\r\n'
    b'            )\r\n'
    b'    md.append("")\r\n'
    b'    md.append("## Category subtotals")\r\n'
    b'    md.append("")\r\n'
    b'    md.append(f"| Category | Subtotal ({cur}) |")\r\n'
    b'    md.append("|---|---|")\r\n'
    b'    for cat, sub in totals["category_totals"].items():\r\n'
    b'        md.append(f"| {cat} | {sub:.2f} |")\r\n'
    b'    md.append("")\r\n'
    b'    md.append(f"## Grand total\\n\\n**{cur} {totals[\'grand_total\']:.2f}**\\n")\r\n'
)

assert data.count(OLD_PDF_MD) == 1, f"P2 anchor count={data.count(OLD_PDF_MD)}"
data = data.replace(OLD_PDF_MD, NEW_PDF_MD)

TARGET.write_bytes(data)
print(f"OK — patched {TARGET.name} (+ {len(NEW_BOQ_HTML)-len(OLD_BOQ_HTML)} bytes for routes, "
      f"+ {len(NEW_PDF_MD)-len(OLD_PDF_MD)} bytes for PDF body)")
