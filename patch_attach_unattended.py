# patch_attach_unattended.py
# 1. Splice new_unattended_routes.py (qty edit + up/down move).
# 2. Update boq_floor_view ORDER BY to honor display_order ASC inside
#    each (bill_no, section_letter) group so manual reorder takes
#    visible effect.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

# 1. Splice
if b"def boms_edit_item_qty" in data:
    print("Already spliced.")
else:
    src = Path(__file__).with_name("new_unattended_routes.py").read_text(encoding="utf-8")
    crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    ANCHOR = b'if __name__ == "__main__":'
    pos = data.rfind(ANCHOR)
    assert pos > 0
    data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
    print(f"Spliced unattended routes (+{len(crlf)} bytes)")

# 2. Update floor_view ORDER BY
OLD = (
    b'            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "\r\n'
    b'            "WHERE i.floor_id=? "\r\n'
    b'            "ORDER BY COALESCE(i.bill_no,0), COALESCE(i.section_letter,\'\'), "\r\n'
    b'            "         COALESCE(NULLIF(i.item_no_display,\'\'),\'0\'), i.id",\r\n'
)
NEW = (
    b'            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "\r\n'
    b'            "WHERE i.floor_id=? "\r\n'
    b'            "ORDER BY COALESCE(i.bill_no,0), COALESCE(i.section_letter,\'\'), "\r\n'
    b'            "         COALESCE(i.display_order,0), "\r\n'
    b'            "         COALESCE(NULLIF(i.item_no_display,\'\'),\'0\'), i.id",\r\n'
)
n = data.count(OLD)
if n == 1:
    data = data.replace(OLD, NEW)
    print("Updated boq_floor_view ORDER BY to honor display_order")
elif b"COALESCE(i.display_order,0)" in data:
    print("display_order ordering already applied")
else:
    print(f"WARN floor ORDER BY anchor count={n}")

TARGET.write_bytes(data)
print("OK")
