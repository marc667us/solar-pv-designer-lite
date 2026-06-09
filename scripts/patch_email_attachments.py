"""
Binary patch: add PDF-attachment support to web_app.py.

Why a binary patch:
  web_app.py is CRLF + Windows-1252 mojibake + UTF-8 BOM. Using the Edit tool
  introduces Unicode curly quotes that corrupt the file. So we read bytes,
  do byte-level replace, and write bytes back. Idempotent (safe to re-run).

What it does:
  1) Adds `attachments=None` to `_send_email()` and passes it through to api_manager.
  2) In project_email POST handler, renders the selected report's PDF in-memory by
     calling the existing PDF view function directly, then attaches the bytes.

Inputs:  none (path hardcoded relative to this script)
Output:  exit 0 on success; prints what was patched / skipped
"""
from pathlib import Path
import sys

WEB = Path(__file__).parent.parent / "web_app.py"
data = WEB.read_bytes()
orig_size = len(data)

# ── Patch 1: _send_email() signature + pass-through ──────────────────────────
P1_OLD = (
    b'def _send_email(to_addr, subject, html_body, text_body=None, from_addr=None, resend_key=None):\r\n'
    b'    """Delegate to api_manager (single source). Resend -> SMTP fallback."""\r\n'
    b'    return _api.email.send(to_addr, subject, html_body,\r\n'
    b'                           text_body=text_body, from_addr=from_addr,\r\n'
    b'                           resend_key_override=resend_key)\r\n'
)
P1_NEW = (
    b'def _send_email(to_addr, subject, html_body, text_body=None, from_addr=None, resend_key=None, attachments=None):\r\n'
    b'    """Delegate to api_manager (single source). Resend -> SMTP fallback. attachments: optional [(filename, bytes, mime), ...]."""\r\n'
    b'    return _api.email.send(to_addr, subject, html_body,\r\n'
    b'                           text_body=text_body, from_addr=from_addr,\r\n'
    b'                           resend_key_override=resend_key, attachments=attachments)\r\n'
)

if P1_OLD in data:
    data = data.replace(P1_OLD, P1_NEW, 1)
    print("[patch 1] _send_email signature updated")
elif P1_NEW in data:
    print("[patch 1] already applied — skipping")
else:
    print("[patch 1] ERROR: anchor not found in web_app.py — aborting before any write")
    sys.exit(2)

# ── Patch 2: project_email POST — render PDF + attach ────────────────────────
# Anchor: the _phtml block + the existing _send_email call. We insert the
# attachment-rendering logic between them and add attachments= to the call.
P2_OLD = (
    b'        _phtml = (\r\n'
    b'            "<div style=\'font-family:sans-serif;padding:24px\'>"\r\n'
    b'            "<p>" + _ptxt + "</p>"\r\n'
    b'            "<hr><p style=\'color:#888;font-size:12px\'>SolarPro Global</p></div>"\r\n'
    b'        )\r\n'
    b'        _ok, _err = _send_email(\r\n'
    b'            recipients, subject, _phtml, text_body=_ptxt,\r\n'
    b'            from_addr=eff_from, resend_key=eff_resend or None,\r\n'
    b'        )\r\n'
)
P2_NEW = (
    b'        _phtml = (\r\n'
    b'            "<div style=\'font-family:sans-serif;padding:24px\'>"\r\n'
    b'            "<p>" + _ptxt + "</p>"\r\n'
    b'            "<hr><p style=\'color:#888;font-size:12px\'>SolarPro Global</p></div>"\r\n'
    b'        )\r\n'
    b'        # Render the selected report to PDF bytes and attach it.\r\n'
    b'        # Why: prior code only sent the message body and the placeholder said\r\n'
    b'        # "...attached" but nothing was. We dispatch to the existing PDF view\r\n'
    b'        # function (registered as a Flask endpoint) and capture its bytes.\r\n'
    b'        _attachments = None\r\n'
    b'        _report_label = (request.form.get("report") or "").strip()\r\n'
    b'        _endpoint_map = {\r\n'
    b'            "Full Proposal (All Reports)": "export_pdf_proposal",\r\n'
    b'            "PV System Design Report":     "export_pdf_pv",\r\n'
    b'            "BOQ Report":                  "export_pdf_boq",\r\n'
    b'            "Economic Analysis":           "export_pdf_economic",\r\n'
    b'            "Energy Impact":               "export_pdf_energy",\r\n'
    b'            "AC Cable Schedule":           "export_pdf_cable",\r\n'
    b'            "Installation Plan":           "export_pdf_installation",\r\n'
    b'            "Installation Work Plan":      "export_pdf_workplan",\r\n'
    b'            "Staffing Plan":               "export_pdf_staffing",\r\n'
    b'            "Procurement Plan":            "export_pdf_procurement",\r\n'
    b'            "Site Assessment":             "export_pdf_inspection",\r\n'
    b'        }\r\n'
    b'        _ep_name = _endpoint_map.get(_report_label)\r\n'
    b'        if _ep_name:\r\n'
    b'            _vf = app.view_functions.get(_ep_name)\r\n'
    b'            if _vf:\r\n'
    b'                try:\r\n'
    b'                    _resp = _vf(pid)\r\n'
    b'                    _pdf_bytes = _resp.get_data() if hasattr(_resp, "get_data") else None\r\n'
    b'                    if _pdf_bytes and _pdf_bytes[:4] == b"%PDF":\r\n'
    b'                        _fname = getattr(_resp, "download_name", None) or (_report_label.replace(" ", "_") + ".pdf")\r\n'
    b'                        _attachments = [(_fname, _pdf_bytes, "application/pdf")]\r\n'
    b'                except Exception as _pdf_exc:\r\n'
    b'                    logger.warning("PDF attachment render failed for %s: %s", _report_label, _pdf_exc)\r\n'
    b'        _ok, _err = _send_email(\r\n'
    b'            recipients, subject, _phtml, text_body=_ptxt,\r\n'
    b'            from_addr=eff_from, resend_key=eff_resend or None,\r\n'
    b'            attachments=_attachments,\r\n'
    b'        )\r\n'
)

if P2_OLD in data:
    data = data.replace(P2_OLD, P2_NEW, 1)
    print("[patch 2] project_email PDF-attach block inserted")
elif P2_NEW in data:
    print("[patch 2] already applied — skipping")
else:
    print("[patch 2] ERROR: anchor not found in web_app.py — aborting before any write")
    sys.exit(3)

# Sanity: bytes only grew, no CRLF→LF conversion happened
crlf = data.count(b'\r\n')
lf   = data.count(b'\n') - crlf
if lf != 0:
    print(f"[abort] bare LFs present after patch: {lf}")
    sys.exit(4)

# Backup + write
bak = WEB.with_suffix(WEB.suffix + ".bak_pdfattach")
if not bak.exists():
    bak.write_bytes(WEB.read_bytes())
    print(f"[backup] {bak.name} written ({orig_size} bytes)")
WEB.write_bytes(data)
print(f"[write]  web_app.py: {orig_size} -> {len(data)} bytes (CRLF preserved)")
