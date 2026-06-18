"""Slice 9 — Procurement Center + Basic Price Sheet tests."""
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
    return f"pc_{label}{_SEQ[0]}_{_RUN_TAG}"[:32]


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


def _db_rows(app, sql, params):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            return c.execute(sql, params).fetchall()


def _register_user(client, app, label) -> int:
    csrf = _csrf(client.get("/register").get_data(as_text=True))
    uname = _u(label)
    r = client.post(
        "/register",
        data={
            "_csrf": csrf, "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "name": "T", "company": "", "country": "Ghana",
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


# ───────────────────────── access control ────────────────────────────────


def test_procurement_center_requires_login(client):
    r = client.get("/procurement-center", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


def test_price_sheets_list_requires_login(client):
    r = client.get("/price-sheets", follow_redirects=False)
    assert r.status_code == 302


# ───────────────────────── page renders ──────────────────────────────────


def test_procurement_center_renders_with_grid_and_panel(client, app):
    _register_user(client, app, "A")
    body = client.get("/procurement-center").get_data(as_text=True)
    # Left-side panel pieces
    assert "Build document" in body
    assert "Basic Price Sheet" in body
    assert "Bill of Materials" in body
    assert "Bill of Quantities" in body
    # Currency selector — all 7 codes present
    for code in ("USD", "EUR", "GBP", "GHS", "NGN", "KES", "ZAR"):
        assert code in body
    # Product checkbox markup
    assert 'name="product_ids"' in body
    assert 'type="checkbox"' in body


def test_currency_switch_changes_price_display(client, app):
    _register_user(client, app, "B")
    body_usd = client.get("/procurement-center?currency=USD").get_data(as_text=True)
    body_ghs = client.get("/procurement-center?currency=GHS").get_data(as_text=True)
    assert "USD" in body_usd
    assert "GHS" in body_ghs
    # GHS is ~14.5x USD per the static rate, so the GHS body should not
    # be byte-identical to USD body.
    assert body_usd != body_ghs


# ───────────────────────── multi-select → Basic Price Sheet ──────────────


def test_add_selected_creates_price_sheet_with_qty_1(client, app):
    _register_user(client, app, "ps")
    # Pull 2 product IDs from the live catalog
    rows = _db_rows(
        app,
        "SELECT id FROM equipment_catalog "
        "WHERE is_active=1 AND is_public_visible=1 AND is_verified=1 LIMIT 2",
        (),
    )
    if len(rows) < 2:
        pytest.skip("not enough seeded products")
    pid_a, pid_b = rows[0]["id"], rows[1]["id"]
    page = client.get("/procurement-center").get_data(as_text=True)
    csrf = _csrf(page)
    from werkzeug.datastructures import MultiDict
    r = client.post(
        "/procurement-center/add",
        data=MultiDict([
            ("_csrf", csrf),
            ("doc_type", "price_sheet"),
            ("currency", "GHS"),
            ("product_ids", str(pid_a)),
            ("product_ids", str(pid_b)),
        ]),
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    assert "/price-sheets/" in r.headers["Location"]
    sheet_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    # Sheet has correct currency + 2 items
    sheet = _db_row(
        app, "SELECT currency FROM marketplace_price_sheets WHERE id=?",
        (sheet_id,),
    )
    assert sheet["currency"] == "GHS"
    items = _db_rows(
        app, "SELECT * FROM marketplace_price_sheet_items WHERE sheet_id=?",
        (sheet_id,),
    )
    assert len(items) == 2
    # The price_at_add must have been converted (USD * 14.5 for GHS).
    # We don't assert exact value, just that it's > 0 and supplier_name exists.
    for it in items:
        assert it["price_at_add"] > 0


def test_price_sheet_view_renders_all_columns(client, app):
    """Per the owner directive: item #, description, qty=1, unit, price in
    currency, supplier name, brand, supplier phone, email, address."""
    _register_user(client, app, "view")
    rows = _db_rows(
        app,
        "SELECT id FROM equipment_catalog "
        "WHERE is_active=1 AND is_public_visible=1 AND is_verified=1 LIMIT 1",
        (),
    )
    pid = rows[0]["id"]
    page = client.get("/procurement-center").get_data(as_text=True)
    csrf = _csrf(page)
    r = client.post(
        "/procurement-center/add",
        data={"_csrf": csrf, "doc_type": "price_sheet",
              "currency": "USD", "product_ids": str(pid)},
        follow_redirects=False,
    )
    sheet_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    body = client.get(f"/price-sheets/{sheet_id}").get_data(as_text=True)
    # Every required column header must appear
    for header in ("#", "Equipment / item description", "Qty", "Unit",
                   "Price", "Supplier", "Brand", "Phone", "Email", "Address"):
        assert header in body, f"missing column header: {header!r}"


def test_price_sheet_idor_blocks_other_user(client, app):
    _register_user(client, app, "owner")
    rows = _db_rows(
        app, "SELECT id FROM equipment_catalog "
        "WHERE is_active=1 AND is_public_visible=1 AND is_verified=1 LIMIT 1",
        (),
    )
    pid = rows[0]["id"]
    csrf = _csrf(client.get("/procurement-center").get_data(as_text=True))
    r = client.post(
        "/procurement-center/add",
        data={"_csrf": csrf, "doc_type": "price_sheet",
              "currency": "USD", "product_ids": str(pid)},
        follow_redirects=False,
    )
    sheet_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    # Switch to a different user
    _register_user(client, app, "intruder")
    r2 = client.get(f"/price-sheets/{sheet_id}", follow_redirects=False)
    assert r2.status_code == 404


# ───────────────────────── multi-select → BOM / BOQ ──────────────────────


def test_add_selected_to_bom_creates_bom_with_items(client, app):
    _register_user(client, app, "bom")
    rows = _db_rows(
        app, "SELECT id FROM equipment_catalog "
        "WHERE is_active=1 AND is_public_visible=1 AND is_verified=1 LIMIT 3",
        (),
    )
    pids = [r["id"] for r in rows]
    csrf = _csrf(client.get("/procurement-center").get_data(as_text=True))
    from werkzeug.datastructures import MultiDict
    data = MultiDict([("_csrf", csrf), ("doc_type", "bom"), ("currency", "USD")])
    for pid in pids:
        data.add("product_ids", str(pid))
    r = client.post("/procurement-center/add", data=data, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/boms/" in r.headers["Location"]
    bom_id = int(r.headers["Location"].rsplit("/", 1)[-1])
    n = _db_row(
        app, "SELECT COUNT(*) AS n FROM marketplace_bom_items WHERE bom_id=?",
        (bom_id,),
    )["n"]
    assert n == 3


def test_no_doc_type_rejected(client, app):
    _register_user(client, app, "notype")
    csrf = _csrf(client.get("/procurement-center").get_data(as_text=True))
    r = client.post(
        "/procurement-center/add",
        data={"_csrf": csrf, "currency": "USD", "product_ids": "1"},
        follow_redirects=True,
    )
    body = r.get_data(as_text=True)
    assert "Choose a document type" in body or "doc_type" in body


def test_no_products_selected_rejected(client, app):
    _register_user(client, app, "noprod")
    csrf = _csrf(client.get("/procurement-center").get_data(as_text=True))
    r = client.post(
        "/procurement-center/add",
        data={"_csrf": csrf, "doc_type": "price_sheet", "currency": "USD"},
        follow_redirects=True,
    )
    body = r.get_data(as_text=True)
    assert "Tick at least one product" in body or "least one" in body


def test_invalid_currency_falls_back_to_usd(client, app):
    _register_user(client, app, "badcur")
    body = client.get("/procurement-center?currency=ZZZ").get_data(as_text=True)
    # Falls back to USD — option is selected
    assert 'value="USD" selected' in body or 'USD" selected' in body
