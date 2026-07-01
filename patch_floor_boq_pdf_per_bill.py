#!/usr/bin/env python
"""Follow-up to patch_floor_boq_pdf_rework.py.

Empirical finding: PyMuPDF's HTML story renderer (used by markdown-pdf)
does NOT repeat <thead> on page breaks even with display:table-header-group.
Pages 2/3 lost their column headers.

Fix: emit one <table> PER BILL. Each bill's table has its own <thead>
so column headers are visible at the start of each bill (and each new
bill typically starts near the top of a page in a real BOQ).

Also adds:
  * a page-break-inside: avoid + subtotal banner after each bill's table.
  * a bill-banner element ABOVE the table (was previously the first row
    inside the table) so a bill title cannot end up orphaned at the
    bottom of a page while its rows spill to the next.

Idempotent: skips if 'bill-banner' class already in the file.
"""
from pathlib import Path

ROOT = Path(__file__).parent
target = ROOT / "web_app.py"
data = target.read_bytes()
orig_len = len(data)

# --- Old body-building block from the previous patch ------------------
old_body = (
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
)

new_body = (
    b'    # ------------------------------------------------------------------\r\n'
    b'    # One <table> PER BILL. PyMuPDF story renderer does not repeat\r\n'
    b'    # <thead> across page breaks -- fresh headers per bill guarantee\r\n'
    b'    # that continuation pages always start near a table with visible\r\n'
    b'    # column headers.\r\n'
    b'    # ------------------------------------------------------------------\r\n'
    b'    _thead = (\r\n'
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
    b'\r\n'
    b'    # Group rows by bill number in stable order of first appearance.\r\n'
    b'    _bill_order = []\r\n'
    b'    _by_bill = {}\r\n'
    b'    for r in rows:\r\n'
    b'        bn = int(r["bill_no"] or 0)\r\n'
    b'        if bn not in _by_bill:\r\n'
    b'            _bill_order.append(bn)\r\n'
    b'            _by_bill[bn] = {"name": r["bill_name"] or "OTHER", "rows": []}\r\n'
    b'        _by_bill[bn]["rows"].append(r)\r\n'
    b'\r\n'
    b'    # Bill subtotals from the pre-computed bills list (fallback: sum).\r\n'
    b'    _sub_by_bill = {int(b["bill_no"] or 0): float(b["subtotal"] or 0) for b in bills}\r\n'
    b'\r\n'
    b'    _bill_blocks = []\r\n'
    b'    for bn in _bill_order:\r\n'
    b'        _bname = _by_bill[bn]["name"]\r\n'
    b'        _brows = _by_bill[bn]["rows"]\r\n'
    b'        _tbody = ["<tbody>"]\r\n'
    b'        prev_sec = None\r\n'
    b'        for r in _brows:\r\n'
    b'            sl = (r["section_letter"] or "").upper()\r\n'
    b'            if sl != prev_sec:\r\n'
    b'                _tbody.append(\r\n'
    b'                    f"<tr class=\'sec\'><td colspan=\'9\'>{_h(sl)}. "\r\n'
    b'                    f"{_h(str(r[\'section\'] or \'\').upper())}</td></tr>"\r\n'
    b'                )\r\n'
    b'                prev_sec = sl\r\n'
    b'            _tbody.append(\r\n'
    b'                "<tr>"\r\n'
    b'                f"<td class=\'c-item\'>{_h(str(r[\'item_no_display\'] or r[\'item_no\'] or \'\'))}</td>"\r\n'
    b'                f"<td class=\'c-desc\'>{_h(str(r[\'description\'] or \'\'))}</td>"\r\n'
    b'                f"<td class=\'c-qty\'>{_int(r[\'qty\'])}</td>"\r\n'
    b'                f"<td class=\'c-unit\'>{_h(str(r[\'unit\'] or \'\'))}</td>"\r\n'
    b'                f"<td class=\'c-num\'>{_num(r[\'basic_price\'])}</td>"\r\n'
    b'                f"<td class=\'c-num\'>{_num(r[\'supply_rate\'])}</td>"\r\n'
    b'                f"<td class=\'c-num\'>{_num(r[\'install_rate\'])}</td>"\r\n'
    b'                f"<td class=\'c-num\'>{_num(r[\'final_built_up_rate\'])}</td>"\r\n'
    b'                f"<td class=\'c-amt\'>{_num(r[\'total_amount\'])}</td>"\r\n'
    b'                "</tr>"\r\n'
    b'            )\r\n'
    b'        _tbody.append("</tbody>")\r\n'
    b'        _sub = _sub_by_bill.get(bn, sum(float(r["total_amount"] or 0) for r in _brows))\r\n'
    b'        _bill_blocks.append(\r\n'
    b'            f"<div class=\'bill-banner\'>BILL No. {bn} &mdash; "\r\n'
    b'            f"{_h(str(_bname))}</div>"\r\n'
    b'            f"<table class=\'boq\'>{_thead}{\'\'.join(_tbody)}</table>"\r\n'
    b'            f"<div class=\'bill-subtotal\'>Bill {bn} Subtotal: "\r\n'
    b'            f"{sym} {_num(_sub)}</div>"\r\n'
    b'        )\r\n'
    b'    items_table = "".join(_bill_blocks)\r\n'
)

