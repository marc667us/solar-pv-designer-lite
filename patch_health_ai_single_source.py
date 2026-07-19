"""Make /api/health/ai read the SAME source the AI chain reads.

WHY (2026-07-19)
----------------
The route hand-rolled its own provider check from os.environ, and it drifted from the code:

    "github_models": "configured" if os.environ.get("GITHUB_MODELS_TOKEN") else ...

api_manager reads **GITHUB_TOKEN**. The health endpoint read **GITHUB_MODELS_TOKEN** -- a
variable nothing sets and nothing else mentions. So the provider would have reported
"not_configured" forever, even once correctly configured, and the endpoint everyone uses to
diagnose this feature would have reported the opposite of the truth.

It also read os.environ directly, so it bypassed the secrets broker that actually serves these
keys -- a provider served from Vault would read as absent.

Both are the same defect: a SECOND, independent notion of "is this provider set up". This
patch deletes it and has the route ask `api.status()`, which is what the chain itself uses.

It also surfaces the derived `health` field (not_configured|untried|failing|degraded|working),
so the endpoint can finally distinguish "has a key" from "actually answers" -- the conflation
that let a 100%-failing provider look healthy for months.

BACKWARD COMPATIBLE: `services` keeps its exact {name: "configured"|"not_configured"} shape,
because beta-monitor and the smoke tests parse it. `health` is added alongside.

web_app.py is CRLF + mojibake, so this is a byte-level splice, never an Edit. Idempotent:
re-running it detects the marker and does nothing.
"""
SRC = "web_app.py"

OLD = (
    b'    services = {\r\n'
    b'        "anthropic":   "configured" if os.environ.get("ANTHROPIC_API_KEY") else "not_configured",\r\n'
    b'        "openrouter":  "configured" if os.environ.get("OPENROUTER_API_KEY") else "not_configured",\r\n'
    b'        "ollama":      "configured" if os.environ.get("OLLAMA_URL") else "not_configured",\r\n'
    b'        "github_models": "configured" if os.environ.get("GITHUB_MODELS_TOKEN") else "not_configured",\r\n'
    b'    }\r\n'
    b'    any_ok = any(v == "configured" for v in services.values())\r\n'
    b'    return jsonify({\r\n'
    b'        "status": "ok" if any_ok else "degraded",\r\n'
    b'        "services": services,\r\n'
    b'        "timestamp": datetime.utcnow().isoformat() + "Z",\r\n'
    b'    }), 200\r\n'
)

NEW = (
    b'    # SINGLE SOURCE OF TRUTH: ask the AI client itself.\r\n'
    b'    # This used to hand-roll its own os.environ check and it had DRIFTED -- it tested\r\n'
    b'    # GITHUB_MODELS_TOKEN while api_manager reads GITHUB_TOKEN, so github_models would\r\n'
    b'    # have reported "not_configured" forever no matter how correctly it was set up. It\r\n'
    b'    # also read os.environ directly, bypassing the secrets broker that serves these keys.\r\n'
    b'    # Any second opinion about "is this provider configured" eventually disagrees with\r\n'
    b'    # the first; the fix is to not have one.\r\n'
    b'    try:\r\n'
    b'        from api_manager import api as _api\r\n'
    b'        _provs = _api.status().get("providers", {})\r\n'
    b'    except Exception:\r\n'
    b'        _provs = {}\r\n'
    b'    _names = ("anthropic", "openrouter", "ollama", "github_models")\r\n'
    b'    # `claude` is this app\'s name for the anthropic provider in status().\r\n'
    b'    _alias = {"anthropic": "claude"}\r\n'
    b'    services, health = {}, {}\r\n'
    b'    for _n in _names:\r\n'
    b'        _p = _provs.get(_alias.get(_n, _n), {})\r\n'
    b'        services[_n] = "configured" if _p.get("configured") else "not_configured"\r\n'
    b'        # not_configured | untried | failing | degraded | working -- derived from the\r\n'
    b'        # last 24h of recorded calls, so it costs no upstream request to read.\r\n'
    b'        health[_n] = _p.get("health", "unknown")\r\n'
    b'    any_ok = any(v == "configured" for v in services.values())\r\n'
    b'    # A provider that is configured but has ONLY ever errored is not healthy, and saying\r\n'
    b'    # "ok" because a key exists is what hid the github_models outage.\r\n'
    b'    _live = any(h in ("working", "degraded", "untried") for h in health.values())\r\n'
    b'    return jsonify({\r\n'
    b'        "status": "ok" if (any_ok and _live) else "degraded",\r\n'
    b'        "services": services,\r\n'
    b'        "health": health,\r\n'
    b'        "timestamp": datetime.utcnow().isoformat() + "Z",\r\n'
    b'    }), 200\r\n'
)

MARKER = b"SINGLE SOURCE OF TRUTH: ask the AI client itself."


def main():
    data = open(SRC, "rb").read()
    if MARKER in data:
        print("already patched -- nothing to do")
        return 0
    if data.count(OLD) != 1:
        print(f"REFUSING: expected exactly 1 match, found {data.count(OLD)}")
        return 1
    open(SRC, "wb").write(data.replace(OLD, NEW))
    print("patched /api/health/ai to read api.status()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
