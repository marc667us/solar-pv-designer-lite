# patch_shading_building_dims.py
# Owner directive 2026-06-21: the 3D shading simulation must take input
# from the actual building the solar system is being designed for AND
# the obstruction data. Previously the SVG width was a fake h*2.8
# derive-from-height.
#
# Adds building_width_m + building_length_m to the project_shading POST
# handler's `_existing.update({...})` block so they persist alongside
# roof_height_m and feed the SVG render + engine.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

OLD = (
    b'            "roof_height_m":        _shading_num(request.form.get("roof_height_m")),\r\n'
    b'            "inspection_confirmed": bool(request.form.get("inspection_confirmed")),\r\n'
)
NEW = (
    b'            "roof_height_m":        _shading_num(request.form.get("roof_height_m")),\r\n'
    b'            # Owner directive 2026-06-21: real operator-entered building\r\n'
    b'            # dimensions drive the 3D scene + engine, not a fake h*2.8.\r\n'
    b'            "building_width_m":     _shading_num(request.form.get("building_width_m")),\r\n'
    b'            "building_length_m":    _shading_num(request.form.get("building_length_m")),\r\n'
    b'            "inspection_confirmed": bool(request.form.get("inspection_confirmed")),\r\n'
)
if OLD in data:
    data = data.replace(OLD, NEW)
    TARGET.write_bytes(data)
    print("OK building_width_m + building_length_m persist on save")
elif b'"building_width_m":     _shading_num' in data:
    print("Already patched")
else:
    print("WARN anchor not found")
