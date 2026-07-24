"""Public payment-legal pages (Slice 4 of the payments-legal suite).

Adds two read-only, public routes:
    GET /terms-of-payment  -> templates/terms_of_payment.html
    GET /refund-policy      -> templates/refund_policy.html

Registered from wsgi.py (web_app.py is CRLF + mojibake and must not be edited
directly), following the same boot-resilient `register_*` pattern as the ops
support and CDC surfaces. Registration never raises; a failure to register a
static legal page must never stop the app serving.
"""

from __future__ import annotations

from flask import render_template


def register_legal_payment(app) -> None:
    """Attach the payment-legal routes to `app`. Idempotent-safe: guards against
    a double registration (e.g. if wsgi imports run twice) by checking the
    endpoint name first."""

    if "terms_of_payment" not in app.view_functions:
        @app.route("/terms-of-payment")
        def terms_of_payment():
            return render_template("terms_of_payment.html")

    if "refund_policy" not in app.view_functions:
        @app.route("/refund-policy")
        def refund_policy():
            return render_template("refund_policy.html")
