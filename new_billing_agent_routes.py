"""Admin surface for the Billing Agent (ADR-0009).

GET /admin/billing-agent -- runs the agent's read-only oversight skills and
renders the billing-health report. Read-only: the agent flags and reports; it
takes no money action (§14).

Registered from wsgi.py (web_app.py is CRLF+mojibake, never edited directly),
boot-resilient like the other new_* surfaces.
"""

from __future__ import annotations

import os

from flask import render_template

import billing_agent


def register_billing_agent(app, *, admin_required, get_db, current_user,
                           is_postgres=None):
    """Attach GET /admin/billing-agent. Idempotent against double registration."""

    def _is_pg():
        try:
            return bool(is_postgres()) if callable(is_postgres) else bool(is_postgres)
        except Exception:
            return False

    if "admin_billing_agent" in app.view_functions:
        return

    @app.route("/admin/billing-agent")
    @admin_required
    def admin_billing_agent():
        try:
            report = billing_agent.run_oversight(
                get_db=get_db,
                view_functions=app.view_functions,
                env=os.environ,
                is_pg=_is_pg(),
            )
        except Exception as _e:  # never 500 an oversight page
            report = {
                "agent": billing_agent.AGENT,
                "generated_at": "",
                "overall_status": "unknown",
                "score": 0,
                "skills": [{"name": "oversight", "title": "Oversight run",
                            "status": "unknown",
                            "detail": "The oversight run could not complete: %s" % type(_e).__name__}],
            }
        return render_template("admin_billing_agent.html",
                               user=current_user(), report=report,
                               agent=report["agent"])
