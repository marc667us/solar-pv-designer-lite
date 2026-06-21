# patch_attach_section_grid.py
# Splice the GRID routes (boq_section_grid / boq_section_grid_save) into
# web_app.py and switch boq_section_open to redirect to the GRID flow.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
NEW_FILE = Path(__file__).with_name("new_boq_section_grid_routes.py")

data = TARGET.read_bytes()
new_code = NEW_FILE.read_text(encoding="utf-8")

if b"def boq_section_grid" in data:
    print("grid routes already spliced.")
else:
    new_code_crlf = new_code.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    ANCHOR = b'if __name__ == "__main__":'
    pos = data.rfind(ANCHOR)
    assert pos > 0, "anchor not found"
    data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
    print(f"Spliced grid routes (+{len(new_code_crlf)} bytes).")

# Switch boq_section_open's redirect from loop -> grid (in-place edit on
# the already-spliced content from the loop routes splice).
OLD = (
    b'    subsec = (f.get("subsection_label") or "").strip()[:20]\r\n'
    b'    return redirect(url_for(\r\n'
    b'        "boq_section_loop",\r\n'
    b'        pid=pid, bid=bid, fid=fid,\r\n'
    b'        bill_no=bill_no, letter=letter,\r\n'
    b'        title=title, bill_name=bill_name, sub=subsec,\r\n'
    b'    ))\r\n'
)
NEW = (
    b'    subsec = (f.get("subsection_label") or "").strip()[:20]\r\n'
    b'    # Default flow = grid (bulk auto-populated from section catalogue, 90% faster).\r\n'
    b'    return redirect(url_for(\r\n'
    b'        "boq_section_grid",\r\n'
    b'        pid=pid, bid=bid, fid=fid,\r\n'
    b'        bill_no=bill_no, letter=letter,\r\n'
    b'        title=title, bill_name=bill_name, sub=subsec,\r\n'
    b'    ))\r\n'
)
if OLD in data:
    data = data.replace(OLD, NEW)
    print("Switched boq_section_open redirect: loop -> grid.")
elif b'"boq_section_grid"' in data:
    print("boq_section_open already redirects to grid.")
else:
    print("WARN: boq_section_open anchor missing -- skip.")

TARGET.write_bytes(data)
print("OK.")
