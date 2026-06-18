"""Apply Codex Slice 4 medium-severity fix to the already-injected web_app.py.

Codex Slice 4 finding: /rfqs/<id>/send filtered supplier IDs against
is_active=1 AND is_verified=1, but updated the RFQ status to 'sent' even
when zero targets survived the filter — producing a permanently
unanswerable RFQ with no recipients.

Fix: count successfully inserted targets; if zero, keep the RFQ in draft
status and flash an error. Otherwise flip to 'sent' as before.

Idempotent — skips if already applied.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"


OLD = (
    b"        for sid in sids:\r\n"
    b"            # Only target verified active suppliers; skip silently otherwise.\r\n"
    b"            ok = c.execute(\r\n"
    b"                \"SELECT 1 FROM suppliers WHERE id=? AND is_active=1 AND is_verified=1\",\r\n"
    b"                (sid,),\r\n"
    b"            ).fetchone()\r\n"
    b"            if not ok:\r\n"
    b"                continue\r\n"
    b"            try:\r\n"
    b"                c.execute(\r\n"
    b"                    \"INSERT INTO rfq_supplier_targets (rfq_id, supplier_id, status) \"\r\n"
    b"                    \"VALUES (?, ?, 'pending')\",\r\n"
    b"                    (rfq_id, sid),\r\n"
    b"                )\r\n"
    b"            except sqlite3.IntegrityError:\r\n"
    b"                pass  # already targeted \xe2\x80\x94 idempotent\r\n"
    b"        c.execute(\r\n"
    b"            \"UPDATE rfqs SET status='sent', sent_at=CURRENT_TIMESTAMP, \"\r\n"
    b"            \"updated_at=CURRENT_TIMESTAMP WHERE id=?\",\r\n"
    b"            (rfq_id,),\r\n"
    b"        )\r\n"
    b"    flash(f\"RFQ sent to {len(sids)} supplier{'s' if len(sids) != 1 else ''}.\", \"success\")\r\n"
    b"    return redirect(url_for(\"rfqs_view\", rfq_id=rfq_id))\r\n"
)


NEW = (
    b"        targeted = 0\r\n"
    b"        for sid in sids:\r\n"
    b"            # Only target verified active suppliers; skip silently otherwise.\r\n"
    b"            ok = c.execute(\r\n"
    b"                \"SELECT 1 FROM suppliers WHERE id=? AND is_active=1 AND is_verified=1\",\r\n"
    b"                (sid,),\r\n"
    b"            ).fetchone()\r\n"
    b"            if not ok:\r\n"
    b"                continue\r\n"
    b"            try:\r\n"
    b"                c.execute(\r\n"
    b"                    \"INSERT INTO rfq_supplier_targets (rfq_id, supplier_id, status) \"\r\n"
    b"                    \"VALUES (?, ?, 'pending')\",\r\n"
    b"                    (rfq_id, sid),\r\n"
    b"                )\r\n"
    b"                targeted += 1\r\n"
    b"            except sqlite3.IntegrityError:\r\n"
    b"                pass  # already targeted \xe2\x80\x94 idempotent\r\n"
    b"        # If no submitted supplier survived the active+verified filter the\r\n"
    b"        # RFQ stays in draft. Otherwise it would land in 'sent' status with\r\n"
    b"        # zero targets and become permanently unanswerable (Codex finding).\r\n"
    b"        if targeted == 0:\r\n"
    b"            flash(\r\n"
    b"                \"None of the selected suppliers are currently verified \xe2\x80\x94 \"\r\n"
    b"                \"the RFQ stays in draft. Pick at least one verified supplier.\",\r\n"
    b"                \"danger\",\r\n"
    b"            )\r\n"
    b"            return redirect(url_for(\"rfqs_view\", rfq_id=rfq_id))\r\n"
    b"        c.execute(\r\n"
    b"            \"UPDATE rfqs SET status='sent', sent_at=CURRENT_TIMESTAMP, \"\r\n"
    b"            \"updated_at=CURRENT_TIMESTAMP WHERE id=?\",\r\n"
    b"            (rfq_id,),\r\n"
    b"        )\r\n"
    b"    flash(f\"RFQ sent to {targeted} supplier{'s' if targeted != 1 else ''}.\", \"success\")\r\n"
    b"    return redirect(url_for(\"rfqs_view\", rfq_id=rfq_id))\r\n"
)


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"targeted = 0\r\n        for sid in sids:" in src:
        print("[skip] zero-target guard already present")
        return 0
    if OLD not in src:
        print("[fail] expected pre-fix block not found in web_app.py")
        return 4
    src = src.replace(OLD, NEW)
    open(TARGET, "wb").write(src)
    print("[ok] applied zero-target guard fix to /rfqs/<id>/send")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
