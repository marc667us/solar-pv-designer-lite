"""
Campaign portal — Flask blueprint that serves the multi-product internal sales app.

What it does
------------
- Serves static files from `static/campaign/` at TWO URLs:
    1. Path-based:        https://<solarpro-host>/campaign/...
    2. Subdomain-based:   https://campaign.aiappinvent.com/...   (host-routed)
- No auth wrapper yet. The portal is semi-public (URL-known) during beta — it does
  not expose any solar-app session state. When admin-only reps need to access it,
  wrap `campaign_portal` with `@admin_required` from web_app.py.

Inputs
------
- `app` (Flask) — the existing Flask application to register against.

Outputs
-------
- 2 routes (path-based + path-with-subpath) and 1 `before_request` handler that
  rewrites campaign.aiappinvent.com hits onto the path-based route.

Syntax notes
------------
- We define a small Blueprint so this module touches `web_app.py` minimally
  (just one import + one register_blueprint call). This keeps the CRLF/mojibake
  risk down to a single 2-line patch.
- `send_from_directory` is the safe Flask helper — it joins paths via secure_filename
  semantics and returns 404 if you try to escape the directory.
"""
import os
from flask import Blueprint, send_from_directory, request, abort

CAMPAIGN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "campaign")

campaign_bp = Blueprint("campaign", __name__)


@campaign_bp.route("/campaign/", defaults={"path": "index.html"})
@campaign_bp.route("/campaign/<path:path>")
def campaign_files(path):
    """Serve any file inside static/campaign/.

    Inputs:  path = relative file path under static/campaign/, default 'index.html'
    Output:  the file's bytes with the right Content-Type, or 404
    """
    full = os.path.join(CAMPAIGN_DIR, path)
    if not os.path.isfile(full):
        abort(404)
    return send_from_directory(CAMPAIGN_DIR, path)


def register_campaign(app):
    """Wire the blueprint + the subdomain rewrite onto an existing Flask app.

    Inputs:  app = the Flask app object from web_app.py
    Output:  None (side effect: blueprint registered + before_request added)
    Syntax:  `app.before_request` decorator is applied once during registration
             so the host check runs on every request after this point.
    """
    app.register_blueprint(campaign_bp)

    @app.before_request
    def _campaign_subdomain_rewrite():
        # request.host contains 'campaign.aiappinvent.com' (no port unless non-default).
        # If the request arrived at the campaign subdomain but on a path outside /campaign/,
        # internally fall through to the static file under static/campaign/.
        host = (request.host or "").lower()
        if host.startswith("campaign."):
            # Already routed via /campaign/<path> — let Flask handle it
            if request.path.startswith("/campaign/") or request.path == "/campaign":
                return None
            # Rewrite '/' -> 'index.html', '/foo/bar' -> 'foo/bar'
            rel = request.path.lstrip("/") or "index.html"
            full = os.path.join(CAMPAIGN_DIR, rel)
            if os.path.isfile(full):
                return send_from_directory(CAMPAIGN_DIR, rel)
            # If the file doesn't exist, fall back to index.html (SPA-style)
            return send_from_directory(CAMPAIGN_DIR, "index.html")
        return None
