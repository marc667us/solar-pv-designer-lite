#!/usr/bin/env python
"""Delete orphan code retired by earlier BOQ refactors.

Zero callers confirmed via grep in web_app.py for all three symbols:
  * _template_services()             -- L27329, stub returning []
  * _inject_service_bills()          -- L27332, stub returning input
  * _boq_template_lines_with_overrides()  -- L32987, unused after
                                            Build-by-Template retirement

Also cleans the source of truth `new_boq_services_engine.py` for
_template_services + _inject_service_bills (that file is currently NOT
spliced into web_app.py either, but leaving stale stubs in the source
is a defect trap for the next refactor).

Removes the accompanying "5b. Legacy stubs" comment block in both
files -- it's a tombstone that no longer describes anything.

Idempotent: skips if the target functions are already absent.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB  = ROOT / "web_app.py"
SVCE = ROOT / "new_boq_services_engine.py"

# ---------------------------------------------------------------------
# Block 1: stubs + their comment header in web_app.py
# ---------------------------------------------------------------------
web = WEB.read_bytes()
orig_web_len = len(web)

stubs_web = (
    b'# ---------------------------------------------------------------------------\r\n'
    b'# 5b. Legacy stubs (kept ONLY until Task #7 retires the template picker).\r\n'
    b'#     These functions used to score templates against chosen services and\r\n'
    b'#     inject placeholder bills for any uncovered service. The new engine\r\n'
    b'#     drives sections directly from services + the skeleton above, so these\r\n'
    b'#     stubs return inputs unchanged and will be deleted together with the\r\n'
    b'#     template picker code in the same commit.\r\n'
    b'# ---------------------------------------------------------------------------\r\n'
    b'\r\n'
    b'def _template_services(template: dict) -> list:\r\n'
    b'    return []\r\n'
    b'\r\n'
    b'def _inject_service_bills(template: dict, chosen_services: list) -> dict:\r\n'
    b'    return template\r\n'
    b'\r\n'
    b'\r\n'
)

if stubs_web in web:
    web = web.replace(stubs_web, b'', 1)
    print(f"[ok] removed _template_services + _inject_service_bills stubs in web_app.py ({len(stubs_web)} bytes)")
else:
    if b'def _template_services(template: dict) -> list:\r\n    return []' in web:
        print("[warn] stubs present but comment header differs -- inspect manually")
    else:
        print("[skip] stubs already absent in web_app.py")

# ---------------------------------------------------------------------
# Block 2: _boq_template_lines_with_overrides in web_app.py
# ---------------------------------------------------------------------
tpl_overrides = (
    b'def _boq_template_lines_with_overrides(uid: int, template: dict):\r\n'
    b'    """Yield template lines overlaid with the user\'s recorded overrides.\r\n'
    b'    Wraps _boq_template_iter_lines from new_boq_project_templates so the\r\n'
    b'    static templates `learn` from prior projects.\r\n'
    b'\r\n'
    b'    Yields the same 11-tuple shape:\r\n'
    b'      (bill_no, bill_name, sect_letter, sect_title, subsec, idx,\r\n'
    b'       desc, unit, qty, basic, spec)\r\n'
    b'    where unit / qty / basic come from the override when present.\r\n'
    b'    """\r\n'
    b'    from new_boq_project_templates import _boq_template_iter_lines\r\n'
    b'    ov = _boq_lookup_overrides_for_user(uid)\r\n'
    b'    for (bill_no, bill_name, sect_letter, sect_title, subsec, idx,\r\n'
    b'         desc, unit, qty, basic, spec) in _boq_template_iter_lines(template):\r\n'
    b'        key = _boq_desc_key(desc)\r\n'
    b'        if key in ov:\r\n'
    b'            ov_unit, ov_basic, _ov_sp, _ov_ip, ov_qty = ov[key]\r\n'
    b'            unit = ov_unit or unit\r\n'
    b'            if ov_basic > 0:\r\n'
    b'                basic = ov_basic\r\n'
    b'            if ov_qty > 0:\r\n'
    b'                qty = ov_qty\r\n'
    b'        yield (bill_no, bill_name, sect_letter, sect_title, subsec, idx,\r\n'
    b'               desc, unit, qty, basic, spec)\r\n'
    b'\r\n'
    b'\r\n'
)
if tpl_overrides in web:
    web = web.replace(tpl_overrides, b'', 1)
    print(f"[ok] removed _boq_template_lines_with_overrides in web_app.py ({len(tpl_overrides)} bytes)")
else:
    print("[skip] _boq_template_lines_with_overrides already absent in web_app.py")

if len(web) != orig_web_len:
    backup = WEB.with_suffix(".py.bak-orphan-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(web)
    print(f"[write] web_app.py updated ({orig_web_len} -> {len(web)} bytes)")

# ---------------------------------------------------------------------
# Block 3: same stubs + comment in new_boq_services_engine.py
# ---------------------------------------------------------------------
svc = SVCE.read_bytes()
orig_svc_len = len(svc)

# Both LF and CRLF variants may exist in this source file.
for line_sep in (b'\n', b'\r\n'):
    stubs_svc = (
        b'# ---------------------------------------------------------------------------' + line_sep +
        b'# 5b. Legacy stubs (kept ONLY until Task #7 retires the template picker).' + line_sep +
        b'#     These functions used to score templates against chosen services and' + line_sep +
        b'#     inject placeholder bills for any uncovered service. The new engine' + line_sep +
        b'#     drives sections directly from services + the skeleton above, so these' + line_sep +
        b'#     stubs return inputs unchanged and will be deleted together with the' + line_sep +
        b'#     template picker code in the same commit.' + line_sep +
        b'# ---------------------------------------------------------------------------' + line_sep +
        line_sep +
        b'def _template_services(template: dict) -> list:' + line_sep +
        b'    return []' + line_sep +
        line_sep +
        b'def _inject_service_bills(template: dict, chosen_services: list) -> dict:' + line_sep +
        b'    return template' + line_sep +
        line_sep +
        line_sep
    )
    if stubs_svc in svc:
        svc = svc.replace(stubs_svc, b'', 1)
        print(f"[ok] removed stubs from new_boq_services_engine.py ({line_sep!r} lines, {len(stubs_svc)} bytes)")
        break
else:
    print("[skip] stubs already absent in new_boq_services_engine.py")

if len(svc) != orig_svc_len:
    backup = SVCE.with_suffix(".py.bak-orphan-2026-07-01")
    if not backup.exists():
        backup.write_bytes(SVCE.read_bytes())
        print(f"[backup] {backup.name}")
    SVCE.write_bytes(svc)
    print(f"[write] new_boq_services_engine.py updated ({orig_svc_len} -> {len(svc)} bytes)")

print("[done]")
