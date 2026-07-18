"""The Ops Center's technical-support surface: run the checks, explain them, fix what can be
fixed.

OWNER, 2026-07-18:
  "in the app operation center when a test fail or gives error there must be a button to fix
   it and a button to fix all -- this must be one of the agent tech support"
  "the test results must also have plain english to explain at the opcenter test result pane"
  "check if the agent technical support are still working and able to catch and fix the
   issues and error"

That last question is why this file exists. `ops_support.py` was written and tested, and then
imported by NOTHING -- so on the live site it did precisely nothing. Logic with no route in
front of it is not a feature, and the honest answer to "is it working" was no.

REGISTERED FROM wsgi.py, not from web_app.py, mirroring how the enterprise module is attached:
web_app.py is CRLF + mojibake and must never be edited (CLAUDE.md).

WHAT IT DOES NOT DO. It does not invent new powers. Every check is an EXISTING /admin/ops/*
endpoint and every fix delegates to one, so this surface can do nothing an admin could not
already do by hand -- it only says what the results MEAN and offers the remedy that fits. That
boundary is deliberate: a support agent that can take novel actions on production is a much
larger security question than the one the owner asked.
"""

from __future__ import annotations

import ops_support


# The checks worth running for a health sweep, in the order an operator reads them.
# All of these already exist; see the /admin/ops/* routes in web_app.py.
SWEEP = (
    ("ping/backend",  "/admin/ops/ping/backend",  "Application"),
    ("ping/database", "/admin/ops/ping/database", "Database"),
    ("ping/ai",       "/admin/ops/ping/ai",       "AI provider"),
    ("ping/storage",  "/admin/ops/ping/storage",  "Disk space"),
    ("ping/redis",    "/admin/ops/ping/redis",    "Redis cache"),
    ("ping/queue",    "/admin/ops/ping/queue",    "Background queue"),
    ("email/status",  "/admin/ops/email/status",  "Email"),
)


def _status_of(payload) -> tuple[str, str]:
    """Pull a status word and any detail out of whatever an ops endpoint returned.

    The 30 ops endpoints do not share a response shape -- some return {"status": ...}, some
    {"ok": true}, some a bare string. Rather than rewrite 30 endpoints (and risk the ones that
    work), this normalises what they already produce. An unrecognised shape becomes "unknown",
    which `ops_support.explain` reports honestly instead of guessing at.
    """
    if isinstance(payload, str):
        return payload, ""
    if isinstance(payload, dict):
        for key in ("status", "state", "result"):
            if key in payload and isinstance(payload[key], str):
                return payload[key], str(payload.get("message") or payload.get("detail") or "")
        if "ok" in payload:
            return ("ok" if payload["ok"] else "error"), str(payload.get("message") or "")
    return "unknown", ""


def register_ops_support(app, *, admin_required, csrf_protect):
    """Mount the support surface.

    Input:  the Flask app, plus the app's OWN admin guard and CSRF check, injected rather
            than imported -- the same pattern the enterprise module uses to avoid a circular
            import back into web_app.
    Output: none.

    The admin guard is the app's real one. This surface must never be a way around it: every
    route it exposes runs an admin-only action, so it is admin-only too.
    """
    from flask import jsonify, request

    def _run_check(client, path):
        """Call one ops endpoint in-process and normalise its answer."""
        try:
            resp = client.get(path)
            try:
                payload = resp.get_json(silent=True)
            except Exception:
                payload = None
            if payload is None:
                payload = resp.get_data(as_text=True)[:200]
            status, detail = _status_of(payload)
            if resp.status_code >= 500:
                status = "error"
            return status, detail
        except Exception as exc:
            # A check that cannot even be called is a failed check, not a crashed page.
            return "error", type(exc).__name__

    @app.route("/admin/ops/support/sweep", methods=["GET"])
    @admin_required
    def ops_support_sweep():
        """Run every check and return each one EXPLAINED."""
        client = app.test_client()
        # Carry the caller's session so the admin guard on each check is satisfied by the
        # same person who asked for the sweep -- never by a privileged internal shortcut.
        with client.session_transaction() as sess:
            from flask import session as _s
            sess.update(dict(_s))

        results, explanations = [], {}
        for check_id, path, label in SWEEP:
            status, detail = _run_check(client, path)
            exp = ops_support.explain(check_id, status, detail)
            explanations[check_id] = exp
            results.append({
                "id": check_id,
                "label": label,
                "raw": status,
                "severity": exp.severity,
                "plain": exp.plain,
                "manual": exp.manual,
                "fix_id": exp.fix_id,
                "fix_label": exp.fix_label,
            })

        return jsonify({
            "summary": ops_support.summarise(explanations),
            "results": results,
            "fix_all": [{"id": f, "label": ops_support.FIXES[f].label}
                        for f in ops_support.fixable(explanations)],
        })

    @app.route("/admin/ops/support/fix/<fix_id>", methods=["POST"])
    @admin_required
    def ops_support_fix(fix_id):
        """Run ONE registered fix by delegating to the endpoint that already performs it."""
        csrf_protect()
        fix = ops_support.FIXES.get(fix_id)
        if not fix:
            # An unknown id is refused rather than attempted. This endpoint must never become
            # a way to call arbitrary routes.
            return jsonify({"ok": False,
                            "message": f"There is no fix called '{fix_id}'."}), 404

        client = app.test_client()
        with client.session_transaction() as sess:
            from flask import session as _s
            sess.update(dict(_s))

        try:
            if fix.method == "POST":
                resp = client.post(fix.endpoint,
                                   data={"_csrf": request.form.get("_csrf", "")})
            else:
                resp = client.get(fix.endpoint)
            ok = resp.status_code < 400
            return jsonify({
                "ok": ok,
                "message": fix.done if ok else
                           f"{fix.label} did not succeed. Nothing was changed.",
            })
        except Exception as exc:
            return jsonify({"ok": False,
                            "message": f"{fix.label} could not run ({type(exc).__name__}). "
                                       f"Nothing was changed."}), 500
