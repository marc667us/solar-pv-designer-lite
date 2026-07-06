# Pattern A byte-patches: default per-category operating hours ("timers").
#   1. Add DEFAULT_HOURS + _default_hours_for() right after DEMAND_FACTORS.
#   2. In project_loads POST, fall back to the category default when the operator
#      leaves hours blank/0, so the design calculation never runs a load at 0h.
# User-entered hours always take precedence. Idempotent; fail-loud on miss.
data = open("web_app.py", "rb").read()
orig = data
missing = []

# ── 1. DEFAULT_HOURS table + helper ──
a1 = (b'    "Other":       0.70,   # General diversity allowance\r\n'
      b'}\r\n'
      b'\r\n'
      b'def inverter_brand(inv_kw):')
b1 = (b'    "Other":       0.70,   # General diversity allowance\r\n'
      b'}\r\n'
      b'\r\n'
      b'# Assumed daily operating hours ("timer") per appliance category. Used as a\r\n'
      b'# fallback so a load never enters the design calculation at 0 hours; a value\r\n'
      b'# entered during design always overrides these. (Owner directive 2026-07-06.)\r\n'
      b'DEFAULT_HOURS = {\r\n'
      b'    "Lighting":    14.0,  # owner-specified daily on-time\r\n'
      b'    "Cooling":     10.0,  # fans (owner-specified daily on-time)\r\n'
      b'    "Appliances":  4.0,   # mixed kitchen / laundry duty cycles\r\n'
      b'    "Electronics": 5.0,   # TV / audio / chargers\r\n'
      b'    "Pumps":       3.0,   # intermittent water pumping\r\n'
      b'    "Heating":     2.0,   # water heaters / short heating bursts\r\n'
      b'    "Office":      8.0,   # a working day\r\n'
      b'    "Other":       4.0,   # general default\r\n'
      b'}\r\n'
      b'\r\n'
      b'def _default_hours_for(category):\r\n'
      b'    """Assumed daily operating hours for a load category, applied when the\r\n'
      b'    operator has not entered a value. User-entered hours take precedence."""\r\n'
      b'    try:\r\n'
      b'        return float(DEFAULT_HOURS.get(category, 4.0))\r\n'
      b'    except (TypeError, ValueError):\r\n'
      b'        return 4.0\r\n'
      b'\r\n'
      b'def inverter_brand(inv_kw):')
if b'def _default_hours_for(' in data:
    print("SKIP 1: DEFAULT_HOURS already present")
elif a1 in data:
    data = data.replace(a1, b1, 1); print("OK 1: DEFAULT_HOURS added")
else:
    missing.append("DEFAULT_HOURS block")

# ── 2. hours fallback in project_loads POST ──
a2 = (b'            df_val = max(0.10, min(1.0, df_val))\r\n'
      b'            loads.append({')
b2 = (b'            df_val = max(0.10, min(1.0, df_val))\r\n'
      b'            # Operating hours ("timer"): use the value entered during\r\n'
      b'            # design; if blank or 0, fall back to the category default so\r\n'
      b'            # the calculation never runs a load at 0 hours.\r\n'
      b'            try:\r\n'
      b'                _h = float(hours[i]) if (i < len(hours) and str(hours[i]).strip() != "") else 0.0\r\n'
      b'            except (ValueError, IndexError):\r\n'
      b'                _h = 0.0\r\n'
      b'            if _h <= 0:\r\n'
      b'                _h = _default_hours_for(cat)\r\n'
      b'            loads.append({')
a2b = b'                "hours":         float(hours[i]) if i < len(hours) else 0,\r\n'
b2b = b'                "hours":         _h,\r\n'
if b'_h = _default_hours_for(cat)' in data:
    print("SKIP 2: hours fallback already present")
elif a2 in data and a2b in data:
    data = data.replace(a2, b2, 1).replace(a2b, b2b, 1); print("OK 2: hours fallback added")
else:
    missing.append("project_loads hours fallback")

if missing:
    raise SystemExit("FAIL: anchors not found: " + ", ".join(missing))
if data != orig:
    open("web_app.py", "wb").write(data)
    print("WROTE web_app.py")
else:
    print("NO CHANGE")
