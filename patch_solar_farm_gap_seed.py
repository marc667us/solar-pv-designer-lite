# patch_solar_farm_gap_seed.py
# Splices new_solar_farm_marketplace_seed.py into web_app.py (Pattern B, CRLF)
# and wires _seed_solar_farm_gap_products() into BOTH seed paths of
# _ensure_marketplace_tables(), right after the curated-doc-links call.
# Idempotent: exits early if already patched.

data = open("web_app.py", "rb").read()

if b"def _seed_solar_farm_gap_products" in data:
    print("already patched -- no-op")
    raise SystemExit(0)

# 1. Insert the module block before the __main__ guard.
new_code = open("new_solar_farm_marketplace_seed.py", "rb").read()
new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
assert pos > 0, "anchor __main__ not found"
data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]

# 2. Postgres path (8-space indent, before `return`).
pg_old = (
    b"        # 2026-07-04: curated official datasheet/literature URLs (solar).\r\n"
    b"        try: _seed_curated_doc_links()\r\n"
    b"        except Exception: pass\r\n"
    b"        return"
)
pg_new = (
    b"        # 2026-07-04: curated official datasheet/literature URLs (solar).\r\n"
    b"        try: _seed_curated_doc_links()\r\n"
    b"        except Exception: pass\r\n"
    b"        # 2026-07-04: solar-farm BOQ gap products (breakers/IPS/SCADA).\r\n"
    b"        try: _seed_solar_farm_gap_products()\r\n"
    b"        except Exception: pass\r\n"
    b"        return"
)
assert data.count(pg_old) == 1, "postgres-path anchor not unique: %d" % data.count(pg_old)
data = data.replace(pg_old, pg_new)

# 3. SQLite path (4-space indent).
sq_old = (
    b"    # 2026-07-04: curated official datasheet/literature URLs (solar).\r\n"
    b"    try: _seed_curated_doc_links()\r\n"
    b"    except Exception: pass\r\n"
    b"\r\n"
    b"\r\ndef _seed_market"
)
sq_new = (
    b"    # 2026-07-04: curated official datasheet/literature URLs (solar).\r\n"
    b"    try: _seed_curated_doc_links()\r\n"
    b"    except Exception: pass\r\n"
    b"    # 2026-07-04: solar-farm BOQ gap products (breakers/IPS/SCADA).\r\n"
    b"    try: _seed_solar_farm_gap_products()\r\n"
    b"    except Exception: pass\r\n"
    b"\r\n"
    b"\r\ndef _seed_market"
)
assert data.count(sq_old) == 1, "sqlite-path anchor not unique: %d" % data.count(sq_old)
data = data.replace(sq_old, sq_new)

open("web_app.py", "wb").write(data)
print("patched: solar-farm gap seed inserted + wired into both seed paths")
