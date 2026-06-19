"""Phase 6 task 30: splice POST /api/keycloak/events into web_app.py.

Pattern B (block insertion via file read). Idempotent.
"""
from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).parent
WEB_APP = HERE / "web_app.py"
ROUTE_SRC = HERE / "new_keycloak_events_route.py"

INSERT_ANCHOR = b'if __name__ == "__main__":'
ROUTE_MARKER = b"# Phase 6: Keycloak event webhook"


def main() -> int:
    data = WEB_APP.read_bytes()
    new_code = ROUTE_SRC.read_bytes()
    new_code = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    if ROUTE_MARKER in data:
        print("[skip] webhook already present")
        return 0
    pos = data.rfind(INSERT_ANCHOR)
    if pos < 0:
        print(f"[FAIL] anchor missing: {INSERT_ANCHOR!r}")
        return 1
    data = data[:pos] + new_code + b"\r\n" + data[pos:]
    WEB_APP.write_bytes(data)
    print(f"[ok] inserted /api/keycloak/events (+{len(new_code) + 2} bytes); total {len(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
