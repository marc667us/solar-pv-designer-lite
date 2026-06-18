# ─── Routes — Marketplace Supplier Self-Service ───────────────────────────────
# Slice 2A: suppliers register themselves, manage their company profile, add
# their own products to equipment_catalog. Products land with is_verified=0 so
# an admin must approve before they show up on the public marketplace browse.
#
# Role model: users.role = 'supplier_admin' for supplier-owned accounts.
# Existing solar users (role = '' or NULL) keep working unchanged.

def _ensure_supplier_schema():
    """Idempotent — extends users and suppliers tables with self-service fields."""
    with get_db() as c:
        # users: add 'role' column for supplier_admin scope
        ucols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in ucols:
            c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT ''")
        # suppliers: link to the user who owns the record + verification flag
        scols = {r["name"] for r in c.execute("PRAGMA table_info(suppliers)").fetchall()}
        if "user_id" not in scols:
            c.execute("ALTER TABLE suppliers ADD COLUMN user_id INTEGER DEFAULT 0")
        if "is_verified" not in scols:
            c.execute("ALTER TABLE suppliers ADD COLUMN is_verified INTEGER DEFAULT 0")
        # Mark the seeded reference suppliers (JinkoSolar, LONGi, etc.) as verified
        # so they continue to show up on the public marketplace.
        c.execute("UPDATE suppliers SET is_verified=1 WHERE user_id=0 AND is_verified=0")
        # equipment_catalog: marketplace approval flag
        ecols = {r["name"] for r in c.execute("PRAGMA table_info(equipment_catalog)").fetchall()}
        if "is_verified" not in ecols:
            c.execute("ALTER TABLE equipment_catalog ADD COLUMN is_verified INTEGER DEFAULT 1")
            # All pre-existing rows were admin-curated so treat them as verified.


