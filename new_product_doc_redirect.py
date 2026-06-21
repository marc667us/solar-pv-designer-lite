# new_product_doc_redirect.py
# Owner-reported 2026-06-21: "502 on the links for literature and datasheet
# of product".
#
# The marketplace product cards render p.literature_url and p.datasheet_url
# as direct external links. When the upstream supplier domain is down or
# the URL is stale, the browser shows the upstream 502 / DNS error / TLS
# error -- not a SolarPro page.
#
# Fix: route every literature / datasheet click through this redirect.
# We do a 6 s HEAD probe. If 200/301/302/303/307/308 -- 302 the user
# there. If anything else (5xx, 4xx, timeout, DNS error, TLS error) we
# render templates/error.html with the URL surfaced so the user can copy
# it manually and we can fix the stored value.


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
        # Some servers reject HEAD with 405. We try HEAD first, then a 1-byte
        # GET as fallback before declaring upstream broken.
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
    302 the user there. If not, render the friendly error page so the
    user never sees a bare 502 from the supplier domain."""
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
    # Upstream is down / dead / 502. Show the friendly page with the
    # URL exposed so the user can copy/paste into a new tab themselves.
    msg = (
        f"The supplier {kind} for <strong>{name}</strong> isn't reachable "
        f"right now (upstream returned <code>{status}</code>). "
        "You can try the link manually below -- the supplier site may "
        "come back. We'll re-check the link on the next crawl."
    )
    try:
        return render_template(
            "error.html", code=502,
            title=f"{kind.title()} temporarily unreachable",
            message=msg + f'<br><br><a href="{url}" target="_blank" rel="noopener" '
                          f'class="text-info">{url}</a>',
            user=current_user() if 'current_user' in globals() else None,
        ), 502
    except Exception:
        return redirect(url_for("marketplace_product_view", pid=pid)
                        if "marketplace_product_view" in app.view_functions
                        else url_for("marketplace_index")), 302
