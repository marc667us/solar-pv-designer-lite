"""Slice 4 RFQ workflow tests.

End-to-end: buyer creates RFQ, adds items, sends to 2 suppliers, both respond,
buyer compares + awards. Cross-supplier isolation. Auth gating. CSRF on every
mutation. Public marketplace integration ("Request Quote" → /rfqs/new?product_id=X).
"""
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
    return f"rfq_{label}{_SEQ[0]}_{_RUN_TAG}"[:32]


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


def _db_row(app, sql: str, params: tuple):
    """Run a SELECT against solar's own get_db() so we hit the same DB file."""
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            return c.execute(sql, params).fetchone()


def _db_exec(app, sql: str, params: tuple) -> None:
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            c.execute(sql, params)


def _register_buyer(client, app, label: str) -> int:
    """Register a normal solar user (not a supplier). Return user_id."""
    csrf = _csrf(client.get("/register").get_data(as_text=True))
    uname = _u(label)
    r = client.post(
        "/register",
        data={
            "_csrf": csrf,
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "name": "Buyer",
            "company": "",
            "country": "Ghana",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    row = _db_row(app, "SELECT id FROM users WHERE username=?", (uname,))
    assert row, f"user {uname} not persisted"
    uid = row["id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


def _register_supplier(client, app, label: str) -> tuple[int, int]:
    """Returns (user_id, supplier_id) and leaves client logged in as them."""
    csrf = _csrf(client.get("/supplier/register").get_data(as_text=True))
    uname = _u(label)
    r = client.post(
        "/supplier/register",
        data={
            "_csrf": csrf,
            "company": f"RFQ Test {label} Co.",
            "country": "Ghana",
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "contact_name": "Sup",
            "phone": "+1",
            "categories": "LV Cables",
            "lead_time_days": "21",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:300]
    with client.session_transaction() as sess:
        uid = sess["user_id"]
    row = _db_row(app, "SELECT id FROM suppliers WHERE user_id=?", (uid,))
    sid = row["id"]
    # Promote supplier to verified so they're selectable as RFQ targets.
    _db_exec(app, "UPDATE suppliers SET is_verified=1 WHERE id=?", (sid,))
    return uid, sid


def _login_as(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# ─────────────────────── auth gating ─────────────────────────────────────


def test_rfqs_list_requires_login(client) -> None:
    r = client.get("/rfqs", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


def test_supplier_inbox_requires_supplier_role(client, app) -> None:
    _register_buyer(client, app, "guard1")
    r = client.get("/supplier/rfqs", follow_redirects=False)
    assert r.status_code == 403


# ─────────────────────── buyer flow ──────────────────────────────────────


def test_buyer_creates_draft_rfq_and_adds_item(client, app) -> None:
    uid = _register_buyer(client, app, "buyA")
    csrf = _csrf(client.get("/rfqs/new").get_data(as_text=True))
    title = f"RFQ-A {_RUN_TAG}"
    r = client.post(
        "/rfqs/new",
        data={
            "_csrf": csrf,
            "title": title,
            "delivery_country": "Ghana",
            "deadline_date": "2026-07-01",
            "notes": "test",
            "first_item_name": "LV cable 16mm²",
            "first_item_qty": "200",
            "first_item_unit": "m",
            "first_item_spec": "Cu XLPE/SWA/PVC",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    rfq_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    page = client.get(f"/rfqs/{rfq_id}").get_data(as_text=True)
    assert title in page
    assert "LV cable 16mm" in page
    # Add a second item.
    csrf = _csrf(page)
    r2 = client.post(
        f"/rfqs/{rfq_id}/items/add",
        data={
            "_csrf": csrf,
            "name": "DB 18-way TPN",
            "qty": "2",
            "unit": "No.",
            "spec_notes": "100A incomer",
        },
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)
    page2 = client.get(f"/rfqs/{rfq_id}").get_data(as_text=True)
    assert "DB 18-way TPN" in page2


def test_buyer_cannot_view_another_users_rfq(client, app) -> None:
    uid_a = _register_buyer(client, app, "buyB")
    csrf = _csrf(client.get("/rfqs/new").get_data(as_text=True))
    r = client.post(
        "/rfqs/new",
        data={"_csrf": csrf, "title": f"Private {_RUN_TAG}", "first_item_name": "x"},
        follow_redirects=False,
    )
    rfq_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    # Different user.
    uid_b = _register_buyer(client, app, "buyC")
    r2 = client.get(f"/rfqs/{rfq_id}", follow_redirects=False)
    assert r2.status_code == 404


# ─────────────────────── end-to-end RFQ → response → award ───────────────


def test_full_rfq_lifecycle(client, app) -> None:
    # 1. Register two suppliers.
    sup1_uid, sup1_sid = _register_supplier(client, app, "sup1")
    sup2_uid, sup2_sid = _register_supplier(client, app, "sup2")
    # 2. Register a buyer + create RFQ + add item + send to both suppliers.
    buyer_uid = _register_buyer(client, app, "buyFull")
    csrf = _csrf(client.get("/rfqs/new").get_data(as_text=True))
    r = client.post(
        "/rfqs/new",
        data={
            "_csrf": csrf,
            "title": f"FullCycle {_RUN_TAG}",
            "first_item_name": "Cable 25mm",
            "first_item_qty": "100",
            "first_item_unit": "m",
        },
        follow_redirects=False,
    )
    rfq_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    csrf = _csrf(client.get(f"/rfqs/{rfq_id}").get_data(as_text=True))
    from werkzeug.datastructures import MultiDict
    r2 = client.post(
        f"/rfqs/{rfq_id}/send",
        data=MultiDict([
            ("_csrf", csrf),
            ("supplier_ids", str(sup1_sid)),
            ("supplier_ids", str(sup2_sid)),
        ]),
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)
    # 3. Supplier 1 responds.
    _login_as(client, sup1_uid)
    inbox = client.get("/supplier/rfqs").get_data(as_text=True)
    assert f"FullCycle {_RUN_TAG}" in inbox
    page = client.get(f"/supplier/rfqs/{rfq_id}").get_data(as_text=True)
    csrf = _csrf(page)
    # Find the item id from the form field name.
    item_id = re.search(r'name="unit_price_(\d+)"', page).group(1)
    r3 = client.post(
        f"/supplier/rfqs/{rfq_id}",
        data={
            "_csrf": csrf,
            "currency": "USD",
            "lead_time_days": "21",
            "valid_until": "2026-07-15",
            "notes": "Stock available",
            f"unit_price_{item_id}": "15.50",
            f"available_{item_id}": "on",
        },
        follow_redirects=False,
    )
    assert r3.status_code in (302, 303)
    # 4. Supplier 2 responds with higher price.
    _login_as(client, sup2_uid)
    page2 = client.get(f"/supplier/rfqs/{rfq_id}").get_data(as_text=True)
    csrf = _csrf(page2)
    item_id2 = re.search(r'name="unit_price_(\d+)"', page2).group(1)
    r4 = client.post(
        f"/supplier/rfqs/{rfq_id}",
        data={
            "_csrf": csrf,
            "currency": "USD",
            "lead_time_days": "30",
            "valid_until": "2026-08-01",
            "notes": "Bulk discount available",
            f"unit_price_{item_id2}": "18.00",
            f"available_{item_id2}": "on",
        },
        follow_redirects=False,
    )
    assert r4.status_code in (302, 303)
    # 5. Buyer sees both responses + awards the cheaper one.
    _login_as(client, buyer_uid)
    view = client.get(f"/rfqs/{rfq_id}").get_data(as_text=True)
    assert "1550" in view or "1,550" in view or "1550.00" in view  # 15.50 * 100
    csrf = _csrf(view)
    r5 = client.post(
        f"/rfqs/{rfq_id}/award/{sup1_sid}",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r5.status_code in (302, 303)
    awarded_view = client.get(f"/rfqs/{rfq_id}").get_data(as_text=True)
    assert "Awarded" in awarded_view


# ─────────────────────── supplier cross-isolation ────────────────────────


def test_supplier_cannot_see_rfq_not_targeted_at_them(client, app) -> None:
    # Buyer sends RFQ to supplier A only.
    _, sup_a_sid = _register_supplier(client, app, "isoA")
    _, sup_b_sid = _register_supplier(client, app, "isoB")
    # supplier B's user_id is currently in session — we need supplier B's user_id
    # for later. Capture it.
    with client.session_transaction() as sess:
        sup_b_uid = sess["user_id"]
    buyer_uid = _register_buyer(client, app, "isoBuyer")
    csrf = _csrf(client.get("/rfqs/new").get_data(as_text=True))
    r = client.post(
        "/rfqs/new",
        data={"_csrf": csrf, "title": f"Isolated {_RUN_TAG}", "first_item_name": "x"},
        follow_redirects=False,
    )
    rfq_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    csrf = _csrf(client.get(f"/rfqs/{rfq_id}").get_data(as_text=True))
    client.post(
        f"/rfqs/{rfq_id}/send",
        data={"_csrf": csrf, "supplier_ids": str(sup_a_sid)},
        follow_redirects=False,
    )
    # Supplier B logs in — should NOT be able to view this RFQ.
    _login_as(client, sup_b_uid)
    r2 = client.get(f"/supplier/rfqs/{rfq_id}", follow_redirects=False)
    assert r2.status_code == 404
    # And it must NOT appear in supplier B's inbox.
    inbox = client.get("/supplier/rfqs").get_data(as_text=True)
    assert f"Isolated {_RUN_TAG}" not in inbox


# ─────────────────────── marketplace integration ─────────────────────────


def test_send_with_no_verified_targets_keeps_rfq_in_draft(client, app) -> None:
    """Codex Slice 4 finding: /rfqs/<id>/send filtered out all submitted
    supplier IDs (none verified). Previously the route still flipped status
    to 'sent', leaving an unanswerable RFQ. Now it must stay in draft."""
    # Register a supplier and IMMEDIATELY un-verify them so the buyer's
    # submitted supplier_id is filtered out by the active+verified gate.
    _, sup_sid = _register_supplier(client, app, "ghost")
    _db_exec(app, "UPDATE suppliers SET is_verified=0 WHERE id=?", (sup_sid,))
    # Buyer creates RFQ + tries to send to that now-unverified supplier.
    _register_buyer(client, app, "ghostBuyer")
    csrf = _csrf(client.get("/rfqs/new").get_data(as_text=True))
    r = client.post(
        "/rfqs/new",
        data={"_csrf": csrf, "title": f"Ghost {_RUN_TAG}", "first_item_name": "x"},
        follow_redirects=False,
    )
    rfq_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    csrf = _csrf(client.get(f"/rfqs/{rfq_id}").get_data(as_text=True))
    client.post(
        f"/rfqs/{rfq_id}/send",
        data={"_csrf": csrf, "supplier_ids": str(sup_sid)},
        follow_redirects=False,
    )
    # RFQ must still be 'draft' — the zero-target guard kept it that way.
    row = _db_row(app, "SELECT status FROM rfqs WHERE id=?", (rfq_id,))
    assert row["status"] == "draft", f"expected draft, got {row['status']}"
    # And no rfq_supplier_targets row was created for this RFQ.
    n_row = _db_row(
        app, "SELECT COUNT(*) AS n FROM rfq_supplier_targets WHERE rfq_id=?", (rfq_id,)
    )
    assert n_row["n"] == 0


def test_marketplace_request_quote_button_links_to_rfqs_new_when_logged_in(client, app) -> None:
    _register_buyer(client, app, "linkA")
    body = client.get("/marketplace").get_data(as_text=True)
    # When logged in, the action links go to /rfqs/new?product_id=
    assert "/rfqs/new?product_id=" in body


def test_marketplace_request_quote_button_redirects_to_register_when_anon(client) -> None:
    body = client.get("/marketplace").get_data(as_text=True)
    # Anonymous: action button points to the action gate, not /rfqs/new.
    assert "/marketplace/action/request_quote" in body
