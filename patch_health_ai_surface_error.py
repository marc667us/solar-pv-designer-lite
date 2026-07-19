"""Stop /api/health/ai from silently reporting a broken status() as "not_configured".

Codex LOW (2026-07-19): the broad `except Exception` around `api.status()` converts a broker
or store regression into "every provider not_configured" -- which reads to ops and to
beta-monitor as a configuration problem rather than the health check itself being broken.

That is the exact failure class this whole session has been unpicking: a fault rendered as a
benign-looking state, so nobody investigates. Log it, and say so in the payload.

`services` is untouched, so the documented shape survives.
"""
SRC = "web_app.py"

OLD = (
    b'    try:\r\n'
    b'        from api_manager import api as _api\r\n'
    b'        _provs = _api.status().get("providers", {})\r\n'
    b'    except Exception:\r\n'
    b'        _provs = {}\r\n'
)

NEW = (
    b'    _health_error = ""\r\n'
    b'    try:\r\n'
    b'        from api_manager import api as _api\r\n'
    b'        _provs = _api.status().get("providers", {})\r\n'
    b'    except Exception as _e:\r\n'
    b'        # Do NOT let this look like "nothing is configured". A failure to READ the\r\n'
    b'        # provider state is a different fault from the providers being absent, and\r\n'
    b'        # reporting the second when the first happened sends ops to fix the wrong thing.\r\n'
    # app.logger, NOT logger: web_app.py has no module-level `logger` (it uses app.logger in
    # 112 places). A bare `logger` here raises NameError INSIDE the except handler and turns a
    # handled failure into a 500 -- the health check becoming the outage. Caught by
    # test_endpoint_survives_the_ai_client_blowing_up, which is why that test exists.
    b'        app.logger.warning("health/ai: api.status() failed: %s", _e)\r\n'
    b'        _provs = {}\r\n'
    b'        _health_error = "api_status_unavailable"\r\n'
)

OLD2 = (
    b'        "services": services,\r\n'
    b'        "health": health,\r\n'
    b'        "timestamp": datetime.utcnow().isoformat() + "Z",\r\n'
)

NEW2 = (
    b'        "services": services,\r\n'
    b'        "health": health,\r\n'
    b'        **({"health_error": _health_error} if _health_error else {}),\r\n'
    b'        "timestamp": datetime.utcnow().isoformat() + "Z",\r\n'
)

MARKER = b"api_status_unavailable"


def main():
    data = open(SRC, "rb").read()
    if MARKER in data:
        print("already patched -- nothing to do")
        return 0
    for name, old in (("status-try", OLD), ("payload", OLD2)):
        if data.count(old) != 1:
            print(f"REFUSING: {name} expected 1 match, found {data.count(old)}")
            return 1
    data = data.replace(OLD, NEW).replace(OLD2, NEW2)
    open(SRC, "wb").write(data)
    print("patched: health/ai now surfaces api_status_unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
