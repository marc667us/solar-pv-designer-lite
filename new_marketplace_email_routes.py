# ─── Marketplace Email Notifications ──────────────────────────────────────────
# Slice 7E: wires Brevo-backed transactional emails for the key marketplace
# state transitions. Uses solar's existing _send_system_email pipeline
# (Brevo -> Axigen -> Resend -> SMTP). Every send is wrapped in try/except
# so a flaky email backend can never block the user-facing action.
#
# SECURITY (Codex Slice 7 finding): supplier-controlled strings (company name,
# RFQ title, etc.) MUST NOT land raw in email subject or HTML body. Subjects
# get stripped of CR/LF (header-injection defence) and bodies get escaped via
# html.escape() before they reach _send_system_email — which itself wraps
# body_text in <pre>{body}</pre> with no escaping of its own.

import html as _mp_html


def _safe_email_subject(s: str, limit: int = 160) -> str:
    """Strip CR/LF (RFC 5322 header-injection defence) and clip length."""
    if not s:
        return ""
    return s.replace("\r", " ").replace("\n", " ").strip()[:limit]


def _safe_email_text(s: str) -> str:
    """HTML-escape every <, >, & so user-controlled strings can't break out
    of the <pre> wrapper that _send_system_email injects into the HTML body."""
    if s is None:
        return ""
    return _mp_html.escape(str(s), quote=False)


def _marketplace_admin_emails():
    """List of admin email addresses to notify on new supplier registration."""
    with get_db() as c:
        rows = c.execute(
            "SELECT email FROM users WHERE is_admin=1 AND email != '' "
            "ORDER BY id LIMIT 5"
        ).fetchall()
    return [r["email"] for r in rows if r["email"]]


def _notify_admin_new_supplier(supplier_name, supplier_email, supplier_country):
    """Email every admin when a supplier signs up via /supplier/register."""
    try:
        recipients = _marketplace_admin_emails()
        if not recipients:
            return
        safe_name = _safe_email_text(supplier_name)
        safe_email = _safe_email_text(supplier_email)
        safe_country = _safe_email_text(supplier_country or "-")
        body = (
            f"A new supplier has registered on the SolarPro Marketplace:\n\n"
            f"  Company : {safe_name}\n"
            f"  Email   : {safe_email}\n"
            f"  Country : {safe_country}\n\n"
            "They are awaiting verification before their products appear on "
            "the public marketplace.\n\n"
            "Review the pending queue:\n"
            "  https://solarpro.aiappinvent.com/admin/marketplace/pending\n\n"
            "The SolarPro Marketplace Team"
        )
        subject = _safe_email_subject(
            f"[Marketplace] New supplier awaiting verification: {supplier_name}"
        )
        for addr in recipients:
            try:
                _send_system_email(addr, subject, body)
            except Exception as e:
                app.logger.warning("admin notify failed (%s): %s", addr, e)
    except Exception as e:
        app.logger.warning("admin notify outer failed: %s", e)


def _notify_supplier_verified(supplier_email, supplier_name):
    """Email a supplier when admin approves their registration."""
    if not supplier_email:
        return
    try:
        safe_name = _safe_email_text(supplier_name)
        body = (
            f"Hello {safe_name},\n\n"
            "Good news — your supplier account on the SolarPro Marketplace "
            "has been verified by our team.\n\n"
            "Your verified products are now visible on the public marketplace "
            "at https://solarpro.aiappinvent.com/marketplace — and buyers can "
            "send you RFQs directly.\n\n"
            "Open your dashboard to add more products or manage prices:\n"
            "  https://solarpro.aiappinvent.com/supplier/dashboard\n\n"
            "Welcome aboard.\n\n"
            "The SolarPro Marketplace Team"
        )
        _send_system_email(
            supplier_email,
            _safe_email_subject("[Marketplace] Your supplier account is verified"),
            body,
        )
    except Exception as e:
        app.logger.warning("supplier verify notify failed (%s): %s",
                           supplier_email, e)


def _notify_rfq_sent_to_supplier(supplier_email, supplier_name, rfq_title, rfq_id):
    """Email a supplier when a buyer sends them a new RFQ."""
    if not supplier_email:
        return
    try:
        safe_name = _safe_email_text(supplier_name)
        safe_title = _safe_email_text(rfq_title)
        body = (
            f"Hello {safe_name},\n\n"
            f"You have received a new Request for Quote on the SolarPro "
            f"Marketplace:\n\n"
            f"  Title : {safe_title}\n\n"
            "View the line items and submit your prices here:\n"
            f"  https://solarpro.aiappinvent.com/supplier/rfqs/{int(rfq_id)}\n\n"
            "Respond quickly to give yourself the best chance of winning the "
            "award.\n\n"
            "The SolarPro Marketplace Team"
        )
        _send_system_email(
            supplier_email,
            _safe_email_subject(f"[Marketplace] New RFQ for you: {rfq_title}"),
            body,
        )
    except Exception as e:
        app.logger.warning("rfq notify failed (%s): %s", supplier_email, e)


def _notify_buyer_rfq_response(buyer_email, buyer_name, supplier_name, rfq_title, rfq_id):
    """Email a buyer when a supplier responds to their RFQ."""
    if not buyer_email:
        return
    try:
        safe_buyer = _safe_email_text(buyer_name)
        safe_supplier = _safe_email_text(supplier_name)
        safe_title = _safe_email_text(rfq_title)
        body = (
            f"Hello {safe_buyer},\n\n"
            f"A supplier has just responded to your RFQ on the SolarPro "
            f"Marketplace:\n\n"
            f"  RFQ      : {safe_title}\n"
            f"  Supplier : {safe_supplier}\n\n"
            "Compare the offers and award the contract here:\n"
            f"  https://solarpro.aiappinvent.com/rfqs/{int(rfq_id)}\n\n"
            "The SolarPro Marketplace Team"
        )
        _send_system_email(
            buyer_email,
            _safe_email_subject(f"[Marketplace] New response on your RFQ: {rfq_title}"),
            body,
        )
    except Exception as e:
        app.logger.warning("buyer notify failed (%s): %s", buyer_email, e)
