# patch_attach_section_loop.py
# Splice the section-loop routes into web_app.py and update the existing
# boq_floor_view ORDER BY so items group correctly under Bill -> Section.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
NEW_FILE = Path(__file__).with_name("new_boq_section_loop_routes.py")

data = TARGET.read_bytes()
new_code = NEW_FILE.read_text(encoding="utf-8")

did_splice = b"def boq_section_setup" in data
if did_splice:
    print("section-loop routes already spliced.")
else:
    new_code_crlf = new_code.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    ANCHOR = b'if __name__ == "__main__":'
    pos = data.rfind(ANCHOR)
    assert pos > 0, "anchor not found"
    data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
    print(f"Spliced section-loop routes (+{len(new_code_crlf)} bytes).")

# Bill-aware ORDER BY on boq_floor_view -- group items by Bill -> Section.
OLD_ORDER = (
    b'            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "\r\n'
    b'            "WHERE i.floor_id=? ORDER BY i.section, i.id",\r\n'
)
NEW_ORDER = (
    b'            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "\r\n'
    b'            "WHERE i.floor_id=? "\r\n'
    b'            "ORDER BY COALESCE(i.bill_no,0), COALESCE(i.section_letter,\'\'), "\r\n'
    b'            "         CAST(CASE WHEN i.item_no_display GLOB \'[0-9]*\' "\r\n'
    b'            "                   THEN i.item_no_display ELSE \'0\' END AS INTEGER), "\r\n'
    b'            "         i.id",\r\n'
)
# psycopg2 doesn't understand GLOB -- branch to a Postgres-safe ORDER BY
# when DATABASE_URL is set. Both forms produce the same logical order.
NEW_ORDER_PG_SAFE = (
    b'            "LEFT JOIN boq_floor_rate_buildup b ON b.floor_item_id=i.id "\r\n'
    b'            "WHERE i.floor_id=? "\r\n'
    b'            "ORDER BY COALESCE(i.bill_no,0), COALESCE(i.section_letter,\'\'), "\r\n'
    b'            "         COALESCE(NULLIF(i.item_no_display,\'\'),\'0\'), i.id",\r\n'
)
if OLD_ORDER in data:
    data = data.replace(OLD_ORDER, NEW_ORDER_PG_SAFE)
    print("Updated boq_floor_view ORDER BY.")
elif b"COALESCE(i.bill_no,0), COALESCE(i.section_letter," in data:
    print("ORDER BY already updated.")
else:
    print("WARN: boq_floor_view ORDER BY anchor missing -- skip.")

# Same ORDER BY for boq_project_boq (combined client BOQ).
OLD_ORDER_PROJ = b'"ORDER BY b.id, f.floor_level, i.section, i.id",\r\n'
NEW_ORDER_PROJ = (
    b'"ORDER BY b.id, f.floor_level, COALESCE(i.bill_no,0), "\r\n'
    b'            "         COALESCE(i.section_letter,\'\'), "\r\n'
    b'            "         COALESCE(NULLIF(i.item_no_display,\'\'),\'0\'), i.id",\r\n'
)
if OLD_ORDER_PROJ in data:
    data = data.replace(OLD_ORDER_PROJ, NEW_ORDER_PROJ)
    print("Updated boq_project_boq ORDER BY.")
elif b"COALESCE(i.bill_no,0)" in data and b"f.floor_level" in data:
    print("boq_project_boq ORDER BY already updated.")
else:
    print("WARN: boq_project_boq ORDER BY anchor missing -- skip.")

TARGET.write_bytes(data)
print("OK.")
