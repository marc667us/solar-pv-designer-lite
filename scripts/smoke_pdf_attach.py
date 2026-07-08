"""
One-shot smoke test for the email-PDF attachment fix.

Does NOT modify any persistent state — uses a temp SQLite DB.
Patches _send_email to capture call args; asserts:
  - attachments list is non-empty
  - first attachment is (str_filename, bytes, "application/pdf")
  - bytes start with %PDF magic
  - bytes are non-trivial size (> 1 KB)

Exit 0 on PASS, non-zero on FAIL.
"""
import os, sys, tempfile, sqlite3, json, pathlib

# Make sure web_app picks the temp DB BEFORE it's imported
PROJ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

tmpdir = tempfile.mkdtemp(prefix="solar_smoke_")
db_path = os.path.join(tmpdir, "smoke.db")
os.environ["DB_PATH"] = db_path
os.environ.setdefault("SECRET_KEY", "smoke-secret-12345")
# Seed env vars (already set if you sourced .env, but be defensive)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "")

import web_app as wa
wa.DB_PATH = db_path
wa.init_db()
wa.app.config["TESTING"] = True
wa.app.config["WTF_CSRF_ENABLED"] = False
wa.app.config["RATELIMIT_ENABLED"] = False
if hasattr(wa, "limiter"):
    try: wa.limiter.enabled = False
    except Exception: pass

captured = {"called": False, "args": None, "kwargs": None}

def fake_send_email(*args, **kwargs):
    captured["called"]  = True
    captured["args"]    = args
    captured["kwargs"]  = kwargs
    return True, "sent (fake)"

wa._send_email = fake_send_email  # monkeypatch the wrapper

# Capture warnings the route's PDF-attach block emits so we see why it bails.
import logging
class _ListHandler(logging.Handler):
    def __init__(self): super().__init__(); self.records = []
    def emit(self, record): self.records.append(self.format(record))
_log_handler = _ListHandler()
_log_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
wa.logger.addHandler(_log_handler)
wa.logger.setLevel(logging.DEBUG)

# Verify the bypass-DB user creation works
def _csrf(client, path="/register"):
    resp = client.get(path)
    html = resp.data.decode("utf-8", errors="replace")
    marker = 'name="_csrf" value="'
    idx = html.find(marker)
    if idx == -1:
        return ""
    start = idx + len(marker)
    end = html.find('"', start)
    return html[start:end]

