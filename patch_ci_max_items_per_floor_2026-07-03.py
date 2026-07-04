# Byte-level fix: cap the per-floor lean-starter item count so pricing ONE
# facility floor stays well under the free-tier worker limit. Live measurement:
# a control room (77 items) took ~40s of PG round-trips and killed the worker.
# 45 items/floor keeps a floor's "Finish BOQ pricing" click ~23s. Env-overridable
# (CI_MAX_ITEMS_PER_FLOOR) so a paid tier can raise it. web_app.py is byte-patched
# only (never text-edited). Idempotent.
data = open("web_app.py", "rb").read()
OLD = b"_CI_MAX_ITEMS_PER_FLOOR = 500\r\n"
NEW = (b'_CI_MAX_ITEMS_PER_FLOOR = max(1, int('
       b'os.environ.get("CI_MAX_ITEMS_PER_FLOOR", "45")))\r\n')
if NEW in data:
    print("ALREADY PATCHED - no change")
else:
    n = data.count(OLD)
    assert n == 1, f"expected 1 match, found {n}"
    open("web_app.py", "wb").write(data.replace(OLD, NEW))
    print("PATCHED _CI_MAX_ITEMS_PER_FLOOR -> env default 45")
