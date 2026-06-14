"""Add ?demo=10 / ?demo=heavy / ?demo=severe URL param to the shading
route so the operator can see the full dashboard in action without
typing in obstructions. Each preset injects a calibrated sample
obstruction set known to land in the matching bucket.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = b'    # Engine runs on GET whenever no engine output exists yet, regardless\r\n'
NEW = (b'    # ?demo=<level> injects sample obstructions so the dashboard shows\r\n'
       b'    # something even on a project with no real obstructions saved. The\r\n'
       b'    # operator can test the engine + agent + 3D scene with one click.\r\n'
       b'    _demo = (request.args.get("demo") or "").strip().lower()\r\n'
       b'    _demo_obs = {\r\n'
       b'        "10":  [{"type": "parapet wall", "height": 1.8, "width": 8.0,\r\n'
       b'                 "distance": 4.0, "direction": "South",\r\n'
       b'                 "mitigation": "Bypass diodes",\r\n'
       b'                 "notes": "demo: light shading sample"}],\r\n'
       b'        "20":  [{"type": "neighbour building", "height": 8.0, "width": 10.0,\r\n'
       b'                 "distance": 8.0, "direction": "West",\r\n'
       b'                 "mitigation": "Bypass diodes",\r\n'
       b'                 "notes": "demo: significant shading sample"}],\r\n'
       b'        "25":  [{"type": "large tree", "height": 9.0, "width": 6.0,\r\n'
       b'                 "distance": 5.0, "direction": "South-West",\r\n'
       b'                 "mitigation": "Bypass diodes",\r\n'
       b'                 "notes": "demo: heavy shading sample"}],\r\n'
       b'        "30":  [{"type": "10-storey building", "height": 32.0, "width": 18.0,\r\n'
       b'                 "distance": 18.0, "direction": "West",\r\n'
       b'                 "mitigation": "Bypass diodes",\r\n'
       b'                 "notes": "demo: severe shading sample"}],\r\n'
       b'    }\r\n'
       b'    if _demo in _demo_obs:\r\n'
       b'        shading = dict(shading)\r\n'
       b'        shading["obstructions"] = _demo_obs[_demo]\r\n'
       b'        shading.pop("engine", None)\r\n'
       b'        shading.pop("agent_v2", None)\r\n'
       b'\r\n'
       b'    # Engine runs on GET whenever no engine output exists yet, regardless\r\n')


def patch():
    src = open(TARGET, "rb").read()
    if b'?demo=<level> injects sample obstructions' in src:
        print("[skip] demo mode already wired")
        return 0
    if OLD not in src:
        print("[fail] anchor not found")
        return 2
    open(TARGET, "wb").write(src.replace(OLD, NEW, 1))
    print("[ok] demo mode wired (?demo=10 / 20 / 25 / 30)")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
