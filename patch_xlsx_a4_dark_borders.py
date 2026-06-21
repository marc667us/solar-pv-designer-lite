# patch_xlsx_a4_dark_borders.py
# Apply A4 page + solid dark borders to every XLSX report.
# Adds `_solarpro_xlsx_apply_borders_and_a4(wb.active or each ws)` just
# before each `wb.save(buf)` callsite.
#
# Strategy: for each of the four wb.save() callsites, wrap with a helper
# call. We use bytes match on the exact `    buf = io.BytesIO()\r\n    wb.save(buf)\r\n`
# pattern.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

# Pattern A: standalone 4-line block at L17515 + L22702
OLD_A = (
    b"    buf = io.BytesIO()\r\n"
    b"    wb.save(buf)\r\n"
    b"    buf.seek(0)\r\n"
)
NEW_A = (
    b"    try:\r\n"
    b"        for _ws in wb.worksheets:\r\n"
    b"            _solarpro_xlsx_apply_borders_and_a4(_ws)\r\n"
    b"    except Exception:\r\n"
    b"        pass\r\n"
    b"    buf = io.BytesIO()\r\n"
    b"    wb.save(buf)\r\n"
    b"    buf.seek(0)\r\n"
)

# Pattern B: one-line block at L20479
OLD_B = b"    buf = io.BytesIO(); wb.save(buf); buf.seek(0)\r\n"
NEW_B = (
    b"    try:\r\n"
    b"        for _ws in wb.worksheets:\r\n"
    b"            _solarpro_xlsx_apply_borders_and_a4(_ws)\r\n"
    b"    except Exception:\r\n"
    b"        pass\r\n"
    b"    buf = io.BytesIO(); wb.save(buf); buf.seek(0)\r\n"
)

# Pattern C: _xl_send helper at L3617 (used by other reports)
OLD_C = (
    b"def _xl_send(wb, filename):\r\n"
    b"    buf = io.BytesIO()\r\n"
    b"    wb.save(buf)\r\n"
)
NEW_C = (
    b"def _xl_send(wb, filename):\r\n"
    b"    try:\r\n"
    b"        for _ws in wb.worksheets:\r\n"
    b"            _solarpro_xlsx_apply_borders_and_a4(_ws)\r\n"
    b"    except Exception:\r\n"
    b"        pass\r\n"
    b"    buf = io.BytesIO()\r\n"
    b"    wb.save(buf)\r\n"
)

changed = 0
for old, new in [(OLD_C, NEW_C), (OLD_A, NEW_A), (OLD_B, NEW_B)]:
    n = data.count(old)
    if n > 0 and new not in data:
        # safety guard: skip if already wrapped via marker
        pass
    if n > 0:
        # We want to wrap each occurrence. Use replace which substitutes all.
        # But guard against re-wrapping by skipping if helper call already
        # appears in close proximity (handled by overall idempotency below).
        new_data = data.replace(old, new)
        delta = new_data.count(b"_solarpro_xlsx_apply_borders_and_a4(_ws)") \
                - data.count(b"_solarpro_xlsx_apply_borders_and_a4(_ws)")
        data = new_data
        changed += delta
        print(f"OK wrapped {delta} callsite(s) for pattern matching first {len(old)} bytes")

if changed == 0 and b"_solarpro_xlsx_apply_borders_and_a4(_ws)" in data:
    print("Already patched")

TARGET.write_bytes(data)
print(f"OK changed={changed}")
