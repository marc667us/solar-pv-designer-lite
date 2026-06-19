# Patch M: BOQ compliance check using _MARKETPLACE_SPEC_FIELDS registry.
# Wires the brief's "Compliance Review Agent" into the BOQ generator.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b"def _boq_compliance_check(" in data:
    print("Already patched. No changes written.")
    raise SystemExit(0)

# M1: include category_code + catalog_unit in _bom_items_with_prices.
OLD1 = (
    b'def _bom_items_with_prices(bom_id: int):\r\n'
    b'    """Fetch BOM items joined to the catalog so we have current prices\r\n'
    b'    + category names ready for both the editor and the printable BOQ."""\r\n'
    b'    with get_db() as c:\r\n'
    b'        return c.execute(\r\n'
    b'            "SELECT bi.*, "\r\n'
    b'            "       ec.name        AS catalog_name, "\r\n'
    b'            "       ec.brand       AS catalog_brand, "\r\n'
    b'            "       ec.model       AS catalog_model, "\r\n'
    b'            "       ec.spec        AS catalog_spec, "\r\n'
    b'            "       ec.price_usd   AS catalog_price, "\r\n'
    b'            "       ec.is_verified AS catalog_verified, "\r\n'
    b'            "       s.name         AS supplier_name, "\r\n'
    b'            "       s.country      AS supplier_country, "\r\n'
    b'            "       pc.name        AS category_name "\r\n'
    b'            "FROM marketplace_bom_items bi "\r\n'
)
NEW1 = (
    b'def _bom_items_with_prices(bom_id: int):\r\n'
    b'    """Fetch BOM items joined to the catalog so we have current prices\r\n'
    b'    + category names ready for both the editor and the printable BOQ.\r\n'
    b'    Also pulls `category_code` so the Compliance Review uses the right\r\n'
    b'    `_MARKETPLACE_SPEC_FIELDS` registry entry per line."""\r\n'
    b'    with get_db() as c:\r\n'
    b'        return c.execute(\r\n'
    b'            "SELECT bi.*, "\r\n'
    b'            "       ec.name        AS catalog_name, "\r\n'
    b'            "       ec.brand       AS catalog_brand, "\r\n'
    b'            "       ec.model       AS catalog_model, "\r\n'
    b'            "       ec.spec        AS catalog_spec, "\r\n'
    b'            "       ec.price_usd   AS catalog_price, "\r\n'
    b'            "       ec.is_verified AS catalog_verified, "\r\n'
    b'            "       s.name         AS supplier_name, "\r\n'
    b'            "       s.country      AS supplier_country, "\r\n'
    b'            "       pc.name        AS category_name, "\r\n'
    b'            "       pc.code        AS category_code "\r\n'
    b'            "FROM marketplace_bom_items bi "\r\n'
)
assert data.count(OLD1) == 1, f"M1 anchor count={data.count(OLD1)}"
data = data.replace(OLD1, NEW1)

# M2: insert the compliance helper right after _bom_totals.
INSERT_AFTER = b"def _bom_totals(items) -> dict:\r\n"
idx = data.find(INSERT_AFTER)
assert idx >= 0

# Scan to start of next top-level def / decorator.
i = idx + len(INSERT_AFTER)
while True:
    nl = data.find(b"\r\n", i)
    if nl == -1:
        break
    line_start = nl + 2
    if data[line_start:line_start + 4] == b"def " or data[line_start:line_start + 1] == b"@":
        break
    i = nl + 1

