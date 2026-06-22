# === BEGIN: marketplace_pagination splice ===
# 2026-06-22 (session B): admin-tunable products_per_page setting +
# helpers that paginate marketplace_public / procurement_center, plus a
# small admin settings page.

def _ensure_admin_settings_table():
    is_pg = bool(os.environ.get("DATABASE_URL"))
    if is_pg:
        ddl = """CREATE TABLE IF NOT EXISTS admin_settings (
            key   VARCHAR(80) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    else:
        ddl = """CREATE TABLE IF NOT EXISTS admin_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""
    try:
        with get_db() as c:
            c.execute(ddl)
    except Exception:
        pass


def _admin_setting(key, default=None):
    """Read a value from admin_settings. Falls back to ``default``."""
    _ensure_admin_settings_table()
    try:
        with get_db() as c:
            r = c.execute(
                "SELECT value FROM admin_settings WHERE key=?", (key,)
            ).fetchone()
        if r:
            return r["value"] if hasattr(r, "keys") else r[0]
    except Exception:
        pass
    return default


def _admin_setting_set(key, value):
    """Write (upsert) a value into admin_settings."""
    _ensure_admin_settings_table()
    is_pg = bool(os.environ.get("DATABASE_URL"))
    try:
        with get_db() as c:
            if is_pg:
                c.execute(
                    "INSERT INTO admin_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=CURRENT_TIMESTAMP",
                    (key, str(value)),
                )
            else:
                c.execute(
                    "INSERT OR REPLACE INTO admin_settings (key, value, updated_at) "
                    "VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (key, str(value)),
                )
        return True
    except Exception:
        return False


def _products_per_page():
    """Return the admin-tunable products_per_page (default 24, clamped 6..200)."""
    try:
        v = int(_admin_setting("products_per_page", 24) or 24)
    except (TypeError, ValueError):
        v = 24
    return max(6, min(200, v))


@app.route("/admin/marketplace/settings", methods=["GET", "POST"])
@admin_required
def admin_marketplace_settings():
    _ensure_admin_settings_table()
    if request.method == "POST":
        csrf_protect()
        try:
            ppp = int(request.form.get("products_per_page") or 24)
        except (TypeError, ValueError):
            ppp = 24
        ppp = max(6, min(200, ppp))
        _admin_setting_set("products_per_page", ppp)
        flash(f"Saved: products per page = {ppp}.", "success")
        return redirect(url_for("admin_marketplace_settings"))
    return render_template(
        "admin_marketplace_settings.html",
        user=current_user(),
        products_per_page=_products_per_page(),
    )


# === END: marketplace_pagination splice ===
