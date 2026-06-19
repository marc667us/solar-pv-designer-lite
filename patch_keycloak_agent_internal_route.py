"""Phase 3 task 15-18 pilot: install /api/agents/internal/heartbeat.

Two byte-level edits on web_app.py:

1) Widen the Phase 2 import line to bring in require_service_account
   and get_request_context (require_role stays).

2) Splice the new route just before `if __name__ == "__main__":`
   (CLAUDE.md Pattern B anchor).

Idempotent: re-running is a no-op once both edits are present.
"""
from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).parent
WEB_APP = HERE / "web_app.py"
ROUTE_SRC = HERE / "new_keycloak_agent_internal_route.py"

OLD_IMPORT = b"from app.security.decorators import require_role  # Phase 2: Keycloak parallel-run decorators\r\n"
NEW_IMPORT = (
    b"from app.security.decorators import (\r\n"
    b"    require_role,\r\n"
    b"    require_service_account,\r\n"
    b"    get_request_context,\r\n"
    b")  # Phase 2 + 3: Keycloak parallel-run decorators\r\n"
)

INSERT_ANCHOR = b'if __name__ == "__main__":'
ROUTE_MARKER = b"# Phase 3 pilot: SA-only internal route"


def main() -> int:
    data = WEB_APP.read_bytes()
    new_code = ROUTE_SRC.read_bytes()
    # Normalise the new file to CRLF — Python writers default to LF on Unix
    # but web_app.py is CRLF throughout (per CLAUDE.md).
    new_code = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    # 1) Import widening
    if NEW_IMPORT in data:
        print("[skip] import already widened")
    elif OLD_IMPORT not in data:
        print(f"[FAIL] Phase 2 import anchor missing: {OLD_IMPORT!r}")
        return 1
    else:
        data = data.replace(OLD_IMPORT, NEW_IMPORT, 1)
        print("[ok] widened decorator import")

    # 2) Route splice
    if ROUTE_MARKER in data:
        print("[skip] heartbeat route already present")
    else:
        pos = data.rfind(INSERT_ANCHOR)
        if pos < 0:
            print(f"[FAIL] insertion anchor missing: {INSERT_ANCHOR!r}")
            return 1
        data = data[:pos] + new_code + b"\r\n" + data[pos:]
        print(f"[ok] inserted heartbeat route (+{len(new_code) + 2} bytes)")

    WEB_APP.write_bytes(data)
    print(f"[done] wrote {WEB_APP} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
