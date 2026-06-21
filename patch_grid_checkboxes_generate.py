# patch_grid_checkboxes_generate.py
# Apply checkbox-aware filtering and the Generate BOQ next_action to the
# spliced boq_section_grid_save handler in web_app.py.

from pathlib import Path
TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b'ticked_raw   = f.getlist("tick[]")' in data:
    print("Already patched.")
    raise SystemExit(0)

# P1 — add row_ids + ticked parsing after the existing remarks_l line.
OLD1 = b'    remarks_l    = f.getlist("remarks[]")\r\n'
NEW1 = (
    b'    remarks_l    = f.getlist("remarks[]")\r\n'
    b'    # tick[] contains the row indices the owner checked. row_id[] is the\r\n'
    b'    # parallel array of indices for each rendered row so we can map ticks\r\n'
    b'    # back to row positions. If neither is present, fall back to saving\r\n'
    b'    # any non-empty row (legacy behaviour, pre-checkbox grid).\r\n'
    b'    row_ids      = f.getlist("row_id[]")\r\n'
    b'    ticked_raw   = f.getlist("tick[]")\r\n'
    b'    ticked = set()\r\n'
    b'    legacy_mode = not row_ids\r\n'
    b'    for v in ticked_raw:\r\n'
    b'        try: ticked.add(int(v))\r\n'
    b'        except (TypeError, ValueError): pass\r\n'
)
assert data.count(OLD1) == 1, f"P1 anchor count={data.count(OLD1)}"
data = data.replace(OLD1, NEW1)

# P2 — insert tick check inside the row loop, before the empty-row skip.
OLD2 = (
    b'            remark = (remarks_l[i] if i < len(remarks_l) else "").strip()[:500]\r\n'
    b'\r\n'
    b'            # Skip rows the owner left empty.\r\n'
)
NEW2 = (
    b'            remark = (remarks_l[i] if i < len(remarks_l) else "").strip()[:500]\r\n'
    b'\r\n'
    b'            # Skip unticked rows when the grid posts a tick[] array.\r\n'
    b'            if not legacy_mode:\r\n'
    b'                try:\r\n'
    b'                    rid = int(row_ids[i]) if i < len(row_ids) else i\r\n'
    b'                except (TypeError, ValueError):\r\n'
    b'                    rid = i\r\n'
    b'                if rid not in ticked:\r\n'
    b'                    skipped += 1\r\n'
    b'                    continue\r\n'
    b'\r\n'
    b'            # Skip rows the owner left empty.\r\n'
)
assert data.count(OLD2) == 1, f"P2 anchor count={data.count(OLD2)}"
data = data.replace(OLD2, NEW2)

# P3 — add the "generate" next_action redirect.
OLD3 = (
    b'    if nxt == "stay":\r\n'
    b'        return redirect(url_for(\r\n'
    b'            "boq_section_grid",\r\n'
    b'            pid=pid, bid=bid, fid=fid, bill_no=bill_no, letter=letter,\r\n'
    b'            title=title, bill_name=bill_name, sub=subsec,\r\n'
    b'        ))\r\n'
    b'    return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))\r\n'
)
NEW3 = (
    b'    if nxt == "stay":\r\n'
    b'        return redirect(url_for(\r\n'
    b'            "boq_section_grid",\r\n'
    b'            pid=pid, bid=bid, fid=fid, bill_no=bill_no, letter=letter,\r\n'
    b'            title=title, bill_name=bill_name, sub=subsec,\r\n'
    b'        ))\r\n'
    b'    if nxt == "generate":\r\n'
    b'        return redirect(url_for("boq_project_boq", pid=pid))\r\n'
    b'    return redirect(url_for("boq_floor_view", pid=pid, bid=bid, fid=fid))\r\n'
)
assert data.count(OLD3) == 1, f"P3 anchor count={data.count(OLD3)}"
data = data.replace(OLD3, NEW3)

TARGET.write_bytes(data)
print("OK -- 3 patches applied (row_ids parsing, tick check, generate redirect).")
