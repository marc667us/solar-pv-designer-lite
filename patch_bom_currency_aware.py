"""
Make BOM + BOQ currency-aware in web_app.py.

Edits:
  1. _ensure_bom_tables(): idempotent ALTER TABLE to add `currency` column.
  2. boms_view + boms_boq: compute target-currency rate, pass `currency`
     and `rate` to the template.
  3. boms_new POST: read `currency` from form (default GHS) on INSERT.

The template-side display change is done separately via Edit() on
bom_view.html and bom_boq.html.

The procurement_center_add path is patched separately because it lives
inside the spliced new_marketplace_procurement_center_routes.py code.

Idempotent — each replacement checks for the new shape before applying.
"""
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()
orig = data

# ── 1. _ensure_bom_tables: add idempotent ALTER TABLE block ────────────────
OLD_ENSURE = (
    b"            CREATE TABLE IF NOT EXISTS marketplace_bom_items (\r\n"
    b"                id                  INTEGER PRIMARY KEY AUTOINCREMENT,\r\n"
    b"                bom_id              INTEGER NOT NULL,\r\n"
    b"                product_id          INTEGER DEFAULT 0,\r\n"
    b"                custom_name         TEXT NOT NULL,\r\n"
    b"                qty                 REAL DEFAULT 1,\r\n"
    b"                unit                TEXT DEFAULT 'No.',\r\n"
    b"                unit_price_override REAL,\r\n"
    b"                notes               TEXT DEFAULT '',\r\n"
    b"                created_at          TEXT DEFAULT CURRENT_TIMESTAMP\r\n"
    b"            );\r\n"
    b"            CREATE INDEX IF NOT EXISTS idx_marketplace_bom_items_bom\r\n"
    b"                ON marketplace_bom_items(bom_id);\r\n"
    b"            \"\"\"\r\n"
    b"        )"
)
NEW_ENSURE = (
    b"            CREATE TABLE IF NOT EXISTS marketplace_bom_items (\r\n"
    b"                id                  INTEGER PRIMARY KEY AUTOINCREMENT,\r\n"
    b"                bom_id              INTEGER NOT NULL,\r\n"
    b"                product_id          INTEGER DEFAULT 0,\r\n"
    b"                custom_name         TEXT NOT NULL,\r\n"
    b"                qty                 REAL DEFAULT 1,\r\n"
    b"                unit                TEXT DEFAULT 'No.',\r\n"
    b"                unit_price_override REAL,\r\n"
    b"                notes               TEXT DEFAULT '',\r\n"
    b"                created_at          TEXT DEFAULT CURRENT_TIMESTAMP\r\n"
    b"            );\r\n"
    b"            CREATE INDEX IF NOT EXISTS idx_marketplace_bom_items_bom\r\n"
    b"                ON marketplace_bom_items(bom_id);\r\n"
    b"            \"\"\"\r\n"
    b"        )\r\n"
    b"        # Idempotent ALTER to add currency column on pre-existing DBs.\r\n"
    b"        # SQLite + Postgres both reject duplicate ADD COLUMN, so wrap.\r\n"
    b"        try:\r\n"
    b"            with get_db() as _c:\r\n"
    b"                _c.execute(\"ALTER TABLE marketplace_boms ADD COLUMN currency TEXT DEFAULT 'GHS'\")\r\n"
    b"        except Exception:\r\n"
    b"            pass"
)
if OLD_ENSURE in data:
    data = data.replace(OLD_ENSURE, NEW_ENSURE, 1)
    print("[1/3] _ensure_bom_tables now adds currency column")
elif b"ALTER TABLE marketplace_boms ADD COLUMN currency" in data:
    print("[1/3] currency-column ALTER already present (skip)")
else:
    print("[1/3] MISS — _ensure_bom_tables shape changed; aborting")
    sys.exit(1)

