# new_product_doc_redirect.py
# Owner-reported 2026-06-21: "502 on the links for literature and datasheet
# of product" + follow-up: "if its says the literature and datasheet are
# load where can i find them as the links dont work".
#
# Fix shape:
#   1. GET /marketplace/product/<id>/doc/<kind> -- HEAD-probes the saved
#      URL, 302s to it if reachable, otherwise renders error.html with
#      the URL as a properly-clickable "Open directly" + Copy widget.
#   2. GET /marketplace/product/<id>/docs -- always-on fallback page that
#      lists EVERY saved URL for the product verbatim, regardless of
#      whether it's reachable. So even when the supplier site is down the
#      owner can copy the URL, save it, share it, try it later.
#
# Both paths are public (no login) so anonymous marketplace browsers
# still benefit.


import urllib.request
import urllib.error
import urllib.parse
import ssl


def _doc_url_for_product(c, pid, kind):
    """Look up the URL stored on a marketplace product. kind in
    {'literature','datasheet'}."""
    col = "literature_url" if kind == "literature" else "datasheet_url"
    row = c.execute(
        f"SELECT id, name, brand, {col} AS url FROM equipment_catalog WHERE id=?",
        (int(pid),),
    ).fetchone()
    return row


def _all_doc_urls_for_product(c, pid):
    """Return both URLs at once for the /docs fallback page."""
    row = c.execute(
        "SELECT id, name, brand, literature_url, datasheet_url "
        "FROM equipment_catalog WHERE id=?",
        (int(pid),),
    ).fetchone()
    return row


def _probe_url_ok(url, timeout=6.0):
    """HEAD-probe. Returns (ok, status_or_reason)."""
    try:
        if not url or not isinstance(url, str):
            return (False, "no_url")
        u = url.strip()
        if not (u.startswith("http://") or u.startswith("https://")):
            return (False, "not_http")
        parsed = urllib.parse.urlparse(u)
        if not parsed.netloc:
            return (False, "no_host")
        ctx = ssl.create_default_context()
        for method in ("HEAD", "GET"):
            req = urllib.request.Request(u, method=method, headers={
                "User-Agent": "Mozilla/5.0 (SolarPro probe)",
                "Range": "bytes=0-0",
                "Accept": "*/*",
            })
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    code = getattr(resp, "status", 200)
                    if code and 200 <= int(code) < 400:
                        return (True, int(code))
                    if method == "GET":
                        return (False, f"status_{code}")
            except urllib.error.HTTPError as he:
                if int(he.code) == 405 and method == "HEAD":
                    continue
                if int(he.code) in (200, 301, 302, 303, 307, 308):
                    return (True, int(he.code))
                return (False, f"status_{he.code}")
            except urllib.error.URLError as ue:
                if method == "GET":
                    return (False, f"net_{type(ue.reason).__name__}")
            except Exception as e:
                if method == "GET":
                    return (False, f"err_{type(e).__name__}")
        return (False, "unknown")
    except Exception as e:
        return (False, f"crash_{type(e).__name__}")


@app.route("/marketplace/product/<int:pid>/doc/<kind>")
def marketplace_product_doc_redirect(pid, kind):
    """HEAD-probe the stored literature/datasheet URL. If upstream is OK,
    302 the user there. If not, render the friendly error page with the
    URL surfaced so the user can copy it."""
    kind = (kind or "").strip().lower()
    if kind not in ("literature", "datasheet"):
        from flask import abort as _abort
        return _abort(404)
    try:
        with get_db() as c:
            row = _doc_url_for_product(c, pid, kind)
    except Exception as e:
        try: app.logger.warning("doc redirect lookup failed pid=%s kind=%s: %s", pid, kind, e)
        except Exception: pass
        row = None
    if not row or not row["url"]:
        return render_template(
            "error.html", code=404,
            title=f"No {kind.title()} link yet",
            message=(f"This product doesn't have a {kind} link saved. "
                     "An admin can run the link finder to look one up."),
            user=current_user() if 'current_user' in globals() else None,
        ), 404
    url = (row["url"] or "").strip()
    name = row["name"] or "this product"
    ok, status = _probe_url_ok(url, timeout=6.0)
    if ok:
        return redirect(url)
    # Upstream is down. Surface the URL as a real clickable widget via
    # doc_url + doc_name (NOT embedded in message -- error.html escapes
    # message text).
    return render_template(
        "error.html", code=502,
        title=f"{kind.title()} temporarily unreachable",
        message=(f"The supplier site that hosts the {kind} for "
                 f"{name} isn't responding right now "
                 f"(upstream returned {status}). The URL is saved -- "
                 "open it directly below or copy it for later."),
        doc_url=url,
        doc_name=f"{name} -- {kind}",
        user=current_user() if 'current_user' in globals() else None,
    ), 200  # 200 so the browser shows the body, not its own error page


@app.route("/marketplace/product/<int:pid>/docs")
def marketplace_product_docs_listing(pid):
    """Always-on fallback page that lists every saved URL for a product
    verbatim, regardless of reachability. So even when the supplier
    site is 502 the owner can still see, copy, and bookmark the URL."""
    try:
        with get_db() as c:
            row = _all_doc_urls_for_product(c, pid)
    except Exception as e:
        try: app.logger.warning("docs listing lookup failed pid=%s: %s", pid, e)
        except Exception: pass
        row = None
    if not row:
        return render_template(
            "error.html", code=404,
            title="Product not found",
            message="That product isn't in the catalogue.",
            user=current_user() if 'current_user' in globals() else None,
        ), 404
    return render_template(
        "product_docs.html",
        product=row,
        user=current_user() if 'current_user' in globals() else None,
    )
