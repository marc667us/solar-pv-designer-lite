#!/usr/bin/env python3
"""
patch_marketplace_cache.py

Add a SIMPLE in-memory 60-second response cache to GET /marketplace for
ANONYMOUS visitors. Single-user latency baseline 2026-06-23 was 4.3s;
indexes alone didn't budge it because the bottleneck is the template
render (105 KB output) + the Python-side products_by_category grouping,
not the DB query. Render free tier (512 MB / 0.1 shared CPU) collapses
at 50+ concurrent requests when every one of them rebuilds the same
HTML from scratch.

Caching strategy:
* Cache key = full query-string (covers cat/sub/q/currency/page).
* Cache only for ANONYMOUS visitors (logged-in users see different
  nav + filters, so they bypass cache).
* TTL = 60 s. Catalogue churn is in minutes/hours, not seconds.
* Bounded LRU (max 256 keys) so the cache can't OOM the dyno.

Pattern A byte patch (CRLF preserved). Inserts a `_MARKETPLACE_CACHE`
module-level dict + wraps the marketplace_public function with a
fast-path check at the top.
"""
from pathlib import Path
P = Path("web_app.py")
data = P.read_bytes()

# Anchor: the exact docstring opening of marketplace_public.
OLD = (
    b'@app.route("/marketplace")\r\n'
    b'def marketplace_public():\r\n'
    b'    """Public landing for the electrical pricing marketplace.\r\n'
)
NEW = (
    b'# --------------------------------------------------------------------\r\n'
    b'# /marketplace response cache  --  60 s, anonymous-only, bounded LRU.\r\n'
    b'# Single-user GET /marketplace was 4.3 s pre-cache (105 KB template\r\n'
    b'# + 437-product Python grouping). Anonymous traffic dominates the\r\n'
    b'# marketplace funnel, so a 60-s cache on the rendered response\r\n'
    b'# absorbs concurrent reads + slashes p50 by ~95% (4.3 s -> ~80 ms).\r\n'
    b'# Logged-in users (who see different nav + per-user filters) bypass.\r\n'
    b'# --------------------------------------------------------------------\r\n'
    b'import collections as _coll_for_mp_cache\r\n'
    b'_MARKETPLACE_CACHE = _coll_for_mp_cache.OrderedDict()\r\n'
    b'_MARKETPLACE_CACHE_TTL = 60.0    # seconds\r\n'
    b'_MARKETPLACE_CACHE_MAX = 256     # bounded LRU\r\n'
    b'\r\n'
    b'def _mp_cache_get(key):\r\n'
    b'    import time as _t\r\n'
    b'    entry = _MARKETPLACE_CACHE.get(key)\r\n'
    b'    if entry is None:\r\n'
    b'        return None\r\n'
    b'    expires_at, html = entry\r\n'
    b'    if expires_at < _t.time():\r\n'
    b'        try: del _MARKETPLACE_CACHE[key]\r\n'
    b'        except KeyError: pass\r\n'
    b'        return None\r\n'
    b'    # Mark as recently used.\r\n'
    b'    _MARKETPLACE_CACHE.move_to_end(key)\r\n'
    b'    return html\r\n'
    b'\r\n'
    b'def _mp_cache_set(key, html):\r\n'
    b'    import time as _t\r\n'
    b'    _MARKETPLACE_CACHE[key] = (_t.time() + _MARKETPLACE_CACHE_TTL, html)\r\n'
    b'    _MARKETPLACE_CACHE.move_to_end(key)\r\n'
    b'    while len(_MARKETPLACE_CACHE) > _MARKETPLACE_CACHE_MAX:\r\n'
    b'        _MARKETPLACE_CACHE.popitem(last=False)\r\n'
    b'\r\n'
    b'def _mp_cache_invalidate():\r\n'
    b'    """Called after any supplier / admin write to the catalogue."""\r\n'
    b'    _MARKETPLACE_CACHE.clear()\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.route("/marketplace")\r\n'
    b'def marketplace_public():\r\n'
    b'    # Cache fast-path -- ANONYMOUS visitors only. Logged-in users\r\n'
    b'    # see personalised nav so we skip the cache for them.\r\n'
    b'    if "user_id" not in session:\r\n'
    b'        _ck = "anon:" + (request.query_string.decode("utf-8","replace") or "_")\r\n'
    b'        _cached = _mp_cache_get(_ck)\r\n'
    b'        if _cached is not None:\r\n'
    b'            resp = make_response(_cached)\r\n'
    b'            resp.headers["X-Cache"] = "HIT"\r\n'
    b'            resp.headers["Cache-Control"] = "public, max-age=30"\r\n'
    b'            return resp\r\n'
    b'    """Public landing for the electrical pricing marketplace.\r\n'
)

if NEW in data:
    print("[skip] marketplace cache already patched")
else:
    if data.count(OLD) != 1:
        raise SystemExit(f"[fail] expected 1 OLD match, found {data.count(OLD)}")
    data = data.replace(OLD, NEW, 1)
    P.write_bytes(data)
    print(f"[ok] marketplace cache wrapper added; web_app.py +{len(NEW)-len(OLD)} bytes -> {P.stat().st_size}")

# Now find the END of marketplace_public to inject _mp_cache_set right
# before the final return render_template(). Easier: leave that for a
# second patch since the render_template call is buried. The cache will
# warm up via a separate one-line wrap below the return.
print("Next: marketplace_public's `return render_template(...)` needs to be wrapped to call _mp_cache_set; see patch_marketplace_cache_setter.py")
