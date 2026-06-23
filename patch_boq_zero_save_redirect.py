#!/usr/bin/env python3
"""
patch_boq_zero_save_redirect.py

Pattern-A byte patch (CRLF preserved). Two changes to web_app.py:

1.  boq_section_grid_save -- when saved==0, the current code flashes a
    "Saved 0 item(s) ..." success toast and redirects to the project BOQ
    page (which is now empty, since nothing was saved). Owner reports
    the user-visible symptom: "Generate BOQ button does nothing". The
    fix: when saved==0 and skipped>0, flash a WARNING explaining what
    to do, and redirect BACK to the same grid (preserving section title
    + bill name + sub-section label) so the owner can enter Qty and try
    again. The non-zero path is unchanged.

2.  boq_template_save -- identical pattern. When saved==0 (template
    pre-fills basic + ticks but leaves Qty blank), redirect back to the
    template-picker checkbox view with a warning instead of dumping the
    user on an empty BOQ rollup.

Both changes are MINIMAL (one new branch each) and preserve every
existing audit-log call + commit semantics. The byte patcher matches
the exact CRLF-prefixed bytes around each edit point so a re-run is
safe (idempotency check up top).
"""

from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()
orig = data

# --------------------------------------------------------------------------
# CHANGE 1 -- boq_section_grid_save (around line 20546-20560)
# --------------------------------------------------------------------------
OLD_1 = (
    b'    flash(f"Saved {saved} item(s) under {letter}. {title}. "\r\n'
    b'          f"({skipped} blank row(s) ignored.)", "success")\r\n'
    b'\r\n'
    b'    nxt = (f.get("next_action") or "back").strip()\r\n'
)
NEW_1 = (
    b'    # When zero rows actually saved (every row was skipped because the\r\n'
    b'    # catalog pre-tick leaves Qty blank by default), this used to look\r\n'
    b'    # like the Generate button "did nothing": success toast + redirect\r\n'
    b'    # to an empty BOQ page. Reroute owner back to the grid with a\r\n'
    b'    # clearer warning so they can fill Qty and try again.\r\n'
    b'    if saved == 0 and skipped > 0:\r\n'
    b'        flash(\r\n'
    b'            "Nothing saved -- " + str(skipped) + " row(s) were skipped because "\r\n'
    b'            "Qty was blank, the description was empty, or the Basic price was 0. "\r\n'
    b'            "Tick at least one row and enter a Qty greater than 0, then try again.",\r\n'
    b'            "warning",\r\n'
    b'        )\r\n'
    b'        return redirect(url_for(\r\n'
    b'            "boq_section_grid",\r\n'
    b'            pid=pid, bid=bid, fid=fid, bill_no=bill_no, letter=letter,\r\n'
    b'            title=title, bill_name=bill_name, sub=subsec,\r\n'
    b'        ))\r\n'
    b'\r\n'
    b'    flash(f"Saved {saved} item(s) under {letter}. {title}. "\r\n'
    b'          f"({skipped} blank row(s) ignored.)", "success")\r\n'
    b'\r\n'
    b'    nxt = (f.get("next_action") or "back").strip()\r\n'
)

# --------------------------------------------------------------------------
# CHANGE 2 -- boq_template_save (around line 20822-20824)
# --------------------------------------------------------------------------
OLD_2 = (
    b'    flash(f"Generated {saved} line(s) from template \'{slug}\'. ({skipped} skipped.)", "success")\r\n'
    b'    # "Generate BOQ" lands on the project BOQ view immediately.\r\n'
    b'    return redirect(url_for("boq_project_boq", pid=pid))\r\n'
)
NEW_2 = (
    b'    # When zero rows actually generated (template pre-fills basic + ticks\r\n'
    b'    # but leaves Qty blank by default), the user otherwise lands on an\r\n'
    b'    # empty BOQ page wondering why "Generate BOQ" did nothing. Redirect\r\n'
    b'    # back to the template-picker with a clear warning instead.\r\n'
    b'    if saved == 0:\r\n'
    b'        flash(\r\n'
    b'            "Nothing generated -- " + str(skipped) + " row(s) were skipped "\r\n'
    b'            "(blank Qty, empty description, or Basic price = 0). Enter a Qty "\r\n'
    b'            "for at least one ticked row, then click Generate BOQ again.",\r\n'
    b'            "warning",\r\n'
    b'        )\r\n'
    b'        return redirect(url_for(\r\n'
    b'            "boq_template_checkbox", pid=pid, bid=bid, fid=fid, slug=slug,\r\n'
    b'        ))\r\n'
    b'\r\n'
    b'    flash(f"Generated {saved} line(s) from template \'{slug}\'. ({skipped} skipped.)", "success")\r\n'
    b'    # "Generate BOQ" lands on the project BOQ view immediately.\r\n'
    b'    return redirect(url_for("boq_project_boq", pid=pid))\r\n'
)

def apply_change(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    if new in data:
        print(f"[skip] {label} already patched")
        return data
    n = data.count(old)
    if n != 1:
        raise SystemExit(f"[fail] {label}: expected exactly 1 OLD match, found {n}")
    print(f"[ok]   {label}: applied (+{len(new) - len(old)} bytes)")
    return data.replace(old, new, 1)

data = apply_change(data, OLD_1, NEW_1, "section_grid_save zero-save redirect")
data = apply_change(data, OLD_2, NEW_2, "template_save zero-save redirect")

if data == orig:
    print("[noop] file unchanged")
else:
    P.write_bytes(data)
    print(f"[done] web_app.py: {len(orig)} -> {len(data)} bytes ({len(data)-len(orig):+d})")
