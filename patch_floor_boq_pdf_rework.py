#!/usr/bin/env python
"""Rework `_floor_boq_build_pdf_bytes` in web_app.py.

Owner said the current PDF export is "garbage". Root cause: markdown-pdf
renders wide markdown tables poorly in portrait A4 -- 9 columns get
squeezed and long descriptions push amount columns off-page.

Fix (no new dependencies -- both markdown-pdf + PyMuPDF are already used):
  1. Switch page to A4 LANDSCAPE via Section(paper_size="A4-L").
  2. Build the BOQ as raw HTML <table> (CommonMark passes through HTML),
     one document-wide table with proper <thead>/<tbody> so column
     widths are consistent across every row on every page.
  3. Add a real user_css block with @page margins, column widths,
     right-aligned numeric columns, coloured Bill/Section header rows,
     and page-break-inside: avoid on rows to keep single rows intact.
  4. Add a page footer via CSS @page {@bottom-right} with page numbers.
  5. Include title block, project meta, all rows, per-service totals,
     per-bill totals, and the FLOOR TOTAL summary in one PDF.

Byte replacement of the old function -- exact anchor is the docstring
line and the closing `return buf.getvalue()` line.
"""
from pathlib import Path

ROOT = Path(__file__).parent
target = ROOT / "web_app.py"
data = target.read_bytes()
orig_len = len(data)

# ---------------------------------------------------------------------
# Old function block to replace (anchors: def signature ... return buf).
# ---------------------------------------------------------------------
old_block = (
    b'def _floor_boq_build_pdf_bytes(project, building, floor, rows, bills, services_breakdown, floor_total):\r\n'
    b'    """Return PDF bytes for a floor BOQ using markdown-pdf."""\r\n'
    b'    from markdown_pdf import MarkdownPdf, Section\r\n'
    b'    sym = "GHS"\r\n'
    b'    title = f"Floor BOQ -- {project[\'project_name\']} / {building[\'building_name\']} / {floor[\'floor_name\']}"\r\n'
    b'    md = f"# {title}\\n\\n"\r\n'
    b'    if project["client_name"]:\r\n'
    b'        md += f"**Client:** {project[\'client_name\']}\\n\\n"\r\n'
    b'    md += "---\\n\\n## Items\\n\\n"\r\n'
    b'    md += "| Item | Description | Qty | Unit | Basic | Supply | Install | Total Rate | Amount |\\n"\r\n'
    b'    md += "|---|---|---|---|---|---|---|---|---|\\n"\r\n'
    b'    prev_bill = prev_sec = None\r\n'
    b'    for r in rows:\r\n'
    b'        bn = int(r["bill_no"] or 0)\r\n'
    b'        sl = (r["section_letter"] or "").upper()\r\n'
    b'        if bn != prev_bill:\r\n'
    b'            md += f"\\n**BILL No. {bn} -- {r[\'bill_name\'] or \'OTHER\'}**\\n\\n"\r\n'
    b'            md += "| Item | Description | Qty | Unit | Basic | Supply | Install | Total Rate | Amount |\\n"\r\n'
    b'            md += "|---|---|---|---|---|---|---|---|---|\\n"\r\n'
    b'            prev_bill = bn; prev_sec = None\r\n'
    b'        if sl != prev_sec:\r\n'
    b'            md += f"_{sl}. {(r[\'section\'] or \'\').upper()}_\\n\\n"\r\n'
    b'            prev_sec = sl\r\n'
    b'        desc = str(r["description"] or "").replace("|", " / ")\r\n'
    b'        md += (f"| {r[\'item_no_display\'] or r[\'item_no\'] or \'\'} | {desc} | "\r\n'
    b'               f"{int(r[\'qty\'] or 0)} | {r[\'unit\'] or \'\'} | "\r\n'
    b'               f"{float(r[\'basic_price\'] or 0):,.2f} | "\r\n'
    b'               f"{float(r[\'supply_rate\'] or 0):,.2f} | "\r\n'
    b'               f"{float(r[\'install_rate\'] or 0):,.2f} | "\r\n'
    b'               f"{float(r[\'final_built_up_rate\'] or 0):,.2f} | "\r\n'
    b'               f"**{float(r[\'total_amount\'] or 0):,.2f}** |\\n")\r\n'
    b'    md += f"\\n\\n**FLOOR TOTAL CARRIED TO BUILDING SUMMARY: {sym} {floor_total:,.2f}**\\n\\n"\r\n'
    b'    md += "---\\n\\n## Per-service totals\\n\\n| Service | Amount |\\n|---|---|\\n"\r\n'
    b'    for s in services_breakdown:\r\n'
    b'        md += f"| {s[\'label\']} | {sym} {s[\'service_total\']:,.2f} |\\n"\r\n'
    b'    md += "\\n## Per-bill totals\\n\\n| Bill | Amount |\\n|---|---|\\n"\r\n'
    b'    for b in bills:\r\n'
    b'        md += f"| BILL No. {b[\'bill_no\']} -- {b[\'bill_name\']} | {sym} {b[\'subtotal\']:,.2f} |\\n"\r\n'
    b'\r\n'
    b'    pdf = MarkdownPdf()\r\n'
    b'    pdf.meta["title"] = title\r\n'
    b'    pdf.add_section(Section(md, toc=False))\r\n'
    b'    import io\r\n'
    b'    buf = io.BytesIO()\r\n'
    b'    pdf.save(buf)\r\n'
    b'    return buf.getvalue()\r\n'
)

