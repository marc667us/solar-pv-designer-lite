"""Payment disputes & billing complaints (Slice 2 of the payments-legal suite).

WHAT THIS PROVIDES
    A first-class dispute/complaint object tied to a payment, plus the routes to
    raise, view, and resolve one:

      USER
        GET  /account/disputes            list my disputes + raise a new one
        POST /account/disputes/new        raise a dispute / billing complaint
      ADMIN
        GET  /admin/disputes              queue (filter by status) + counts
        GET  /admin/disputes/<id>         detail + the linked payment's EVIDENCE
                                          (payment_events from slice 1)
        POST /admin/disputes/<id>/update  set status + resolution note, notify user

    A "dispute" and a "billing complaint" are the same object here (owner asked
    for both) -- the `category` distinguishes duplicate_charge / not_upgraded /
    unauthorized / refund_request / other.

WHY A SEPARATE MODULE + wsgi registration
    web_app.py is CRLF + mojibake and must never be edited directly (CLAUDE.md).
    Dependencies (get_db, auth decorators, current_user, audit, evidence writer,
    email) are injected by wsgi.py, matching register_cdc_drain / register_ops_support.

DIALECT SAFETY
    `?` placeholders (db_adapter translates to %s on Postgres), timestamps are
    Python-computed UTC strings bound as params -- never datetime('now'), which
    is SQLite-only and 500s on Postgres.
"""

from __future__ import annotations

from datetime import datetime

from flask import request, redirect, render_template, flash, url_for, session, abort

