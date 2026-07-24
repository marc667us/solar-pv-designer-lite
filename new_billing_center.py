"""User billing center (Slice 3 of the payments-legal suite).

GET /billing -- a full, richer transaction preview than the /account snippet:
every payment the user has made, each with a DERIVED status (Paid / Disputed /
Dispute resolved / Refunded), a receipt-download link, and a per-row action to
raise a refund request or dispute (which reuses slice 2's /account/disputes, not
a duplicate flow). Answers items 4 (receipts) + 5 (preview transactions).

Status is derived by merging `payments` with `payment_disputes` (slice 2) in
Python -- no correlated subquery, so it is dialect-safe on SQLite and Postgres.
The disputes table is ensured on an ISOLATED connection first, so /billing works
even for a user who has never opened the disputes page (and a failed ensure can
never poison the read transaction -- same rule as slices 1 and 2).

Registered from wsgi.py (web_app.py is CRLF+mojibake, never edited directly).
"""

from __future__ import annotations

from flask import render_template, session

from new_payment_disputes import ensure_disputes_schema

# payment.status values that count as a completed, money-received payment.
_PAID_STATES = {"success", "paid", "completed"}


def register_billing_center(app, *, get_db, login_required, current_user,
                            is_postgres=None):
    """Attach GET /billing. Idempotent against double registration."""

    def _is_pg():
        try:
            return bool(is_postgres()) if callable(is_postgres) else bool(is_postgres)
        except Exception:
            return False

    if "billing_center" in app.view_functions:
        return

    @app.route("/billing")
    @login_required
    def billing_center():
        uid = session.get("user_id")

        # Ensure the disputes table on its OWN connection so the read below can
        # LEFT-merge it safely and a DDL hiccup can't poison the read txn.
        try:
            with get_db() as _sc:
                ensure_disputes_schema(_sc, _is_pg())
        except Exception:
            pass

        with get_db() as c:
            pays = c.execute(
                "SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 200",
                (uid,)).fetchall()
            try:
                drows = c.execute(
                    "SELECT reference, status FROM payment_disputes "
                    "WHERE user_id=? AND reference <> '' ORDER BY id ASC",
                    (uid,)).fetchall()
            except Exception:
                drows = []

        # latest dispute status per reference (ascending id -> last wins)
        disp_by_ref = {}
        for d in drows:
            disp_by_ref[d["reference"]] = d["status"]

        txns = []
        total_paid = 0.0
        for p in pays:
            ref = p["reference"] or ""
            dstat = disp_by_ref.get(ref) if ref else None
            pstatus = (p["status"] or "").lower()
            if dstat == "refunded":
                label, kind = "Refunded", "refunded"
            elif dstat in ("open", "under_review"):
                label, kind = "Disputed", "disputed"
            elif dstat == "resolved":
                label, kind = "Dispute resolved", "resolved"
            elif pstatus in _PAID_STATES:
                label, kind = "Paid", "paid"
            else:
                label, kind = (p["status"] or "Pending"), "other"

            # "Total paid" excludes refunded transactions.
            if pstatus in _PAID_STATES and dstat != "refunded":
                try:
                    total_paid += float(p["amount_usd"] or 0)
                except Exception:
                    pass

            txns.append({
                "id": p["id"],
                "reference": ref,
                "gateway": p["gateway"],
                "plan": p["plan"],
                "amount_usd": p["amount_usd"],
                "currency": p["currency"],
                "created_at": p["created_at"],
                "label": label,
                "kind": kind,
            })

        return render_template(
            "billing.html", user=current_user(), txns=txns,
            total_paid=round(total_paid, 2), count=len(pays))
