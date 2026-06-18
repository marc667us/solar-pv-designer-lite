"""Slice 2 supplier + upload + ADK-agent smoke tests.

Covers:
  - /supplier/register GET renders.
  - /supplier/register POST creates user + supplier row + auto-logs-in.
  - /supplier/dashboard requires login; supplier_admin scope allowed; anon → /login.
  - /supplier/products lists only that supplier's products (tenant scope).
  - /supplier/products/add persists a product linked to the right supplier.
  - /supplier/upload GET renders for supplier_admin.
  - /supplier/upload/template returns a CSV with the canonical column header.
  - /supplier/upload POST imports a small CSV correctly + rejects missing columns.
  - The 4 ADK agents construct + the deterministic cores return expected shapes.
  - Existing /procurement admin routes still 302 to login (no regression).
"""
from __future__ import annotations

import importlib.util
import io
import time
import uuid
from pathlib import Path

import pytest


# Per-run unique suffix so successive `pytest` invocations don't collide on
# the users.email/username UNIQUE constraint (solar.db persists across runs).
_RUN_TAG = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"


def _u(label: str) -> str:
    return f"t_{label}_{_RUN_TAG}"[:32]


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location(
        "web_app", Path(__file__).resolve().parent / "web_app.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Disable the per-hour rate limit on /supplier/register so tests can
    # register multiple times within one run. Production keeps the limit.
    try:
        mod.limiter.enabled = False
    except Exception:
        pass
    return mod.app


@pytest.fixture
def client(app):
    return app.test_client()


def _register_supplier(client, username: str = "test_supplier_x") -> None:
    """Helper — registers a supplier and leaves the client logged in."""
    # GET first to obtain CSRF token from rendered form.
    r0 = client.get("/supplier/register")
    assert r0.status_code == 200, f"register GET returned {r0.status_code}"
    body = r0.get_data(as_text=True)
    import re
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', body)
    assert m, "CSRF token not found in register form"
    csrf = m.group(1)
    r = client.post(
        "/supplier/register",
        data={
            "_csrf": csrf,
            "company": "Test Supplier Co.",
            "country": "Ghana",
            "username": username,
            "email": f"{username}@example.com",
            "password": "longenoughpw9",
            "contact_name": "Test Person",
            "phone": "+233123456",
            "categories": "LV Cables, Switchgear",
            "lead_time_days": "21",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303), r.get_data(as_text=True)[:500]


def test_register_get_renders(client) -> None:
    r = client.get("/supplier/register")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "List your products" in body
    assert "Categories you supply" in body


def test_dashboard_requires_login(client) -> None:
    r = client.get("/supplier/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


def test_register_post_creates_and_logs_in(client) -> None:
    _register_supplier(client, username=_u("a"))
    # Now /supplier/dashboard should 200 (logged in).
    r = client.get("/supplier/dashboard")
    assert r.status_code == 200
    assert "Test Supplier Co." in r.get_data(as_text=True)


def test_add_product_persists(client) -> None:
    _register_supplier(client, username=_u("b"))
    # Look up CSRF from the add-product form
    page = client.get("/supplier/products/add")
    body = page.get_data(as_text=True)
    import re
    csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', body).group(1)
    cat_id = re.search(r'<option value="(\d+)">Transformers', body).group(1)
    r = client.post(
        "/supplier/products/add",
        data={
            "_csrf": csrf,
            "name": "Test Transformer 100 kVA",
            "brand": "TestBrand",
            "model": "T-100",
            "spec": "100 kVA, 11/0.4 kV",
            "unit": "No.",
            "price_usd": "5500",
            "lead_time_days": "30",
            "category_id": cat_id,
            "subcategory": "Distribution",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    lst = client.get("/supplier/products").get_data(as_text=True)
    assert "Test Transformer 100 kVA" in lst


def test_upload_get_renders(client) -> None:
    _register_supplier(client, username=_u("c"))
    r = client.get("/supplier/upload")
    assert r.status_code == 200
    assert "Drop a CSV or XLSX" in r.get_data(as_text=True)


def test_upload_template_csv(client) -> None:
    _register_supplier(client, username=_u("d"))
    r = client.get("/supplier/upload/template")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "name" in body and "category" in body and "price_usd" in body
    assert "Transformers" in body


def test_upload_csv_happy_path(client) -> None:
    _register_supplier(client, username=_u("e"))
    # GET upload to obtain CSRF.
    p = client.get("/supplier/upload").get_data(as_text=True)
    import re
    csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', p).group(1)
    csv_body = (
        "name,category,price_usd,brand,model,spec,unit,lead_time_days,subcategory\n"
        "Test Cable 4C 16mm,LV Power Cables,18,Nexans,LV-4C-16,test spec,m,21,Armoured\n"
        "Test Socket Twin,Sockets,14,MK,TS-1,test,No.,7,Switched\n"
    )
    data = {
        "_csrf": csrf,
        "file": (io.BytesIO(csv_body.encode("utf-8")), "test.csv"),
    }
    r = client.post(
        "/supplier/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    # Land on /supplier/products and see at least one of the uploaded rows.
    lst = client.get("/supplier/products").get_data(as_text=True)
    assert "Test Cable 4C 16mm" in lst


def test_upload_rejects_missing_required_column(client) -> None:
    _register_supplier(client, username=_u("f"))
    p = client.get("/supplier/upload").get_data(as_text=True)
    import re
    csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', p).group(1)
    # Missing 'price_usd' column.
    bad_csv = "name,category\nFoo,Transformers\n"
    data = {
        "_csrf": csrf,
        "file": (io.BytesIO(bad_csv.encode("utf-8")), "bad.csv"),
    }
    r = client.post(
        "/supplier/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    # Redirect back to /supplier/upload with the missing-column flash.
    body = r.get_data(as_text=True)
    assert "Missing required columns" in body or "price_usd" in body


def test_procurement_admin_no_regression(client) -> None:
    """Existing solar admin routes still redirect anon to /login (no 500s
    from new columns)."""
    for path in ("/procurement", "/procurement/suppliers", "/procurement/catalog"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 302, f"{path} returned {r.status_code}"


def test_supplier_routes_403_for_non_supplier(client, app) -> None:
    """Authenticated user without supplier_admin role must get 403 on
    /supplier/* routes — covers the supplier_required decorator's abort path
    (Codex noted this gap on the Slice 2 review)."""
    import re
    # Register as a NORMAL solar user via /register (not /supplier/register),
    # so the new user lands without role='supplier_admin'.
    csrf_form = client.get("/register")
    if csrf_form.status_code != 200:
        pytest.skip("solar /register form unreachable in this env")
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', csrf_form.get_data(as_text=True))
    if not m:
        pytest.skip("solar /register CSRF not found in form")
    csrf = m.group(1)
    uname = _u("notsupp")
    r = client.post(
        "/register",
        data={
            "_csrf": csrf,
            "username": uname,
            "email": f"{uname}@example.com",
            "password": "longenoughpw9",
            "name": "Solar User",
            "company": "", "country": "Ghana",
            "terms_agreed": "1",
        },
        follow_redirects=False,
    )
    if r.status_code not in (302, 303):
        pytest.skip(f"solar register returned {r.status_code}; cannot test 403 path")
    # Solar's register requires email verification before login can grant session.
    # Force the session directly via Flask test_client's session_transaction.
    with client.session_transaction() as sess:
        with app.app_context():
            from web_app import get_db
            with get_db() as c:
                row = c.execute(
                    "SELECT id FROM users WHERE username=?", (uname,)
                ).fetchone()
            if not row:
                pytest.skip("user did not persist")
            sess["user_id"] = row["id"]
    r2 = client.get("/supplier/dashboard")
    assert r2.status_code == 403, f"expected 403, got {r2.status_code}"


# ──────────────────── ADK marketplace agents — deterministic tests ────────────


def test_classify_product_picks_transformers() -> None:
    from engine.agents.marketplace import classify_product
    code, conf = classify_product(
        "ABB 500 kVA Distribution Transformer", "11/0.433 kV Dyn11 ONAN", "ABB"
    )
    assert code == "transformers"
    assert conf >= 0.55


def test_validate_spec_flags_missing_fields() -> None:
    from engine.agents.marketplace import validate_spec
    out = validate_spec("lv_cables", {"conductor_material": "Cu"})
    assert out["status"] == "incomplete"
    assert "size_mm2" in out["missing_fields"]
    assert "voltage_rating" in out["missing_fields"]


def test_normalise_price_parses_ghs() -> None:
    from engine.agents.marketplace import normalise_price
    out = normalise_price("GHS 9 800.00")
    assert out["amount"] == 9800.0
    assert out["currency"] == "GHS"


def test_supplier_product_agent_pipeline_accepts_good_row() -> None:
    from engine.agents.marketplace import classify_extracted_row
    row = {
        "name": "ABB 500 kVA Distribution Transformer",
        "brand": "ABB",
        "spec": "500 kVA 11/0.433 kV Dyn11 ONAN",
        "price": "$9800",
        "kva_rating": "500",
        "voltage_ratio": "11/0.4",
        "phase": "3",
        "vector_group": "Dyn11",
        "cooling_type": "ONAN",
    }
    out = classify_extracted_row(row)
    assert out["verdict"] == "accept"
    assert out["classification"]["category"] == "transformers"


def test_all_four_agents_construct() -> None:
    from engine.agents.marketplace import (
        SupplierProductAgent,
        ProductClassificationAgent,
        SpecificationValidationAgent,
        PriceNormalisationAgent,
    )
    assert SupplierProductAgent().name == "supplier_product_agent"
    assert ProductClassificationAgent().name == "product_classification_agent"
    assert SpecificationValidationAgent().name == "specification_validation_agent"
    assert PriceNormalisationAgent().name == "price_normalisation_agent"