# Allowed values -- inputs are validated against these so a hand-posted form
# cannot write an arbitrary status/category.
CATEGORIES = {
    "duplicate_charge": "Charged twice / duplicate charge",
    "not_upgraded":     "Paid but plan not upgraded",
    "unauthorized":     "Charge I did not authorise",
    "refund_request":   "Refund request",
    "other":            "Other billing complaint",
}
STATUSES = ("open", "under_review", "resolved", "rejected", "refunded")
# Statuses an admin may set (all of them); "open" is the creation default.
ADMIN_SETTABLE = ("open", "under_review", "resolved", "rejected", "refunded")


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def ensure_disputes_schema(conn, is_postgres: bool = False) -> None:
    """Create payment_disputes idempotently. Safe on every cold start."""
    if is_postgres:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_disputes (
                id              SERIAL PRIMARY KEY,
                reference       TEXT    DEFAULT '',
                user_id         INTEGER,
                gateway         TEXT    DEFAULT '',
                amount_usd      REAL    DEFAULT 0,
                currency        TEXT    DEFAULT 'USD',
                category        TEXT    DEFAULT 'other',
                description     TEXT    DEFAULT '',
                status          TEXT    DEFAULT 'open',
                resolution_note TEXT    DEFAULT '',
                created_at      TEXT    DEFAULT '',
                updated_at      TEXT    DEFAULT ''
            )
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_disputes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                reference       TEXT    DEFAULT '',
                user_id         INTEGER,
                gateway         TEXT    DEFAULT '',
                amount_usd      REAL    DEFAULT 0,
                currency        TEXT    DEFAULT 'USD',
                category        TEXT    DEFAULT 'other',
                description     TEXT    DEFAULT '',
                status          TEXT    DEFAULT 'open',
                resolution_note TEXT    DEFAULT '',
                created_at      TEXT    DEFAULT '',
                updated_at      TEXT    DEFAULT ''
            )
            """
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payment_disputes_user ON payment_disputes(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payment_disputes_status ON payment_disputes(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payment_disputes_ref ON payment_disputes(reference)")


def register_payment_disputes(app, *, get_db, login_required, admin_required,
                              csrf_protect, current_user, write_audit_event=None,
                              record_payment_event=None, send_email=None,
                              admin_notify=None, is_postgres=None):
    """Attach the dispute routes. Idempotent against double registration."""

    def _is_pg():
        try:
            return bool(is_postgres()) if callable(is_postgres) else bool(is_postgres)
        except Exception:
            return False

    def _ensure_schema():
        # Ensure DDL on its OWN connection. On Postgres a failed CREATE aborts
        # the whole transaction, so it must NOT share a route's query/write
        # connection -- otherwise a schema hiccup poisons the next statement
        # ("current transaction is aborted"). Same isolation as slice 1. (Codex HIGH)
        try:
            with get_db() as _sc:
                ensure_disputes_schema(_sc, _is_pg())
        except Exception:
            pass

    def _audit(action, **kw):
        if write_audit_event:
            try:
                write_audit_event(action, **kw)
            except Exception:
                pass

    # ── USER: list + raise ────────────────────────────────────────────────────
    if "account_disputes" not in app.view_functions:
        @app.route("/account/disputes")
        @login_required
        def account_disputes():
            uid = session.get("user_id")
            _ensure_schema()
            with get_db() as c:
                mine = c.execute(
                    "SELECT * FROM payment_disputes WHERE user_id=? "
                    "ORDER BY id DESC LIMIT 100", (uid,)).fetchall()
                # The user's payments they might dispute (most recent first).
                pays = c.execute(
                    "SELECT reference, gateway, plan, amount_usd, currency, created_at "
                    "FROM payments WHERE user_id=? AND reference <> '' "
                    "ORDER BY id DESC LIMIT 50", (uid,)).fetchall()
            return render_template("account_disputes.html", user=current_user(),
                                   disputes=mine, payments=pays,
                                   categories=CATEGORIES)

    if "account_dispute_new" not in app.view_functions:
        @app.route("/account/disputes/new", methods=["POST"])
        @login_required
        def account_dispute_new():
            csrf_protect()
            uid = session.get("user_id")
            reference   = (request.form.get("reference") or "").strip()[:200]
            category    = (request.form.get("category") or "other").strip()
            description = (request.form.get("description") or "").strip()[:4000]
            if category not in CATEGORIES:
                category = "other"
            if not description:
                flash("Please describe the problem so we can help.", "warning")
                return redirect(url_for("account_disputes"))

            gateway = ""
            amount_usd = 0
            currency = "USD"
            _ensure_schema()
            with get_db() as c:
                # If a reference is given, confirm it belongs to THIS user and
                # pull its details (never trust the posted amount/gateway).
                if reference:
                    prow = c.execute(
                        "SELECT gateway, amount_usd, currency FROM payments "
                        "WHERE reference=? AND user_id=? LIMIT 1",
                        (reference, uid)).fetchone()
                    if prow is None:
                        # Not their payment -- treat as a general complaint,
                        # don't leak whether the reference exists.
                        reference = ""
                    else:
                        gateway    = prow["gateway"] or ""
                        amount_usd = prow["amount_usd"] or 0
                        currency   = prow["currency"] or "USD"
                now = _now()
                c.execute(
                    "INSERT INTO payment_disputes (reference, user_id, gateway, "
                    "amount_usd, currency, category, description, status, "
                    "resolution_note, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (reference, uid, gateway, amount_usd, currency, category,
                     description, "open", "", now, now))
            # Evidence + audit (best-effort, isolated).
            if record_payment_event:
                try:
                    with get_db() as _ec:
                        record_payment_event(
                            _ec, reference=reference, gateway=gateway,
                            event_type="dispute_opened", user_id=uid,
                            amount_usd=amount_usd, signature_verified=False,
                            payload={"category": category})
                except Exception:
                    pass
            _audit("payment_dispute_opened", user_id=uid,
                   details='{"category": "%s", "reference": "%s"}' % (category, reference))
            # Notify admin so it lands in the ops queue.
            if admin_notify:
                try:
                    admin_notify("New payment dispute (%s)" % CATEGORIES.get(category, category),
                                 "A customer raised a billing dispute/complaint. "
                                 "See /admin/disputes.")
                except Exception:
                    pass
            flash("Your dispute has been submitted. Our billing team will review it "
                  "and respond by email.", "success")
            return redirect(url_for("account_disputes"))

    # ── ADMIN: queue, detail, resolve ────────────────────────────────────────
    if "admin_disputes" not in app.view_functions:
        @app.route("/admin/disputes")
        @admin_required
        def admin_disputes():
            status_flt = (request.args.get("status") or "").strip()
            _ensure_schema()
            with get_db() as c:
                if status_flt in STATUSES:
                    rows = c.execute(
                        "SELECT d.*, u.username, u.email FROM payment_disputes d "
                        "LEFT JOIN users u ON u.id=d.user_id WHERE d.status=? "
                        "ORDER BY d.id DESC LIMIT 300", (status_flt,)).fetchall()
                else:
                    rows = c.execute(
                        "SELECT d.*, u.username, u.email FROM payment_disputes d "
                        "LEFT JOIN users u ON u.id=d.user_id "
                        "ORDER BY d.id DESC LIMIT 300").fetchall()
                counts = {}
                for s in STATUSES:
                    counts[s] = c.execute(
                        "SELECT COUNT(*) FROM payment_disputes WHERE status=?",
                        (s,)).fetchone()[0]
            return render_template("admin_disputes.html", user=current_user(),
                                   disputes=rows, counts=counts,
                                   status_filter=status_flt, statuses=STATUSES,
                                   categories=CATEGORIES)

    if "admin_dispute_detail" not in app.view_functions:
        @app.route("/admin/disputes/<int:did>")
        @admin_required
        def admin_dispute_detail(did):
            _ensure_schema()
            with get_db() as c:
                d = c.execute(
                    "SELECT d.*, u.username, u.email FROM payment_disputes d "
                    "LEFT JOIN users u ON u.id=d.user_id WHERE d.id=?",
                    (did,)).fetchone()
                if d is None:
                    abort(404)
                payment = None
                evidence = []
                if d["reference"]:
                    payment = c.execute(
                        "SELECT * FROM payments WHERE reference=? LIMIT 1",
                        (d["reference"],)).fetchone()
                    try:
                        evidence = c.execute(
                            "SELECT event_type, signature_verified, client_ip, "
                            "created_at FROM payment_events WHERE reference=? "
                            "ORDER BY id DESC LIMIT 50", (d["reference"],)).fetchall()
                    except Exception:
                        evidence = []
            return render_template("admin_dispute_detail.html", user=current_user(),
                                   d=d, payment=payment, evidence=evidence,
                                   statuses=ADMIN_SETTABLE, categories=CATEGORIES)

    if "admin_dispute_update" not in app.view_functions:
        @app.route("/admin/disputes/<int:did>/update", methods=["POST"])
        @admin_required
        def admin_dispute_update(did):
            csrf_protect()
            new_status = (request.form.get("status") or "").strip()
            note       = (request.form.get("resolution_note") or "").strip()[:4000]
            if new_status not in ADMIN_SETTABLE:
                flash("Invalid status.", "warning")
                return redirect(url_for("admin_dispute_detail", did=did))
            _ensure_schema()
            with get_db() as c:
                d = c.execute("SELECT * FROM payment_disputes WHERE id=?", (did,)).fetchone()
                if d is None:
                    abort(404)
                c.execute(
                    "UPDATE payment_disputes SET status=?, resolution_note=?, "
                    "updated_at=? WHERE id=?", (new_status, note, _now(), did))
                urow = c.execute("SELECT email, username FROM users WHERE id=?",
                                 (d["user_id"],)).fetchone()
            _audit("payment_dispute_updated", user_id=session.get("user_id"),
                   details='{"dispute_id": %d, "status": "%s"}' % (did, new_status))
            # Notify the customer of the resolution.
            if send_email and urow and urow["email"]:
                try:
                    _label = {"resolved": "resolved", "rejected": "reviewed",
                              "refunded": "refunded", "under_review": "under review"}.get(
                                  new_status, new_status)
                    _html = (
                        "<div style='font-family:sans-serif;background:#0a0a14;color:#e2e2f0;"
                        "padding:24px;border-radius:12px;max-width:600px'>"
                        "<h3 style='color:#a78bfa'>Update on your billing dispute</h3>"
                        "<p>Hi " + str(urow["username"]) + ", the status of your billing "
                        "dispute is now: <b>" + _label + "</b>.</p>"
                        + ("<p style='background:#12122a;padding:12px;border-radius:8px'>"
                           + note + "</p>" if note else "")
                        + "<p>You can view your disputes on your "
                        "<a href='https://solarpro.aiappinvent.com/account/disputes' "
                        "style='color:#a78bfa'>account page</a>.</p>"
                        "<p style='color:#6868a0;font-size:12px'>Billing: billing@aiappinvent.com</p>"
                        "</div>")
                    send_email(urow["email"], "Your billing dispute has been updated", _html)
                except Exception:
                    pass
            flash("Dispute updated and customer notified.", "success")
            return redirect(url_for("admin_dispute_detail", did=did))