# ── 2a. boms_view: pass currency + rate to template ─────────────────────────
OLD_VIEW = (
    b"    bom_rates = _bom_rates_for(bom_id)\r\n"
    b"    totals = _bom_totals_with_rates(items, bom_rates)\r\n"
    b"    return render_template(\r\n"
    b"        \"bom_view.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n"
    b"    )"
)
NEW_VIEW = (
    b"    bom_rates = _bom_rates_for(bom_id)\r\n"
    b"    _bcur = (bom[\"currency\"] if \"currency\" in bom.keys() and bom[\"currency\"] else \"GHS\")\r\n"
    b"    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n"
    b"    totals = _bom_totals_with_rates(items, bom_rates, fx_rate=_brate)\r\n"
    b"    return render_template(\r\n"
    b"        \"bom_view.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n"
    b"        currency=_bcur, fx_rate=_brate,\r\n"
    b"        currencies=list(_CURRENCY_RATES_FROM_USD.keys()),\r\n"
    b"        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n"
    b"    )"
)
# This pattern appears TWICE — once for boms_view, once for boms_boq.
n_view = data.count(OLD_VIEW)
print(f"     boms_view/boms_boq render block matches: {n_view}")
if n_view == 0:
    if b"currency=_bcur, fx_rate=_brate" in data:
        print("[2/3] currency wiring already present (skip)")
    else:
        print("[2/3] MISS — boms_view render block changed; aborting")
        sys.exit(1)
else:
    # First occurrence is boms_view (template bom_view.html).
    # Replace both — boms_boq has the same shape but different template.
    data = data.replace(OLD_VIEW, NEW_VIEW, 1)
    print("[2a/3] boms_view passes currency+fx_rate to bom_view.html")

# ── 2b. boms_boq: same shape, different template name ───────────────────────
OLD_BOQ = (
    b"    bom_rates = _bom_rates_for(bom_id)\r\n"
    b"    totals = _bom_totals_with_rates(items, bom_rates)\r\n"
    b"    return render_template(\r\n"
    b"        \"bom_boq.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n"
    b"    )"
)
NEW_BOQ = (
    b"    bom_rates = _bom_rates_for(bom_id)\r\n"
    b"    _bcur = (bom[\"currency\"] if \"currency\" in bom.keys() and bom[\"currency\"] else \"GHS\")\r\n"
    b"    _brate = _CURRENCY_RATES_FROM_USD.get(_bcur, 1.0)\r\n"
    b"    totals = _bom_totals_with_rates(items, bom_rates, fx_rate=_brate)\r\n"
    b"    return render_template(\r\n"
    b"        \"bom_boq.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        bom=bom, items=items, totals=totals, bom_rates=bom_rates,\r\n"
    b"        currency=_bcur, fx_rate=_brate,\r\n"
    b"        rates_as_of=_CURRENCY_RATES_AS_OF,\r\n"
    b"    )"
)
if OLD_BOQ in data:
    data = data.replace(OLD_BOQ, NEW_BOQ, 1)
    print("[2b/3] boms_boq passes currency+fx_rate to bom_boq.html")
elif b"\"bom_boq.html\"" in data and b"currency=_bcur, fx_rate=_brate" in data:
    print("[2b/3] boms_boq already wired (skip)")
else:
    print("[2b/3] MISS — boms_boq render block not found")
    sys.exit(1)

# ── 3. _bom_totals_with_rates: accept fx_rate, scale all amounts by it ─────
OLD_TOTALS = (
    b"def _bom_totals_with_rates(items, rates: dict) -> dict:"
)
NEW_TOTALS = (
    b"def _bom_totals_with_rates(items, rates: dict, fx_rate: float = 1.0) -> dict:"
)
if OLD_TOTALS in data:
    data = data.replace(OLD_TOTALS, NEW_TOTALS, 1)
    print("[3a/3] _bom_totals_with_rates accepts fx_rate")
elif b"fx_rate: float = 1.0" in data:
    print("[3a/3] _bom_totals_with_rates already has fx_rate (skip)")
else:
    print("[3a/3] MISS — _bom_totals_with_rates signature not found")
    sys.exit(1)

