"""Slice 7 tests — procurement specialist role, admin CRUD, /me dashboard,
and email notification triggers."""
from __future__ import annotations

import importlib.util
import re
import time
import uuid
from pathlib import Path

import pytest


_RUN_TAG = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _u(label: str) -> str:
    _SEQ[0] += 1
    return f"sf_{label}{_SEQ[0]}_{_RUN_TAG}"[:32]


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location(
        "web_app", Path(__file__).resolve().parent / "web_app.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.limiter.enabled = False
    except Exception:
        pass
    return mod


@pytest.fixture
def client(app):
    return app.app.test_client()


def _csrf(html: str) -> str:
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    assert m, "CSRF token not found"
    return m.group(1)


def _db_row(app, sql, params):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            return c.execute(sql, params).fetchone()


def _db_exec(app, sql, params):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            c.execute(sql, params)


def _register_user(client, app, label, role="") -> int:
    csrf = _csrf(client.get("/register").get_data(as_text=True))
    uname = _u(label)
    r = client.post(
        "/register",
        data={
            "_csrf": csrf, "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "name": "User", "company": "", "country": "Ghana",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    row = _db_row(app, "SELECT id FROM users WHERE username=?", (uname,))
    uid = row["id"]
    if role:
        _db_exec(app, "UPDATE users SET role=? WHERE id=?", (role, uid))
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


def _make_admin(client, app, label):
    uid = _register_user(client, app, label)
    _db_exec(app, "UPDATE users SET is_admin=1 WHERE id=?", (uid,))
    return uid


# ───────────────────────── 7A: role decorator ────────────────────────────


def test_procurement_role_admin_can_access(client, app):
    _make_admin(client, app, "admA")
    for path in ("/admin/marketplace/suppliers", "/admin/marketplace/products"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}"


def test_procurement_role_specialist_can_access(client, app):
    _register_user(client, app, "spec1", role="procurement_specialist")
    for path in ("/admin/marketplace/suppliers", "/admin/marketplace/products"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}"


def test_procurement_role_blocks_regular_user(client, app):
    _register_user(client, app, "regA")
    r = client.get("/admin/marketplace/suppliers", follow_redirects=False)
    assert r.status_code == 403


def test_procurement_role_blocks_supplier_admin(client, app):
    _register_user(client, app, "supA", role="supplier_admin")
    r = client.get("/admin/marketplace/suppliers", follow_redirects=False)
    assert r.status_code == 403


def test_procurement_role_blocks_anonymous(client):
    r = client.get("/admin/marketplace/suppliers", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


# ───────────────────────── 7B: admin elects specialists ──────────────────


def test_admin_can_promote_user_to_specialist(client, app):
    target_uid = _register_user(client, app, "elect1")
    _make_admin(client, app, "elector1")
    csrf = _csrf(client.get("/admin/marketplace/staff").get_data(as_text=True))
    r = client.post(
        f"/admin/marketplace/staff/{target_uid}/promote",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    row = _db_row(app, "SELECT role FROM users WHERE id=?", (target_uid,))
    assert row["role"] == "procurement_specialist"


def test_admin_can_demote_specialist(client, app):
    target_uid = _register_user(client, app, "dem1", role="procurement_specialist")
    _make_admin(client, app, "elector2")
    csrf = _csrf(client.get("/admin/marketplace/staff").get_data(as_text=True))
    r = client.post(
        f"/admin/marketplace/staff/{target_uid}/demote",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    row = _db_row(app, "SELECT role FROM users WHERE id=?", (target_uid,))
    assert (row["role"] or "") == ""


def test_non_admin_cannot_promote(client, app):
    _register_user(client, app, "nonadm")
    target_uid = _register_user(client, app, "victim")
    _register_user(client, app, "wouldbeElector")  # not admin
    csrf_html = "<form><input name='_csrf' value='dummy'></form>"
    r = client.post(
        f"/admin/marketplace/staff/{target_uid}/promote",
        data={"_csrf": "x"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 403)


def test_cannot_promote_supplier_admin_to_specialist(client, app):
    target_uid = _register_user(client, app, "supclash", role="supplier_admin")
    _make_admin(client, app, "elector3")
    csrf = _csrf(client.get("/admin/marketplace/staff").get_data(as_text=True))
    client.post(
        f"/admin/marketplace/staff/{target_uid}/promote",
        data={"_csrf": csrf},
        follow_redirects=True,
    )
    row = _db_row(app, "SELECT role FROM users WHERE id=?", (target_uid,))
    assert row["role"] == "supplier_admin", "supplier_admin should not be promoted"


# ───────────────────────── 7C: CRUD ──────────────────────────────────────


def test_specialist_can_edit_supplier(client, app):
    _register_user(client, app, "specEdit", role="procurement_specialist")
    # Pick any existing supplier from the seed
    row = _db_row(app, "SELECT id, name FROM suppliers WHERE is_active=1 LIMIT 1", ())
    if not row:
        pytest.skip("no supplier in seed")
    sid = row["id"]
    page = client.get(f"/admin/marketplace/suppliers/{sid}/edit").get_data(as_text=True)
    assert page  # 200 + form renders
    csrf = _csrf(page)
    r = client.post(
        f"/admin/marketplace/suppliers/{sid}/edit",
        data={
            "_csrf": csrf,
            "name": f"Edited Name {_RUN_TAG}",
            "country": "Ghana",
            "contact_name": "T",
            "phone": "+1",
            "email": "a@b.test",
            "website": "https://x.test",
            "categories": "X",
            "lead_time_days": "14",
            "payment_terms": "TT 30 days",
            "rating": "4",
            "is_verified": "1",
            "is_active": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    row2 = _db_row(app, "SELECT name FROM suppliers WHERE id=?", (sid,))
    assert row2["name"] == f"Edited Name {_RUN_TAG}"


def test_specialist_can_delete_supplier_softly(client, app):
    _register_user(client, app, "specDel", role="procurement_specialist")
    # Insert a throw-away supplier
    _db_exec(
        app,
        "INSERT INTO suppliers (name, country, email, is_verified, is_active) "
        "VALUES (?, ?, ?, 1, 1)",
        (f"ToDelete {_RUN_TAG}", "Ghana", f"del{_RUN_TAG}@test.test"),
    )
    sid_row = _db_row(
        app, "SELECT id FROM suppliers WHERE email=?",
        (f"del{_RUN_TAG}@test.test",),
    )
    sid = sid_row["id"]
    page = client.get("/admin/marketplace/suppliers").get_data(as_text=True)
    csrf = _csrf(page)
    r = client.post(
        f"/admin/marketplace/suppliers/{sid}/delete",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    after = _db_row(app, "SELECT is_active FROM suppliers WHERE id=?", (sid,))
    assert after["is_active"] == 0


# ───────────────────────── 7D: /me dashboard ─────────────────────────────


def test_me_dashboard_requires_login(client):
    r = client.get("/me", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


def test_me_dashboard_renders_for_user(client, app):
    _register_user(client, app, "meA")
    r = client.get("/me")
    assert r.status_code == 200
    assert "My recent RFQs" in r.get_data(as_text=True)


def test_me_dashboard_shows_supplier_panel_for_supplier(client, app):
    uid = _register_user(client, app, "meSup", role="supplier_admin")
    _db_exec(
        app,
        "INSERT INTO suppliers (name, user_id, is_verified, is_active) "
        "VALUES (?, ?, 0, 1)",
        (f"MeSupplier {_RUN_TAG}", uid),
    )
    body = client.get("/me").get_data(as_text=True)
    assert "Open RFQ inbox" in body
    assert "Supplier" in body


# ───────────────────────── 7E: email notifications ───────────────────────


def test_admin_notified_on_new_supplier(client, app, monkeypatch):
    sent = []

    def fake_send(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(app, "_send_system_email", fake_send)
    # Need at least one admin to notify
    _make_admin(client, app, "notifAdmin")
    # Register a supplier
    csrf = _csrf(client.get("/supplier/register").get_data(as_text=True))
    uname = _u("supEmail")
    client.post(
        "/supplier/register",
        data={
            "_csrf": csrf,
            "company": f"NotifyMe {_RUN_TAG}",
            "country": "Ghana",
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "contact_name": "T",
            "phone": "+1",
            "categories": "X",
            "lead_time_days": "21",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    admin_emails = [s for s in sent if "new supplier" in s["subject"].lower()]
    assert admin_emails, f"no admin notification sent (sent={sent[:3]})"
    assert "NotifyMe" in admin_emails[0]["body"]


def test_email_strings_html_escaped(client, app, monkeypatch):
    """Codex Slice 7 finding (high severity): supplier-controlled company name
    flowed raw into the admin email's HTML body. Now every user-controlled
    string is html.escape()d before substitution + subjects have CR/LF
    stripped (RFC 5322 header-injection defence)."""
    sent = []
    monkeypatch.setattr(
        app, "_send_system_email",
        lambda to, subject, body: sent.append({"to": to, "subject": subject, "body": body}),
    )
    _make_admin(client, app, "escAdmin")
    csrf = _csrf(client.get("/supplier/register").get_data(as_text=True))
    uname = _u("escSup")
    evil_company = "<script>alert(1)</script>Hostile Co. & Friends"
    client.post(
        "/supplier/register",
        data={
            "_csrf": csrf,
            "company": evil_company,
            "country": "Ghana",
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "contact_name": "T",
            "phone": "+1",
            "categories": "X",
            "lead_time_days": "21",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert sent, "no email sent at all"
    admin_email = [s for s in sent if "new supplier" in s["subject"].lower()][0]
    # The raw <script> tag must NOT appear anywhere
    assert "<script>" not in admin_email["body"]
    # The escaped form MUST appear
    assert "&lt;script&gt;" in admin_email["body"]
    # The & must be escaped to &amp;
    assert "&amp;" in admin_email["body"]


def test_email_subject_strips_newlines(client, app, monkeypatch):
    """A supplier could not slip a CR/LF into their company name to inject
    an SMTP header into the subject line."""
    sent = []
    monkeypatch.setattr(
        app, "_send_system_email",
        lambda to, subject, body: sent.append({"to": to, "subject": subject, "body": body}),
    )
    _make_admin(client, app, "crlfAdmin")
    csrf = _csrf(client.get("/supplier/register").get_data(as_text=True))
    uname = _u("crlfSup")
    client.post(
        "/supplier/register",
        data={
            "_csrf": csrf,
            "company": "Legit Co.\r\nBcc: attacker@evil.test",
            "country": "Ghana",
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "contact_name": "T",
            "phone": "+1",
            "categories": "X",
            "lead_time_days": "21",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    admin_emails = [s for s in sent if "new supplier" in s["subject"].lower()]
    assert admin_emails
    subj = admin_emails[0]["subject"]
    # The defence: no CR/LF means the SMTP transport sees one header line
    # regardless of what the supplier typed. The literal "Bcc:" text inside
    # the (now-single-line) subject is benign — it's just subject text.
    assert "\r" not in subj
    assert "\n" not in subj


def test_supplier_notified_on_approval(client, app, monkeypatch):
    sent = []
    monkeypatch.setattr(
        app, "_send_system_email",
        lambda to, subject, body: sent.append({"to": to, "subject": subject, "body": body}),
    )
    # Set up: 1 admin + 1 supplier with email
    admin_uid = _make_admin(client, app, "appAdmin")
    sup_uid = _register_user(client, app, "appSup", role="supplier_admin")
    sup_email = f"approve{_RUN_TAG}@test.test"
    _db_exec(
        app,
        "INSERT INTO suppliers (name, user_id, email, is_verified, is_active) "
        "VALUES (?, ?, ?, 0, 1)",
        (f"AppSup {_RUN_TAG}", sup_uid, sup_email),
    )
    sid_row = _db_row(app, "SELECT id FROM suppliers WHERE email=?", (sup_email,))
    sid = sid_row["id"]
    # Log in as admin and approve
    with client.session_transaction() as sess:
        sess["user_id"] = admin_uid
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    client.post(
        f"/admin/marketplace/supplier/{sid}/approve",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    approval_emails = [
        s for s in sent if "verified" in s["subject"].lower() and s["to"] == sup_email
    ]
    assert approval_emails, f"supplier not notified on approval (sent={sent})"
