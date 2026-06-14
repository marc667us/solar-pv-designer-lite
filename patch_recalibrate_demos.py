"""Recalibrate the ?demo=10/20/25/30 obstruction sets so each actually
lands on its promised bucket. The original parapet/building presets were
producing 67-86% loss because the geometry was too aggressive for an
equatorial site at noon (sun overhead → tall close obstructions cast
large shadows).

Calibrated against engine.shading_engine.run_full_analysis at:
  lat=5.6, lon=-0.2 (Accra), 21-Jun, tilt=15, azimuth=180, 12 panels.

Results (verified):
  demo=10 → 5m tree 6m East   → 12.3% loss → factor 0.90 Light shading
  demo=20 → 5m tree 5m East   → 23.8% loss → factor 0.80 Significant
  demo=25 → 6m wall 6m East   → 25.0% loss → factor 0.75 Heavy
  demo=30 → 5m wall 5m East   → 36.3% loss → factor 0.70 Severe
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = b"""    _demo_obs = {\r
        "10":  [{"type": "parapet wall", "height": 1.8, "width": 8.0,\r
                 "distance": 4.0, "direction": "South",\r
                 "mitigation": "Bypass diodes",\r
                 "notes": "demo: light shading sample"}],\r
        "20":  [{"type": "neighbour building", "height": 8.0, "width": 10.0,\r
                 "distance": 8.0, "direction": "West",\r
                 "mitigation": "Bypass diodes",\r
                 "notes": "demo: significant shading sample"}],\r
        "25":  [{"type": "large tree", "height": 9.0, "width": 6.0,\r
                 "distance": 5.0, "direction": "South-West",\r
                 "mitigation": "Bypass diodes",\r
                 "notes": "demo: heavy shading sample"}],\r
        "30":  [{"type": "10-storey building", "height": 32.0, "width": 18.0,\r
                 "distance": 18.0, "direction": "West",\r
                 "mitigation": "Bypass diodes",\r
                 "notes": "demo: severe shading sample"}],\r
    }\r
"""

NEW = b"""    # Calibrated 2026-06-14 against engine output at Accra/12 panels:
    #   demo=10  -> 5m tree  6m East  -> 12.3% loss -> 0.90 Light
    #   demo=20  -> 5m tree  5m East  -> 23.8% loss -> 0.80 Significant
    #   demo=25  -> 6m wall  6m East  -> 25.0% loss -> 0.75 Heavy
    #   demo=30  -> 5m wall  5m East  -> 36.3% loss -> 0.70 Severe
    _demo_obs = {
        "10":  [{"type": "tree", "height": 5.0, "width": 3.0,
                 "distance": 6.0, "direction": "East",
                 "mitigation": "Bypass diodes",
                 "notes": "demo: light shading (single tree to the east)"}],
        "20":  [{"type": "tree", "height": 5.0, "width": 4.0,
                 "distance": 5.0, "direction": "East",
                 "mitigation": "Bypass diodes",
                 "notes": "demo: significant shading (closer tree)"}],
        "25":  [{"type": "boundary wall", "height": 6.0, "width": 5.0,
                 "distance": 6.0, "direction": "East",
                 "mitigation": "Bypass diodes",
                 "notes": "demo: heavy shading (wall to the east)"}],
        "30":  [{"type": "boundary wall", "height": 5.0, "width": 5.0,
                 "distance": 5.0, "direction": "East",
                 "mitigation": "Bypass diodes",
                 "notes": "demo: severe shading (wall close in)"}],
    }
""".replace(b"\n", b"\r\n")


def patch():
    src = open(TARGET, "rb").read()
    if b"Calibrated 2026-06-14 against engine output" in src:
        print("[skip] demos already recalibrated")
        return 0
    if OLD not in src:
        print("[fail] anchor not found")
        return 2
    open(TARGET, "wb").write(src.replace(OLD, NEW, 1))
    print("[ok] demos recalibrated (10/20/25/30 land on 0.90/0.80/0.75/0.70)")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
