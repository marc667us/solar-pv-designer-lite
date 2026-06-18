"""
Hide test-fixture products from /marketplace and /procurement-center catalog
queries. Patterns: BulkProd-%, ProdB %, TestProd%, AUTOTEST%.

Targets both the public marketplace listing and the procurement-center grid.
Reversible: removing the four NOT-LIKE clauses restores them.
"""
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()
orig = data

FILTER = (
    b"WHERE ec.is_active=1 AND ec.is_public_visible=1 AND ec.is_verified=1 "
    b"  AND ec.name NOT LIKE 'BulkProd-%' "
    b"  AND ec.name NOT LIKE 'ProdB %' "
    b"  AND ec.name NOT LIKE 'TestProd%' "
    b"  AND ec.name NOT LIKE 'AUTOTEST%' "
)
OLD = b"WHERE ec.is_active=1 AND ec.is_public_visible=1 AND ec.is_verified=1 "

# We want to patch *exactly* the two catalog list queries — not the count
# queries that share a `WHERE is_active=1 AND is_public_visible=1 AND is_verified=1`
# without the `ec.` alias. Those don't include 'ec.' so the OLD pattern won't
# match them. Confirmed by inspection: only the two list queries use `ec.`.

count = data.count(OLD)
print(f"  matches of catalog-list WHERE clause: {count}")
if count == 0:
    if FILTER in data:
        print("[skip] already filtered")
        sys.exit(0)
    print("[MISS] catalog-list WHERE pattern not found")
    sys.exit(1)

data = data.replace(OLD, FILTER)
open(PATH, "wb").write(data)
print(f"[done] web_app.py {len(data)-len(orig):+d} bytes, {count} sites patched")