# CSS additions -- bill-banner + bill-subtotal blocks
old_css_snippet = (
    b'    table.boq tr.bill td {\r\n'
    b'        background: #FEF3C7; font-weight: 700; color: #78350F;\r\n'
    b'        padding: 5pt 4pt; font-size: 9pt;\r\n'
    b'    }\r\n'
    b'    table.boq tr.sec td {\r\n'
    b'        background: #E5E7EB; font-weight: 700; color: #1f2937;\r\n'
    b'        padding: 3pt 4pt; font-size: 8pt; font-style: italic;\r\n'
    b'    }\r\n'
)
new_css_snippet = (
    b'    table.boq tr.sec td {\r\n'
    b'        background: #E5E7EB; font-weight: 700; color: #1f2937;\r\n'
    b'        padding: 3pt 4pt; font-size: 8pt; font-style: italic;\r\n'
    b'    }\r\n'
    b'    .bill-banner {\r\n'
    b'        background: #FEF3C7; color: #78350F; font-weight: 700;\r\n'
    b'        font-size: 10pt; padding: 6pt 8pt; margin: 12pt 0 0 0;\r\n'
    b'        border-left: 3pt solid #B45309;\r\n'
    b'    }\r\n'
    b'    .bill-subtotal {\r\n'
    b'        background: #F3F4F6; color: #1E3A5F; font-weight: 700;\r\n'
    b'        font-size: 9pt; padding: 4pt 8pt; margin: 0 0 6pt 0;\r\n'
    b'        text-align: right; border-left: 3pt solid #1E3A5F;\r\n'
    b'    }\r\n'
)

if b"'bill-banner'" in data:
    print("[skip] per-bill tables already applied")
else:
    if old_body not in data:
        print("[abort] old body block not found -- did the prior patch run?")
        raise SystemExit(1)
    if old_css_snippet not in data:
        print("[abort] old CSS snippet not found")
        raise SystemExit(1)
    data = data.replace(old_body, new_body, 1)
    data = data.replace(old_css_snippet, new_css_snippet, 1)
    print(f"[ok] switched to per-bill tables + updated CSS")

if len(data) != orig_len:
    backup = target.with_suffix(".py.bak-boqpdf-perbill-2026-07-01")
    if not backup.exists():
        backup.write_bytes(target.read_bytes())
        print(f"[backup] {backup.name}")
    target.write_bytes(data)
    print(f"[write] web_app.py updated ({orig_len} -> {len(data)} bytes)")
else:
    print("[noop] no change")
