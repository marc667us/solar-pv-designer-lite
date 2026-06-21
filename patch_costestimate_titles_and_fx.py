# patch_costestimate_titles_and_fx.py
# Two fixes on the /boms/<id>/boq.xlsx + /boms/<id>/boq.pdf paths:
#
#   1. PDF + xlsx weren't passing fx_rate to _bom_totals_with_rates,
#      so totals + line amounts stayed in source USD instead of
#      converting to the BOM's currency (GHS/NGN/etc.). The HTML view
#      DID pass fx_rate, so numbers on the page didn't match the
#      downloaded file.
#
#   2. Headings + download filenames still read "Bill of Quantities" /
#      "BOQ_". The BOM editor / its exports are the procurement-center
#      surface the owner renamed to "Quick Cost Estimate (for
#      Electricians)". Project BOQs at /boq-projects keep the formal
#      "Bill of Quantities" wording -- that surface is untouched.

from pathlib import Path
TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

# --- xlsx: add fx_rate to totals call + rename title + download filename ---
OLD_XLSX_TOTALS = (
    b'def boms_boq_xlsx(bom_id):\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    rates = _bom_rates_for(bom_id)\r\n'
    b'    totals = _bom_totals_with_rates(items, rates)\r\n'
)
NEW_XLSX_TOTALS = (
    b'def boms_boq_xlsx(bom_id):\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    rates = _bom_rates_for(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n'
    b'    totals = _bom_totals_with_rates(items, rates, fx_rate=_brate)\r\n'
)
if OLD_XLSX_TOTALS in data:
    data = data.replace(OLD_XLSX_TOTALS, NEW_XLSX_TOTALS)
    print("Patched xlsx: fx_rate now passed to _bom_totals_with_rates")
elif b'_bom_totals_with_rates(items, rates, fx_rate=' in data:
    print("xlsx fx_rate already patched")
else:
    print("WARN xlsx fx_rate anchor not found")

# xlsx title cell
OLD_XLSX_TITLE = b'ws["A1"] = f"Bill of Quantities \xe2\x80\x94 {bom[\'title\']}"\r\n'
NEW_XLSX_TITLE = b'ws["A1"] = f"Quick Cost Estimate (for Electricians) \xe2\x80\x94 {bom[\'title\']}"\r\n'
if OLD_XLSX_TITLE in data:
    data = data.replace(OLD_XLSX_TITLE, NEW_XLSX_TITLE)
    print("Patched xlsx title heading")

# xlsx download filename
OLD_XLSX_DL = b'        download_name=f"BOQ_{safe_title}.xlsx",\r\n'
NEW_XLSX_DL = b'        download_name=f"CostEstimate_{safe_title}.xlsx",\r\n'
if OLD_XLSX_DL in data:
    data = data.replace(OLD_XLSX_DL, NEW_XLSX_DL)
    print("Patched xlsx download filename")

# --- pdf: add fx_rate + rename headings + filename ---
OLD_PDF_TOTALS = (
    b'def boms_boq_pdf(bom_id):\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    rates = _bom_rates_for(bom_id)\r\n'
    b'    totals = _bom_totals_with_rates(items, rates)\r\n'
)
NEW_PDF_TOTALS = (
    b'def boms_boq_pdf(bom_id):\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    bom = _bom_owned_or_404(bom_id, uid)\r\n'
    b'    items = _bom_items_with_prices(bom_id)\r\n'
    b'    rates = _bom_rates_for(bom_id)\r\n'
    b'    _bcur = (bom["currency"] if "currency" in bom.keys() and bom["currency"] else "GHS")\r\n'
    b'    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n'
    b'    totals = _bom_totals_with_rates(items, rates, fx_rate=_brate)\r\n'
)
if OLD_PDF_TOTALS in data:
    data = data.replace(OLD_PDF_TOTALS, NEW_PDF_TOTALS)
    print("Patched pdf: fx_rate now passed to _bom_totals_with_rates")

OLD_PDF_TITLE = b'md.append(f"# Bill of Quantities \xe2\x80\x94 {bom[\'title\']}"'
NEW_PDF_TITLE = b'md.append(f"# Quick Cost Estimate (for Electricians) \xe2\x80\x94 {bom[\'title\']}"'
if OLD_PDF_TITLE in data:
    data = data.replace(OLD_PDF_TITLE, NEW_PDF_TITLE)
    print("Patched pdf title heading")

# pdf send_file download_name
OLD_PDF_DL = b'f"BOQ_{safe_title}.pdf"'
NEW_PDF_DL = b'f"CostEstimate_{safe_title}.pdf"'
if OLD_PDF_DL in data:
    data = data.replace(OLD_PDF_DL, NEW_PDF_DL)
    print("Patched pdf download filename")

# pdf inner _render_pdf first arg (title)
OLD_PDF_RTITLE = b'f"BOQ \xe2\x80\x94 {bom[\'title\']}"'
NEW_PDF_RTITLE = b'f"Quick Cost Estimate \xe2\x80\x94 {bom[\'title\']}"'
if OLD_PDF_RTITLE in data:
    data = data.replace(OLD_PDF_RTITLE, NEW_PDF_RTITLE)
    print("Patched _render_pdf title arg")

TARGET.write_bytes(data)
print("OK")
