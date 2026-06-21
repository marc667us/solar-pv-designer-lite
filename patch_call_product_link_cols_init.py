# patch_call_product_link_cols_init.py
# Add _ensure_product_link_columns() to the marketplace bootstrap path
# so equipment_catalog.literature_url and .datasheet_url exist before
# any marketplace product SELECT runs.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

# Inject the call at the end of _ensure_marketplace_tables (SQLite path).
OLD1 = (
    b'            # Per-category top-up: when _MARKETPLACE_CATEGORIES gains a new\r\n'
    b'            # entry that ships with starter samples (e.g. power_system),\r\n'
    b'            # populate ONLY those empty categories without re-seeding others.\r\n'
    b'            _backfill_marketplace_samples_for_empty_categories(c)\r\n'
    b'\r\n'
)
NEW1 = (
    b'            # Per-category top-up: when _MARKETPLACE_CATEGORIES gains a new\r\n'
    b'            # entry that ships with starter samples (e.g. power_system),\r\n'
    b'            # populate ONLY those empty categories without re-seeding others.\r\n'
    b'            _backfill_marketplace_samples_for_empty_categories(c)\r\n'
    b'    try: _ensure_product_link_columns()\r\n'
    b'    except Exception: pass\r\n'
    b'\r\n'
)
n1 = data.count(OLD1)
if n1 == 1:
    data = data.replace(OLD1, NEW1)
    print("Patched SQLite marketplace bootstrap")
elif b"_ensure_product_link_columns" in data and b"_ensure_marketplace_tables" in data:
    print("Already patched (SQLite)")
else:
    print(f"WARN SQLite anchor count={n1}")

# Inject at the end of _ensure_marketplace_schema_postgres too.
OLD2 = (
    b'                    "INSERT INTO product_categories (code, name, icon, display_order) "\r\n'
)
# Easier: find the end of the function and add a call near the marker variable.
# The function ends with `_MARKETPLACE_PG_DONE["v"] = True` -- find that.
MARK = b'    _MARKETPLACE_PG_DONE["v"] = True\r\n'
n2 = data.count(MARK)
if n2 == 1 and b"_ensure_product_link_columns()  # PG" not in data:
    NEW2 = (
        b'    try: _ensure_product_link_columns()  # PG ALTERs for product link cols\r\n'
        b'    except Exception: pass\r\n'
        b'    _MARKETPLACE_PG_DONE["v"] = True\r\n'
    )
    data = data.replace(MARK, NEW2)
    print("Patched Postgres marketplace bootstrap")
else:
    print(f"PG anchor count={n2} (may already be patched)")

TARGET.write_bytes(data)
print("OK")