# Helper -- assembled from a list of lines to keep the bytes simple.
helper_lines = [
    "",
    "def _boq_compliance_check(items, lines):",
    '    """Compliance Review Agent (lite) -- maps BOQ items against the',
    "    taxonomy registries and surfaces issues the brief's Compliance",
    "    Review Agent calls out: missing specs, missing prices, missing",
    "    supplier, wrong units, duplicate items. Returns a list of findings",
    "    that bom_boq.html renders into a review panel.",
    "",
    "    Findings shape:  {severity: high|medium|low, line_no: int, message: str}",
    "    line_no is 1-based to match printable BOQ row numbers; 0 means",
    '    the finding spans multiple lines (e.g. a duplicate-item warning).',
    '    """',
    "    findings = []",
    "    # Duplicate detection across the BOM.",
    "    name_counts = {}",
    "    for line in lines:",
    '        it = line["item"]',
    '        name = (it["catalog_name"] or it["custom_name"] or "").strip().lower()',
    "        if name:",
    "            name_counts[name] = name_counts.get(name, 0) + 1",
    "    for n, c in name_counts.items():",
    "        if c > 1:",
    "            findings.append({",
    '                "severity": "medium",',
    '                "line_no": 0,',
    '                "message": f"Duplicate item: {n!r} appears {c} times -- consolidate or rename.",',
    "            })",
    "    for idx, line in enumerate(lines, start=1):",
    '        it = line["item"]',
    '        cat_code = it["category_code"] if "category_code" in it.keys() else ""',
    '        spec_text = (it["catalog_spec"] or "").lower()',
    "        required = _MARKETPLACE_SPEC_FIELDS.get(cat_code, [])",
    "        missing_fields = []",
    "        for fld in required:",
    "            # Substring match on the field's first word (lowercased) --",
    '            # supplier wrote free-text spec, so "Number of cores"',
    '            # checks for "number".',
    "            key = fld.split()[0].lower()",
    "            if key not in spec_text:",
    "                missing_fields.append(fld)",
    "        if missing_fields:",
    "            findings.append({",
    '                "severity": "high" if len(missing_fields) >= 3 else "medium",',
    '                "line_no": idx,',
    '                "message": ("Specification incomplete -- missing: "',
    '                            + ", ".join(missing_fields[:4])',
    '                            + ("..." if len(missing_fields) > 4 else "")),',
    "            })",
    '        if (line["unit_price"] or 0) <= 0:',
    "            findings.append({",
    '                "severity": "high",',
    '                "line_no": idx,',
    '                "message": "Missing unit price -- BOQ total will not be accurate.",',
    "            })",
    '        if not it["supplier_name"]:',
    "            findings.append({",
    '                "severity": "low",',
    '                "line_no": idx,',
    '                "message": "No supplier attached -- procurement will need to source.",',
    "            })",
    "        # Wrong-unit check against the category default UoM.",
    "        if cat_code in _MARKETPLACE_DEFAULT_UNIT:",
    "            expected = _MARKETPLACE_DEFAULT_UNIT[cat_code]",
    '            actual = (it["unit"] or "").strip()',
    "            if expected and actual and actual != expected:",
    "                findings.append({",
    '                    "severity": "low",',
    '                    "line_no": idx,',
    '                    "message": f"Unit {actual!r} differs from category default {expected!r}.",',
    "                })",
    '    severity_rank = {"high": 0, "medium": 1, "low": 2}',
    '    findings.sort(key=lambda f: (severity_rank.get(f["severity"], 99), f["line_no"]))',
    "    return findings",
    "",
]
helper = ("\r\n".join(helper_lines) + "\r\n").encode("ascii")
data = data[:i] + helper + data[i:]

# M3: wire helper into boms_boq() render.
OLD3 = (
    b'    totals = _bom_totals_with_rates(items, bom_rates, fx_rate=_brate)\r\n'
    b'    return render_template(\r\n'
    b'        "bom_boq.html",\r\n'
    b'        user=current_user(),\r\n'
    b'        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n'
    b'        currency=_bcur, fx_rate=_brate,\r\n'
    b'        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n'
    b'    )\r\n'
)
NEW3 = (
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
assert data.count(OLD3) == 1, f"M3 anchor count={data.count(OLD3)}"
data = data.replace(OLD3, NEW3)

TARGET.write_bytes(data)
print(f"OK -- BOQ compliance patch applied, size {TARGET.stat().st_size:,}")
