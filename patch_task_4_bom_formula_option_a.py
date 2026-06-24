"""Task #4 Option A: align BOM formula to BOQ formula.

Changes:
  1) _BOM_DEFAULT_RATES adds contingency_pct (default 0).
  2) _ensure_bom_rates_table CREATE includes contingency_pct + idempotent ALTER.
  3) _bom_rates_for SELECT + return contingency_pct.
  4) _bom_totals_with_rates: replace compound (1+ovh)*(1+prf) with sum
     (1+(ovh+prf)/100), and add contingency layer between OH+P and VAT.
  5) boms_save_rates: extend the 4-pct save loop to 5 pcts (adds cnt).
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

# === 1) _BOM_DEFAULT_RATES gains contingency_pct ===
old1 = (
    b'_BOM_DEFAULT_RATES = {\r\n'
    b'    "labour_pct":   15.0,'
)
if data.count(old1) != 1:
    print(f"FAIL: _BOM_DEFAULT_RATES anchor missing (got {data.count(old1)})")
    sys.exit(1)
new1 = old1 + b'   # % of basic supply rate added as install labour (kept for back-compat)\r\n    "contingency_pct": 0.0,'
# To avoid duplicating the existing comment that follows the labour line, match
# a slightly longer signature and replace cleanly.
old1_full = (
    b'_BOM_DEFAULT_RATES = {\r\n'
    b'    "labour_pct":   15.0,   # % of basic supply rate added as install labour\r\n'
    b'    "overhead_pct":  8.0,   # % of (supply + labour) added as overhead\r\n'
    b'    "profit_pct":   12.0,   # % of (supply + labour + overhead) added as profit\r\n'
    b'    "vat_pct":       0.0,   # % VAT applied AFTER profit\r\n'
    b'}\r\n'
)
new1_full = (
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
if data.count(old1_full) != 1:
    print(f"FAIL: _BOM_DEFAULT_RATES full block (got {data.count(old1_full)})")
    sys.exit(1)
data = data.replace(old1_full, new1_full)

# === 2) _ensure_bom_rates_table CREATE includes contingency_pct + ALTER for existing ===
old2_pg = (
    b'        for ddl in [\r\n'
    b'            """CREATE TABLE IF NOT EXISTS marketplace_bom_rates (\r\n'
    b'                bom_id       INTEGER PRIMARY KEY,\r\n'
    b'                labour_pct   REAL DEFAULT 15,\r\n'
    b'                overhead_pct REAL DEFAULT 8,\r\n'
    b'                profit_pct   REAL DEFAULT 12,\r\n'
    b'                vat_pct      REAL DEFAULT 0,\r\n'
    b'                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP\r\n'
    b'            )""",\r\n'
    b'        ]:\r\n'
)
new2_pg = (
    b'        for ddl in [\r\n'
    b'            """CREATE TABLE IF NOT EXISTS marketplace_bom_rates (\r\n'
    b'                bom_id           INTEGER PRIMARY KEY,\r\n'
    b'                labour_pct       REAL DEFAULT 15,\r\n'
    b'                overhead_pct     REAL DEFAULT 8,\r\n'
    b'                profit_pct       REAL DEFAULT 12,\r\n'
    b'                contingency_pct  REAL DEFAULT 0,\r\n'
    b'                vat_pct          REAL DEFAULT 0,\r\n'
    b'                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP\r\n'
    b'            )""",\r\n'
    b'            "ALTER TABLE marketplace_bom_rates ADD COLUMN IF NOT EXISTS contingency_pct REAL DEFAULT 0",\r\n'
    b'        ]:\r\n'
)
if data.count(old2_pg) != 1:
    print(f"FAIL: PG bom_rates DDL block (got {data.count(old2_pg)})")
    sys.exit(1)
data = data.replace(old2_pg, new2_pg)

old2_sqlite = (
    b'    with get_db() as c:\r\n'
    b'        c.executescript(\r\n'
    b'            """\r\n'
    b'            CREATE TABLE IF NOT EXISTS marketplace_bom_rates (\r\n'
    b'                bom_id       INTEGER PRIMARY KEY,\r\n'
    b'                labour_pct   REAL DEFAULT 15,\r\n'
    b'                overhead_pct REAL DEFAULT 8,\r\n'
    b'                profit_pct   REAL DEFAULT 12,\r\n'
    b'                vat_pct      REAL DEFAULT 0,\r\n'
    b'                updated_at   TEXT DEFAULT CURRENT_TIMESTAMP\r\n'
    b'            );\r\n'
    b'            """\r\n'
    b'        )\r\n'
)
new2_sqlite = (
    b'    with get_db() as c:\r\n'
    b'        c.executescript(\r\n'
    b'            """\r\n'
    b'            CREATE TABLE IF NOT EXISTS marketplace_bom_rates (\r\n'
    b'                bom_id           INTEGER PRIMARY KEY,\r\n'
    b'                labour_pct       REAL DEFAULT 15,\r\n'
    b'                overhead_pct     REAL DEFAULT 8,\r\n'
    b'                profit_pct       REAL DEFAULT 12,\r\n'
    b'                contingency_pct  REAL DEFAULT 0,\r\n'
    b'                vat_pct          REAL DEFAULT 0,\r\n'
    b'                updated_at       TEXT DEFAULT CURRENT_TIMESTAMP\r\n'
    b'            );\r\n'
    b'            """\r\n'
    b'        )\r\n'
    b'        # SQLite-side idempotent ALTER for pre-Task-#4 DBs.\r\n'
    b'        try:\r\n'
    b'            c.execute("ALTER TABLE marketplace_bom_rates ADD COLUMN contingency_pct REAL DEFAULT 0")\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
)
if data.count(old2_sqlite) != 1:
    print(f"FAIL: SQLite bom_rates DDL block (got {data.count(old2_sqlite)})")
    sys.exit(1)
