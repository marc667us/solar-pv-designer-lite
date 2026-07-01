#!/usr/bin/env python
"""Splice opps_persistence module into web_app.py; add write-through
call in fetch_opportunities(); add history stats to admin_opportunities().

Idempotent: BEGIN marker + existence checks on each patch site.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "web_app.py"
SRC = ROOT / "new_opps_persistence.py"

data = WEB.read_bytes()
orig = len(data)

BEGIN = b"# === BEGIN: opps_persistence splice ==="

# ---------------------------------------------------------------------
# 1. Splice the module before `if __name__ == "__main__":`
# ---------------------------------------------------------------------
if BEGIN in data:
    print("[skip] opps_persistence splice already present")
else:
    new_code = SRC.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    MAIN = b'if __name__ == "__main__":'
    pos = data.rfind(MAIN)
    if pos < 0:
        print("[abort] __main__ guard not found")
        raise SystemExit(1)
    data = data[:pos] + new_code + b"\r\n\r\n" + data[pos:]
    print(f"[ok] spliced {len(new_code)} bytes")

# ---------------------------------------------------------------------
# 2. Wire write-through into fetch_opportunities right before it returns.
# ---------------------------------------------------------------------
old_return = (
    b"    items.sort(key=_key)\r\n"
    b"    _OPPS_CACHE[\"items\"] = items\r\n"
    b"    _OPPS_CACHE[\"fetched_at\"] = now\r\n"
    b"    return items\r\n"
)
new_return = (
    b"    items.sort(key=_key)\r\n"
    b"    _OPPS_CACHE[\"items\"] = items\r\n"
    b"    _OPPS_CACHE[\"fetched_at\"] = now\r\n"
    b"    # 2026-07-01 Item F persistence: upsert every fetched opportunity\r\n"
    b"    # into solar_opportunities_crawled so history survives redeploys.\r\n"
    b"    try: _persist_opportunities(items)\r\n"
    b"    except Exception: pass\r\n"
    b"    return items\r\n"
)
if b"_persist_opportunities(items)" in data.split(BEGIN)[0]:
    print("[skip] fetch_opportunities already wired for persistence")
elif old_return in data:
    data = data.replace(old_return, new_return, 1)
    print("[ok] wired write-through into fetch_opportunities")
else:
    print("[warn] fetch_opportunities return block not found -- write-through NOT wired")

# ---------------------------------------------------------------------
# 3. Pass history stats to the admin_opportunities template.
# ---------------------------------------------------------------------
old_render = (
    b"    return render_template(\r\n"
    b"        \"admin_opportunities.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        items=items,\r\n"
    b"        countries=countries,\r\n"
    b"        types=types,\r\n"
    b"        sources=sources,\r\n"
    b"        active_country=f_country,\r\n"
    b"        active_type=f_type,\r\n"
    b"        active_source=f_source,\r\n"
    b"        cache_age_sec=int(time.time() - _OPPS_CACHE.get(\"fetched_at\", time.time())),\r\n"
    b"        total_unfiltered=len(all_items),\r\n"
    b"    )\r\n"
)
new_render = (
    b"    _history = _opportunities_history_stats()\r\n"
    b"    return render_template(\r\n"
    b"        \"admin_opportunities.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        items=items,\r\n"
    b"        countries=countries,\r\n"
    b"        types=types,\r\n"
    b"        sources=sources,\r\n"
    b"        active_country=f_country,\r\n"
    b"        active_type=f_type,\r\n"
    b"        active_source=f_source,\r\n"
    b"        cache_age_sec=int(time.time() - _OPPS_CACHE.get(\"fetched_at\", time.time())),\r\n"
    b"        total_unfiltered=len(all_items),\r\n"
    b"        history_stats=_history,\r\n"
    b"    )\r\n"
)
if b"history_stats=" in data.split(BEGIN)[0]:
    print("[skip] admin_opportunities already passes history_stats")
elif old_render in data:
    data = data.replace(old_render, new_render, 1)
    print("[ok] admin_opportunities now passes history_stats")
else:
    print("[warn] admin_opportunities render block not found")

if len(data) != orig:
    backup = WEB.with_suffix(".py.bak-opps-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(data)
    print(f"[write] web_app.py {orig} -> {len(data)} bytes")
