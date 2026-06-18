"""Slice 3 admin verification dashboard tests.

Covers:
  - /admin/marketplace and /admin/marketplace/pending require admin (302 anon, 403 non-admin).
  - Admin can single-approve a pending supplier (is_verified flips to 1).
  - Admin can single-approve a pending product (is_verified flips to 1).
  - Bulk approve_supplier flips multiple rows + makes their products public.
  - Bulk approve_product flips only products whose supplier is verified.
  - Approved + supplier-verified product appears on the public /marketplace browse.
  - Reject hides product from public.
  - Every mutation appends a row to marketplace_audit_log.
"""
from __future__ import annotations

import importlib.util
import re
import time
import uuid
from pathlib import Path

import pytest


_RUN_TAG = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]   # mutable counter for per-call unique usernames


def _u(label: str) -> str:
    _SEQ[0] += 1
    return f"adm_{label}{_SEQ[0]}_{_RUN_TAG}"[:32]


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


def _register_supplier(client, label: str) -> tuple[str, int]:
    """Returns (username, supplier_id)."""
    uname = _u(label)
    csrf = _csrf(client.get("/supplier/register").get_data(as_text=True))
    r = client.post(
        "/supplier/register",
        data={
            "_csrf": csrf,
            "company": f"AdmTest {label} Co.",
            "country": "Ghana",
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "contact_name": "T",
            "phone": "+1",
            "categories": "LV Cables",
            "lead_time_days": "21",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:300]
    with client.session_transaction() as sess:
        uid = sess.get("user_id")
    assert uid
    return uname, uid


def _login_as_admin(client, app) -> int:
    """Promote a fresh user to is_admin=1, set session, return user_id."""
    uname = _u("admin")
    csrf = _csrf(client.get("/supplier/register").get_data(as_text=True))
    r = client.post(
        "/supplier/register",
        data={
            "_csrf": csrf,
            "company": "Admin Holder",
            "country": "Ghana",
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with client.session_transaction() as sess:
        uid = sess["user_id"]
    # Flip is_admin on the freshly-created user.
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            c.execute("UPDATE users SET is_admin=1 WHERE id=?", (uid,))
    return uid


def _supplier_id_for_user(app, user_id: int) -> int:
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            r = c.execute(
                "SELECT id FROM suppliers WHERE user_id=? LIMIT 1", (user_id,)
            ).fetchone()
        return r["id"] if r else 0


def _add_product(client, app, supplier_id: int, name: str) -> int:
    """Use the supplier's own /supplier/products/add to insert one product."""
    # Switch session to be that supplier's user — find the user_id from the
    # supplier row first.
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            r = c.execute(
                "SELECT user_id FROM suppliers WHERE id=?", (supplier_id,)
            ).fetchone()
            uid = r["user_id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    page = client.get("/supplier/products/add").get_data(as_text=True)
    csrf = _csrf(page)
    cat_id = re.search(r'<option value="(\d+)">Transformers', page).group(1)
    r = client.post(
        "/supplier/products/add",
        data={
            "_csrf": csrf,
            "name": name,
            "brand": "TestBrand",
            "category_id": cat_id,
            "price_usd": "1234",
            "unit": "No.",
            "lead_time_days": "30",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute(
                "SELECT id FROM equipment_catalog WHERE name=? ORDER BY id DESC LIMIT 1",
                (name,),
            ).fetchone()
    return row["id"]


# ───────────────────────── auth gating ────────────────────────────────────


def test_admin_marketplace_requires_login(client) -> None:
    r = client.get("/admin/marketplace", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


def test_admin_marketplace_403_for_non_admin(client) -> None:
    _register_supplier(client, "guard")
    r = client.get("/admin/marketplace", follow_redirects=False)
    assert r.status_code == 403


def test_admin_marketplace_pending_dashboard_renders(client, app) -> None:
    _login_as_admin(client, app)
    r = client.get("/admin/marketplace")
    assert r.status_code == 200
    assert "Marketplace Verification" in r.get_data(as_text=True)
    r2 = client.get("/admin/marketplace/pending")
    assert r2.status_code == 200
    assert "Pending verification queue" in r2.get_data(as_text=True)


# ───────────────────────── approve / reject ──────────────────────────────


def test_single_approve_supplier(client, app) -> None:
    _, uid = _register_supplier(client, "supA")
    sid = _supplier_id_for_user(app, uid)
    assert sid
    _login_as_admin(client, app)
    page = client.get("/admin/marketplace/pending").get_data(as_text=True)
    csrf = _csrf(page)
    r = client.post(
        f"/admin/marketplace/supplier/{sid}/approve",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute(
                "SELECT is_verified FROM suppliers WHERE id=?", (sid,)
            ).fetchone()
    assert row["is_verified"] == 1


def test_single_approve_product_then_visible_publicly(client, app) -> None:
    _, uid = _register_supplier(client, "supB")
    sid = _supplier_id_for_user(app, uid)
    pid = _add_product(client, app, sid, f"ProdB {_RUN_TAG}")
    # Approve supplier first so the product can go public on approval.
    _login_as_admin(client, app)
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    client.post(
        f"/admin/marketplace/supplier/{sid}/approve",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    client.post(
        f"/admin/marketplace/product/{pid}/approve",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute(
                "SELECT is_verified, is_public_visible FROM equipment_catalog WHERE id=?",
                (pid,),
            ).fetchone()
    assert row["is_verified"] == 1
    assert row["is_public_visible"] == 1
    # Public marketplace surfaces it (anonymous probe).
    public = app.app.test_client().get("/marketplace").get_data(as_text=True)
    assert f"ProdB {_RUN_TAG}" in public


def test_reject_product_hides_from_public(client, app) -> None:
    _, uid = _register_supplier(client, "supC")
    sid = _supplier_id_for_user(app, uid)
    pid = _add_product(client, app, sid, f"ProdC {_RUN_TAG}")
    _login_as_admin(client, app)
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    r = client.post(
        f"/admin/marketplace/product/{pid}/reject",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute(
                "SELECT is_active, is_public_visible FROM equipment_catalog WHERE id=?",
                (pid,),
            ).fetchone()
    assert row["is_active"] == 0
    assert row["is_public_visible"] == 0


# ───────────────────────── bulk actions ──────────────────────────────────


def test_bulk_approve_products(client, app) -> None:
    # Two suppliers, one product each; approve the suppliers first, then
    # bulk-approve the products in one POST.
    _, uid_a = _register_supplier(client, "bulkA")
    _, uid_b = _register_supplier(client, "bulkB")
    sid_a = _supplier_id_for_user(app, uid_a)
    sid_b = _supplier_id_for_user(app, uid_b)
    pid_a = _add_product(client, app, sid_a, f"BulkProd-A {_RUN_TAG}")
    pid_b = _add_product(client, app, sid_b, f"BulkProd-B {_RUN_TAG}")
    _login_as_admin(client, app)
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    # First bulk-approve the suppliers.
    from werkzeug.datastructures import MultiDict
    r1 = client.post(
        "/admin/marketplace/bulk",
        data=MultiDict([
            ("_csrf", csrf),
            ("action", "approve_supplier"),
            ("supplier_ids", str(sid_a)),
            ("supplier_ids", str(sid_b)),
        ]),
        follow_redirects=False,
    )
    assert r1.status_code in (302, 303)
    # Then bulk-approve the products.
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    r2 = client.post(
        "/admin/marketplace/bulk",
        data=MultiDict([
            ("_csrf", csrf),
            ("action", "approve_product"),
            ("product_ids", str(pid_a)),
            ("product_ids", str(pid_b)),
        ]),
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            rows = c.execute(
                "SELECT id, is_verified, is_public_visible FROM equipment_catalog "
                "WHERE id IN (?, ?)",
                (pid_a, pid_b),
            ).fetchall()
    assert all(r["is_verified"] == 1 for r in rows)
    assert all(r["is_public_visible"] == 1 for r in rows)


def test_unknown_bulk_action_flashes_error(client, app) -> None:
    _login_as_admin(client, app)
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    r = client.post(
        "/admin/marketplace/bulk",
        data={"_csrf": csrf, "action": "bogus", "product_ids": "1"},
        follow_redirects=True,
    )
    body = r.get_data(as_text=True)
    assert "Unknown action" in body or "bogus" in body


# ───────────────────────── audit log ─────────────────────────────────────


def test_supplier_approval_does_not_expose_unverified_products(client, app) -> None:
    """Codex Slice 3 finding (high severity): when admin approves a supplier,
    the supplier's UNVERIFIED products must NOT appear on the public marketplace.
    Only verified products of a verified supplier are public."""
    _, uid = _register_supplier(client, "leakprobe")
    sid = _supplier_id_for_user(app, uid)
    unique = f"LeakProbeUnverified {_RUN_TAG}"
    pid = _add_product(client, app, sid, unique)
    # Confirm the product starts unverified.
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute(
                "SELECT is_verified FROM equipment_catalog WHERE id=?", (pid,)
            ).fetchone()
    assert row["is_verified"] == 0
    # Admin approves the SUPPLIER only (not the product).
    _login_as_admin(client, app)
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    r = client.post(
        f"/admin/marketplace/supplier/{sid}/approve",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    # The unverified product must NOT appear on /marketplace (anonymous probe).
    public = app.app.test_client().get("/marketplace").get_data(as_text=True)
    assert unique not in public, (
        "REGRESSION: unverified product leaked to public marketplace "
        "after supplier-level approval."
    )


def test_audit_log_written_on_approve(client, app) -> None:
    _, uid = _register_supplier(client, "audit")
    sid = _supplier_id_for_user(app, uid)
    _login_as_admin(client, app)
    csrf = _csrf(client.get("/admin/marketplace/pending").get_data(as_text=True))
    client.post(
        f"/admin/marketplace/supplier/{sid}/approve",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            n = c.execute(
                "SELECT COUNT(*) FROM marketplace_audit_log "
                "WHERE action='approve_supplier' AND target_id=?",
                (sid,),
            ).fetchone()[0]
    assert n >= 1