data = data.replace(old2_sqlite, new2_sqlite)

# === 3) _bom_rates_for SELECT + return ===
old3 = (
    b'            row = c.execute(\r\n'
    b'                "SELECT labour_pct, overhead_pct, profit_pct, vat_pct "\r\n'
    b'                "FROM marketplace_bom_rates WHERE bom_id=?", (bom_id,),\r\n'
    b'            ).fetchone()\r\n'
    b'    except Exception:\r\n'
    b'        row = None\r\n'
    b'    if row:\r\n'
    b'        return {\r\n'
    b'            "labour_pct":   float(row["labour_pct"]   or 0),\r\n'
    b'            "overhead_pct": float(row["overhead_pct"] or 0),\r\n'
    b'            "profit_pct":   float(row["profit_pct"]   or 0),\r\n'
    b'            "vat_pct":      float(row["vat_pct"]      or 0),\r\n'
    b'        }\r\n'
)
new3 = (
    b'            row = c.execute(\r\n'
    b'                "SELECT labour_pct, overhead_pct, profit_pct, vat_pct, contingency_pct "\r\n'
    b'                "FROM marketplace_bom_rates WHERE bom_id=?", (bom_id,),\r\n'
    b'            ).fetchone()\r\n'
    b'    except Exception:\r\n'
    b'        # contingency_pct missing on pre-Task-#4 DBs -- retry without it.\r\n'
    b'        try:\r\n'
    b'            with get_db() as c:\r\n'
    b'                row = c.execute(\r\n'
    b'                    "SELECT labour_pct, overhead_pct, profit_pct, vat_pct "\r\n'
    b'                    "FROM marketplace_bom_rates WHERE bom_id=?", (bom_id,),\r\n'
    b'                ).fetchone()\r\n'
    b'        except Exception:\r\n'
    b'            row = None\r\n'
    b'    if row:\r\n'
    b'        # Postgres rows expose .keys(); SQLite Row objects do too.\r\n'
    b'        _keys = list(row.keys()) if hasattr(row, "keys") else []\r\n'
    b'        return {\r\n'
    b'            "labour_pct":      float(row["labour_pct"]   or 0),\r\n'
    b'            "overhead_pct":    float(row["overhead_pct"] or 0),\r\n'
    b'            "profit_pct":      float(row["profit_pct"]   or 0),\r\n'
    b'            "vat_pct":         float(row["vat_pct"]      or 0),\r\n'
    b'            "contingency_pct": float(row["contingency_pct"] or 0) if "contingency_pct" in _keys else 0.0,\r\n'
    b'        }\r\n'
)
if data.count(old3) != 1:
    print(f"FAIL: _bom_rates_for SELECT/return block (got {data.count(old3)})")
    sys.exit(1)
data = data.replace(old3, new3)

# === 4) _bom_totals_with_rates formula swap ===
old4 = (
    b'    lab_pct  = max(0.0, float(rates.get("labour_pct",   0)))\r\n'
    b'    ovh_pct  = max(0.0, float(rates.get("overhead_pct", 0)))\r\n'
    b'    prf_pct  = max(0.0, float(rates.get("profit_pct",   0)))\r\n'
    b'    vat_pct  = max(0.0, float(rates.get("vat_pct",      0)))\r\n'
)
new4 = (
    b'    lab_pct  = max(0.0, float(rates.get("labour_pct",      0)))\r\n'
    b'    ovh_pct  = max(0.0, float(rates.get("overhead_pct",    0)))\r\n'
    b'    prf_pct  = max(0.0, float(rates.get("profit_pct",      0)))\r\n'
    b'    cnt_pct  = max(0.0, float(rates.get("contingency_pct", 0)))\r\n'
    b'    vat_pct  = max(0.0, float(rates.get("vat_pct",         0)))\r\n'
)
if data.count(old4) != 1:
    print(f"FAIL: _bom_totals_with_rates pct block (got {data.count(old4)})")
    sys.exit(1)
data = data.replace(old4, new4)

