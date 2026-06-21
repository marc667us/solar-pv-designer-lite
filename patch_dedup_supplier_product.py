# patch_dedup_supplier_product.py
# Before INSERT, refuse if a product with the same (supplier_id,
# brand, name) trio already exists for this supplier. Case-insensitive
# comparison on brand + name; supplier_id is the integer id of the
# logged-in supplier_admin's supplier row.

from pathlib import Path
TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

OLD = (
    b'    csrf_protect()\r\n'
    b'    f = request.form\r\n'
    b'    name = (f.get("name") or "").strip()\r\n'
    b'    if not name:\r\n'
    b'        flash("Product name is required.", "danger")\r\n'
    b'        return redirect(url_for("supplier_product_add"))\r\n'
    b'    cat_id = _safe_int(f.get("category_id"), 0)\r\n'
)
NEW = (
    b'    csrf_protect()\r\n'
    b'    f = request.form\r\n'
    b'    name = (f.get("name") or "").strip()\r\n'
    b'    if not name:\r\n'
    b'        flash("Product name is required.", "danger")\r\n'
    b'        return redirect(url_for("supplier_product_add"))\r\n'
    b'    # De-dup: refuse if the same (supplier, brand, name) trio already\r\n'
    b'    # exists for this supplier. Case-insensitive comparison.\r\n'
    b'    _brand = (f.get("brand") or "").strip()\r\n'
    b'    try:\r\n'
    b'        with get_db() as _c:\r\n'
    b'            _dup = _c.execute(\r\n'
    b'                "SELECT id, name, brand FROM equipment_catalog "\r\n'
    b'                "WHERE supplier_id=? AND COALESCE(is_active,1)=1 "\r\n'
    b'                "  AND LOWER(COALESCE(brand,\'\')) = LOWER(?) "\r\n'
    b'                "  AND LOWER(name) = LOWER(?) LIMIT 1",\r\n'
    b'                (s["id"], _brand, name),\r\n'
    b'            ).fetchone()\r\n'
    b'    except Exception:\r\n'
    b'        _dup = None\r\n'
    b'    if _dup:\r\n'
    b'        flash(\r\n'
    b'            f"You already have a product called \'{_dup[\'name\']}\' from brand "\r\n'
    b'            f"\'{_dup[\'brand\'] or \'(no brand)\'}\'. Use Edit instead of adding a duplicate.",\r\n'
    b'            "warning",\r\n'
    b'        )\r\n'
    b'        return redirect(url_for("supplier_products"))\r\n'
    b'    cat_id = _safe_int(f.get("category_id"), 0)\r\n'
)
n = data.count(OLD)
if n == 1 and b"De-dup: refuse if the same (supplier, brand, name)" not in data:
    data = data.replace(OLD, NEW)
    TARGET.write_bytes(data)
    print(f"Patched supplier_product_add with dedup guard (+{len(NEW)-len(OLD)} bytes)")
elif b"De-dup: refuse" in data:
    print("Already patched.")
else:
    print(f"WARN: anchor count={n}")