def supplier_required(f):
    """Decorator: require an authenticated supplier_admin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        u = current_user()
        if not u:
            return redirect(url_for("login"))
        if (u["role"] or "") != "supplier_admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _current_supplier():
    """Return the supplier row that belongs to the current supplier_admin user."""
    u = current_user()
    if not u:
        return None
    with get_db() as c:
        return c.execute(
            "SELECT * FROM suppliers WHERE user_id=? LIMIT 1", (u["id"],)
        ).fetchone()


@app.route("/supplier/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def supplier_register():
    """Self-service supplier signup. Creates a users row with role='supplier_admin'
    and a paired suppliers row owned by that user."""
    _ensure_supplier_schema()
    _ensure_marketplace_tables()
    if request.method == "GET":
        return render_template(
            "supplier_register.html", user=current_user(), countries=get_countries()
        )
    csrf_protect()
    f = request.form
    if not f.get("terms_agreed"):
        flash("Please accept the Terms of Service and Privacy Policy.", "danger")
        return render_template(
            "supplier_register.html", user=current_user(), countries=get_countries()
        )
    # Minimal required fields
    company = (f.get("company") or "").strip()
    username = (f.get("username") or "").strip().lower()
    email = (f.get("email") or "").strip().lower()
    password = f.get("password") or ""
    country = (f.get("country") or "").strip()
    if not all([company, username, email, password]):
        flash("Company name, username, email, and password are required.", "danger")
        return render_template(
            "supplier_register.html", user=current_user(), countries=get_countries()
        )
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return render_template(
            "supplier_register.html", user=current_user(), countries=get_countries()
        )
    ph = generate_password_hash(password)
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO users (username,email,password_hash,name,company,country,plan,role) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (username, email, ph, f.get("contact_name", ""), company,
                 country, "free", "supplier_admin"),
            )
            uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            c.execute(
                "INSERT INTO suppliers (name,country,contact_name,phone,email,website,"
                "categories,lead_time_days,payment_terms,rating,user_id,is_verified,is_active) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (company, country, f.get("contact_name", ""), f.get("phone", ""),
                 email, f.get("website", ""), f.get("categories", ""),
                 _safe_int(f.get("lead_time_days"), 30),
                 f.get("payment_terms", "TT 30 days"), 5, uid, 0),
            )
    except sqlite3.IntegrityError as e:
        msg = str(e).lower()
        if "username" in msg:
            flash("That username is already taken.", "danger")
        elif "email" in msg:
            flash("That email is already registered.", "danger")
        else:
            flash("Registration failed — please check your inputs.", "danger")
        return render_template(
            "supplier_register.html", user=current_user(), countries=get_countries()
        )
    # Auto-login the new supplier
    session["user_id"] = uid
    flash(
        "Welcome to the SolarPro Marketplace. Your supplier account is pending "
        "verification by our team — your products will appear publicly once approved.",
        "success",
    )
    return redirect(url_for("supplier_dashboard"))


@app.route("/supplier/dashboard")
@supplier_required
def supplier_dashboard():
    s = _current_supplier()
    if not s:
        # Supplier row went missing — log them out, force re-registration.
        session.pop("user_id", None)
        flash("Your supplier profile could not be found. Please register again.", "danger")
        return redirect(url_for("supplier_register"))
    with get_db() as c:
        product_count = c.execute(
            "SELECT COUNT(*) FROM equipment_catalog WHERE supplier_id=?", (s["id"],)
        ).fetchone()[0]
        recent_products = c.execute(
            "SELECT ec.*, pc.name AS category_name FROM equipment_catalog ec "
            "LEFT JOIN product_categories pc ON pc.id=ec.category_id "
            "WHERE ec.supplier_id=? ORDER BY ec.created_at DESC LIMIT 10",
            (s["id"],),
        ).fetchall()
    return render_template(
        "supplier_dashboard.html",
        user=current_user(),
        supplier=s,
        product_count=product_count,
        recent_products=recent_products,
    )


@app.route("/supplier/products")
@supplier_required
def supplier_products():
    s = _current_supplier()
    if not s:
        return redirect(url_for("supplier_dashboard"))
    with get_db() as c:
        rows = c.execute(
            "SELECT ec.*, pc.name AS category_name "
            "FROM equipment_catalog ec "
            "LEFT JOIN product_categories pc ON pc.id=ec.category_id "
            "WHERE ec.supplier_id=? ORDER BY ec.created_at DESC",
            (s["id"],),
        ).fetchall()
    return render_template(
        "supplier_products.html",
        user=current_user(),
        supplier=s,
        products=rows,
    )


@app.route("/supplier/products/add", methods=["GET", "POST"])
@supplier_required
def supplier_product_add():
    s = _current_supplier()
    if not s:
        return redirect(url_for("supplier_dashboard"))
    with get_db() as c:
        categories = c.execute(
            "SELECT id, name FROM product_categories "
            "WHERE is_active=1 ORDER BY display_order"
        ).fetchall()
    if request.method == "GET":
        return render_template(
            "supplier_product_add.html",
            user=current_user(),
            supplier=s,
            categories=categories,
        )
    csrf_protect()
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        flash("Product name is required.", "danger")
        return redirect(url_for("supplier_product_add"))
    cat_id = _safe_int(f.get("category_id"), 0)
    # Look up the legacy free-text category label for backward compatibility
    # with solar's BOQ generator (it queries equipment_catalog.category by string).
    with get_db() as c:
        cat_row = c.execute(
            "SELECT name FROM product_categories WHERE id=?", (cat_id,)
        ).fetchone()
        cat_label = cat_row["name"] if cat_row else ""
        c.execute(
            "INSERT INTO equipment_catalog (category, name, brand, model, spec, unit, "
            "price_usd, supplier_id, lead_time_days, category_id, subcategory, "
            "is_public_visible, is_verified) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                cat_label,
                name,
                (f.get("brand") or "").strip(),
                (f.get("model") or "").strip(),
                (f.get("spec") or "").strip(),
                (f.get("unit") or "No.").strip(),
                _safe_int(f.get("price_usd"), 0),
                s["id"],
                _safe_int(f.get("lead_time_days"), 30),
                cat_id,
                (f.get("subcategory") or "").strip(),
                1 if s["is_verified"] else 0,  # publicly visible only if supplier is verified
                0,  # new products start unverified; admin or LLM agent approves
            ),
        )
    flash(f"Added '{name}'. It will appear on the public marketplace after admin verification.", "success")
    return redirect(url_for("supplier_products"))