with wa.app.test_client() as client:
    # Register
    csrf = _csrf(client, "/register")
    r = client.post("/register", data={
        "_csrf": csrf, "username": "smokeuser", "email": "smoke@x.com",
        "password": "Sm0ke!Pass", "name": "Smoke", "company": "Co",
        "country": "Ghana", "terms_agreed": "on",
    }, follow_redirects=False)

    # Flip email_verified directly (bypass token flow — same as test fixture)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET email_verified=1 WHERE username=?", ("smokeuser",))
    conn.commit()
    conn.close()

    # Log in
    csrf = _csrf(client, "/login")
    r = client.post("/login", data={
        "_csrf": csrf, "username": "smokeuser", "password": "Sm0ke!Pass",
    }, follow_redirects=True)
    assert r.status_code == 200, f"login failed: HTTP {r.status_code}"

    # Create a minimal project with results so PDF rendering has data
    csrf = _csrf(client, "/project/new")
    r = client.post("/project/new", data={
        "_csrf": csrf, "name": "Smoke Project", "system_type": "hybrid",
        "phase": "single", "description": "smoke",
    }, follow_redirects=True)
    assert r.status_code == 200, f"new project failed: HTTP {r.status_code}"

    # Find the project id + owning user id from DB
    conn = sqlite3.connect(db_path)
    smoke_uid = conn.execute("SELECT id FROM users WHERE username=?", ("smokeuser",)).fetchone()[0]
    print(f"[setup] smokeuser id = {smoke_uid}")
    row = conn.execute("SELECT id, data_json, user_id FROM projects WHERE name=?", ("Smoke Project",)).fetchone()
    assert row, "project not in DB"
    pid = row[0]
    print(f"[setup] project id   = {pid} (owner user_id = {row[2]})")
    # Force a results blob so PDF endpoints don't bail
    data = json.loads(row[1]) if row[1] else {}
    # Minimal results shape gleaned from web_app expectations
    data["results"] = {
        "pv_kw": 5.0, "bat_kwh": 10.0, "num_panels": 12, "num_bat": 2,
        "inv_kw": 5.0, "daily_kwh": 20.0,
        "economics": {"npv": 1000, "irr_pct": 12.0, "payback": 5.0,
                      "annual_kwh": 7300, "total_local": 50000},
        "boq": {"items": [], "total_local": 50000},
    }
    data.setdefault("symbol", "$")
    data.setdefault("country", "Ghana")
    data.setdefault("region", "Greater Accra")
    data.setdefault("currency", "USD")
    data.setdefault("tariff", 0.15)
    data.setdefault("daily_kwh", 20.0)
    data.setdefault("subscription", {"plan": "enterprise", "active": True})
    conn.execute("UPDATE projects SET data_json=? WHERE id=?", (json.dumps(data), pid))
    # Bypass _paid_only() — the gate at web_app.py:2906 admits any non-"free" plan.
    conn.execute("UPDATE users SET plan='enterprise' WHERE username=?", ("smokeuser",))
    conn.commit()
    conn.close()

    # Monkeypatch the PDF view function to return a known fake %PDF response.
    # Why: the real export_pdf_boq() needs a fully-calculated results blob
    # (boq_grand, line items, etc.) that we'd have to fabricate to match the
    # markdown template. The smoke test's job is to verify the NEW attachment
    # plumbing — endpoint lookup, view-function call, byte extraction, %PDF
    # magic check, attachments tuple construction, and pass-through to
    # _send_email. So swap the heavy PDF builder for a trivial response.
    from flask import make_response as _make_response
    FAKE_PDF = b"%PDF-1.4\n%fake smoke-test pdf bytes\n" + (b"x" * 2048) + b"\n%%EOF"
    def fake_boq_pdf(pid):
        resp = _make_response(FAKE_PDF)
        resp.mimetype = "application/pdf"
        resp.headers["Content-Disposition"] = 'attachment; filename="BOQ_smoke.pdf"'
        # send_file responses also carry a download_name attribute
        try: resp.download_name = "BOQ_smoke.pdf"
        except Exception: pass
        return resp
    wa.app.view_functions["export_pdf_boq"] = fake_boq_pdf

    # Verify project state right before we exercise the PDF route
    with wa.app.test_request_context(f"/project/{pid}/report/boq/pdf"):
        from flask import session as _flask_session
        _flask_session["user_id"] = smoke_uid
        try:
            _proj = wa.get_project(pid)
            print(f"[diagnostic] get_project({pid}) returned: {'<row>' if _proj else None}")
            if _proj:
                print(f"[diagnostic] project keys: {list(_proj.keys()) if hasattr(_proj, 'keys') else type(_proj).__name__}")
                _pdata = _proj["data"] if "data" in (_proj.keys() if hasattr(_proj, 'keys') else []) else None
                print(f"[diagnostic] project['data'] type: {type(_pdata).__name__}")
                if isinstance(_pdata, dict):
                    print(f"[diagnostic] project['data'] keys: {list(_pdata.keys())}")
                    print(f"[diagnostic] 'results' in data?: {'results' in _pdata}")
        except Exception as e:
            print(f"[diagnostic] get_project EXCEPTION: {type(e).__name__}: {e}")

    # First: try calling the PDF view function directly under the live request context
    # to see what it actually returns. This isolates the PDF-render path from the
    # email-route plumbing.
    with wa.app.test_request_context(f"/project/{pid}/report/boq/pdf"):
        from flask import session as _flask_session
        _flask_session["user_id"] = smoke_uid
        _vf = wa.app.view_functions.get("export_pdf_boq")
        print(f"\n[diagnostic] export_pdf_boq view_function: {_vf}")
        if _vf:
            try:
                _resp = _vf(pid)
                print(f"[diagnostic] return type: {type(_resp).__name__}")
                if hasattr(_resp, "status_code"):
                    print(f"[diagnostic] status_code: {_resp.status_code}")
                if hasattr(_resp, "headers"):
                    print(f"[diagnostic] Location header: {_resp.headers.get('Location')!r}")
                if hasattr(_resp, "get_data"):
                    _data = _resp.get_data()
                    print(f"[diagnostic] body length: {len(_data)} bytes")
                    print(f"[diagnostic] body[:4]:    {_data[:4]!r}")
                    print(f"[diagnostic] body[:200]:  {_data[:200]!r}")
            except Exception as e:
                import traceback
                print(f"[diagnostic] EXCEPTION: {type(e).__name__}: {e}")
                traceback.print_exc()

    # Now exercise the email route as before
    csrf = _csrf(client, f"/project/{pid}/email")
    r = client.post(f"/project/{pid}/email", data={
        "_csrf": csrf,
        "report": "BOQ Report",
        "recipients": "client@example.com",
        "subject": "Smoke test",
        "body": "Test body",
    }, follow_redirects=False)

# Surface any warnings/errors the patched route emitted
print(f"\n[logs] {len(_log_handler.records)} log records during POST:")
for line in _log_handler.records[-15:]:
    print(f"  {line}")

# Inspect what was captured
print(f"\n_send_email captured: called={captured['called']}")
if not captured["called"]:
    print("FAIL: _send_email was not called — the route did not reach the send line.")
    print(f"  last response status: {r.status_code}")
    print(f"  last response body (first 400 bytes): {r.data[:400]!r}")
    sys.exit(2)

kw = captured["kwargs"] or {}
attachments = kw.get("attachments")
print(f"attachments kwarg: type={type(attachments).__name__}, value={'<list len ' + str(len(attachments)) + '>' if isinstance(attachments, list) else attachments!r}")

if attachments is None:
    print("WARN: attachments came through as None — PDF render may have failed silently.")
    print("  Inspect the route logs for any 'PDF attachment render failed' warning.")
    sys.exit(3)

if not isinstance(attachments, list) or not attachments:
    print(f"FAIL: attachments is not a non-empty list — got {attachments!r}")
    sys.exit(4)

a = attachments[0]
if not (isinstance(a, tuple) and len(a) == 3):
    print(f"FAIL: attachment is not a 3-tuple — got {a!r}")
    sys.exit(5)

fname, body, mime = a
print(f"attachment[0]: filename={fname!r}, body_len={len(body)}, mime={mime!r}")
print(f"  body[:4] = {body[:4]!r}")
print(f"  body[:50]= {body[:50]!r}")

if mime != "application/pdf":
    print(f"FAIL: wrong mime — got {mime!r}")
    sys.exit(6)
if body[:4] != b"%PDF":
    print(f"FAIL: body does not start with %PDF — got {body[:8]!r}")
    sys.exit(7)
if len(body) < 1024:
    print(f"FAIL: body suspiciously small ({len(body)} bytes)")
    sys.exit(8)

print("\nPASS: PDF attachment plumbed correctly")
print(f"  filename: {fname}")
print(f"  size:     {len(body):,} bytes")
print(f"  mime:     {mime}")
print(f"  starts:   {body[:8]!r}")
