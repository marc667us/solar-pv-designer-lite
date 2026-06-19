"""
When an RFQ has items linked to marketplace products, pre-tick the
suppliers behind those products on the "send to suppliers" form.

One byte edit inside web_app.py: compute suggested_supplier_ids in
rfqs_view and pass it to the template. The template change lives in
templates/rfq_view.html (Edit tool, not part of this script).
"""
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()
orig = data

OLD = (
    b"        # Available suppliers for the \"send\" picker.\r\n"
    b"        suppliers = c.execute(\r\n"
    b"            \"SELECT id, name, country FROM suppliers \"\r\n"
    b"            \"WHERE is_active=1 AND is_verified=1 \"\r\n"
    b"            \"ORDER BY name\"\r\n"
    b"        ).fetchall()\r\n"
    b"    return render_template(\r\n"
    b"        \"rfq_view.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        rfq=rfq,\r\n"
    b"        items=items,\r\n"
    b"        targets=targets,\r\n"
    b"        responses=responses,\r\n"
    b"        suppliers=suppliers,\r\n"
    b"    )"
)
NEW = (
    b"        # Available suppliers for the \"send\" picker.\r\n"
    b"        suppliers = c.execute(\r\n"
    b"            \"SELECT id, name, country FROM suppliers \"\r\n"
    b"            \"WHERE is_active=1 AND is_verified=1 \"\r\n"
    b"            \"ORDER BY name\"\r\n"
    b"        ).fetchall()\r\n"
    b"        # Suggested-supplier set: any supplier behind a product the\r\n"
    b"        # buyer already added to this RFQ. Pre-ticks the checkboxes\r\n"
    b"        # so the buyer doesn't have to hunt for them in the list.\r\n"
    b"        _pids = [int(it[\"product_id\"]) for it in items if it[\"product_id\"]]\r\n"
    b"        suggested_supplier_ids = set()\r\n"
    b"        if _pids:\r\n"
    b"            _ph = \",\".join([\"?\"] * len(_pids))\r\n"
    b"            for _r in c.execute(\r\n"
    b"                f\"SELECT DISTINCT supplier_id FROM equipment_catalog WHERE id IN ({_ph})\",\r\n"
    b"                _pids,\r\n"
    b"            ).fetchall():\r\n"
    b"                if _r[\"supplier_id\"]:\r\n"
    b"                    suggested_supplier_ids.add(int(_r[\"supplier_id\"]))\r\n"
    b"    return render_template(\r\n"
    b"        \"rfq_view.html\",\r\n"
    b"        user=current_user(),\r\n"
    b"        rfq=rfq,\r\n"
    b"        items=items,\r\n"
    b"        targets=targets,\r\n"
    b"        responses=responses,\r\n"
    b"        suppliers=suppliers,\r\n"
    b"        suggested_supplier_ids=suggested_supplier_ids,\r\n"
    b"    )"
)

if OLD in data:
    data = data.replace(OLD, NEW, 1)
    open(PATH, "wb").write(data)
    print(f"[done] web_app.py {len(data)-len(orig):+d} bytes")
elif b"suggested_supplier_ids=suggested_supplier_ids" in data:
    print("[skip] already patched")
else:
    print("[MISS] rfqs_view render block not in expected shape")
    sys.exit(1)
