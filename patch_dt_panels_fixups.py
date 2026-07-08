# 2026-07-07 Codex fixups for the Digital Twin panel + metrics change:
#  HIGH: lay PV rows E-W (long in X, spaced N-S in Z) so a south tilt (about X)
#        faces the equator -- the standard fixed-tilt layout AND what the
#        reference aerial shows (horizontal rows). dt_scene_v2 already picks the
#        tilt axis from w vs l, so long-in-X auto-tilts about X = south-facing.
#  MED : coerce finance numbers to float|None so a malformed computed value
#        (e.g. "abc") can't 500 the dashboard when the template formats it.
#  LOW : round loss items sequentially so they always sum to the real total.
# CRLF-aware byte patch (file is CRLF + mojibake -> never Edit).
import sys

PATH = "new_capital_investment_routes.py"
data = open(PATH, "rb").read()
orig = data
nl = b"\r\n" if b"\r\n" in data else b"\n"


def c(s):
    return s.replace("\n", "\r\n").encode() if nl == b"\r\n" else s.encode()


def rep(old, new, label, count=1):
    global data
    a, b = c(old), c(new)
    if b in data and a not in data:
        print(f"[skip] {label}: already applied")
        return
    n = data.count(a)
    if n == count:
        data = data.replace(a, b, count)
        print(f"[ok]   {label}")
    else:
        print(f"[warn] {label}: anchor count={n} (expected {count})")


# ---- HIGH: E-W row relayout (minimal line flips) ----
rep("    row_length = max(pv_field_l - 10.0, 10.0)\n",
    "    row_length = max(pv_field_w - 10.0, 10.0)\n",
    "row_length spans X (E-W)")
rep("    max_rows = max(1, int(pv_field_w / row_pitch))\n",
    "    max_rows = max(1, int(pv_field_l / row_pitch))\n",
    "rows spaced along Z (N-S)")
rep("        x_i = pv_field_x_start + row_pitch / 2.0 + i * row_pitch\n",
    "        z_i = pv_field_z_start + row_pitch / 2.0 + i * row_pitch\n",
    "row index axis -> Z")
rep('            "x":     x_i,\n',
    '            "x":     (pv_field_x_start + pv_field_x_end) / 2.0,\n',
    "row x -> field centre")
rep('            "z":     (pv_field_z_start + pv_field_z_end) / 2.0,\n',
    '            "z":     z_i,\n',
    "row z -> per-row spacing")
rep('            "w":     row_width,\n',
    '            "w":     row_length,\n',
    "row w -> long in X")
rep('            "l":     row_length,\n',
    '            "l":     row_width,\n',
    "row l -> narrow in Z")

# ---- MED: coerce finance numerics ----
rep(
    '        "capex": computed.get("total_capex_local"),\n'
    '        "lcoe": computed.get("lcoe_local_per_kwh"),\n'
    '        "irr_pct": computed.get("irr_pct"),\n'
    '        "npv": computed.get("npv_local"),\n'
    '        "payback_years": computed.get("payback_years"),\n'
    '        "tariff": computed.get("tariff_local_per_kwh"),\n',
    '        "capex": _fn(computed.get("total_capex_local")),\n'
    '        "lcoe": _fn(computed.get("lcoe_local_per_kwh")),\n'
    '        "irr_pct": _fn(computed.get("irr_pct")),\n'
    '        "npv": _fn(computed.get("npv_local")),\n'
    '        "payback_years": _fn(computed.get("payback_years")),\n'
    '        "tariff": _fn(computed.get("tariff_local_per_kwh")),\n',
    "finance float coercion")

# add the _fn helper right after the existing _fl helper in _ci_dt_metrics
rep(
    "    def _fl(v, d=0.0):\n"
    "        try:\n"
    "            return float(v)\n"
    "        except (TypeError, ValueError):\n"
    "            return d\n\n"
    "    pv = _safe_json(proj.get(\"pv_config\"))\n",
    "    def _fl(v, d=0.0):\n"
    "        try:\n"
    "            return float(v)\n"
    "        except (TypeError, ValueError):\n"
    "            return d\n\n"
    "    def _fn(v):\n"
    "        try:\n"
    "            return float(v)\n"
    "        except (TypeError, ValueError):\n"
    "            return None\n\n"
    "    pv = _safe_json(proj.get(\"pv_config\"))\n",
    "add _fn helper")

# ---- LOW: sequential loss rounding ----
rep(
    "    if total_loss > 0.0:\n"
    "        losses[\"items\"] = [\n"
    "            {\"label\": lbl, \"pct\": round(total_loss * share, 1), \"color\": col}\n"
    "            for (lbl, share, col) in _CI_LOSS_SHARES]\n",
    "    if total_loss > 0.0:\n"
    "        _items, _acc = [], 0.0\n"
    "        for _i, (lbl, share, col) in enumerate(_CI_LOSS_SHARES):\n"
    "            if _i < len(_CI_LOSS_SHARES) - 1:\n"
    "                _p = round(total_loss * share, 1); _acc += _p\n"
    "            else:\n"
    "                _p = round(total_loss - _acc, 1)   # last absorbs rounding drift\n"
    "            _items.append({\"label\": lbl, \"pct\": _p, \"color\": col})\n"
    "        losses[\"items\"] = _items\n",
    "loss sequential rounding")

if data != orig:
    open(PATH + ".before-panelfix-bak", "wb").write(orig)
    open(PATH, "wb").write(data)
    print(f"       WROTE (+{len(data)-len(orig)} bytes)")
else:
    print("       NO CHANGE")
    sys.exit(1)