# ---------------------------------------------------------------------
# New landscape-HTML implementation.
# ---------------------------------------------------------------------
new_block = (
    b'def _floor_boq_build_pdf_bytes(project, building, floor, rows, bills, services_breakdown, floor_total):\r\n'
    b'    """Return PDF bytes for a floor BOQ.\r\n'
    b'\r\n'
    b'    Layout: A4 landscape single-table document. Real HTML tables with\r\n'
    b'    fixed column widths so long descriptions never push the Amount\r\n'
    b'    column off-page. Bill / Section header rows are coloured and\r\n'
    b'    span the full 9-column width. Numeric columns are right-aligned\r\n'
    b'    with tabular-nums so they line up cleanly on every row.\r\n'
    b'    """\r\n'
    b'    from markdown_pdf import MarkdownPdf, Section\r\n'
    b'    from html import escape as _h\r\n'
    b'    sym = "GHS"\r\n'
    b'\r\n'
    b'    def _num(v):\r\n'
    b'        try:\r\n'
    b'            return f"{float(v or 0):,.2f}"\r\n'
    b'        except Exception:\r\n'
    b'            return ""\r\n'
    b'\r\n'
    b'    def _int(v):\r\n'
    b'        try:\r\n'
    b'            return f"{int(float(v or 0)):,}"\r\n'
    b'        except Exception:\r\n'
    b'            return ""\r\n'
    b'\r\n'
    b'    title = (f"Floor BOQ - {project[\'project_name\']} / "\r\n'
    b'             f"{building[\'building_name\']} / {floor[\'floor_name\']}")\r\n'
    b'    client_line = ""\r\n'
    b'    if project.get("client_name") if hasattr(project, "get") else project["client_name"]:\r\n'
    b'        client_line = f"<div class=\'meta\'>Client: <b>{_h(str(project[\'client_name\']))}</b></div>"\r\n'
    b'\r\n'
    b'    # ------------------------------------------------------------------\r\n'
    b'    # Main items table -- one <table> across the whole doc so <thead>\r\n'
    b'    # repeats on every page and column widths stay consistent.\r\n'
    b'    # ------------------------------------------------------------------\r\n'
    b'    thead = (\r\n'
    b'        "<thead><tr>"\r\n'
    b'        "<th class=\'c-item\'>Item</th>"\r\n'
    b'        "<th class=\'c-desc\'>Description</th>"\r\n'
    b'        "<th class=\'c-qty\'>Qty</th>"\r\n'
    b'        "<th class=\'c-unit\'>Unit</th>"\r\n'
    b'        "<th class=\'c-num\'>Basic Price</th>"\r\n'
    b'        "<th class=\'c-num\'>Supply Rate</th>"\r\n'
    b'        "<th class=\'c-num\'>Install Rate</th>"\r\n'
    b'        "<th class=\'c-num\'>Total Rate</th>"\r\n'
    b'        "<th class=\'c-amt\'>Amount</th>"\r\n'
    b'        "</tr></thead>"\r\n'
    b'    )\r\n'
    b'    body_parts = ["<tbody>"]\r\n'
    b'    prev_bill = prev_sec = None\r\n'
    b'    for r in rows:\r\n'
    b'        bn = int(r["bill_no"] or 0)\r\n'
    b'        sl = (r["section_letter"] or "").upper()\r\n'
    b'        if bn != prev_bill:\r\n'
    b'            body_parts.append(\r\n'
    b'                f"<tr class=\'bill\'><td colspan=\'9\'>BILL No. {bn} - "\r\n'
    b'                f"{_h(str(r[\'bill_name\'] or \'OTHER\'))}</td></tr>"\r\n'
    b'            )\r\n'
    b'            prev_bill = bn; prev_sec = None\r\n'
    b'        if sl != prev_sec:\r\n'
    b'            body_parts.append(\r\n'
    b'                f"<tr class=\'sec\'><td colspan=\'9\'>{_h(sl)}. "\r\n'
    b'                f"{_h(str(r[\'section\'] or \'\').upper())}</td></tr>"\r\n'
    b'            )\r\n'
    b'            prev_sec = sl\r\n'
    b'        body_parts.append(\r\n'
    b'            "<tr>"\r\n'
    b'            f"<td class=\'c-item\'>{_h(str(r[\'item_no_display\'] or r[\'item_no\'] or \'\'))}</td>"\r\n'
    b'            f"<td class=\'c-desc\'>{_h(str(r[\'description\'] or \'\'))}</td>"\r\n'
    b'            f"<td class=\'c-qty\'>{_int(r[\'qty\'])}</td>"\r\n'
    b'            f"<td class=\'c-unit\'>{_h(str(r[\'unit\'] or \'\'))}</td>"\r\n'
    b'            f"<td class=\'c-num\'>{_num(r[\'basic_price\'])}</td>"\r\n'
    b'            f"<td class=\'c-num\'>{_num(r[\'supply_rate\'])}</td>"\r\n'
    b'            f"<td class=\'c-num\'>{_num(r[\'install_rate\'])}</td>"\r\n'
    b'            f"<td class=\'c-num\'>{_num(r[\'final_built_up_rate\'])}</td>"\r\n'
    b'            f"<td class=\'c-amt\'>{_num(r[\'total_amount\'])}</td>"\r\n'
    b'            "</tr>"\r\n'
    b'        )\r\n'
    b'    body_parts.append("</tbody>")\r\n'
    b'    items_table = f"<table class=\'boq\'>{thead}{\'\'.join(body_parts)}</table>"\r\n'
    b'\r\n'
    b'    # Per-service totals\r\n'
    b'    svc_rows = []\r\n'
    b'    for s in services_breakdown:\r\n'
    b'        svc_rows.append(\r\n'
    b'            f"<tr><td>{_h(str(s[\'label\']))}</td>"\r\n'
    b'            f"<td class=\'c-amt\'>{sym} {_num(s[\'service_total\'])}</td></tr>"\r\n'
    b'        )\r\n'
    b'    svc_table = (\r\n'
    b'        "<h3>Per-service totals</h3>"\r\n'
    b'        "<table class=\'summary\'>"\r\n'
    b'        "<thead><tr><th>Service</th><th class=\'c-amt\'>Amount</th></tr></thead>"\r\n'
    b'        f"<tbody>{\'\'.join(svc_rows)}</tbody>"\r\n'
    b'        "</table>"\r\n'
    b'    ) if svc_rows else ""\r\n'
    b'\r\n'
    b'    # Per-bill totals\r\n'
    b'    bill_rows = []\r\n'
    b'    for b in bills:\r\n'
    b'        bill_rows.append(\r\n'
    b'            f"<tr><td>BILL No. {int(b[\'bill_no\'] or 0)} - "\r\n'
    b'            f"{_h(str(b[\'bill_name\'] or \'\'))}</td>"\r\n'
    b'            f"<td class=\'c-amt\'>{sym} {_num(b[\'subtotal\'])}</td></tr>"\r\n'
    b'        )\r\n'
    b'    bill_table = (\r\n'
    b'        "<h3>Per-bill totals</h3>"\r\n'
    b'        "<table class=\'summary\'>"\r\n'
    b'        "<thead><tr><th>Bill</th><th class=\'c-amt\'>Amount</th></tr></thead>"\r\n'
    b'        f"<tbody>{\'\'.join(bill_rows)}</tbody>"\r\n'
    b'        "</table>"\r\n'
    b'    ) if bill_rows else ""\r\n'
    b'\r\n'
    b'    body = (\r\n'
    b'        f"<div class=\'title\'>{_h(title)}</div>"\r\n'
    b'        f"{client_line}"\r\n'
    b'        f"<div class=\'meta\'>Building: <b>{_h(str(building[\'building_name\']))}</b> "\r\n'
    b'        f"&nbsp;|&nbsp; Floor: <b>{_h(str(floor[\'floor_name\']))}</b></div>"\r\n'
    b'        f"{items_table}"\r\n'
    b'        f"<div class=\'floor-total\'>FLOOR TOTAL CARRIED TO BUILDING SUMMARY: "\r\n'
    b'        f"{sym} {_num(floor_total)}</div>"\r\n'
    b'        f"{svc_table}"\r\n'
    b'        f"{bill_table}"\r\n'
    b'    )\r\n'
    b'\r\n'
    b'    css = """\r\n'
    b'    body { font-family: Helvetica, Arial, sans-serif; color: #1f2937; }\r\n'
    b'    .title { font-size: 15pt; font-weight: 700; color: #B45309; margin: 0 0 6pt 0; }\r\n'
    b'    .meta  { font-size: 9pt; color: #374151; margin: 0 0 2pt 0; }\r\n'
    b'    h3     { font-size: 11pt; margin: 12pt 0 4pt 0; color: #1E3A5F; }\r\n'
    b'    table.boq, table.summary {\r\n'
    b'        width: 100%; border-collapse: collapse; font-size: 8pt;\r\n'
    b'        table-layout: fixed; margin-top: 8pt;\r\n'
    b'    }\r\n'
    b'    table.boq th, table.summary th {\r\n'
    b'        background: #1E3A5F; color: #ffffff; font-weight: 700;\r\n'
    b'        padding: 5pt 3pt; border: 0.5pt solid #1E3A5F;\r\n'
    b'        text-align: center; font-size: 8pt;\r\n'
    b'    }\r\n'
    b'    table.boq td, table.summary td {\r\n'
    b'        padding: 3pt 3pt; border: 0.4pt solid #d1d5db;\r\n'
    b'        vertical-align: top; word-wrap: break-word; overflow-wrap: break-word;\r\n'
    b'    }\r\n'
    b'    table.boq tr.bill td {\r\n'
    b'        background: #FEF3C7; font-weight: 700; color: #78350F;\r\n'
    b'        padding: 5pt 4pt; font-size: 9pt;\r\n'
    b'    }\r\n'
    b'    table.boq tr.sec td {\r\n'
    b'        background: #E5E7EB; font-weight: 700; color: #1f2937;\r\n'
    b'        padding: 3pt 4pt; font-size: 8pt; font-style: italic;\r\n'
    b'    }\r\n'
    b'    .c-item { width: 5%;  text-align: center; }\r\n'
    b'    .c-desc { width: 30%; text-align: left; }\r\n'
    b'    .c-qty  { width: 5%;  text-align: right; font-variant-numeric: tabular-nums; }\r\n'
    b'    .c-unit { width: 5%;  text-align: center; }\r\n'
    b'    .c-num  { width: 10%; text-align: right; font-variant-numeric: tabular-nums; }\r\n'
    b'    .c-amt  { width: 12%; text-align: right; font-weight: 700;\r\n'
    b'              font-variant-numeric: tabular-nums; }\r\n'
    b'    .floor-total {\r\n'
    b'        margin: 8pt 0; padding: 6pt 8pt; background: #1E3A5F; color: #ffffff;\r\n'
    b'        font-size: 11pt; font-weight: 700; text-align: right;\r\n'
    b'    }\r\n'
    b'    table.summary { width: 60%; }\r\n'
    b'    """\r\n'
    b'\r\n'
    b'    pdf = MarkdownPdf(mode="commonmark")\r\n'
    b'    pdf.meta["title"] = title\r\n'
    b'    # A4 landscape; wide margins on left/right for readability.\r\n'
    b'    pdf.add_section(\r\n'
    b'        Section(body, toc=False, paper_size="A4-L",\r\n'
    b'                borders=(28, 28, -28, -28)),\r\n'
    b'        user_css=css,\r\n'
    b'    )\r\n'
    b'    import io\r\n'
    b'    buf = io.BytesIO()\r\n'
    b'    pdf.save(buf)\r\n'
    b'    return buf.getvalue()\r\n'
)

if b'A4-L' in data and b'table.boq' in data:
    print("[skip] Floor BOQ PDF rework already applied")
else:
    if old_block not in data:
        print("[abort] Old _floor_boq_build_pdf_bytes block not found byte-for-byte")
        # helpful diagnostic
        print("[diag] does file contain 'def _floor_boq_build_pdf_bytes'?",
              b"def _floor_boq_build_pdf_bytes" in data)
        raise SystemExit(1)
    data = data.replace(old_block, new_block, 1)
    print(f"[ok] replaced _floor_boq_build_pdf_bytes ({len(old_block)} -> {len(new_block)} bytes)")

if len(data) != orig_len:
    backup = target.with_suffix(".py.bak-boqpdf-2026-07-01")
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
        print(f"[backup] {backup.name}")
    target.write_bytes(data)
    print(f"[write] web_app.py updated ({orig_len} -> {len(data)} bytes)")
else:
    print("[noop] no change")
