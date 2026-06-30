"""Fix: Excel floor BOQ -- BOQ Detail sheet must come FIRST.

Owner directive 2026-06-30: the Excel showed Summary as the first sheet
(aggregate only), so it looked like 'amounts removed / different sheet'.
The familiar project-level BOQ.xlsx has a 'BOQ' sheet first with every
item + every amount column.

Restructure _floor_boq_build_xlsx_bytes:
  Sheet 1 (active) "BOQ"       -- every item, grouped by Bill -> Section
                                  -> Subsection, with all 9 amount columns
                                  + FLOOR TOTAL CARRIED TO BUILDING SUMMARY
  Sheet 2          "Summary"   -- per-service + per-bill aggregates
                                  + FLOOR TOTAL CARRIED TO BUILDING SUMMARY
  Sheets 3..N      per service -- items in that service, with SERVICE TOTAL

Re-runnable byte patch.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
CRLF = b"\r\n"

def crlf(s: bytes) -> bytes:
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)

def replace_once(d, old, new, label):
    old_c, new_c = crlf(old), crlf(new)
    if new_c in d:
        print(f"  {label}: already patched, skipping"); return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


WEB = REPO / "web_app.py"
data = WEB.read_bytes()

# Anchor: the "----- Summary sheet -----" block that was the FIRST sheet.
# Replace with: (BOQ detail block first) + (Summary as second sheet).
SUM_OLD = b'''    # ----- Summary sheet -----
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"Floor BOQ Summary -- {project['project_name']}"
    ws["A1"].font = title_font
    ws.merge_cells("A1:D1")
    ws["A2"] = f"Building : {building['building_name']}"
    ws["A3"] = f"Floor    : {floor['floor_name']}"
    ws["A4"] = f"Client   : {project['client_name'] or '-'}"'''

SUM_NEW = b'''    # ----- BOQ Detail sheet (FIRST -- every saved item, grouped by Bill -> Section -> Subsection) -----
    ws = wb.active
    ws.title = "BOQ"
    ws["A1"] = f"Floor BOQ -- {project['project_name']}"
    ws["A1"].font = title_font
    ws.merge_cells("A1:I1")
    ws["A2"] = f"Building : {building['building_name']}"
    ws["A3"] = f"Floor    : {floor['floor_name']}"
    ws["A4"] = f"Client   : {project['client_name'] or '-'}"

    headers = ["Item", "Description", "Qty", "Unit", "Basic Price",
               "Supply Amount Rate", "Installation Amount Rate",
               "Total Amount Rate", "Amount"]
    HROW = 6
    for col, h in enumerate(headers, 1):
        c_ = ws.cell(row=HROW, column=col, value=h)
        c_.font = header_font; c_.fill = header_fill; c_.border = box
        c_.alignment = Alignment(horizontal="center")

    r1 = HROW + 1
    prev_bill = prev_sec = prev_sub = None
    for r in rows:
        bn = int(r["bill_no"] or 0)
        sl = (r["section_letter"] or "").upper()
        sub = r["subsection_label"] or ""
        if bn != prev_bill:
            ws.cell(row=r1, column=1,
                    value=f"BILL No. {bn} -- {r['bill_name'] or 'OTHER'}").font = bold
            ws.cell(row=r1, column=1).fill = bill_fill
            ws.merge_cells(start_row=r1, start_column=1, end_row=r1, end_column=9)
            r1 += 1
            prev_bill = bn; prev_sec = None; prev_sub = None
        if sl != prev_sec:
            ws.cell(row=r1, column=1,
                    value=f"  {sl}. {(r['section'] or '').upper()}").font = bold
            ws.merge_cells(start_row=r1, start_column=1, end_row=r1, end_column=9)
            r1 += 1
            prev_sec = sl; prev_sub = None
        if sub and sub != prev_sub:
            ws.cell(row=r1, column=2, value=sub).font = Font(italic=True)
            r1 += 1
            prev_sub = sub
        ws.cell(row=r1, column=1, value=_san(r["item_no_display"] or r["item_no"] or ""))
        ws.cell(row=r1, column=2, value=_san(r["description"]))
        ws.cell(row=r1, column=3, value=float(r["qty"] or 0))
        ws.cell(row=r1, column=4, value=_san(r["unit"]))
        ws.cell(row=r1, column=5, value=round(float(r["basic_price"] or 0), 2))
        ws.cell(row=r1, column=6, value=round(float(r["supply_rate"] or 0), 2))
        ws.cell(row=r1, column=7, value=round(float(r["install_rate"] or 0), 2))
        ws.cell(row=r1, column=8, value=round(float(r["final_built_up_rate"] or 0), 2))
        ws.cell(row=r1, column=9, value=round(float(r["total_amount"] or 0), 2))
        for col in range(1, 10):
            ws.cell(row=r1, column=col).border = box
        r1 += 1
    r1 += 1
    ws.cell(row=r1, column=8, value="FLOOR TOTAL CARRIED TO BUILDING SUMMARY").font = title_font
    ws.cell(row=r1, column=9, value=round(floor_total, 2)).font = title_font
    ws.cell(row=r1, column=9).fill = bill_fill
    for col, w in enumerate([8, 50, 8, 8, 14, 14, 14, 14, 16], 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # ----- Summary sheet (SECOND -- per-service + per-bill aggregates) -----
    ws = wb.create_sheet("Summary")
    ws["A1"] = f"Floor BOQ Summary -- {project['project_name']}"
    ws["A1"].font = title_font
    ws.merge_cells("A1:D1")
    ws["A2"] = f"Building : {building['building_name']}"
    ws["A3"] = f"Floor    : {floor['floor_name']}"
    ws["A4"] = f"Client   : {project['client_name'] or '-'}"'''

data = replace_once(data, SUM_OLD, SUM_NEW,
                    "BOQ detail sheet inserted first; Summary moved to second", )

WEB.write_bytes(data)
print("done.")
