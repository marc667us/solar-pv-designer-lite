# patch_attach_data_v2_and_edit.py
# 1. Splice new_boq_data_v2.py (v2 catalogue + templates, including the
#    new residence template and Subfeeder section in every template).
#    Because it's appended AFTER the original definitions, the v2 dicts
#    override the v1 dicts at runtime.
# 2. Splice new_boq_edit_and_learn_routes.py (item-edit route + per-user
#    catalogue override learning).
# 3. Byte-patch the section grid loader so the catalogue dropdown reflects
#    the owner's recorded overrides.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()
ANCHOR = b'if __name__ == "__main__":'

# ---- 1. data v2 ----
if b'"residence-typical"' in data:
    print("data v2 already spliced.")
else:
    src = Path(__file__).with_name("new_boq_data_v2.py").read_text(encoding="utf-8")
    crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    pos = data.rfind(ANCHOR)
    assert pos > 0
    data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
    print(f"Spliced new_boq_data_v2.py (+{len(crlf)} bytes)")

# ---- 2. edit + learn routes ----
if b"def boq_floor_item_edit" in data:
    print("edit+learn routes already spliced.")
else:
    src = Path(__file__).with_name("new_boq_edit_and_learn_routes.py").read_text(encoding="utf-8")
    crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    pos = data.rfind(ANCHOR)
    assert pos > 0
    data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
    print(f"Spliced new_boq_edit_and_learn_routes.py (+{len(crlf)} bytes)")

# ---- 3. wrap catalogue lookup with the override layer ----
OLD3 = b"    catalog = _boq_catalog_for_section(title)\r\n"
NEW3 = (
    b"    catalog = _boq_catalog_for_section(title)\r\n"
    b"    # Personalise the catalogue dropdown with this user's last-saved\r\n"
    b"    # (unit, basic_price) edits per description so future BOQs reflect\r\n"
    b"    # their corrections automatically.\r\n"
    b"    try: catalog = _boq_apply_overrides(uid, catalog)\r\n"
    b"    except Exception: pass\r\n"
)
n = data.count(OLD3)
if n == 1 and b"_boq_apply_overrides(uid, catalog)" not in data:
    data = data.replace(OLD3, NEW3)
    print("Wrapped catalogue with _boq_apply_overrides")
elif b"_boq_apply_overrides(uid, catalog)" in data:
    print("override wrap already applied.")
else:
    print(f"WARN: catalog anchor count={n}")

TARGET.write_bytes(data)
print("OK")
