"""Phase 2 task 11 of docs/SECURITY_MIGRATION_KEYCLOAK.md.

Applies two byte-level edits to web_app.py:

1) Insert `from app.security.decorators import require_role` right after the
   `import secrets_broker as _sb` line near the top imports.
2) Insert `@require_role("marketplace_admin")` between the `/admin/marketplace`
   route decorator and the existing `@admin_required`.

Per CLAUDE.md (project root): never use the Edit tool on web_app.py -- it
has CRLF line endings + mojibake. Read the file as bytes, .replace() exact
byte sequences, write back as bytes. CRLF is preserved by including \r\n in
both the source and the replacement.

Idempotent: re-running is a no-op once both edits are present.
"""
from __future__ import annotations

import sys
from pathlib import Path


WEB_APP = Path(__file__).parent / "web_app.py"

IMPORT_ANCHOR  = b"import secrets_broker as _sb  # Phase 1: audit + tier + Vault-ready secret reads\r\n"
IMPORT_INSERT  = IMPORT_ANCHOR + b"from app.security.decorators import require_role  # Phase 2: Keycloak parallel-run decorators\r\n"

ROUTE_ANCHOR   = b'@app.route("/admin/marketplace")\r\n@admin_required\r\n'
ROUTE_INSERT   = b'@app.route("/admin/marketplace")\r\n@require_role("marketplace_admin")  # Phase 2 pilot: enforced only when KEYCLOAK_ENABLED=true\r\n@admin_required\r\n'


def main() -> int:
    data = WEB_APP.read_bytes()

    # 1) Import line
    if IMPORT_INSERT in data:
        print("[skip] import already patched")
    elif IMPORT_ANCHOR not in data:
        print(f"[FAIL] import anchor not found: {IMPORT_ANCHOR!r}")
        return 1
    else:
        before = len(data)
        data = data.replace(IMPORT_ANCHOR, IMPORT_INSERT, 1)
        print(f"[ok] inserted require_role import (+{len(data) - before} bytes)")

    # 2) Pilot route decorator
    if ROUTE_INSERT in data:
        print("[skip] route already patched")
    elif ROUTE_ANCHOR not in data:
        print(f"[FAIL] route anchor not found: {ROUTE_ANCHOR!r}")
        return 1
    else:
        before = len(data)
        data = data.replace(ROUTE_ANCHOR, ROUTE_INSERT, 1)
        print(f"[ok] inserted @require_role on /admin/marketplace (+{len(data) - before} bytes)")

    WEB_APP.write_bytes(data)
    print(f"[done] wrote {WEB_APP} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
