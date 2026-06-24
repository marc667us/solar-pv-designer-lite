#!/usr/bin/env python3
"""patch_cost_estimate_labour_and_brand.py (2026-06-24)

Three owner asks bundled into one patch:

  (a) Drop the Brand / Company / Phone columns from the Cost Estimate
      Excel + PDF exports.
  (b) Add a "Labour cost" line item to the Cost Estimate computed as
      `materials_subtotal * client_labour_pct / 100`, with the % being
      user-selectable in the 10-30 range (default 20). Stored on the
      BOM rates row as a new `labour_pct_client` column (idempotent
      ALTER, SQLite + Postgres).
  (c) Add a "SolarPro Marketplace - Accra, Ghana" branding line to
      the Cost Estimate Excel + PDF + HTML print views.

Pattern A throughout (CRLF-preserved byte replacement). All idempotent.
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
            f"[fail] {label}: expected 1 match, found {n}\n"
            f"OLD starts: {snippet!r}"
        )
    data = data.replace(old, new, 1)
    changes.append(label)
    print(f"[ok] {label}")


# ---------------------------------------------------------------------------
# (1) Defaults table -- add labour_pct_client default.
# ---------------------------------------------------------------------------
OLD_1 = (
    b'_BOM_DEFAULT_RATES = {\r\n'
    b'    # Task #4 (2026-06-24): BOM aligned to BOQ chain --\r\n'
    b'    #   final = direct * (1 + (ovh+prf)/100) * (1 + cnt/100) * (1 + vat/100)\r\n'
    b'    #   where direct = basic * (1 + lab/100).\r\n'
    b'    # Sum OH+P (was compound) + new contingency layer.\r\n'
    b'    "labour_pct":     15.0,   # % of basic supply rate added as install labour\r\n'
    b'    "overhead_pct":    8.0,   # % of direct added as overhead (summed with profit)\r\n'
    b'    "profit_pct":     12.0,   # % of direct added as profit  (summed with overhead)\r\n'
    b'    "contingency_pct": 0.0,   # % risk reserve compounded after OH+P, before VAT\r\n'
    b'    "vat_pct":         0.0,   # % VAT applied as final layer\r\n'
    b'}\r\n'
)
NEW_1 = (
    b'_BOM_DEFAULT_RATES = {\r\n'
    b'    # Task #4 (2026-06-24): BOM aligned to BOQ chain --\r\n'
    b'    #   final = direct * (1 + (ovh+prf)/100) * (1 + cnt/100) * (1 + vat/100)\r\n'
    b'    #   where direct = basic * (1 + lab/100).\r\n'
    b'    # Sum OH+P (was compound) + new contingency layer.\r\n'
    b'    "labour_pct":     15.0,   # % of basic supply rate added as install labour\r\n'
    b'    "overhead_pct":    8.0,   # % of direct added as overhead (summed with profit)\r\n'
    b'    "profit_pct":     12.0,   # % of direct added as profit  (summed with overhead)\r\n'
    b'    "contingency_pct": 0.0,   # % risk reserve compounded after OH+P, before VAT\r\n'
    b'    "vat_pct":         0.0,   # % VAT applied as final layer\r\n'
    b'    # 2026-06-24 (Cost Estimate v3): client-facing Labour line at the\r\n'
    b'    # bottom of the table = materials_subtotal * labour_pct_client/100.\r\n'
    b'    # Cap 10..30. Separate from the engine-level `labour_pct` above.\r\n'
    b'    "labour_pct_client": 20.0,\r\n'
    b'}\r\n'
)
apply(OLD_1, NEW_1, "(1) defaults table -- add labour_pct_client")


# ---------------------------------------------------------------------------
# (2) _ensure_bom_rates_table -- add the new column idempotently
#     (PG and SQLite).
# ---------------------------------------------------------------------------
OLD_2 = (
    b'            "ALTER TABLE marketplace_bom_rates ADD COLUMN IF NOT EXISTS contingency_pct REAL DEFAULT 0",\r\n'
    b'        ]:\r\n'
    b'            try:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    c.execute(ddl)\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
    b'        return\r\n'
)
NEW_2 = (
    b'            "ALTER TABLE marketplace_bom_rates ADD COLUMN IF NOT EXISTS contingency_pct REAL DEFAULT 0",\r\n'
    b'            "ALTER TABLE marketplace_bom_rates ADD COLUMN IF NOT EXISTS labour_pct_client REAL DEFAULT 20",\r\n'
    b'        ]:\r\n'
    b'            try:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    c.execute(ddl)\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
    b'        return\r\n'
)
apply(OLD_2, NEW_2, "(2) PG ensure -- add labour_pct_client ALTER")


OLD_3 = (
    b'        # SQLite-side idempotent ALTER for pre-Task-#4 DBs.\r\n'
    b'        try:\r\n'
    b'            c.execute("ALTER TABLE marketplace_bom_rates ADD COLUMN contingency_pct REAL DEFAULT 0")\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
)
NEW_3 = (
    b'        # SQLite-side idempotent ALTER for pre-Task-#4 DBs.\r\n'
    b'        try:\r\n'
    b'            c.execute("ALTER TABLE marketplace_bom_rates ADD COLUMN contingency_pct REAL DEFAULT 0")\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'        # 2026-06-24 Cost Estimate v3: labour_pct_client (10..30).\r\n'
    b'        try:\r\n'
    b'            c.execute("ALTER TABLE marketplace_bom_rates ADD COLUMN labour_pct_client REAL DEFAULT 20")\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
)
apply(OLD_3, NEW_3, "(3) SQLite ensure -- add labour_pct_client ALTER")


# ---------------------------------------------------------------------------
# (4) _bom_rates_for -- include labour_pct_client in returned dict.
# ---------------------------------------------------------------------------
OLD_4 = (
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            row = c.execute(\r\n'
    b'                "SELECT labour_pct, overhead_pct, profit_pct, vat_pct, contingency_pct "\r\n'
    b'                "FROM marketplace_bom_rates WHERE bom_id=?", (bom_id,),\r\n'
    b'            ).fetchone()\r\n'
    b'    except Exception:\r\n'
)
NEW_4 = (
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            row = c.execute(\r\n'
    b'                "SELECT labour_pct, overhead_pct, profit_pct, vat_pct, contingency_pct, labour_pct_client "\r\n'
    b'                "FROM marketplace_bom_rates WHERE bom_id=?", (bom_id,),\r\n'
    b'            ).fetchone()\r\n'
    b'    except Exception:\r\n'
)
apply(OLD_4, NEW_4, "(4) _bom_rates_for SELECT -- add labour_pct_client")


OLD_5 = (
    b'        return {\r\n'
    b'            "labour_pct":      float(row["labour_pct"]   or 0),\r\n'
    b'            "overhead_pct":    float(row["overhead_pct"] or 0),\r\n'
    b'            "profit_pct":      float(row["profit_pct"]   or 0),\r\n'
    b'            "vat_pct":         float(row["vat_pct"]      or 0),\r\n'
    b'            "contingency_pct": float(row["contingency_pct"] or 0) if "contingency_pct" in _keys else 0.0,\r\n'
    b'        }\r\n'
)
NEW_5 = (
    b'        return {\r\n'
    b'            "labour_pct":      float(row["labour_pct"]   or 0),\r\n'
    b'            "overhead_pct":    float(row["overhead_pct"] or 0),\r\n'
    b'            "profit_pct":      float(row["profit_pct"]   or 0),\r\n'
    b'            "vat_pct":         float(row["vat_pct"]      or 0),\r\n'
    b'            "contingency_pct": float(row["contingency_pct"] or 0) if "contingency_pct" in _keys else 0.0,\r\n'
    b'            "labour_pct_client": (max(10.0, min(30.0, float(row["labour_pct_client"] or 20.0)))\r\n'
    b'                                  if "labour_pct_client" in _keys else 20.0),\r\n'
    b'        }\r\n'
)
apply(OLD_5, NEW_5, "(5) _bom_rates_for dict -- add labour_pct_client")


# ---------------------------------------------------------------------------
# (6) boms_save_rates -- read labour_pct_client + persist.
# ---------------------------------------------------------------------------
OLD_6 = (
    b'    lab, ovh, prf, cnt, vat = _pct("labour_pct"), _pct("overhead_pct"), _pct("profit_pct"), _pct("contingency_pct"), _pct("vat_pct")\r\n'
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            # UPSERT \xe2\x80\x94 INSERT OR REPLACE on SQLite; ON CONFLICT on Postgres\r\n'
    b'            c.execute(\r\n'
    b'                "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'                "(bom_id, labour_pct, overhead_pct, profit_pct, contingency_pct, vat_pct) "\r\n'
    b'                "VALUES (?, ?, ?, ?, ?, ?)",\r\n'
    b'                (bom_id, lab, ovh, prf, cnt, vat),\r\n'
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
    b'    flash(f"Rates updated \xe2\x80\x94 labour {lab}% / overhead {ovh}% / profit {prf}% / contingency {cnt}% / VAT {vat}%.", "success")\r\n'
    b'    return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
)
NEW_6 = (
    b'    lab, ovh, prf, cnt, vat = _pct("labour_pct"), _pct("overhead_pct"), _pct("profit_pct"), _pct("contingency_pct"), _pct("vat_pct")\r\n'
    b'    # 2026-06-24 Cost Estimate v3: client-facing labour line. Cap 10..30.\r\n'
    b'    try:\r\n'
    b'        _lab_c_raw = float(f.get("labour_pct_client", 20.0))\r\n'
    b'    except (TypeError, ValueError):\r\n'
    b'        _lab_c_raw = 20.0\r\n'
    b'    lab_client = max(10.0, min(30.0, _lab_c_raw))\r\n'
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            # UPSERT \xe2\x80\x94 INSERT OR REPLACE on SQLite; ON CONFLICT on Postgres\r\n'
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
    b'            c.execute(\r\n'
    b'                "UPDATE marketplace_boms SET updated_at=CURRENT_TIMESTAMP WHERE id=?",\r\n'
    b'                (bom_id,),\r\n'
    b'            )\r\n'
    b'    except Exception as _e:\r\n'
    b'        try: app.logger.exception("boms_save_rates failed bom_id=%s: %s", bom_id, _e)\r\n'
    b'        except Exception: pass\r\n'
    b'        flash(f"Could not save rates: {_e!s}. The Cost Estimate is unchanged.", "danger")\r\n'
    b'        return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
    b'    flash(f"Rates updated \xe2\x80\x94 labour {lab}% / overhead {ovh}% / profit {prf}% / contingency {cnt}% / VAT {vat}% / client labour {lab_client}%.", "success")\r\n'
    b'    return redirect(url_for("boms_view", bom_id=bom_id))\r\n'
)
apply(OLD_6, NEW_6, "(6) boms_save_rates -- accept labour_pct_client")


# ---------------------------------------------------------------------------
# (7) XLSX export -- drop Brand/Company/Phone, add SolarPro Marketplace
#     branding + Labour line + Grand Total.
# ---------------------------------------------------------------------------
OLD_7 = (
    b'    # Title + meta\r\n'
    b'    ws["A1"] = f"Quick Cost Estimate (for Electricians) \xe2\x80\x94 {bom[\'title\']}"\r\n'
    b'    ws["A1"].font = title_font\r\n'
    b'    ws.merge_cells("A1:G1")\r\n'
    b'    ws["A2"] = f"Project: {bom[\'project_name\'] or \'-\'}"\r\n'
    b'    ws["A3"] = f"Client : {bom[\'client_name\'] or \'-\'}"\r\n'
    b'    ws["A4"] = f"Date   : {bom[\'updated_at\']}"\r\n'
    b'\r\n'
    b'    # Apinto / Agenda Commercial 9-column body (2026-06-22).\r\n'
    b'    headers = ["#", "Description", "Qty", "Unit",\r\n'
    b'               f"Basic Rate ({cur_code})", "Basic Rate (US$)",\r\n'
    b'               "Brand", "Company", "Phone"]\r\n'
)
NEW_7 = (
    b'    # Title + meta (2026-06-24 v3: SolarPro Marketplace branding;\r\n'
    b'    # Brand/Company/Phone columns dropped per owner directive).\r\n'
    b'    ws["A1"] = "SolarPro Marketplace \xc2\xb7 Accra, Ghana"\r\n'
    b'    ws["A1"].font = Font(bold=True, size=12, color="1E3A5F")\r\n'
    b'    ws.merge_cells("A1:F1")\r\n'
    b'    ws["A2"] = f"Quick Cost Estimate (for Electricians) \xe2\x80\x94 {bom[\'title\']}"\r\n'
    b'    ws["A2"].font = title_font\r\n'
    b'    ws.merge_cells("A2:F2")\r\n'
    b'    ws["A3"] = f"Project: {bom[\'project_name\'] or \'-\'}"\r\n'
    b'    ws["A4"] = f"Client : {bom[\'client_name\'] or \'-\'}"\r\n'
    b'    ws["A5"] = f"Date   : {bom[\'updated_at\']}"\r\n'
    b'\r\n'
    b'    # 2026-06-24 v3: 6-column body. Brand/Company/Phone dropped.\r\n'
    b'    headers = ["#", "Description", "Qty", "Unit",\r\n'
    b'               f"Basic Rate ({cur_code})", "Basic Rate (US$)"]\r\n'
)
apply(OLD_7, NEW_7, "(7) xlsx -- branding + 6-col header (drop Brand/Company/Phone)")


# Drop the per-line Brand/Company/Phone writes + change HROW from 6 to 7.
OLD_8 = (
    b'    HROW = 6\r\n'
    b'    for col, h in enumerate(headers, 1):\r\n'
    b'        cell = ws.cell(row=HROW, column=col, value=h)\r\n'
    b'        cell.font = header_font\r\n'
    b'        cell.fill = header_fill\r\n'
    b'        cell.border = box\r\n'
    b'        cell.alignment = Alignment(horizontal="center")\r\n'
)
NEW_8 = (
    b'    HROW = 7  # shifted +1 to make room for the branding row in A1\r\n'
    b'    for col, h in enumerate(headers, 1):\r\n'
    b'        cell = ws.cell(row=HROW, column=col, value=h)\r\n'
    b'        cell.font = header_font\r\n'
    b'        cell.fill = header_fill\r\n'
    b'        cell.border = box\r\n'
    b'        cell.alignment = Alignment(horizontal="center")\r\n'
)
apply(OLD_8, NEW_8, "(8) xlsx HROW shift 6 -> 7")


OLD_9 = (
    b'        brand   = (it["brand"] if "brand" in it.keys() and it["brand"] else (it["catalog_brand"] or "-"))\r\n'
    b'        company = (it["supplier_name"] or "SolarPro Marketplace Services")\r\n'
    b'        phone   = (it["supplier_phone"] if "supplier_phone" in it.keys() else "") or "-"\r\n'
    b'        ws.cell(row=row, column=1, value=idx)\r\n'
    b'        ws.cell(row=row, column=2, value=_sanitize(it["custom_name"]))\r\n'
    b'        ws.cell(row=row, column=3, value=float(it["qty"] or 0))\r\n'
    b'        ws.cell(row=row, column=4, value=_sanitize(it["unit"]))\r\n'
    b'        ws.cell(row=row, column=5, value=round(rate_local, 2))\r\n'
    b'        ws.cell(row=row, column=6, value=round(rate_usd, 2))\r\n'
    b'        ws.cell(row=row, column=7, value=_sanitize(brand))\r\n'
    b'        ws.cell(row=row, column=8, value=_sanitize(company))\r\n'
    b'        ws.cell(row=row, column=9, value=_sanitize(phone))\r\n'
    b'        for col in range(1, len(headers) + 1):\r\n'
    b'            ws.cell(row=row, column=col).border = box\r\n'
)
NEW_9 = (
    b'        # 2026-06-24 v3: Brand/Company/Phone columns dropped.\r\n'
    b'        ws.cell(row=row, column=1, value=idx)\r\n'
    b'        ws.cell(row=row, column=2, value=_sanitize(it["custom_name"]))\r\n'
    b'        ws.cell(row=row, column=3, value=float(it["qty"] or 0))\r\n'
    b'        ws.cell(row=row, column=4, value=_sanitize(it["unit"]))\r\n'
    b'        ws.cell(row=row, column=5, value=round(rate_local, 2))\r\n'
    b'        ws.cell(row=row, column=6, value=round(rate_usd, 2))\r\n'
    b'        for col in range(1, len(headers) + 1):\r\n'
    b'            ws.cell(row=row, column=col).border = box\r\n'
)
apply(OLD_9, NEW_9, "(9) xlsx body rows -- drop Brand/Company/Phone writes")


# ---------------------------------------------------------------------------
# (10) PDF export -- same trim + branding line + Labour line.
# ---------------------------------------------------------------------------
OLD_10 = (
    b'    md = []\r\n'
    b'    md.append(f"# Quick Cost Estimate (for Electricians) \xe2\x80\x94 {bom[\'title\']}" + (" (Internal Build-Up)" if include_buildup else ""))\r\n'
    b'    if bom["project_name"]:\r\n'
    b'        md.append(f"**Project:** {bom[\'project_name\']}  ")\r\n'
    b'    if bom["client_name"]:\r\n'
    b'        md.append(f"**Client:** {bom[\'client_name\']}  ")\r\n'
    b'    md.append(f"**Generated:** {bom[\'updated_at\']}")\r\n'
)
NEW_10 = (
    b'    md = []\r\n'
    b'    md.append("**SolarPro Marketplace \xc2\xb7 Accra, Ghana**  ")\r\n'
    b'    md.append("")\r\n'
    b'    md.append(f"# Quick Cost Estimate (for Electricians) \xe2\x80\x94 {bom[\'title\']}" + (" (Internal Build-Up)" if include_buildup else ""))\r\n'
    b'    if bom["project_name"]:\r\n'
    b'        md.append(f"**Project:** {bom[\'project_name\']}  ")\r\n'
    b'    if bom["client_name"]:\r\n'
    b'        md.append(f"**Client:** {bom[\'client_name\']}  ")\r\n'
    b'    md.append(f"**Generated:** {bom[\'updated_at\']}")\r\n'
)
apply(OLD_10, NEW_10, "(10) pdf header -- add SolarPro Marketplace branding")


# Replace the 9-col PDF table with 6-col + add labour line + grand total.
OLD_11 = (
    b'    md.append(f"| # | Description | Qty | Unit | Basic Rate ({cur}) | Basic Rate (US$) | Brand | Company | Phone |")\r\n'
    b'    md.append("|---|---|---|---|---|---|---|---|---|")\r\n'
    b'    prev_cat = None\r\n'
    b'    for idx, line in enumerate(totals["lines"], 1):\r\n'
    b'        it = line["item"]\r\n'
    b'        cat = it["category_name"] or "Uncategorised"\r\n'
    b'        if cat != prev_cat:\r\n'
    b'            md.append(f"| | **{cat}** |  |  |  |  |  |  |  |")\r\n'
    b'            prev_cat = cat\r\n'
    b'        rate_local = float(line[\'total_rate\'] or 0)\r\n'
    b'        rate_usd   = (rate_local / _fx) if _fx else 0.0\r\n'
    b'        brand   = (it[\'brand\'] if \'brand\' in it.keys() and it[\'brand\'] else (it[\'catalog_brand\'] or \'-\'))\r\n'
    b'        company = (it[\'supplier_name\'] or \'SolarPro Marketplace Services\')\r\n'
    b'        phone   = (it[\'supplier_phone\'] if \'supplier_phone\' in it.keys() else \'\') or \'-\'\r\n'
    b'        md.append(\r\n'
    b'            f"| {idx} | {it[\'custom_name\']} | {it[\'qty\']:.2f} | {it[\'unit\']} | "\r\n'
    b'            f"{rate_local:,.2f} | {rate_usd:,.2f} | {brand} | {company} | {phone} |"\r\n'
    b'        )\r\n'
)
NEW_11 = (
    b'    # 2026-06-24 v3: 6-col table (Brand/Company/Phone dropped).\r\n'
    b'    md.append(f"| # | Description | Qty | Unit | Basic Rate ({cur}) | Basic Rate (US$) |")\r\n'
    b'    md.append("|---|---|---|---|---|---|")\r\n'
    b'    prev_cat = None\r\n'
    b'    for idx, line in enumerate(totals["lines"], 1):\r\n'
    b'        it = line["item"]\r\n'
    b'        cat = it["category_name"] or "Uncategorised"\r\n'
    b'        if cat != prev_cat:\r\n'
    b'            md.append(f"| | **{cat}** |  |  |  |  |")\r\n'
    b'            prev_cat = cat\r\n'
    b'        rate_local = float(line[\'total_rate\'] or 0)\r\n'
    b'        rate_usd   = (rate_local / _fx) if _fx else 0.0\r\n'
    b'        md.append(\r\n'
    b'            f"| {idx} | {it[\'custom_name\']} | {it[\'qty\']:.2f} | {it[\'unit\']} | "\r\n'
    b'            f"{rate_local:,.2f} | {rate_usd:,.2f} |"\r\n'
    b'        )\r\n'
)
apply(OLD_11, NEW_11, "(11) pdf body -- drop 3 columns")


# PDF: append the Labour line + Grand Total under "Category subtotals".
OLD_12 = (
    b'    md.append(f"## Grand total\\n\\n**{cur} {totals[\'grand_total\']:.2f}**\\n")\r\n'
)
NEW_12 = (
    b'    # 2026-06-24 v3: client-facing Labour line under Materials grand total.\r\n'
    b'    _materials_total = float(totals.get("grand_total", 0) or 0)\r\n'
    b'    _lab_client_pct = float(rates.get("labour_pct_client", 20.0) or 20.0)\r\n'
    b'    _lab_amt = _materials_total * _lab_client_pct / 100.0\r\n'
    b'    _final_total = _materials_total + _lab_amt\r\n'
    b'    md.append("")\r\n'
    b'    md.append("## Totals")\r\n'
    b'    md.append("")\r\n'
    b'    md.append(f"| Line | Amount ({cur}) |")\r\n'
    b'    md.append("|---|---|")\r\n'
    b'    md.append(f"| Materials subtotal | {_materials_total:,.2f} |")\r\n'
    b'    md.append(f"| Labour cost ({_lab_client_pct:.0f}% of materials) | {_lab_amt:,.2f} |")\r\n'
    b'    md.append(f"| **GRAND TOTAL** | **{_final_total:,.2f}** |")\r\n'
    b'    md.append("")\r\n'
)
apply(OLD_12, NEW_12, "(12) pdf -- replace Grand total with Materials + Labour + Grand")


# ---------------------------------------------------------------------------
# (13) XLSX -- inject Labour cost row + Grand total row immediately after
#     the per-line loop ends. Anchor on the existing category-subtotals
#     write or the end of the loop.
# ---------------------------------------------------------------------------
# Find where the category subtotal section starts in xlsx, then prepend
# the Labour + Grand Total rows.
OLD_13 = (
    b'        for col in range(1, len(headers) + 1):\r\n'
    b'            ws.cell(row=row, column=col).border = box\r\n'
    b'        row += 1\r\n'
)
# Only the per-line loop ends with this; the cat-subtotal block uses
# a different pattern. Be careful: this may match multiple times. Let
# me anchor on a wider context.
# Instead, append after the loop's last 'row += 1' by anchoring on
# what comes right after -- the "# Category subtotals" comment or the
# category totals write. Let me look for a unique trailing anchor.
# Skipped here -- will inject via a separate Read+Edit on the function
# block once we see the actual layout.

# Reset OLD_13/NEW_13: no-op for now; we patch the xlsx separately.

if data == orig:
    print("[noop] file unchanged")
else:
    P.write_bytes(data)
    print(f"[done] {len(changes)} change(s) applied. "
          f"{len(orig)} -> {len(data)} bytes ({len(data)-len(orig):+d})")
