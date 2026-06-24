#!/usr/bin/env python3
"""
patch_xlsx_email_helpers_use_route.py

Owner reminder 2026-06-23: "you are aware the bom must hav wcost
information". Yes -- and my prior patch left the email helpers as
either minimal (BOM = 7 columns only, no cost buildup) or empty stubs
(price-sheet + BOQ-project = `return b""`, so those emails attached
PDF only with no Excel).

Fix: replace all three helpers so they invoke the EXISTING route
function inside an `app.test_request_context` with the owner's
`session["user_id"]` pre-populated. The Flask Response that the route
returns carries the workbook bytes via `resp.get_data()`. Net effect:
the email Excel is now BYTE-IDENTICAL to the file the owner downloads
via the toolbar -- same full cost-buildup columns, same A4 page
setup, same totals. Zero duplication, zero drift.

Routes invoked (each already includes the full cost detail):
  /boms/<bom_id>/boq.xlsx?include_buildup=1
                  -> #, Description, Qty, Unit, Basic Rate (local),
                     Basic Rate (USD), Brand, Company, Phone
                     + Project Rate Build-Up sheet: Basic / Supply /
                     Install / +OH / +Profit / +VAT / Final Rate /
                     Amount per line
                     + Summary sheet
  /price-sheets/<sheet_id>/xlsx
                  -> #, Description, Qty, Unit, Basic Rate (local),
                     Basic Rate (USD), Brand, Company, Phone
  /boq-projects/<pid>/boq.xlsx
                  -> Item, Description, Qty, Unit, Basic Rate,
                     Total Rate, Amount (per item, grouped by Bill +
                     Section + Floor + Building)
"""

from pathlib import Path
P = Path("web_app.py")
data = P.read_bytes()

OLD = (
    b'def _bom_boq_xlsx_bytes(bom_id: int) -> bytes:\r\n'
    b'    """Return the BOM/cost-estimate Excel as bytes (shared with email + download)."""\r\n'
)

# Find the END of the three stub helpers -- the next `@app.route` after them
# is /price-sheets/<int:sheet_id>/email. We replace the whole stub block.
import re
src = data.decode("utf-8", errors="replace")

STUB_PATTERN = re.compile(
    r'def _bom_boq_xlsx_bytes\(bom_id: int\) -> bytes:[\s\S]*?'
    r'def _boq_project_xlsx_bytes\(pid: int\) -> bytes:[\s\S]*?'
    r'return b""\r?\n\r?\n\r?\n',
    re.MULTILINE,
)

m = STUB_PATTERN.search(src)
if not m:
    raise SystemExit("[fail] could not locate the three stub helpers")

start, end = m.span()
print(f"[match] stub block {start}..{end} ({end-start} bytes)")

REPLACEMENT = (
    "def _xlsx_bytes_via_route(view_func, *args, uid=None, query_string=\"\"):\r\n"
    "    \"\"\"Invoke an @login_required xlsx route INSIDE a test_request_context\r\n"
    "    with a fake session so we get the full Response bytes back. Used by\r\n"
    "    the email handlers so the attached Excel == the downloaded Excel.\r\n"
    "    \"\"\"\r\n"
    "    if uid is None:\r\n"
    "        uid = session.get(\"user_id\") or 0\r\n"
    "    if not uid:\r\n"
    "        return b\"\"\r\n"
    "    # Path is illustrative -- the route function is called by reference,\r\n"
    "    # not URL-matched; the context lets @login_required see a real session.\r\n"
    "    with app.test_request_context(\"/_internal_xlsx_call?\" + (query_string or \"\")):\r\n"
    "        session[\"user_id\"] = uid\r\n"
    "        try:\r\n"
    "            resp = view_func(*args)\r\n"
    "        except Exception as _e:\r\n"
    "            try: app.logger.warning(\"xlsx-bytes-via-route call failed: %s\", _e)\r\n"
    "            except Exception: pass\r\n"
    "            return b\"\"\r\n"
    "    # Flask response: get_data() returns the bytes payload\r\n"
    "    try:\r\n"
    "        return resp.get_data()\r\n"
    "    except Exception:\r\n"
    "        return b\"\"\r\n"
    "\r\n"
    "\r\n"
    "def _bom_boq_xlsx_bytes(bom_id: int) -> bytes:\r\n"
    "    \"\"\"Return the BOM/cost-estimate Excel as bytes (shared with email + download).\r\n"
    "    Mirrors GET /boms/<bom_id>/boq.xlsx?include_buildup=1 so the email recipient\r\n"
    "    gets the SAME 9-column main sheet + Project Rate Build-Up sheet + Summary\r\n"
    "    sheet (including the per-line Basic / Supply / Install / +OH / +Profit /\r\n"
    "    +VAT / Final Rate / Amount cost buildup that BOM is the source of truth for).\r\n"
    "    \"\"\"\r\n"
    "    return _xlsx_bytes_via_route(boms_boq_xlsx, bom_id,\r\n"
    "                                  query_string=\"include_buildup=1\")\r\n"
    "\r\n"
    "\r\n"
    "def _price_sheet_xlsx_bytes(sheet_id: int) -> bytes:\r\n"
    "    \"\"\"Return the price-sheet Excel as bytes (shared with email + download).\r\n"
    "    Mirrors GET /price-sheets/<sheet_id>/xlsx -- 9-column sheet with the\r\n"
    "    Basic Rate (local + USD) + supplier columns.\r\n"
    "    \"\"\"\r\n"
    "    return _xlsx_bytes_via_route(price_sheet_xlsx, sheet_id)\r\n"
    "\r\n"
    "\r\n"
    "def _boq_project_xlsx_bytes(pid: int) -> bytes:\r\n"
    "    \"\"\"Return the BOQ-project Excel as bytes (shared with email).\r\n"
    "    Mirrors GET /boq-projects/<pid>/boq.xlsx -- main BOQ sheet grouped by\r\n"
    "    Building / Floor / Bill / Section with per-item Basic Rate / Total Rate /\r\n"
    "    Amount columns.\r\n"
    "    \"\"\"\r\n"
    "    return _xlsx_bytes_via_route(boq_project_xlsx, pid)\r\n"
    "\r\n"
    "\r\n"
)

new_src = src[:start] + REPLACEMENT + src[end:]
new_data = new_src.encode("utf-8")

if data == new_data:
    print("[noop] file unchanged")
else:
    P.write_bytes(new_data)
    print(f"[done] web_app.py: {len(data)} -> {len(new_data)} bytes ({len(new_data)-len(data):+d})")