# Multiply basic_rate by fx_rate at the line-build step so every downstream
# computation (labour, overhead, profit, VAT, line_total, grand_total) ends
# up in the target currency.
OLD_BASIC = (
    b"        basic_rate = float(\r\n"
    b"            (it[\"unit_price_override\"] if it[\"unit_price_override\"] is not None\r\n"
    b"             else (it[\"catalog_price\"] or 0)) or 0\r\n"
    b"        )\r\n"
    b"        install_labour = basic_rate * lab_pct / 100.0"
)
NEW_BASIC = (
    b"        basic_rate_usd = float(\r\n"
    b"            (it[\"unit_price_override\"] if it[\"unit_price_override\"] is not None\r\n"
    b"             else (it[\"catalog_price\"] or 0)) or 0\r\n"
    b"        )\r\n"
    b"        # Convert source USD to target currency at the rate the route\r\n"
    b"        # looked up from _CURRENCY_RATES_FROM_USD. All downstream rates\r\n"
    b"        # (labour, overhead, profit, VAT) inherit the currency.\r\n"
    b"        basic_rate = basic_rate_usd * float(fx_rate or 1.0)\r\n"
    b"        install_labour = basic_rate * lab_pct / 100.0"
)
if OLD_BASIC in data:
    data = data.replace(OLD_BASIC, NEW_BASIC, 1)
    print("[3b/3] basic_rate now multiplied by fx_rate at line build")
elif b"basic_rate = basic_rate_usd * float(fx_rate" in data:
    print("[3b/3] fx_rate already applied (skip)")
else:
    print("[3b/3] MISS — basic_rate block not found")
    sys.exit(1)

# ── 4. boms_new INSERT: set currency from form (default GHS) ───────────────
OLD_INSERT = (
    b"        cur = c.execute(\r\n"
    b"            \"INSERT INTO marketplace_boms \"\r\n"
    b"            \"(user_id, title, project_name, client_name, notes) \"\r\n"
    b"            \"VALUES (?,?,?,?,?)\",\r\n"
    b"            (\r\n"
    b"                uid, title,\r\n"
    b"                (request.form.get(\"project_name\") or \"\").strip(),\r\n"
    b"                (request.form.get(\"client_name\") or \"\").strip(),\r\n"
    b"                (request.form.get(\"notes\") or \"\").strip(),\r\n"
    b"            ),\r\n"
    b"        )"
)
NEW_INSERT = (
    b"        _bcur = (request.form.get(\"currency\") or \"GHS\").strip().upper()\r\n"
    b"        if _bcur not in _CURRENCY_RATES_FROM_USD:\r\n"
    b"            _bcur = \"GHS\"\r\n"
    b"        cur = c.execute(\r\n"
    b"            \"INSERT INTO marketplace_boms \"\r\n"
    b"            \"(user_id, title, project_name, client_name, notes, currency) \"\r\n"
    b"            \"VALUES (?,?,?,?,?,?)\",\r\n"
    b"            (\r\n"
    b"                uid, title,\r\n"
    b"                (request.form.get(\"project_name\") or \"\").strip(),\r\n"
    b"                (request.form.get(\"client_name\") or \"\").strip(),\r\n"
    b"                (request.form.get(\"notes\") or \"\").strip(),\r\n"
    b"                _bcur,\r\n"
    b"            ),\r\n"
    b"        )"
)
if OLD_INSERT in data:
    data = data.replace(OLD_INSERT, NEW_INSERT, 1)
    print("[4/3] boms_new INSERT now sets currency")
elif b"(user_id, title, project_name, client_name, notes, currency)" in data:
    print("[4/3] boms_new INSERT already has currency (skip)")
else:
    print("[4/3] MISS — boms_new INSERT not found")
    sys.exit(1)

if data != orig:
    open(PATH, "wb").write(data)
    print(f"[done] web_app.py {len(data)-len(orig):+d} bytes")
else:
    print("[done] no change")
