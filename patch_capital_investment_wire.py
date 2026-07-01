# -*- coding: utf-8 -*-
"""
patch_capital_investment_wire.py
================================
Byte-level splice that wires new_capital_investment_routes into
web_app.py. Follows the repo's CRLF-safe convention (see CLAUDE.md
Pattern B). Idempotent - safe to re-run.

Splices two lines into web_app.py:

    1. after the last '_obs_scrape_endpoint,' observability import line:
           from new_capital_investment_routes import register_capital_investment

    2. after 'return {"today_iso": ...}' context processor:
           register_capital_investment(app, get_db=get_db,
                                       login_required=login_required,
                                       csrf_protect=csrf_protect,
                                       current_user=current_user)

Run once:  python patch_capital_investment_wire.py
"""

import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(REPO, "web_app.py")


def main() -> int:
    if not os.path.exists(TARGET):
        print(f"[FAIL] {TARGET} not found", file=sys.stderr)
        return 2

    data = open(TARGET, "rb").read()
    changed = False

    # ---- Splice 1: the import line ---------------------------------
    IMPORT_LINE = (
        b"from new_capital_investment_routes import "
        b"register_capital_investment  # PV Capital Investment Design module\r\n"
    )
    if IMPORT_LINE.strip() in data:
        print("[SKIP] import already present")
    else:
        # Anchor: the last observability import line ends with
        # '_obs_scrape_endpoint,' followed by ')  # SOC 2 M3.4: ...'.
        ANCHOR1 = (
            b")  # SOC 2 M3.4: Prometheus /metrics + per-request latency"
            b" + status counters"
        )
        pos = data.find(ANCHOR1)
        if pos < 0:
            print(f"[FAIL] anchor for import splice not found", file=sys.stderr)
            return 3
        # Insert AFTER the anchor line's newline
        end_of_line = data.find(b"\n", pos)
        if end_of_line < 0:
            print("[FAIL] EOL for import anchor not found", file=sys.stderr)
            return 3
        insertion = end_of_line + 1
        data = data[:insertion] + IMPORT_LINE + data[insertion:]
        print(f"[OK] import spliced at byte {insertion}")
        changed = True

    # ---- Splice 2: the register call --------------------------------
    REGISTER_BLOCK = (
        b"\r\n"
        b"# --- PV Capital Investment Design module ---------------------------\r\n"
        b"# Wires /large-scale-solar/* routes (landing + Step 1 + project view)\r\n"
        b"# on top of the existing helpers just defined above. Safe to leave in\r\n"
        b"# place - the register function is idempotent w.r.t. the route table\r\n"
        b"# (Flask raises AssertionError if the same endpoint is added twice, so\r\n"
        b"# any accidental double-import fails loudly rather than silently).\r\n"
        b"register_capital_investment(\r\n"
        b"    app,\r\n"
        b"    get_db=get_db,\r\n"
        b"    login_required=login_required,\r\n"
        b"    csrf_protect=csrf_protect,\r\n"
        b"    current_user=current_user,\r\n"
        b")\r\n"
    )
    MARKER = b"register_capital_investment("
    if MARKER in data:
        print("[SKIP] register_capital_investment(...) already present")
    else:
        # Anchor: the inject_today_iso context processor's body.
        ANCHOR2 = b'return {"today_iso": datetime.utcnow().strftime("%Y-%m-%d")}'
        pos = data.find(ANCHOR2)
        if pos < 0:
            print("[FAIL] anchor for register splice not found", file=sys.stderr)
            return 4
        end_of_line = data.find(b"\n", pos)
        if end_of_line < 0:
            print("[FAIL] EOL for register anchor not found", file=sys.stderr)
            return 4
        insertion = end_of_line + 1
        data = data[:insertion] + REGISTER_BLOCK + data[insertion:]
        print(f"[OK] register block spliced at byte {insertion}")
        changed = True

    if changed:
        open(TARGET, "wb").write(data)
        print(f"[DONE] web_app.py rewritten ({len(data):,} bytes)")
    else:
        print("[NOOP] no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
