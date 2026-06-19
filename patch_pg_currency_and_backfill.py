# Patch N: two Postgres init fixes uncovered by the live smoke test.
#
# (1) marketplace_boms is missing the `currency` column. The SQLite
#     side adds it via ALTER in _ensure_bom_tables but _ensure_bom_tables
#     short-circuits to _ensure_marketplace_schema_postgres on Postgres,
#     so the column never appears. /procurement-center/add doc_type=bom
#     then 500s with "column \"currency\" does not exist".
# (2) New categories (power_system, ict_elv) seeded zero products on
#     Postgres -- the all-or-nothing empty check in
#     _ensure_marketplace_schema_postgres blocks the seeded samples.
#     SQLite got a per-category backfill helper this session; Postgres
#     needs the same.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

SENTINEL = b'"ALTER TABLE marketplace_boms ADD COLUMN IF NOT EXISTS currency'
if SENTINEL in data:
    print("Already patched. No changes written.")
    raise SystemExit(0)

# N1: add the currency ALTER to the Postgres create_stmts list. Put it
# next to the existing equipment_catalog ALTERs so the marketplace
# schema bootstrap covers both tables in one pass.
OLD1 = (
    b'        "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS address TEXT DEFAULT \'\'",\r\n'
    b'\r\n'
    b'        # Slice 3 \xe2\x80\x94 audit log\r\n'
)
NEW1 = (
    b'        "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS address TEXT DEFAULT \'\'",\r\n'
    b'\r\n'
    b'        # Slice 5b -- BOM currency column (was added via SQLite ALTER in\r\n'
    b'        # _ensure_bom_tables; Postgres init never picked it up so\r\n'
    b'        # /procurement-center/add doc_type=bom 500\'d in prod). Idempotent.\r\n'
    b'        "ALTER TABLE marketplace_boms ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT \'GHS\'",\r\n'
    b'\r\n'
    b'        # Slice 3 \xe2\x80\x94 audit log\r\n'
)
assert data.count(OLD1) == 1, f"N1 anchor count={data.count(OLD1)}"
data = data.replace(OLD1, NEW1)

# N2: extend the Postgres "if n_non_solar == 0: _seed_marketplace_postgres_samples()"
# block with a per-category backfill else-branch, same pattern as the
# SQLite side ([[project-solar-pv-session-2026-06-19-catalogue]] patch F).
OLD2 = (
    b'        if n_non_solar == 0:\r\n'
    b'            _seed_marketplace_postgres_samples()\r\n'
)
NEW2 = (
    b'        if n_non_solar == 0:\r\n'
    b'            _seed_marketplace_postgres_samples()\r\n'
    b'        else:\r\n'
    b'            # Per-category backfill -- inserts rows ONLY for categories\r\n'
    b'            # that have zero products today. Same shape as the SQLite\r\n'
    b'            # helper so adding a new category (e.g. power_system) lands\r\n'
    b'            # its starter samples in pre-existing Postgres deployments.\r\n'
    b'            _backfill_marketplace_postgres_samples_for_empty_categories()\r\n'
)
assert data.count(OLD2) == 1, f"N2 anchor count={data.count(OLD2)}"
data = data.replace(OLD2, NEW2)

# N3: insert the Postgres backfill helper next to _seed_marketplace_postgres_samples.
INSERT_AFTER = b'def _seed_marketplace_postgres_samples():\r\n'
idx = data.find(INSERT_AFTER)
assert idx >= 0

# Scan forward to end of function (next top-level def / decorator).
i = idx + len(INSERT_AFTER)
while True:
    nl = data.find(b"\r\n", i)
    if nl == -1:
        break
    line_start = nl + 2
    if data[line_start:line_start + 4] == b"def " or data[line_start:line_start + 1] == b"@":
        break
    i = nl + 1

helper = (
    b'\r\n'
    b'def _backfill_marketplace_postgres_samples_for_empty_categories():\r\n'
    b'    """Postgres twin of _backfill_marketplace_samples_for_empty_categories.\r\n'
    b'    Calls the existing _seed_marketplace_postgres_samples but filters its\r\n'
    b'    INSERTs to categories that currently have zero products. Safe to call\r\n'
    b'    on a populated database -- skips already-populated categories so\r\n'
    b'    existing supplier rows are never disturbed."""\r\n'
    b'    with get_db() as c:\r\n'
    b'        cats_lookup = {}\r\n'
    b'        for r in c.execute(\r\n'
    b'            "SELECT id, code FROM product_categories"\r\n'
    b'        ).fetchall():\r\n'
    b'            cid = r[0] if hasattr(r, "__getitem__") else r["id"]\r\n'
    b'            code = r[1] if hasattr(r, "__getitem__") else r["code"]\r\n'
    b'            cats_lookup[code] = cid\r\n'
    b'        empty_codes = set()\r\n'
    b'        for code, cid in cats_lookup.items():\r\n'
    b'            row = c.execute(\r\n'
    b'                "SELECT COUNT(*) AS n FROM equipment_catalog WHERE category_id=?",\r\n'
    b'                (cid,),\r\n'
    b'            ).fetchone()\r\n'
    b'            n = row[0] if hasattr(row, "__getitem__") else row["n"]\r\n'
    b'            if n == 0:\r\n'
    b'                empty_codes.add(code)\r\n'
    b'    if not empty_codes:\r\n'
    b'        return\r\n'
    b'    # Filtered execute proxy: drops INSERTs whose category_id (at index\r\n'
    b'    # 9 of the parameter tuple) does not belong to a category we marked\r\n'
    b'    # as empty. _seed_marketplace_postgres_samples runs against this.\r\n'
    b'    real_get_db = get_db\r\n'
    b'    class _FilteredConn:\r\n'
    b'        def __init__(self, real):\r\n'
    b'            self._real = real\r\n'
    b'        def __enter__(self):\r\n'
    b'            self._cm = self._real()\r\n'
    b'            self._inner = self._cm.__enter__()\r\n'
    b'            return self\r\n'
    b'        def __exit__(self, *a, **kw):\r\n'
    b'            return self._cm.__exit__(*a, **kw)\r\n'
    b'        def execute(self, sql, params=()):\r\n'
    b'            try:\r\n'
    b'                cat_id = params[9]\r\n'
    b'            except (IndexError, TypeError):\r\n'
    b'                return self._inner.execute(sql, params)\r\n'
    b'            code = next(\r\n'
    b'                (k for k, v in cats_lookup.items() if v == cat_id), None\r\n'
    b'            )\r\n'
    b'            if code in empty_codes:\r\n'
    b'                return self._inner.execute(sql, params)\r\n'
    b'            class _Dummy:\r\n'
    b'                lastrowid = 0\r\n'
    b'                def fetchone(self_inner): return None\r\n'
    b'                def fetchall(self_inner): return []\r\n'
    b'            return _Dummy()\r\n'
    b'    # Re-run the existing Postgres seeder with the filtered connection\r\n'
    b'    # in scope. The seeder calls get_db() internally; we swap the global\r\n'
    b'    # for the duration of the call so its INSERTs route through the\r\n'
    b'    # filter. Restored in finally to avoid any leak.\r\n'
    b'    global get_db\r\n'
    b'    get_db = lambda: _FilteredConn(real_get_db)\r\n'
    b'    try:\r\n'
    b'        _seed_marketplace_postgres_samples()\r\n'
    b'    finally:\r\n'
    b'        get_db = real_get_db\r\n'
    b'\r\n'
)
data = data[:i] + helper + data[i:]

TARGET.write_bytes(data)
print(f"OK -- N applied, size {TARGET.stat().st_size:,}")
