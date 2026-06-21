# patch_template_generate_to_boq.py
# Make the template "Generate BOQ" button redirect to /boq-projects/<pid>/boq
# instead of back to the floor view, so the owner immediately sees the
# generated document.

from pathlib import Path
TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

OLD = (
    b"    flash(f\"Generated {saved} line(s) from template '{slug}'. "
    b"({skipped} skipped.)\", \"success\")\r\n"
    b"    return redirect(url_for(\"boq_floor_view\", pid=pid, bid=bid, fid=fid))\r\n"
)
NEW = (
    b"    flash(f\"Generated {saved} line(s) from template '{slug}'. "
    b"({skipped} skipped.)\", \"success\")\r\n"
    b"    # \"Generate BOQ\" lands on the project BOQ view immediately.\r\n"
    b"    return redirect(url_for(\"boq_project_boq\", pid=pid))\r\n"
)
n = data.count(OLD)
if n == 0:
    if b'return redirect(url_for("boq_project_boq", pid=pid))\r\n' in data:
        print("Already patched.")
    else:
        print("WARN: anchor missing.")
else:
    assert n == 1, f"multi-anchor count={n}"
    data = data.replace(OLD, NEW)
    TARGET.write_bytes(data)
    print("OK -- template Generate BOQ redirect now goes to project BOQ.")
