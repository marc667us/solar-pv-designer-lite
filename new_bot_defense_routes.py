"""Wire the bot-defense guard + admin view (revenue-leakage protection).

A before_request hook inspects sensitive POST endpoints (login / register /
payment) for unambiguous bot signals and blocks them (403), recording every
decision. FAIL-OPEN: any error allows the request -- auth/payments never break.

GET /admin/bot-defense -- recent bot_events + counts (admin-gated).

Registered from wsgi.py (web_app.py is CRLF+mojibake, never edited directly),
boot-resilient like the other new_* surfaces.
"""

from __future__ import annotations

import os

from flask import request, render_template

import bot_defense


def _enforce_ua() -> bool:
    # Honeypot always blocks (zero false positives). UA-signal blocking is gated
    # behind this flag so it can be enabled once verified against real traffic
    # (default OFF = monitor: record would-block events, don't block).
    return os.environ.get("BOT_DEFENSE_ENFORCE", "").strip().lower() in ("1", "true", "yes")


def register_bot_defense(app, *, get_db, admin_required, current_user,
                         get_real_ip=None, is_postgres=None):
    """Attach the guard hook + admin view. Idempotent."""

    def _is_pg():
        try:
            return bool(is_postgres()) if callable(is_postgres) else bool(is_postgres)
        except Exception:
            return False

    def _ip():
        try:
            return get_real_ip() if callable(get_real_ip) else (request.remote_addr or "")
        except Exception:
            return ""

    # Ensure the ledger once at startup (isolated connection; best-effort).
    try:
        with get_db() as _sc:
            bot_defense.ensure_bot_events_schema(_sc, _is_pg())
    except Exception:
        pass

    if not getattr(app, "_bot_defense_hooked", False):
        app._bot_defense_hooked = True

        @app.before_request
        def _bot_guard():
            # FAIL-OPEN wrapper around EVERYTHING: this layer must never be the
            # reason a real login or payment fails.
            try:
                if not bot_defense.is_sensitive(request.method, request.path):
                    return None
                ua = request.headers.get("User-Agent", "")
                # request.form is cached by Flask, so reading the honeypot here
                # does not consume the body the handler needs.
                hp = ""
                try:
                    hp = request.form.get(bot_defense.HONEYPOT_FIELD, "")
                except Exception:
                    hp = ""
                kind, reason = bot_defense.classify(ua, hp)
                if kind == "allow":
                    return None
                # Decide the action for this signal.
                if kind == "honeypot":
                    block, action = True, "block"          # always safe to block
                elif kind == "ua":
                    if _enforce_ua():
                        block, action = True, "block"
                    else:
                        block, action = False, "monitored"  # would-block; recorded only
                else:  # "empty"
                    block, action = False, "flag"
                try:
                    with get_db() as c:
                        bot_defense.record_bot_event(
                            c, path=request.path, method=request.method,
                            action=action, reason=reason, ip=_ip(), ua=ua)
                except Exception:
                    pass
                if block:
                    # A bot doesn't need a friendly page; a terse 403 is enough
                    # and reveals nothing.
                    return ("Request blocked.", 403)
            except Exception:
                return None
            return None

    if "admin_bot_defense" not in app.view_functions:
        @app.route("/admin/bot-defense")
        @admin_required
        def admin_bot_defense():
            rows, counts, total_blocked = [], {}, 0
            try:
                with get_db() as c:
                    bot_defense.ensure_bot_events_schema(c, _is_pg())
            except Exception:
                pass
            try:
                with get_db() as c:
                    rows = c.execute(
                        "SELECT created_at, path, method, action, reason, ip, ua_sample "
                        "FROM bot_events ORDER BY id DESC LIMIT 200").fetchall()
                    for r in c.execute(
                            "SELECT reason, COUNT(*) n FROM bot_events "
                            "GROUP BY reason ORDER BY n DESC LIMIT 30").fetchall():
                        counts[r[0]] = r[1]
                    total_blocked = c.execute(
                        "SELECT COUNT(*) FROM bot_events WHERE action='block'").fetchone()[0]
            except Exception:
                pass
            return render_template("admin_bot_defense.html", user=current_user(),
                                   rows=rows, counts=counts, total_blocked=total_blocked,
                                   ua_enforced=_enforce_ua())
