"""Wire country_compliance into _boq_compliance_check + the two BOM/BOQ
view callers. Adds geo-sensitive equipment + installation findings to
the existing Compliance Review panel.

Idempotent via SENTINEL.
"""
from __future__ import annotations
from pathlib import Path
import re, sys

TARGET = Path(__file__).parent / "web_app.py"
SENTINEL = b"# country-compliance-wired-2026-06-27"

# 1) Top-of-file import (after the existing top imports)
IMPORT_NEEDLE = b"from api_manager import api as _api\r\n"
IMPORT_INSERT = (
    IMPORT_NEEDLE
    + b"# " + SENTINEL + b"\r\n"
    + b"try:\r\n"
    + b"    import country_compliance as _country_compliance  # noqa: F401\r\n"
    + b"except Exception:\r\n"
    + b"    _country_compliance = None  # graceful fallback\r\n"
)

# 2) Patch _boq_compliance_check signature + emit country findings.
OLD_SIG = b"def _boq_compliance_check(items, lines):\r\n"
NEW_SIG = b"def _boq_compliance_check(items, lines, project_country=None):\r\n"

# Insert the country-findings block at the very end of the function,
# right before the severity_rank line.
SEVERITY_NEEDLE = b"    severity_rank = {\"high\": 0, \"medium\": 1, \"low\": 2}"
COUNTRY_BLOCK = (
    b"    # " + SENTINEL + b"\r\n"
    b"    if project_country and _country_compliance is not None:\r\n"
    b"        try:\r\n"
    b"            for f in _country_compliance.compliance_findings_for_lines(\r\n"
    b"                    items, lines, project_country):\r\n"
    b"                findings.append({\r\n"
    b"                    \"severity\": f[\"severity\"],\r\n"
    b"                    \"line_no\":  f[\"line_no\"],\r\n"
    b"                    \"message\":  f[\"message\"],\r\n"
    b"                })\r\n"
    b"        except Exception:\r\n"
    b"            pass\r\n"
    + SEVERITY_NEEDLE
)

# 3) Patch the two call sites to pass project_country.
# Both look like: compliance_findings = _boq_compliance_check(items, totals.get("lines", []))
# We'll insert a small helper line above each that resolves the country
# from session/user/query-param + then change the call.
OLD_CALL = b"compliance_findings = _boq_compliance_check(items, totals.get(\"lines\", []))"
NEW_CALL = (
    b"_pc = (request.args.get(\"country\") or \"\").strip()\r\n"
    b"    if not _pc:\r\n"
    b"        try:\r\n"
    b"            _u = current_user()\r\n"
    b"            _pc = (_u[\"country\"] if _u and \"country\" in _u.keys() else \"\") or \"\"\r\n"
    b"        except Exception:\r\n"
    b"            _pc = \"\"\r\n"
    b"    compliance_findings = _boq_compliance_check(items, totals.get(\"lines\", []),\r\n"
    b"                                                 project_country=_pc or None)"
)

# LF variants in case any segment is LF-only
OLD_CALL_LF = OLD_CALL.replace(b"\r\n", b"\n")
NEW_CALL_LF = NEW_CALL.replace(b"\r\n", b"\n")


def main() -> int:
    src = TARGET.read_bytes()
    if SENTINEL in src:
        print("[skip] country compliance already wired")
        return 0
    n = 0
    # 1) import
    if IMPORT_NEEDLE not in src:
        print("[fail] import anchor 'from api_manager import api' not found")
        return 2
    src = src.replace(IMPORT_NEEDLE, IMPORT_INSERT, 1)
    n += 1
    print("[ok] added country_compliance import")
    # 2) signature
    if OLD_SIG not in src:
        print("[fail] _boq_compliance_check signature anchor not found")
        return 2
    src = src.replace(OLD_SIG, NEW_SIG, 1)
    n += 1
    print("[ok] _boq_compliance_check signature: added project_country param")
    # 3) country block before severity_rank
    if SEVERITY_NEEDLE not in src:
        print("[fail] severity_rank anchor not found inside _boq_compliance_check")
        return 2
    src = src.replace(SEVERITY_NEEDLE, COUNTRY_BLOCK, 1)
    n += 1
    print("[ok] inserted country-findings block before severity_rank")
    # 4) replace BOTH call sites
    call_n = src.count(OLD_CALL) + src.count(OLD_CALL_LF)
    if call_n == 0:
        print("[fail] call site anchor not found")
        return 2
    src = src.replace(OLD_CALL, NEW_CALL)
    src = src.replace(OLD_CALL_LF, NEW_CALL_LF)
    print(f"[ok] rewrote {call_n} call site(s) to pass project_country")
    n += 1
    TARGET.write_bytes(src)
    print(f"=== {n} edits committed to web_app.py ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
