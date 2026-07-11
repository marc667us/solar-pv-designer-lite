"""Additively wire the Tutorial & Demo Engine to the server's admin config
(AC11 enable/disable) and analytics sink (AC12). CRLF-safe byte edits on
static/tutorial/tutorial-engine.js. Idempotent: re-running is a no-op.

Each edit asserts its anchor appears exactly once, so a future engine refactor
that moves an anchor fails loudly here instead of silently skipping a hook.
Run: python patch_tutorial_engine.py
"""

PATH = "static/tutorial/tutorial-engine.js"
SENTINEL = b"function beacon("   # already wired?


def _one(data, anchor, label):
    n = data.count(anchor)
    if n != 1:
        raise SystemExit("[fail] anchor '%s' found %d times (expected 1)" % (label, n))


def main():
    data = open(PATH, "rb").read()
    if SENTINEL in data:
        print("[skip] tutorial-engine.js already wired to config + analytics")
        return

    # ── A. config object + beacon helper, inserted right after the T state obj ──
    a_anchor = (b"    els: {}, timer: null, rec: null, chunks: [], stream: null, alive: false\r\n  };\r\n")
    _one(data, a_anchor, "T-object")
    a_block = a_anchor + (
        b"\r\n"
        b"  // ---------- admin config + analytics (spec AC11 disable, AC12 record) ----------\r\n"
        b"  // The engine asks the server which tutorials the admin left enabled and\r\n"
        b"  // whether to record usage. Both default ON so a failed config fetch never\r\n"
        b"  // silently disables a working tutorial. Beacons are fire-and-forget.\r\n"
        b"  var CFG = { enabled: true, analytics: true, disabled: {} };\r\n"
        b"\r\n"
        b"  function beacon(type, extra) {\r\n"
        b"    if (!CFG.analytics) return;\r\n"
        b"    try {\r\n"
        b"      var payload = { page: PAGE, event_type: type };\r\n"
        b"      if (extra) for (var k in extra) { if (extra[k] != null) payload[k] = extra[k]; }\r\n"
        b"      var body = JSON.stringify(payload);\r\n"
        b"      // sendBeacon survives page unload (navigate/close); fall back to fetch.\r\n"
        b"      if (navigator.sendBeacon) {\r\n"
        b"        navigator.sendBeacon('/api/tutorial/event', new Blob([body], { type: 'application/json' }));\r\n"
        b"      } else {\r\n"
        b"        fetch('/api/tutorial/event', { method: 'POST', credentials: 'same-origin',\r\n"
        b"          headers: { 'Content-Type': 'application/json' }, body: body, keepalive: true });\r\n"
        b"      }\r\n"
        b"    } catch (e) {}\r\n"
        b"  }\r\n")
    data = data.replace(a_anchor, a_block, 1)

    # ── C. start(): reset completion flag + emit 'started' ──
    c_anchor = (b"    T.i = 0; T.alive = true;\r\n"
                b"    if (T.mode === 'explain') return explain();")
    _one(data, c_anchor, "start")
    c_new = (b"    T.i = 0; T.alive = true;\r\n"
             b"    T._completed = false;\r\n"
             b"    beacon('started', { mode: T.mode, total_steps: steps().length });\r\n"
             b"    if (T.mode === 'explain') return explain();")
    data = data.replace(c_anchor, c_new, 1)

    # ── D. finish(): mark completed + emit 'completed' ──
    d_anchor = (b"    clearFlow();\r\n"
                b"    T.playing = false;\r\n"
                b"    setTimeout(stop, 1400);")
    _one(data, d_anchor, "finish")
    d_new = (b"    clearFlow();\r\n"
             b"    T.playing = false;\r\n"
             b"    T._completed = true;\r\n"
             b"    beacon('completed', { step_index: steps().length - 1, total_steps: steps().length });\r\n"
             b"    setTimeout(stop, 1400);")
    data = data.replace(d_anchor, d_new, 1)

    # ── E. stop(): emit 'skipped' when a real tour was exited early ──
    e_anchor = (b"  function stop() {\r\n"
                b"    T.alive = false; T.playing = false;")
    _one(data, e_anchor, "stop")
    e_new = (b"  function stop() {\r\n"
             b"    if (T.alive && !T._completed && T.mode !== 'explain') {\r\n"
             b"      beacon('skipped', { step_index: T.i, total_steps: steps().length });\r\n"
             b"    }\r\n"
             b"    T.alive = false; T.playing = false;")
    data = data.replace(e_anchor, e_new, 1)

    # ── F. runStep(): emit 'step_shown' as each step begins ──
    f_anchor = (b"    markFlow();                       // survive a navigation from any step\r\n"
                b"    var node = q(s.targetSelector);")
    _one(data, f_anchor, "runStep-top")
    f_new = (b"    markFlow();                       // survive a navigation from any step\r\n"
             b"    beacon('step_shown', { step_index: T.i, step_title: s.title, mode: T.mode });\r\n"
             b"    var node = q(s.targetSelector);")
    data = data.replace(f_anchor, f_new, 1)

    # ── G. runStep(): emit 'step_failed' when the target is missing ──
    g_anchor = (b"      // Missing target must degrade, never abort (spec: handle missing target).\r\n"
                b"      caption(s.fallbackMessage")
    _one(data, g_anchor, "step_failed")
    g_new = (b"      // Missing target must degrade, never abort (spec: handle missing target).\r\n"
             b"      beacon('step_failed', { step_index: T.i, step_title: s.title });\r\n"
             b"      caption(s.fallbackMessage")
    data = data.replace(g_anchor, g_new, 1)

    # ── B. boot: fetch admin config first, gate the launcher on it ──
    b_open = b"  fetch(BASE + encodeURIComponent(wanted) + '.json', { credentials: 'same-origin' })"
    _one(data, b_open, "boot-open")
    data = data.replace(
        b_open,
        b"  function _loadScenario() {\r\n" + b_open, 1)

    b_close = b"    .catch(function () { if (flow) clearFlow(); });"
    _one(data, b_close, "boot-close")
    b_close_new = (
        b"    .catch(function () { if (flow) clearFlow(); });\r\n"
        b"  }\r\n"
        b"\r\n"
        b"  // Respect the admin's enable/disable + analytics choices (AC11/AC12)\r\n"
        b"  // before mounting anything. Defaults stay ON if the config call fails.\r\n"
        b"  fetch('/api/tutorial/config', { credentials: 'same-origin' })\r\n"
        b"    .then(function (r) { return r.ok ? r.json() : null; })\r\n"
        b"    .then(function (cfg) {\r\n"
        b"      if (cfg) {\r\n"
        b"        CFG.enabled = cfg.enabled !== false;\r\n"
        b"        CFG.analytics = cfg.analytics !== false;\r\n"
        b"        CFG.disabled = {};\r\n"
        b"        (cfg.disabled || []).forEach(function (s) { CFG.disabled[s] = 1; });\r\n"
        b"      }\r\n"
        b"    })\r\n"
        b"    .catch(function () {})\r\n"
        b"    .then(function () {\r\n"
        b"      if (!CFG.enabled || CFG.disabled[wanted]) { if (flow) clearFlow(); return; }\r\n"
        b"      _loadScenario();\r\n"
        b"    });")
    data = data.replace(b_close, b_close_new, 1)

    open(PATH, "wb").write(data)
    print("[ok] wired tutorial-engine.js -> config gate + 5 analytics beacons")


if __name__ == "__main__":
    main()
