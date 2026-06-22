#!/usr/bin/env python3
"""patch_apinto_9col_reports.py -- 2026-06-22 (session A).

Rebuild the bodies of every BOM/Cost-Estimate + Basic-Price-Sheet report to
the Apinto / Agenda Commercial Limited 9-column layout the owner pointed at
(reference PDFs at pvsolar1/supplier and price/APINTO-ELECTRICAL SCHEDULE.pdf
and pvsolar1/supplier and price/GILGUI WILHEM - T.0137 (3Ph UPS).pdf):

    1 Item No.
    2 Description
    3 Qty
    4 Unit
    5 Basic Rate (LOCAL currency, e.g. GHS)
    6 Basic Rate (US$)
    7 Brand
    8 Company Name (supplier)
    9 Phone Number

Apinto's body has no "Amount" column -- the grand total is computed at the
foot of the table. We keep that. The branded header (shipped 2026-06-21) is
left untouched.

Patches:
  (1) _bom_items_with_prices  -- JOIN s.phone + s.address into the result.
  (2) boms_boq_pdf            -- swap the 7-col markdown body for 9-col.
  (3) boms_boq_xlsx           -- swap the 7-col BOQ sheet for 9-col.
  (4) _price_sheet_markdown   -- 9-col layout (drops Email column to make room
                                 for Basic Rate US$).
  (5) price_sheet_xlsx        -- 9-col layout, same swap.

Each patch is gated on its full-text needle so re-running is a no-op.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    orig_len = len(data)
    log = []

    # ---- (1) _bom_items_with_prices: pull supplier phone + address ---------
    n1 = (
        b"            \"       s.country      AS supplier_country, \"\r\n"
        b"            \"       pc.name        AS category_name, \"\r\n"
    )
    r1 = (
        b"            \"       s.country      AS supplier_country, \"\r\n"
        b"            \"       s.phone        AS supplier_phone, \"\r\n"
        b"            \"       s.address      AS supplier_address, \"\r\n"
        b"            \"       pc.name        AS category_name, \"\r\n"
    )
    if n1 in data:
        data = data.replace(n1, r1, 1)
        log.append("(1) _bom_items_with_prices now joins supplier phone + address.")
    elif b"s.phone        AS supplier_phone" in data:
        log.append("(1) _bom_items_with_prices already joined.")
    else:
        log.append("(1) _bom_items_with_prices anchor NOT FOUND -- aborting.")
        print("\n".join(log)); sys.exit(2)

    # ---- (2) boms_boq_pdf markdown body -> 9-col Apinto layout -------------
    n2 = (
        b"    md.append(\"## Line items\")\r\n"
        b"    md.append(\"\")\r\n"
        b"    if include_buildup:\r\n"
        b"        md.append(f\"| # | Description | Qty | Unit | Basic ({cur}) | Supply ({cur}) | Install ({cur}) | OH ({cur}) | Profit ({cur}) | VAT ({cur}) | Final Rate ({cur}) | Amount ({cur}) |\")\r\n"
        b"        md.append(\"|---|---|---|---|---|---|---|---|---|---|---|---|\")\r\n"
        b"    else:\r\n"
        b"        md.append(f\"| # | Description | Unit | Qty | Rate ({cur}) | Amount ({cur}) | Remarks |\")\r\n"
        b"        md.append(\"|---|---|---|---|---|---|---|\")\r\n"
        b"    prev_cat = None\r\n"
        b"    for idx, line in enumerate(totals[\"lines\"], 1):\r\n"
        b"        it = line[\"item\"]\r\n"
        b"        cat = it[\"category_name\"] or \"Uncategorised\"\r\n"
        b"        if cat != prev_cat:\r\n"
        b"            blank = \" | \" * (11 if include_buildup else 6)\r\n"
        b"            md.append(f\"| | **{cat}** {blank}|\")\r\n"
        b"            prev_cat = cat\r\n"
        b"        if include_buildup:\r\n"
        b"            md.append(\r\n"
        b"                f\"| {idx} | {it['custom_name']} | {it['qty']:.2f} | {it['unit']} | \"\r\n"
        b"                f\"{line['basic_rate']:.2f} | {line['basic_rate']:.2f} | \"\r\n"
        b"                f\"{line['install_labour']:.2f} | {line['overhead']:.2f} | \"\r\n"
        b"                f\"{line['profit']:.2f} | {line['vat']:.2f} | \"\r\n"
        b"                f\"{line['total_rate']:.2f} | {line['line_total']:.2f} |\"\r\n"
        b"            )\r\n"
        b"        else:\r\n"
        b"            remarks = (it[\"remarks\"] if \"remarks\" in it.keys() else None) or it[\"notes\"] or \"\"\r\n"
        b"            md.append(\r\n"
        b"                f\"| {idx} | {it['custom_name']} | {it['unit']} | {it['qty']:.2f} | \"\r\n"
        b"                f\"{line['total_rate']:.2f} | {line['line_total']:.2f} | {remarks} |\"\r\n"
        b"            )\r\n"
    )
    r2 = (
        b"    md.append(\"## Line items\")\r\n"
        b"    md.append(\"\")\r\n"
        b"    # Apinto / Agenda Commercial 9-column body (2026-06-22).\r\n"
        b"    _fx = float(_brate or 1.0) if '_brate' in dir() else float(rates.get('fx_rate', 1.0) or 1.0)\r\n"
        b"    md.append(f\"| # | Description | Qty | Unit | Basic Rate ({cur}) | Basic Rate (US$) | Brand | Company | Phone |\")\r\n"
        b"    md.append(\"|---|---|---|---|---|---|---|---|---|\")\r\n"
        b"    prev_cat = None\r\n"
        b"    for idx, line in enumerate(totals[\"lines\"], 1):\r\n"
        b"        it = line[\"item\"]\r\n"
        b"        cat = it[\"category_name\"] or \"Uncategorised\"\r\n"
        b"        if cat != prev_cat:\r\n"
        b"            md.append(f\"| | **{cat}** |  |  |  |  |  |  |  |\")\r\n"
        b"            prev_cat = cat\r\n"
        b"        rate_local = float(line['total_rate'] or 0)\r\n"
        b"        rate_usd   = (rate_local / _fx) if _fx else 0.0\r\n"
        b"        brand   = (it['brand'] if 'brand' in it.keys() and it['brand'] else (it['catalog_brand'] or '-'))\r\n"
        b"        company = (it['supplier_name'] or 'SolarPro Marketplace Services')\r\n"
        b"        phone   = (it['supplier_phone'] if 'supplier_phone' in it.keys() else '') or '-'\r\n"
        b"        md.append(\r\n"
        b"            f\"| {idx} | {it['custom_name']} | {it['qty']:.2f} | {it['unit']} | \"\r\n"
        b"            f\"{rate_local:,.2f} | {rate_usd:,.2f} | {brand} | {company} | {phone} |\"\r\n"
        b"        )\r\n"
        b"    if include_buildup:\r\n"
        b"        md.append(\"\")\r\n"
        b"        md.append(\"## Internal rate build-up (do not share with client)\")\r\n"
        b"        md.append(\"\")\r\n"
        b"        md.append(f\"| # | Description | Qty | Unit | Basic ({cur}) | +Labour ({cur}) | +OH ({cur}) | +Profit ({cur}) | +VAT ({cur}) | Final Rate ({cur}) | Amount ({cur}) |\")\r\n"
        b"        md.append(\"|---|---|---|---|---|---|---|---|---|---|---|\")\r\n"
        b"        for idx, line in enumerate(totals[\"lines\"], 1):\r\n"
        b"            it = line[\"item\"]\r\n"
        b"            md.append(\r\n"
        b"                f\"| {idx} | {it['custom_name']} | {it['qty']:.2f} | {it['unit']} | \"\r\n"
        b"                f\"{line['basic_rate']:,.2f} | {line['install_labour']:,.2f} | \"\r\n"
        b"                f\"{line['overhead']:,.2f} | {line['profit']:,.2f} | {line['vat']:,.2f} | \"\r\n"
        b"                f\"{line['total_rate']:,.2f} | {line['line_total']:,.2f} |\"\r\n"
        b"            )\r\n"
    )
    if n2 in data:
        data = data.replace(n2, r2, 1)
        log.append("(2) boms_boq_pdf body rewritten to 9-col Apinto.")
    elif b"# Apinto / Agenda Commercial 9-column body (2026-06-22)." in data:
        log.append("(2) boms_boq_pdf body already 9-col Apinto.")
    else:
        log.append("(2) boms_boq_pdf body anchor NOT FOUND -- skipping.")

    # ---- (3) boms_boq_xlsx BOQ sheet -> 9-col Apinto layout ----------------
    n3 = (
        b"    # Client-clean BOQ sheet: # / Description / Unit / Qty / Rate / Amount / Remarks\r\n"
        b"    headers = [\"#\", \"Description\", \"Unit\", \"Qty\",\r\n"
        b"               f\"Rate ({cur_code})\", f\"Amount ({cur_code})\", \"Remarks\"]\r\n"
        b"    HROW = 6\r\n"
    )
    r3 = (
        b"    # Apinto / Agenda Commercial 9-column body (2026-06-22).\r\n"
        b"    headers = [\"#\", \"Description\", \"Qty\", \"Unit\",\r\n"
        b"               f\"Basic Rate ({cur_code})\", \"Basic Rate (US$)\",\r\n"
        b"               \"Brand\", \"Company\", \"Phone\"]\r\n"
        b"    HROW = 6\r\n"
    )
    if n3 in data:
        data = data.replace(n3, r3, 1)
        log.append("(3a) boms_boq_xlsx header swapped to 9-col Apinto.")
    elif b"\"Basic Rate ({cur_code})\", \"Basic Rate (US$)\"," in data:
        log.append("(3a) boms_boq_xlsx header already 9-col Apinto.")
    else:
        log.append("(3a) boms_boq_xlsx header anchor NOT FOUND.")

    # body rows
    n3b = (
        b"        remarks = (it[\"remarks\"] if \"remarks\" in it.keys() else None) or it[\"notes\"] or \"\"\r\n"
        b"        ws.cell(row=row, column=1, value=idx)\r\n"
        b"        ws.cell(row=row, column=2, value=_sanitize(it[\"custom_name\"]))\r\n"
        b"        ws.cell(row=row, column=3, value=_sanitize(it[\"unit\"]))\r\n"
        b"        ws.cell(row=row, column=4, value=float(it[\"qty\"] or 0))\r\n"
        b"        ws.cell(row=row, column=5, value=round(line[\"total_rate\"], 2))\r\n"
        b"        ws.cell(row=row, column=6, value=round(line[\"line_total\"], 2))\r\n"
        b"        ws.cell(row=row, column=7, value=_sanitize(remarks))\r\n"
        b"        for col in range(1, len(headers) + 1):\r\n"
        b"            ws.cell(row=row, column=col).border = box\r\n"
        b"        row += 1\r\n"
    )
    r3b = (
        b"        _fx = float(_brate or 1.0)\r\n"
        b"        rate_local = float(line[\"total_rate\"] or 0)\r\n"
        b"        rate_usd   = (rate_local / _fx) if _fx else 0.0\r\n"
        b"        brand   = (it[\"brand\"] if \"brand\" in it.keys() and it[\"brand\"] else (it[\"catalog_brand\"] or \"-\"))\r\n"
        b"        company = (it[\"supplier_name\"] or \"SolarPro Marketplace Services\")\r\n"
        b"        phone   = (it[\"supplier_phone\"] if \"supplier_phone\" in it.keys() else \"\") or \"-\"\r\n"
        b"        ws.cell(row=row, column=1, value=idx)\r\n"
        b"        ws.cell(row=row, column=2, value=_sanitize(it[\"custom_name\"]))\r\n"
        b"        ws.cell(row=row, column=3, value=float(it[\"qty\"] or 0))\r\n"
        b"        ws.cell(row=row, column=4, value=_sanitize(it[\"unit\"]))\r\n"
        b"        ws.cell(row=row, column=5, value=round(rate_local, 2))\r\n"
        b"        ws.cell(row=row, column=6, value=round(rate_usd, 2))\r\n"
        b"        ws.cell(row=row, column=7, value=_sanitize(brand))\r\n"
        b"        ws.cell(row=row, column=8, value=_sanitize(company))\r\n"
        b"        ws.cell(row=row, column=9, value=_sanitize(phone))\r\n"
        b"        for col in range(1, len(headers) + 1):\r\n"
        b"            ws.cell(row=row, column=col).border = box\r\n"
        b"        row += 1\r\n"
    )
    if n3b in data:
        data = data.replace(n3b, r3b, 1)
        log.append("(3b) boms_boq_xlsx body cells rewritten.")
    elif b"company = (it[\"supplier_name\"] or \"SolarPro Marketplace Services\")" in data:
        log.append("(3b) boms_boq_xlsx body already rewritten.")
    else:
        log.append("(3b) boms_boq_xlsx body anchor NOT FOUND.")

    # subtotals row uses col 6 -> 5 (col 5/6 are local/USD rates; total goes
    # under local). We need to retarget the subtotal/grand total writes.
    n3c = (
        b"    # Subtotals + grand total\r\n"
        b"    row += 1\r\n"
        b"    for cat, sub in totals[\"category_totals\"].items():\r\n"
        b"        ws.cell(row=row, column=2, value=f\"{cat} subtotal\").font = bold\r\n"
        b"        ws.cell(row=row, column=6, value=round(sub, 2)).font = bold\r\n"
        b"        row += 1\r\n"
        b"    row += 1\r\n"
        b"    ws.cell(row=row, column=2, value=\"GRAND TOTAL\").font = title_font\r\n"
        b"    ws.cell(row=row, column=6, value=round(totals[\"grand_total\"], 2)).font = title_font\r\n"
        b"\r\n"
        b"    for col, w in enumerate([5, 40, 8, 8, 14, 14, 30], 1):\r\n"
        b"        ws.column_dimensions[get_column_letter(col)].width = w\r\n"
    )
    r3c = (
        b"    # Subtotals + grand total (9-col layout: rate column is #5).\r\n"
        b"    row += 1\r\n"
        b"    for cat, sub in totals[\"category_totals\"].items():\r\n"
        b"        ws.cell(row=row, column=2, value=f\"{cat} subtotal (qty * rate, {cur_code})\").font = bold\r\n"
        b"        ws.cell(row=row, column=5, value=round(sub, 2)).font = bold\r\n"
        b"        row += 1\r\n"
        b"    row += 1\r\n"
        b"    ws.cell(row=row, column=2, value=f\"GRAND TOTAL ({cur_code})\").font = title_font\r\n"
        b"    ws.cell(row=row, column=5, value=round(totals[\"grand_total\"], 2)).font = title_font\r\n"
        b"\r\n"
        b"    for col, w in enumerate([5, 36, 7, 8, 16, 16, 14, 24, 18], 1):\r\n"
        b"        ws.column_dimensions[get_column_letter(col)].width = w\r\n"
    )
    if n3c in data:
        data = data.replace(n3c, r3c, 1)
        log.append("(3c) boms_boq_xlsx subtotal/grand-total cells retargeted to col 5.")
    elif b"GRAND TOTAL ({cur_code})" in data:
        log.append("(3c) boms_boq_xlsx subtotal/grand-total already retargeted.")
    else:
        log.append("(3c) boms_boq_xlsx subtotal anchor NOT FOUND.")

    # ---- (4) _price_sheet_markdown -> 9-col Apinto layout -------------------
    n4 = (
        b"        f\"| # | Product / item description | Qty | Unit | Price ({cur}) | Supplier | Brand | Phone | Email |\",\r\n"
        b"        \"|---|---|---|---|---|---|---|---|---|\",\r\n"
        b"    ]\r\n"
        b"    for idx, it in enumerate(items, 1):\r\n"
        b"        md.append(\r\n"
        b"            f\"| {idx} | {it['custom_name']} | 1 | {it['unit']} | \"\r\n"
        b"            f\"{float(it['price_at_add'] or 0):.2f} | \"\r\n"
        b"            f\"{it['supplier_name'] or '-'} | \"\r\n"
        b"            f\"{it['supplier_brand'] or '-'} | \"\r\n"
        b"            f\"{it['supplier_phone'] or '-'} | \"\r\n"
        b"            f\"{it['supplier_email'] or '-'} |\"\r\n"
        b"        )\r\n"
    )
    r4 = (
        b"        f\"| # | Description | Qty | Unit | Basic Rate ({cur}) | Basic Rate (US$) | Brand | Company | Phone |\",\r\n"
        b"        \"|---|---|---|---|---|---|---|---|---|\",\r\n"
        b"    ]\r\n"
        b"    try:\r\n"
        b"        _fx = float(_CURRENCY_RATES_FROM_USD.get((cur or 'USD').upper(), 1.0) or 1.0)\r\n"
        b"    except Exception:\r\n"
        b"        _fx = 1.0\r\n"
        b"    for idx, it in enumerate(items, 1):\r\n"
        b"        rate_local = float(it['price_at_add'] or 0)\r\n"
        b"        rate_usd   = (rate_local / _fx) if _fx else 0.0\r\n"
        b"        md.append(\r\n"
        b"            f\"| {idx} | {it['custom_name']} | 1 | {it['unit']} | \"\r\n"
        b"            f\"{rate_local:,.2f} | {rate_usd:,.2f} | \"\r\n"
        b"            f\"{it['supplier_brand'] or '-'} | \"\r\n"
        b"            f\"{it['supplier_name'] or '-'} | \"\r\n"
        b"            f\"{it['supplier_phone'] or '-'} |\"\r\n"
        b"        )\r\n"
    )
    if n4 in data:
        data = data.replace(n4, r4, 1)
        log.append("(4) _price_sheet_markdown rewritten to 9-col Apinto.")
    elif b"f\"| # | Description | Qty | Unit | Basic Rate ({cur}) | Basic Rate (US$) | Brand | Company | Phone |\"" in data:
        log.append("(4) _price_sheet_markdown already 9-col Apinto.")
    else:
        log.append("(4) _price_sheet_markdown anchor NOT FOUND.")

    # ---- (5) price_sheet_xlsx -> 9-col Apinto layout ------------------------
    n5 = (
        b"    headers = [\"#\", \"Product / item description\", \"Qty\", \"Unit\",\r\n"
        b"               f\"Price ({cur})\", \"Supplier\", \"Brand\",\r\n"
        b"               \"Phone\", \"Email\", \"Address\"]\r\n"
        b"    HROW = 5\r\n"
    )
    r5 = (
        b"    headers = [\"#\", \"Description\", \"Qty\", \"Unit\",\r\n"
        b"               f\"Basic Rate ({cur})\", \"Basic Rate (US$)\",\r\n"
        b"               \"Brand\", \"Company\", \"Phone\"]\r\n"
        b"    HROW = 5\r\n"
    )
    if n5 in data:
        data = data.replace(n5, r5, 1)
        log.append("(5a) price_sheet_xlsx header swapped to 9-col Apinto.")
    elif b"\"Basic Rate ({cur})\", \"Basic Rate (US$)\",\r\n               \"Brand\", \"Company\"" in data:
        log.append("(5a) price_sheet_xlsx header already 9-col Apinto.")
    else:
        log.append("(5a) price_sheet_xlsx header anchor NOT FOUND.")

    n5b = (
        b"    row = HROW + 1\r\n"
        b"    for idx, it in enumerate(items, 1):\r\n"
        b"        ws.cell(row=row, column=1, value=idx)\r\n"
        b"        ws.cell(row=row, column=2, value=_san(it[\"custom_name\"]))\r\n"
        b"        ws.cell(row=row, column=3, value=1)\r\n"
        b"        ws.cell(row=row, column=4, value=_san(it[\"unit\"]))\r\n"
        b"        ws.cell(row=row, column=5, value=round(float(it[\"price_at_add\"] or 0), 2))\r\n"
        b"        ws.cell(row=row, column=6, value=_san(it[\"supplier_name\"]))\r\n"
        b"        ws.cell(row=row, column=7, value=_san(it[\"supplier_brand\"]))\r\n"
        b"        ws.cell(row=row, column=8, value=_san(it[\"supplier_phone\"]))\r\n"
        b"        ws.cell(row=row, column=9, value=_san(it[\"supplier_email\"]))\r\n"
        b"        ws.cell(row=row, column=10, value=_san(it[\"supplier_address\"]))\r\n"
        b"        for col in range(1, 11):\r\n"
        b"            ws.cell(row=row, column=col).border = box\r\n"
        b"        row += 1\r\n"
        b"\r\n"
        b"    for col, w in enumerate([5, 38, 6, 8, 14, 22, 16, 16, 24, 32], 1):\r\n"
        b"        ws.column_dimensions[get_column_letter(col)].width = w\r\n"
    )
    r5b = (
        b"    row = HROW + 1\r\n"
        b"    try:\r\n"
        b"        _fx = float(_CURRENCY_RATES_FROM_USD.get((cur or 'USD').upper(), 1.0) or 1.0)\r\n"
        b"    except Exception:\r\n"
        b"        _fx = 1.0\r\n"
        b"    for idx, it in enumerate(items, 1):\r\n"
        b"        rate_local = float(it[\"price_at_add\"] or 0)\r\n"
        b"        rate_usd   = (rate_local / _fx) if _fx else 0.0\r\n"
        b"        ws.cell(row=row, column=1, value=idx)\r\n"
        b"        ws.cell(row=row, column=2, value=_san(it[\"custom_name\"]))\r\n"
        b"        ws.cell(row=row, column=3, value=1)\r\n"
        b"        ws.cell(row=row, column=4, value=_san(it[\"unit\"]))\r\n"
        b"        ws.cell(row=row, column=5, value=round(rate_local, 2))\r\n"
        b"        ws.cell(row=row, column=6, value=round(rate_usd, 2))\r\n"
        b"        ws.cell(row=row, column=7, value=_san(it[\"supplier_brand\"]))\r\n"
        b"        ws.cell(row=row, column=8, value=_san(it[\"supplier_name\"]))\r\n"
        b"        ws.cell(row=row, column=9, value=_san(it[\"supplier_phone\"]))\r\n"
        b"        for col in range(1, 10):\r\n"
        b"            ws.cell(row=row, column=col).border = box\r\n"
        b"        row += 1\r\n"
        b"\r\n"
        b"    for col, w in enumerate([5, 38, 6, 8, 16, 16, 16, 24, 18], 1):\r\n"
        b"        ws.column_dimensions[get_column_letter(col)].width = w\r\n"
    )
    if n5b in data:
        data = data.replace(n5b, r5b, 1)
        log.append("(5b) price_sheet_xlsx body rewritten to 9-col Apinto.")
    elif b"rate_local = float(it[\"price_at_add\"] or 0)" in data:
        log.append("(5b) price_sheet_xlsx body already rewritten.")
    else:
        log.append("(5b) price_sheet_xlsx body anchor NOT FOUND.")

    if len(data) == orig_len and data == open(PATH, "rb").read():
        log.append("\nNo changes -- already patched.")
        print("\n".join(log))
        return
    with open(PATH, "wb") as fh:
        fh.write(data)
    log.append(f"\nwrote {PATH} ({orig_len} -> {len(data)} bytes)")
    print("\n".join(log))


if __name__ == "__main__":
    main()
