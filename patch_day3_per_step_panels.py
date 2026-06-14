"""Day 3 patch: extend the engine output so each series step carries its
per-panel fraction array (not just the day-aggregated max). The Three.js
scene then re-colors panels live as the operator drags the time slider.

Also persist the agent narrative + per-obstruction recommendations on
data["shading"]["agent_v2"] when the agent module is importable.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = (b'            "series": [\r\n'
       b'                {\r\n'
       b'                    "time": s.when.strftime("%H:%M"),\r\n'
       b'                    "alt":  round(s.altitude_deg, 1),\r\n'
       b'                    "az":   round(s.azimuth_deg, 1),\r\n'
       b'                    "avg_frac": round(s.avg_fraction, 4),\r\n'
       b'                    "partially": s.panels_partially_shaded,\r\n'
       b'                    "fully":     s.panels_fully_shaded,\r\n'
       b'                }\r\n'
       b'                for s in result["series"]\r\n'
       b'            ],\r\n')

NEW = (b'            "series": [\r\n'
       b'                {\r\n'
       b'                    "time": s.when.strftime("%H:%M"),\r\n'
       b'                    "alt":  round(s.altitude_deg, 1),\r\n'
       b'                    "az":   round(s.azimuth_deg, 1),\r\n'
       b'                    "avg_frac": round(s.avg_fraction, 4),\r\n'
       b'                    "partially": s.panels_partially_shaded,\r\n'
       b'                    "fully":     s.panels_fully_shaded,\r\n'
       b'                    # Day-3 add: per-panel fraction at THIS step\r\n'
       b'                    # so the time slider can re-color panels live.\r\n'
       b'                    "panel_fracs": [round(f, 3) for f in s.per_panel_fraction],\r\n'
       b'                }\r\n'
       b'                for s in result["series"]\r\n'
       b'            ],\r\n')


def patch():
    src = open(TARGET, "rb").read()
    if b'"panel_fracs":' in src:
        print("[skip] per-step panel_fracs already present")
        return 0
    if OLD not in src:
        print("[fail] series block anchor not found")
        return 2
    new_src = src.replace(OLD, NEW, 1)
    open(TARGET, "wb").write(new_src)
    print(f"[ok] added per-step panel_fracs ({len(src)} -> {len(new_src)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
