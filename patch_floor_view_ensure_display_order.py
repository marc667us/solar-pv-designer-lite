# patch_floor_view_ensure_display_order.py
# Make sure boq_floor_items.display_order exists BEFORE boq_floor_view's
# SELECT runs (the SELECT now uses COALESCE(i.display_order,0)).

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

OLD = (
    b'@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>")\r\n'
    b'@login_required\r\n'
    b'def boq_floor_view(pid, bid, fid):\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    project = _boq_project_owned_or_404(pid, uid)\r\n'
)
NEW = (
    b'@app.route("/boq-projects/<int:pid>/buildings/<int:bid>/floors/<int:fid>")\r\n'
    b'@login_required\r\n'
    b'def boq_floor_view(pid, bid, fid):\r\n'
    b'    try: _ensure_display_order_column()\r\n'
    b'    except Exception: pass\r\n'
    b'    uid = session["user_id"]\r\n'
    b'    project = _boq_project_owned_or_404(pid, uid)\r\n'
)
n = data.count(OLD)
if n == 1 and b"_ensure_display_order_column()" not in data[:data.find(OLD)+200]:
    data = data.replace(OLD, NEW, 1)
    TARGET.write_bytes(data)
    print("Patched boq_floor_view to ensure display_order column")
elif b"def boq_floor_view" in data and b"_ensure_display_order_column" in data:
    print("Already patched (likely)")
else:
    print(f"WARN: anchor count={n}")