# Formula body
old5 = (
    b'        basic_rate = basic_rate_usd * float(fx_rate or 1.0)\r\n'
    b'        install_labour = basic_rate * lab_pct / 100.0\r\n'
    b'        supply_install = basic_rate + install_labour\r\n'
    b'        overhead       = supply_install * ovh_pct / 100.0\r\n'
    b'        with_overhead  = supply_install + overhead\r\n'
    b'        profit         = with_overhead * prf_pct / 100.0\r\n'
    b'        before_vat     = with_overhead + profit\r\n'
    b'        vat            = before_vat * vat_pct / 100.0\r\n'
    b'        total_rate     = before_vat + vat\r\n'
)
new5 = (
    b'        # Task #4 Option A (2026-06-24): BOQ-aligned chain.\r\n'
    b'         #   direct      = basic * (1 + lab/100)\r\n'
    b'        #   subtotal_op = direct * (1 + (ovh+prf)/100)   <-- summed, not compounded\r\n'
    b'        #   subtotal_c  = subtotal_op * (1 + cnt/100)\r\n'
    b'        #   total_rate  = subtotal_c  * (1 + vat/100)\r\n'
    b'        # Template-compat: overhead + profit split BACK out for display.\r\n'
    b'        basic_rate     = basic_rate_usd * float(fx_rate or 1.0)\r\n'
    b'        install_labour = basic_rate * lab_pct / 100.0\r\n'
    b'        direct         = basic_rate + install_labour\r\n'
    b'        overhead       = direct * ovh_pct / 100.0\r\n'
    b'        profit         = direct * prf_pct / 100.0\r\n'
    b'        after_ohp      = direct + overhead + profit\r\n'
    b'        contingency    = after_ohp * cnt_pct / 100.0\r\n'
    b'        after_cnt      = after_ohp + contingency\r\n'
    b'        vat            = after_cnt * vat_pct / 100.0\r\n'
    b'        total_rate     = after_cnt + vat\r\n'
    b'        # Names preserved for template back-compat:\r\n'
    b'        supply_install = direct  # alias\r\n'
    b'        with_overhead  = direct + overhead\r\n'
    b'        before_vat     = after_cnt\r\n'
)
if data.count(old5) != 1:
    print(f"FAIL: _bom_totals_with_rates formula body (got {data.count(old5)})")
    sys.exit(1)
data = data.replace(old5, new5)

# Also expose contingency in the per-line dict for template display
old6 = (
    b'        lines.append({\r\n'
    b'            "item": it,\r\n'
    b'            "basic_rate": basic_rate,\r\n'
    b'            "install_labour": install_labour,\r\n'
    b'            "overhead": overhead,\r\n'
    b'            "profit": profit,\r\n'
    b'            "vat": vat,\r\n'
    b'            "total_rate": total_rate,\r\n'
    b'            "line_total": line_total,\r\n'
    b'            # Backward-compat with the old template:\r\n'
    b'            "unit_price": basic_rate,\r\n'
    b'        })\r\n'
)
new6 = (
    b'        lines.append({\r\n'
    b'            "item": it,\r\n'
    b'            "basic_rate": basic_rate,\r\n'
    b'            "install_labour": install_labour,\r\n'
    b'            "overhead": overhead,\r\n'
    b'            "profit": profit,\r\n'
    b'            "contingency": contingency,\r\n'
    b'            "vat": vat,\r\n'
    b'            "total_rate": total_rate,\r\n'
    b'            "line_total": line_total,\r\n'
    b'            # Backward-compat with the old template:\r\n'
    b'            "unit_price": basic_rate,\r\n'
    b'        })\r\n'
)
if data.count(old6) != 1:
    print(f"FAIL: lines.append block (got {data.count(old6)})")
    sys.exit(1)
data = data.replace(old6, new6)

# === 5) boms_save_rates: include cnt ===
old7 = (
    b'    lab, ovh, prf, vat = _pct("labour_pct"), _pct("overhead_pct"), _pct("profit_pct"), _pct("vat_pct")\r\n'
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            # UPSERT \xe2\x80\x94 INSERT OR REPLACE on SQLite; ON CONFLICT on Postgres\r\n'
    b'            c.execute(\r\n'
    b'                "INSERT OR REPLACE INTO marketplace_bom_rates "\r\n'
    b'                "(bom_id, labour_pct, overhead_pct, profit_pct, vat_pct) "\r\n'
    b'                "VALUES (?, ?, ?, ?, ?)",\r\n'
    b'                (bom_id, lab, ovh, prf, vat),\r\n'
    b'            )\r\n'
)
new7 = (
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
)
if data.count(old7) != 1:
    print(f"FAIL: boms_save_rates UPSERT block (got {data.count(old7)})")
    sys.exit(1)
data = data.replace(old7, new7)

old8 = b'    flash(f"Rates updated \xe2\x80\x94 labour {lab}% / overhead {ovh}% / profit {prf}% / VAT {vat}%.", "success")\r\n'
new8 = b'    flash(f"Rates updated \xe2\x80\x94 labour {lab}% / overhead {ovh}% / profit {prf}% / contingency {cnt}% / VAT {vat}%.", "success")\r\n'
if data.count(old8) != 1:
    print(f"FAIL: boms_save_rates flash (got {data.count(old8)})")
    sys.exit(1)
data = data.replace(old8, new8)

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")
