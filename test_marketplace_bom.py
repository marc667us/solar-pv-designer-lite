"""Slice 5 BOM/BOQ tests.

Covers:
  - /boms requires login (anon → /login).
  - Buyer creates a draft BOM and adds custom line items.
  - Buyer cannot view another buyer's BOM (IDOR → 404).
  - Add-to-BOM from a marketplace product appends to the user's latest draft,
    or creates a fresh BOM if none exists.
  - Per-line + per-category + grand totals render.
  - BOQ printable page renders and includes the grand total.
  - Clone-to-RFQ creates a new RFQ owned by the same user with the same items.
  - Marketplace "Add to BOM" button points to /boms/add-product/X when logged in.
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
    return f"bom_{label}{_SEQ[0]}_{_RUN_TAG}"[:32]


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
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            return c.execute(sql, params).fetchone()


def _register_buyer(client, app, label: str) -> int:
    csrf = _csrf(client.get("/register").get_data(as_text=True))
    uname = _u(label)
    r = client.post(
        "/register",
        data={
            "_csrf": csrf, "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "name": "Buyer", "company": "", "country": "Ghana",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    row = _db_row(app, "SELECT id FROM users WHERE username=?", (uname,))
    uid = row["id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


def _create_bom(client, title: str) -> int:
    csrf = _csrf(client.get("/boms/new").get_data(as_text=True))
    r = client.post(
        "/boms/new",
        data={"_csrf": csrf, "title": title},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    return int(r.headers["Location"].rsplit("/", 1)[-1])


# ────────────────────────── auth gating ──────────────────────────────────


def test_boms_list_requires_login(client) -> None:
    r = client.get("/boms", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


# ────────────────────────── create + add items ───────────────────────────


def test_buyer_creates_draft_bom_and_adds_item(client, app) -> None:
    _register_buyer(client, app, "addA")
    title = f"BOM-A {_RUN_TAG}"
    bom_id = _create_bom(client, title)
    page = client.get(f"/boms/{bom_id}").get_data(as_text=True)
    assert title in page
    csrf = _csrf(page)
    r = client.post(
        f"/boms/{bom_id}/items/add",
        data={
            "_csrf": csrf, "name": "MCB 32A",
            "qty": "12", "unit": "No.", "unit_price_override": "8.50",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    page2 = client.get(f"/boms/{bom_id}").get_data(as_text=True)
    assert "MCB 32A" in page2
    # Slice 8 added default markup rates (15/8/12/0). Line math:
    #   basic = 8.50 -> total_rate = 8.50 × 1.15 × 1.08 × 1.12 ≈ 11.824
    #   amount = 12 × 11.824 ≈ 141.886 → displays as 141.89
    # Basic rate (8.50) still appears in the Basic column.
    assert "8.50" in page2          # basic rate column
    assert "141.89" in page2        # rated line total


def test_buyer_cannot_view_another_users_bom(client, app) -> None:
    _register_buyer(client, app, "ownerX")
    bom_id = _create_bom(client, f"PrivateBOM {_RUN_TAG}")
    # Switch to a different buyer.
    _register_buyer(client, app, "intruderY")
    r = client.get(f"/boms/{bom_id}", follow_redirects=False)
    assert r.status_code == 404


# ────────────────────────── marketplace funnel ───────────────────────────


def test_add_from_marketplace_appends_to_latest_draft(client, app) -> None:
    _register_buyer(client, app, "funnelA")
    # First product on /marketplace.
    body = client.get("/marketplace").get_data(as_text=True)
    m = re.search(r"/boms/add-product/(\d+)", body)
    if not m:
        pytest.skip("no /boms/add-product/ link found in marketplace HTML")
    pid = int(m.group(1))
    csrf = _csrf(body)
    # First POST — creates a new BOM titled "Quick BOM — ...".
    r1 = client.post(
        f"/boms/add-product/{pid}",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r1.status_code in (302, 303)
    bom_id = int(r1.headers["Location"].rsplit("/", 1)[-1])
    # Second POST — appends to the SAME draft (not a new BOM).
    csrf = _csrf(client.get("/marketplace").get_data(as_text=True))
    r2 = client.post(
        f"/boms/add-product/{pid}",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    bom_id2 = int(r2.headers["Location"].rsplit("/", 1)[-1])
    assert bom_id == bom_id2, "second add-from-marketplace created a new BOM"
    # The BOM should now contain 2 line items for that product.
    n_row = _db_row(
        app,
        "SELECT COUNT(*) AS n FROM marketplace_bom_items WHERE bom_id=?",
        (bom_id,),
    )
    assert n_row["n"] == 2


def test_add_from_marketplace_rejects_get_method(client, app) -> None:
    """Codex Slice 5 finding (high severity): state-mutating endpoint must
    not accept GET. A GET should now return 405 Method Not Allowed —
    closing the CSRF-via-<img> attack vector."""
    _register_buyer(client, app, "csrfProbe")
    # Pull any visible product id from the marketplace.
    body = client.get("/marketplace").get_data(as_text=True)
    m = re.search(r"/boms/add-product/(\d+)", body)
    pid = int(m.group(1)) if m else 1
    r = client.get(f"/boms/add-product/{pid}", follow_redirects=False)
    assert r.status_code == 405, (
        f"expected 405 Method Not Allowed on GET, got {r.status_code}"
    )


# ────────────────────────── BOQ + clone-to-RFQ ───────────────────────────


def test_boq_page_renders_with_totals(client, app) -> None:
    _register_buyer(client, app, "boqA")
    bom_id = _create_bom(client, f"BOQ {_RUN_TAG}")
    csrf = _csrf(client.get(f"/boms/{bom_id}").get_data(as_text=True))
    client.post(
        f"/boms/{bom_id}/items/add",
        data={"_csrf": csrf, "name": "DB 18-way TPN", "qty": "3",
              "unit": "No.", "unit_price_override": "285"},
        follow_redirects=False,
    )
    boq = client.get(f"/boms/{bom_id}/boq").get_data(as_text=True)
    assert "Bill of Quantities" in boq
    assert "DB 18-way TPN" in boq
    # Slice 8 default markup rates: 285 × 1.15 × 1.08 × 1.12 = 396.45 per unit
    # × 3 = 1189.34 amount. Basic rate (285) still visible in Basic column.
    assert "285.00" in boq or "USD 285" in boq    # basic rate
    assert "1189.34" in boq or "1189.33" in boq   # rated amount
    assert "GRAND TOTAL" in boq


def test_clone_bom_to_rfq_preserves_owner_and_items(client, app) -> None:
    buyer_uid = _register_buyer(client, app, "cloneA")
    bom_id = _create_bom(client, f"CloneSrc {_RUN_TAG}")
    csrf = _csrf(client.get(f"/boms/{bom_id}").get_data(as_text=True))
    client.post(
        f"/boms/{bom_id}/items/add",
        data={"_csrf": csrf, "name": "Earth rod 1.2m", "qty": "5"},
        follow_redirects=False,
    )
    csrf = _csrf(client.get(f"/boms/{bom_id}").get_data(as_text=True))
    r = client.post(
        f"/boms/{bom_id}/clone-to-rfq",
        data={"_csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    rfq_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    rfq_row = _db_row(app, "SELECT user_id, title FROM rfqs WHERE id=?", (rfq_id,))
    assert rfq_row["user_id"] == buyer_uid
    assert "CloneSrc" in rfq_row["title"]
    item_row = _db_row(
        app, "SELECT COUNT(*) AS n FROM rfq_items WHERE rfq_id=?", (rfq_id,)
    )
    assert item_row["n"] == 1


def test_clone_empty_bom_to_rfq_is_rejected(client, app) -> None:
    _register_buyer(client, app, "emptyClone")
    bom_id = _create_bom(client, f"Empty {_RUN_TAG}")
    csrf = _csrf(client.get(f"/boms/{bom_id}").get_data(as_text=True))
    r = client.post(
        f"/boms/{bom_id}/clone-to-rfq",
        data={"_csrf": csrf},
        follow_redirects=True,
    )
    # Redirect back to the BOM view with a danger flash.
    assert b"Add items" in r.data or b"add items" in r.data.lower()


# ────────────────────────── marketplace integration ──────────────────────


def test_marketplace_add_to_bom_button_when_logged_in(client, app) -> None:
    _register_buyer(client, app, "btnA")
    body = client.get("/marketplace").get_data(as_text=True)
    assert "/boms/add-product/" in body
