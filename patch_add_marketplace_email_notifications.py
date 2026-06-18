"""Inject the marketplace email helpers + wire 4 trigger points.

After this patch web_app.py contains:
  - _marketplace_admin_emails()
  - _notify_admin_new_supplier(...)
  - _notify_supplier_verified(...)
  - _notify_rfq_sent_to_supplier(...)
  - _notify_buyer_rfq_response(...)

And these triggers fire automatically (each wrapped at the call-site
inside its existing route handler):
  - supplier_register success → _notify_admin_new_supplier(...)
  - admin_marketplace_approve_supplier → _notify_supplier_verified(...)
  - rfqs_send → _notify_rfq_sent_to_supplier(...) for every targeted supplier
  - supplier_rfqs_respond POST success → _notify_buyer_rfq_response(...)

All notifications are best-effort: any exception inside the call is
swallowed in the helper itself, so user-facing routes never fail because
the email backend is flaky.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_CODE = "new_marketplace_email_routes.py"


def inject_helpers(src: bytes) -> bytes:
    """Append the helper module before the __main__ guard if not already there."""
    if b"def _notify_admin_new_supplier" in src:
        return src
    new_code = open(NEW_CODE, "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    ANCHOR = b'if __name__ == "__main__":'
    pos = src.rfind(ANCHOR)
    if pos < 0:
        raise RuntimeError("anchor missing")
    return src[:pos] + new_code_crlf + b"\r\n\r\n" + src[pos:]


def patch_supplier_register_trigger(src: bytes) -> tuple[bytes, bool]:
    # Hook: after the auto-login + flash, before the redirect to dashboard.
    OLD = (
        b"    # Auto-login the new supplier\r\n"
        b"    session[\"user_id\"] = uid\r\n"
    )
    NEW = (
        b"    # Auto-login the new supplier\r\n"
        b"    session[\"user_id\"] = uid\r\n"
        b"    _notify_admin_new_supplier(company, email, country)\r\n"
    )
    if NEW in src or OLD not in src:
        return src, OLD in src and NEW in src
    return src.replace(OLD, NEW), True


def patch_supplier_approve_trigger(src: bytes) -> tuple[bytes, bool]:
    # Hook: at the END of admin_marketplace_approve_supplier, right before
    # the final flash + redirect.
    OLD = (
        b"    _log_marketplace_action(\"approve_supplier\", \"supplier\", sid, row[\"name\"])\r\n"
        b"    flash(f\"Approved supplier '{row['name']}'.\", \"success\")\r\n"
    )
    NEW = (
        b"    _log_marketplace_action(\"approve_supplier\", \"supplier\", sid, row[\"name\"])\r\n"
        b"    try:\r\n"
        b"        with get_db() as _c:\r\n"
        b"            _r = _c.execute(\"SELECT email FROM suppliers WHERE id=?\", (sid,)).fetchone()\r\n"
        b"        if _r and _r[\"email\"]:\r\n"
        b"            _notify_supplier_verified(_r[\"email\"], row[\"name\"])\r\n"
        b"    except Exception as _e:\r\n"
        b"        app.logger.warning(\"approve supplier notify failed: %s\", _e)\r\n"
        b"    flash(f\"Approved supplier '{row['name']}'.\", \"success\")\r\n"
    )
    if NEW in src or OLD not in src:
        return src, OLD in src and NEW in src
    return src.replace(OLD, NEW), True


def patch_rfq_send_trigger(src: bytes) -> tuple[bytes, bool]:
    # Hook: after each successful target insert, before the loop's continue.
    # We hook the END of rfqs_send AFTER status is flipped.
    OLD = (
        b"    flash(f\"RFQ sent to {targeted} supplier{'s' if targeted != 1 else ''}.\", \"success\")\r\n"
        b"    return redirect(url_for(\"rfqs_view\", rfq_id=rfq_id))\r\n"
    )
    NEW = (
        b"    try:\r\n"
        b"        with get_db() as _c:\r\n"
        b"            _rfq = _c.execute(\"SELECT title FROM rfqs WHERE id=?\", (rfq_id,)).fetchone()\r\n"
        b"            _rfq_title = _rfq[\"title\"] if _rfq else \"new RFQ\"\r\n"
        b"            _targets = _c.execute(\r\n"
        b"                \"SELECT s.name, s.email FROM rfq_supplier_targets rst \"\r\n"
        b"                \"JOIN suppliers s ON s.id=rst.supplier_id \"\r\n"
        b"                \"WHERE rst.rfq_id=? AND rst.status='pending'\", (rfq_id,)\r\n"
        b"            ).fetchall()\r\n"
        b"        for _t in _targets:\r\n"
        b"            _notify_rfq_sent_to_supplier(_t[\"email\"], _t[\"name\"], _rfq_title, rfq_id)\r\n"
        b"    except Exception as _e:\r\n"
        b"        app.logger.warning(\"rfq send notify failed: %s\", _e)\r\n"
        b"    flash(f\"RFQ sent to {targeted} supplier{'s' if targeted != 1 else ''}.\", \"success\")\r\n"
        b"    return redirect(url_for(\"rfqs_view\", rfq_id=rfq_id))\r\n"
    )
    if NEW in src or OLD not in src:
        return src, OLD in src and NEW in src
    return src.replace(OLD, NEW), True


def patch_rfq_response_trigger(src: bytes) -> tuple[bytes, bool]:
    OLD = (
        b"    flash(\"Response submitted. The buyer can now see your price.\", \"success\")\r\n"
        b"    return redirect(url_for(\"supplier_rfqs_inbox\"))\r\n"
    )
    NEW = (
        b"    try:\r\n"
        b"        with get_db() as _c:\r\n"
        b"            _buyer = _c.execute(\r\n"
        b"                \"SELECT u.email, u.name FROM rfqs r JOIN users u ON u.id=r.user_id \"\r\n"
        b"                \"WHERE r.id=?\", (rfq_id,)\r\n"
        b"            ).fetchone()\r\n"
        b"        if _buyer and _buyer[\"email\"]:\r\n"
        b"            _notify_buyer_rfq_response(\r\n"
        b"                _buyer[\"email\"], _buyer[\"name\"] or \"there\",\r\n"
        b"                s[\"name\"], rfq[\"title\"], rfq_id\r\n"
        b"            )\r\n"
        b"    except Exception as _e:\r\n"
        b"        app.logger.warning(\"rfq response notify failed: %s\", _e)\r\n"
        b"    flash(\"Response submitted. The buyer can now see your price.\", \"success\")\r\n"
        b"    return redirect(url_for(\"supplier_rfqs_inbox\"))\r\n"
    )
    if NEW in src or OLD not in src:
        return src, OLD in src and NEW in src
    return src.replace(OLD, NEW), True


def patch() -> int:
    src = open(TARGET, "rb").read()
    src = inject_helpers(src)
    applied = 0
    for name, fn in [
        ("supplier_register", patch_supplier_register_trigger),
        ("supplier_approve", patch_supplier_approve_trigger),
        ("rfq_send", patch_rfq_send_trigger),
        ("rfq_response", patch_rfq_response_trigger),
    ]:
        src, ok = fn(src)
        if ok:
            applied += 1
            print(f"[ok] hooked {name}")
        else:
            print(f"[warn] no hook site matched for {name}")
    open(TARGET, "wb").write(src)
    print(f"[ok] helpers injected + {applied}/4 triggers wired")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
