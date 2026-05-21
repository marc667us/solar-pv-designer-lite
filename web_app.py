# -*- coding: utf-8 -*-
"""
Intelligent Global PV Solar System Design Platform
Flask web application — complete engineering + financial SaaS
"""
import os, json, math, sqlite3, csv, secrets, io
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify, make_response, abort, send_file)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from config.global_solar_data import (GLOBAL_DATA, get_countries, get_regions,
                                      get_solar_data, temp_derating)
from calculation.ac_cable_sizing import size_all_cables

# Load .env file if present (stable SECRET_KEY across restarts)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config.update(
    TEMPLATES_AUTO_RELOAD  = True,
    SESSION_COOKIE_HTTPONLY= True,
    SESSION_COOKIE_SAMESITE= "Lax",
    SESSION_COOKIE_SECURE  = False,   # works over both http and https tunnels
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8),
)

# ─── Rate limiter ──────────────────────────────────────────────────────────────
def _get_real_ip():
    """Use X-Forwarded-For when behind serveo/proxy, else remote address."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr

limiter = Limiter(
    _get_real_ip,
    app=app,
    default_limits=["600 per hour", "120 per minute"],
    storage_uri="memory://",
)

# ─── Security headers (applied after every response) ──────────────────────────
@app.after_request
def set_security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"]        = "SAMEORIGIN"
    resp.headers["X-XSS-Protection"]       = "1; mode=block"
    resp.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    resp.headers["Cache-Control"]          = "no-store, no-cache, must-revalidate"
    return resp

# ─── CSRF protection ───────────────────────────────────────────────────────────
def generate_csrf():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(24)
    return session["_csrf"]

def csrf_protect():
    """Call at top of POST handlers that mutate state."""
    if request.method == "POST":
        token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("_csrf"):
            abort(403)

app.jinja_env.globals["csrf_token"] = generate_csrf
app.jinja_env.globals["enumerate"]  = enumerate

DB_PATH = os.path.join(os.path.dirname(__file__), "solar_web.db")

# ─── Phase 4 config ───────────────────────────────────────────────────────────

STRIPE_SECRET    = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK   = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICES    = {
    "basic":        os.environ.get("STRIPE_PRICE_BASIC", ""),
    "professional": os.environ.get("STRIPE_PRICE_PROFESSIONAL", ""),
    "enterprise":   os.environ.get("STRIPE_PRICE_ENTERPRISE", ""),
}
PAYSTACK_SECRET  = os.environ.get("PAYSTACK_SECRET_KEY", "")
PAYSTACK_PUBLIC  = os.environ.get("PAYSTACK_PUBLIC_KEY", "")

# ─── Free / demo mode & SMTP ──────────────────────────────────────────────────
# DEMO_MODE=true lets any user instantly activate a Professional plan for
# testing — no payment API calls required.
DEMO_MODE   = os.environ.get("DEMO_MODE", "true").lower() in ("1", "true", "yes")
DEMO_DAYS   = int(os.environ.get("DEMO_DAYS", "14"))

SMTP_HOST   = os.environ.get("SMTP_HOST", "")
SMTP_PORT   = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER   = os.environ.get("SMTP_USER", "")
SMTP_PASS   = os.environ.get("SMTP_PASS", "")
SMTP_FROM   = os.environ.get("SMTP_FROM", "noreply@solarproglobal.com")
SMTP_TLS    = os.environ.get("SMTP_TLS", "true").lower() in ("1", "true", "yes")

PLAN_PRICES = {
    "basic":        {"usd": 9,  "label": "Basic",        "projects": 5,
                     "features": ["5 projects","All calculations","All PDF reports","Email support","Excel & CSV export"]},
    "professional": {"usd": 29, "label": "Professional", "projects": 20,
                     "features": ["20 projects","Priority support","Excel & CSV export","Multi-currency BOQ","Redesign recommendations"]},
    "enterprise":   {"usd": 99, "label": "Enterprise",   "projects": "Unlimited",
                     "features": ["Unlimited projects","API access","Custom branding","White-label reports","Dedicated engineer support"]},
}

_DEFAULT_APPLIANCES = [
    ("Lighting",    "LED Bulb 9W",               9),
    ("Lighting",    "LED Bulb 15W",              15),
    ("Lighting",    "Fluorescent Tube 36W",      36),
    ("Lighting",    "LED Spotlight 7W",          7),
    ("Lighting",    "Emergency Light 8W",        8),
    ("Cooling",     "Ceiling Fan",               75),
    ("Cooling",     "Standing Fan",              60),
    ("Cooling",     "Air Conditioner 1HP",       745),
    ("Cooling",     "Air Conditioner 1.5HP",     1118),
    ("Cooling",     "Air Conditioner 2HP",       1491),
    ("Cooling",     "Air Conditioner 2.5HP",     1864),
    ("Appliances",  "Refrigerator 200L",         150),
    ("Appliances",  "Refrigerator 300L",         200),
    ("Appliances",  "Chest Freezer 300L",        250),
    ("Appliances",  "Microwave Oven",            1200),
    ("Appliances",  "Electric Kettle",           2000),
    ("Appliances",  "Washing Machine",           500),
    ("Appliances",  "Iron",                      1000),
    ("Appliances",  "Blender",                   350),
    ("Appliances",  "Rice Cooker",               700),
    ("Electronics", "TV 32-inch LED",            50),
    ("Electronics", "TV 43-inch LED",            80),
    ("Electronics", "TV 55-inch LED",            120),
    ("Electronics", "Desktop Computer",          300),
    ("Electronics", "Laptop",                    65),
    ("Electronics", "Phone Charger",             10),
    ("Electronics", "Wi-Fi Router",              12),
    ("Electronics", "CCTV System 4ch",           40),
    ("Office",      "Printer",                   200),
    ("Office",      "Photocopier",               1500),
    ("Office",      "Server (small)",            400),
    ("Office",      "Projector",                 300),
    ("Pumps",       "Water Pump 0.5HP",          373),
    ("Pumps",       "Water Pump 1HP",            745),
    ("Pumps",       "Submersible Pump 0.5HP",    373),
    ("Pumps",       "Borehole Pump 1HP",         745),
    ("Heating",     "Electric Water Heater 3kW", 3000),
    ("Heating",     "Electric Cooker 4-ring",    6000),
    ("Heating",     "Electric Oven 2kW",         2000),
]

# ─── Database ─────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email    TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name    TEXT DEFAULT '',
            company TEXT DEFAULT '',
            country TEXT DEFAULT '',
            plan    TEXT DEFAULT 'free',
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name    TEXT NOT NULL,
            data_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL,
            subject  TEXT NOT NULL,
            message  TEXT NOT NULL,
            status   TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS ticket_replies (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            is_admin  INTEGER DEFAULT 0,
            message   TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        );
        CREATE TABLE IF NOT EXISTS appliances (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            category     TEXT NOT NULL,
            name         TEXT NOT NULL,
            default_watt INTEGER NOT NULL,
            notes        TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS payments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            gateway      TEXT NOT NULL DEFAULT 'manual',
            plan         TEXT NOT NULL DEFAULT 'free',
            amount_usd   REAL DEFAULT 0,
            currency     TEXT DEFAULT 'USD',
            reference    TEXT DEFAULT '',
            status       TEXT DEFAULT 'success',
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT NOT NULL,
            phone       TEXT DEFAULT '',
            company     TEXT DEFAULT '',
            country     TEXT DEFAULT '',
            interest    TEXT DEFAULT 'residential',
            message     TEXT DEFAULT '',
            source      TEXT DEFAULT 'website',
            status      TEXT DEFAULT 'new',
            notes       TEXT DEFAULT '',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE NOT NULL,
            name        TEXT DEFAULT '',
            status      TEXT DEFAULT 'active',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS news_posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            category    TEXT DEFAULT 'industry',
            is_published INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS suppliers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            country      TEXT DEFAULT '',
            contact_name TEXT DEFAULT '',
            phone        TEXT DEFAULT '',
            email        TEXT DEFAULT '',
            website      TEXT DEFAULT '',
            categories   TEXT DEFAULT '',
            lead_time_days INTEGER DEFAULT 30,
            payment_terms TEXT DEFAULT 'TT 30 days',
            rating       INTEGER DEFAULT 5,
            notes        TEXT DEFAULT '',
            is_active    INTEGER DEFAULT 1,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS equipment_catalog (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            category     TEXT NOT NULL,
            name         TEXT NOT NULL,
            brand        TEXT DEFAULT '',
            model        TEXT DEFAULT '',
            spec         TEXT DEFAULT '',
            unit         TEXT DEFAULT 'No.',
            price_usd    REAL DEFAULT 0,
            supplier_id  INTEGER DEFAULT 0,
            lead_time_days INTEGER DEFAULT 30,
            notes        TEXT DEFAULT '',
            is_active    INTEGER DEFAULT 1,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS email_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            project_id  INTEGER DEFAULT 0,
            recipients  TEXT DEFAULT '',
            subject     TEXT DEFAULT '',
            status      TEXT DEFAULT 'sent',
            error_msg   TEXT DEFAULT '',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS upgrade_codes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT UNIQUE NOT NULL,
            plan        TEXT NOT NULL DEFAULT 'professional',
            duration_days INTEGER DEFAULT 30,
            max_uses    INTEGER DEFAULT 1,
            uses        INTEGER DEFAULT 0,
            created_by  INTEGER DEFAULT 0,
            expires_at  TEXT DEFAULT '',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS assessment_requests (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL,
            phone         TEXT DEFAULT '',
            company       TEXT DEFAULT '',
            country       TEXT DEFAULT '',
            system_type   TEXT DEFAULT 'off-grid',
            system_size_kw REAL DEFAULT 0,
            budget_usd    TEXT DEFAULT '',
            location_desc TEXT DEFAULT '',
            message       TEXT DEFAULT '',
            ai_score      INTEGER DEFAULT 0,
            ai_grade      TEXT DEFAULT '',
            ai_notes      TEXT DEFAULT '',
            pipeline_stage TEXT DEFAULT 'new',
            assigned_to   TEXT DEFAULT '',
            follow_up_date TEXT DEFAULT '',
            source        TEXT DEFAULT 'website',
            status        TEXT DEFAULT 'open',
            created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS installers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name    TEXT NOT NULL,
            contact_name    TEXT NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            phone           TEXT DEFAULT '',
            country         TEXT DEFAULT '',
            regions         TEXT DEFAULT '',
            years_exp       INTEGER DEFAULT 0,
            staff_count     INTEGER DEFAULT 0,
            certifications  TEXT DEFAULT '',
            specialties     TEXT DEFAULT '',
            max_project_kw  REAL DEFAULT 0,
            website         TEXT DEFAULT '',
            notes           TEXT DEFAULT '',
            status          TEXT DEFAULT 'pending',
            ai_grade        TEXT DEFAULT '',
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
    # Migrate older DBs — ignore if column already exists
    for stmt in [
        "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN stripe_customer_id TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN subscription_end TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN system_type TEXT DEFAULT 'residential'",
        "ALTER TABLE leads ADD COLUMN system_size_kw REAL DEFAULT 0",
        "ALTER TABLE leads ADD COLUMN budget_usd TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN ai_score INTEGER DEFAULT 0",
        "ALTER TABLE leads ADD COLUMN ai_grade TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN ai_notes TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN pipeline_stage TEXT DEFAULT 'new'",
        "ALTER TABLE leads ADD COLUMN follow_up_date TEXT DEFAULT ''",
    ]:
        try:
            with get_db() as c:
                c.execute(stmt)
        except Exception:
            pass
    # Seed default users — ensure admin and owner accounts always exist
    _SEED_USERS = [
        ("admin",    "admin@solarpro.global", "Administrator", "SolarAdmin2026!", "enterprise", 1),
        ("marc667us","marc667us@yahoo.com",   "Marc",          "marc667us",       "enterprise", 1),
    ]
    with get_db() as c:
        for uname, email, name, pwd, plan, is_admin in _SEED_USERS:
            exists = c.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
            if not exists:
                c.execute(
                    "INSERT INTO users (username,email,name,password_hash,plan,is_admin) "
                    "VALUES (?,?,?,?,?,?)",
                    (uname, email, name, generate_password_hash(pwd), plan, is_admin))
    # Grant admin to the first registered user if no admins exist yet
    with get_db() as c:
        admins = c.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
        if admins == 0:
            c.execute("UPDATE users SET is_admin=1 WHERE id=(SELECT MIN(id) FROM users)")
    # Seed appliances once
    with get_db() as c:
        if c.execute("SELECT COUNT(*) FROM appliances").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO appliances (category,name,default_watt) VALUES (?,?,?)",
                _DEFAULT_APPLIANCES)
    # Seed default suppliers
    with get_db() as c:
        if c.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0:
            _default_suppliers = [
                ("JinkoSolar International", "China", "Sales Desk", "+86 21 5183 8777",
                 "info@jinkosolar.com", "www.jinkosolar.com", "PV Modules", 45, "TT 30 days", 5),
                ("LONGi Solar", "China", "Export Team", "+86 29 8118 6677",
                 "export@longi-solar.com", "www.longi.com", "PV Modules", 45, "TT 30 days", 5),
                ("Victron Energy", "Netherlands", "Regional Sales", "+31 36 535 9700",
                 "sales@victronenergy.com", "www.victronenergy.com", "Inverters,MPPT", 21, "TT 30 days", 5),
                ("Pylontech", "China", "Sales", "+86 21 5031 9999",
                 "sales@pylontech.com.cn", "www.pylontech.com.cn", "Batteries", 30, "TT 30 days", 5),
                ("Deye Inverter", "China", "Global Sales", "+86 579 8913 0000",
                 "export@deyeinverter.com", "www.deyeinverter.com", "Inverters", 30, "TT 30 days", 4),
                ("BYD Battery", "China", "Energy Storage", "+86 755 8988 8888",
                 "energy@byd.com", "www.byd.com", "Batteries", 45, "LC 60 days", 5),
                ("RS Components", "UK", "Procurement", "+44 1536 444 222",
                 "export@rs-components.com", "www.rs-online.com", "Cables,Protection,Earthing", 14, "Net 30", 4),
                ("Schneider Electric", "France", "Solar Division", "+33 1 41 29 70 00",
                 "solar@schneider-electric.com", "www.se.com", "Protection,Distribution", 21, "Net 30", 5),
            ]
            c.executemany(
                "INSERT INTO suppliers (name,country,contact_name,phone,email,website,categories,"
                "lead_time_days,payment_terms,rating) VALUES (?,?,?,?,?,?,?,?,?,?)",
                _default_suppliers)
    # Seed default equipment catalog
    with get_db() as c:
        if c.execute("SELECT COUNT(*) FROM equipment_catalog").fetchone()[0] == 0:
            sup = {r["name"]: r["id"] for r in
                   c.execute("SELECT id,name FROM suppliers").fetchall()}
            _default_equip = [
                ("PV Modules","JinkoSolar 400 Wp Mono PERC","JinkoSolar","JKM400M-54HL4-V","400 Wp, Mono PERC, IEC 61215","No.",90, sup.get("JinkoSolar International",0),45),
                ("PV Modules","JinkoSolar 450 Wp Mono PERC","JinkoSolar","JKM450M-60HL4-V","450 Wp, Mono PERC, IEC 61215","No.",100, sup.get("JinkoSolar International",0),45),
                ("PV Modules","LONGi 500 Wp Hi-MO5","LONGi","LR4-72HIH-500M","500 Wp, Mono PERC, IEC 61215","No.",115, sup.get("LONGi Solar",0),45),
                ("Inverters","Victron MultiPlus-II 3kVA","Victron","MultiPlus-II 48/3000","3 kVA, 48V, Hybrid, built-in charger","No.",450, sup.get("Victron Energy",0),21),
                ("Inverters","Victron MultiPlus-II 5kVA","Victron","MultiPlus-II 48/5000","5 kVA, 48V, Hybrid, built-in charger","No.",620, sup.get("Victron Energy",0),21),
                ("Inverters","Deye SUN-8K-SG04LP1","Deye","SUN-8K-SG04LP1","8 kW, LV Hybrid, single-phase","No.",780, sup.get("Deye Inverter",0),30),
                ("Batteries","Pylontech US3000C 3.5kWh","Pylontech","US3000C","3.5 kWh LiFePO4, 48V, BMS, stackable","No.",620, sup.get("Pylontech",0),30),
                ("Batteries","BYD Battery-Box Premium HVS 10","BYD","HVS 10.2","10.2 kWh, HV LiFePO4, IP55","No.",1850, sup.get("BYD Battery",0),45),
                ("MPPT","Victron SmartSolar 100/50","Victron","MPPT 100/50","100V 50A MPPT, Bluetooth","No.",120, sup.get("Victron Energy",0),14),
                ("Cables","DC Solar Cable 6mm² (100m)","General","TUV 6mm²","6mm² TÜV 1.8kV DC solar cable, UV-rated","Roll",85, sup.get("RS Components",0),14),
                ("Protection","Schneider iC60N MCB 32A","Schneider","iC60N-32A","32A MCB Type C, 6kA, DIN","No.",12, sup.get("Schneider Electric",0),14),
                ("Earthing","Copper Earth Rod 1.2m","Generic","CER-12","16mm dia copper-clad steel, 1.2m","No.",8, sup.get("RS Components",0),7),
            ]
            c.executemany(
                "INSERT INTO equipment_catalog (category,name,brand,model,spec,unit,price_usd,"
                "supplier_id,lead_time_days) VALUES (?,?,?,?,?,?,?,?,?)",
                _default_equip)
    # Seed default news posts
    with get_db() as c:
        if c.execute("SELECT COUNT(*) FROM news_posts").fetchone()[0] == 0:
            _default_news = [
                ("Global Solar Capacity Hits 2 TW Milestone",
                 "The world has surpassed 2 terawatts of installed solar photovoltaic capacity, a landmark that took decades but accelerated rapidly in recent years. Africa and Southeast Asia are leading new deployment growth.",
                 "industry"),
                ("LiFePO4 Battery Prices Fall 40% — Storage Projects Now More Bankable",
                 "Lithium iron phosphate battery pack prices dropped 40% year-on-year, making solar-plus-storage projects significantly more financially attractive and bankable for commercial and industrial clients.",
                 "market"),
                ("IEC 61215:2021 Update — What Solar Designers Must Know",
                 "The updated IEC 61215 standard introduces new temperature cycling and thermal shock tests for PV modules. Engineers specifying panels should ensure module certifications reference the 2021 edition.",
                 "technology"),
                ("Solar Financing: New Concessional Loan Facilities for Sub-Saharan Africa",
                 "Several development finance institutions have launched new concessional solar loan windows targeting Sub-Saharan Africa. Interest rates as low as 4% are available for projects with bankable engineering documentation.",
                 "policy"),
            ]
            c.executemany(
                "INSERT INTO news_posts (title,content,category) VALUES (?,?,?)",
                _default_news)


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def current_user():
    if "user_id" not in session:
        return None
    with get_db() as c:
        return c.execute("SELECT * FROM users WHERE id=?",
                         (session["user_id"],)).fetchone()


def get_project(pid):
    with get_db() as c:
        row = c.execute("SELECT * FROM projects WHERE id=? AND user_id=?",
                        (pid, session["user_id"])).fetchone()
    if not row:
        return None
    p = dict(row)
    p["data"] = json.loads(p["data_json"] or "{}")
    return p


def save_project_data(pid, data):
    with get_db() as c:
        c.execute("UPDATE projects SET data_json=?, updated_at=? WHERE id=?",
                  (json.dumps(data), datetime.now().isoformat(), pid))


# ─── Equipment specifications ─────────────────────────────────────────────────

# Battery chemistry parameters — per lithium spec document (pv1/)
BATTERY_CHEMISTRY = {
    "LiFePO4": {
        "name":        "Lithium Iron Phosphate (LiFePO4)",
        "dod":         0.90,
        "efficiency":  0.96,
        "cycle_life":  "4,000–8,000 cycles",
        "lifetime_yr": "10–15 years",
        "cell_v":      3.2,
        "temp_range":  "-20°C to +55°C",
        "brands":      "BYD Battery-Box, Pylontech Force H, Dyness BX51100, Sungrow SBH, Huawei Luna2000",
        "sizes_kwh":   [5.12, 10.24, 13.5, 15.36, 20.48, 30.72],
        "usd_per_kwh": 120,
    },
    "NMC": {
        "name":        "Lithium Nickel Manganese Cobalt (NMC)",
        "dod":         0.85,
        "efficiency":  0.95,
        "cycle_life":  "2,000–4,000 cycles",
        "lifetime_yr": "8–12 years",
        "cell_v":      3.7,
        "temp_range":  "-20°C to +45°C",
        "brands":      "LG RESU, Samsung SDI, Panasonic EverVolt",
        "sizes_kwh":   [9.8, 16.0, 19.6],
        "usd_per_kwh": 140,
    },
    "LTO": {
        "name":        "Lithium Titanate (LTO)",
        "dod":         0.95,
        "efficiency":  0.98,
        "cycle_life":  "15,000–30,000 cycles",
        "lifetime_yr": "20–25 years",
        "cell_v":      2.4,
        "temp_range":  "-40°C to +65°C",
        "brands":      "Toshiba SCiB, Microvast, Yabo Power",
        "sizes_kwh":   [10.0, 20.0, 40.0],
        "usd_per_kwh": 210,
    },
}

# PV Panel specification — monocrystalline PERC (IEC 61215)
PANEL_SPEC = {
    "technology":   "Monocrystalline PERC",
    "temp_coeff":   -0.0035,          # %/°C power temperature coefficient
    "standard_wp":  [400, 450, 500, 550],
    "default_wp":   400,
    "eff_pct":      "21–23%",
    "warranty_yr":  "12 yr product / 25 yr linear power",
    "brands":       "JinkoSolar, LONGi Solar, Canadian Solar, Trina Solar, JA Solar",
}

# Inverter brand recommendations by power range
INVERTER_BRANDS = [
    (3,   "Victron MultiPlus-II, Growatt SPF-3000, Deye SUN-3K-SG04LP1"),
    (5,   "Deye SUN-5K-SG04LP1, Growatt SPF-5000, Victron MultiPlus-II 5kVA"),
    (8,   "Sungrow SH8.0RT, Fronius Symo GEN24, Deye SUN-8K"),
    (12,  "Sungrow SH10RT, SMA Sunny Tripower 10, Huawei SUN2000-10KTL"),
    (9999,"Huawei SUN2000-20KTL, SMA Sunny Tripower CORE1, Sungrow SG25CX"),
]

def inverter_brand(inv_kw):
    for threshold, brand in INVERTER_BRANDS:
        if inv_kw <= threshold:
            return brand
    return INVERTER_BRANDS[-1][1]


# ─── Engineering calculations ─────────────────────────────────────────────────

def calc_loads(loads):
    total = 0.0
    for ld in loads:
        w = float(ld.get("wattage", 0))
        q = float(ld.get("quantity", 1))
        h = float(ld.get("hours", 0))
        total += (w * q * h) / 1000
    return round(total, 3)


def calc_pv(daily_kwh, psh, temp_c, panel_wp=400, sys_eff=0.75):
    """Monocrystalline PERC sizing with temperature derating."""
    td  = temp_derating(temp_c)
    eff = sys_eff * td
    pv_kw      = daily_kwh / (psh * eff)
    num_panels = math.ceil(pv_kw * 1000 / panel_wp)
    return round(pv_kw, 3), num_panels, round(td, 4)


def calc_battery(daily_kwh, autonomy=1, chemistry="LiFePO4"):
    """Size lithium battery bank — fewest compact units, chemistry-aware."""
    chem     = BATTERY_CHEMISTRY.get(chemistry, BATTERY_CHEMISTRY["LiFePO4"])
    dod      = chem["dod"]
    eff      = chem["efficiency"]
    required = max((daily_kwh * autonomy) / (dod * eff), 0.1)
    SIZES    = chem["sizes_kwh"]
    MAX_RATIO = 2.0

    best = None
    for size in SIZES:
        n     = max(1, math.ceil(required / size))
        total = n * size
        if n == 1 and total > required * MAX_RATIO and size != SIZES[0]:
            continue
        score = n * 1000 + (total - required)
        if best is None or score < best[0]:
            best = (score, n, size, total)

    _, n, unit_kwh, total = best
    return round(total, 1), n, unit_kwh


def calc_mppt(pv_kw, dc_voltage):
    """Size MPPT charge controller (A) — 1.25× safety factor."""
    i_max = (pv_kw * 1000) / dc_voltage * 1.25
    for size in [20, 30, 40, 50, 60, 80, 100, 120, 150, 200]:
        if size >= i_max:
            return size
    return math.ceil(i_max / 10) * 10


def calc_inverter(daily_kwh, peak_kw=0.0, peak_factor=0.30, safety=1.25):
    """Inverter must satisfy both energy-based sizing and peak demand."""
    from_energy = daily_kwh * peak_factor * safety
    # Must handle connected peak load — inverter rating ≥ peak demand
    inv_kw = max(from_energy, peak_kw * 1.0)
    # Round up to nearest standard size
    for std in [3.0, 5.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 50.0, 100.0]:
        if std >= inv_kw:
            return std
    return round(inv_kw, 2)


def calc_economics(pv_kw, num_panels, bat_kwh, num_bat, inv_kw,
                   daily_kwh, tariff, currency, symbol,
                   cost_usd_kwp, fx_usd, autonomy=1, boq_total_local=None):
    """Full economic analysis: NPV, IRR, payback, DSCR, loan.
    If boq_total_local is provided it is used as CAPEX (more accurate than flat benchmark)."""
    # ── Cost estimation ───────────────────────────────────────────────────────
    equip_usd   = pv_kw * cost_usd_kwp
    install_usd = equip_usd * 0.18
    total_usd   = equip_usd + install_usd
    if boq_total_local is not None:
        total_local   = boq_total_local
        equip_local   = total_local / 1.18
        install_local = total_local - equip_local
    else:
        total_local   = total_usd * fx_usd
        equip_local   = equip_usd * fx_usd
        install_local = install_usd * fx_usd

    DISC  = 0.12
    ESC   = 0.08   # tariff escalation
    DEGRAD= 0.005
    OM_PCT= 0.012
    LIFE  = 25

    annual_kwh = daily_kwh * 365
    annual_sav = annual_kwh * tariff
    om_yr1     = total_local * OM_PCT
    net_yr1    = annual_sav - om_yr1
    payback    = total_local / net_yr1 if net_yr1 > 0 else float("inf")
    co2_yr     = annual_kwh * 0.40 / 1000   # tonnes CO2

    # Cash flows
    cashflows  = [-total_local]
    npv        = -total_local
    cumul      = -total_local
    breakeven  = None
    cf_rows    = []

    for yr in range(1, LIFE + 1):
        degraded  = annual_kwh * ((1 - DEGRAD) ** yr)
        esc_tarif = tariff * ((1 + ESC) ** yr)
        gross     = degraded * esc_tarif
        om        = om_yr1 * ((1 + 0.05) ** yr)
        net       = gross - om
        disc      = net / ((1 + DISC) ** yr)
        cumul    += net
        npv      += disc
        cashflows.append(net)
        if cumul >= 0 and breakeven is None:
            breakeven = yr
        cf_rows.append({"yr": yr, "gross": gross, "om": om,
                        "net": net, "cumul": cumul, "npv_c": npv})

    cumul_10 = sum(r["net"] for r in cf_rows[:10])
    cumul_25 = sum(r["net"] for r in cf_rows)
    roi_pct  = (cumul_25 / total_local) * 100

    # IRR (Newton-Raphson)
    irr = _irr(cashflows)

    # ── Loan / funding analysis ───────────────────────────────────────────────
    loan_pct   = 0.70
    loan_amt   = total_local * loan_pct
    equity     = total_local - loan_amt
    rate       = 0.15
    tenor_yr   = 7
    n          = tenor_yr * 12
    r_m        = rate / 12
    pmt        = loan_amt * (r_m * (1+r_m)**n) / ((1+r_m)**n - 1) if r_m else loan_amt/n
    annual_pmt = pmt * 12
    dscr       = net_yr1 / annual_pmt if annual_pmt > 0 else 0

    sym = symbol
    if dscr >= 1.25:
        bankability  = "BANKABLE"
        bank_color   = "#34d399"
        bank_reasons = [
            f"DSCR {dscr:.2f} meets lender minimum of 1.25",
            f"Annual savings ({sym} {net_yr1:,.0f}) comfortably cover debt service ({sym} {annual_pmt:,.0f}/yr)",
            "Cash flow is adequate for commercial loan repayment",
        ]
    elif dscr >= 1.0:
        bankability  = "MARGINAL"
        bank_color   = "#fbbf24"
        bank_reasons = [
            f"DSCR {dscr:.2f} is below lender minimum of 1.25 — additional security likely required",
            f"Net savings ({sym} {net_yr1:,.0f}/yr) barely cover debt service ({sym} {annual_pmt:,.0f}/yr)",
            "Lender may require additional collateral or personal guarantee",
            "Consider increasing equity contribution to reduce loan amount and improve DSCR",
            f"Increasing equity by 15% would reduce annual debt service to ~{sym} {annual_pmt*0.85:,.0f}",
        ]
    else:
        bankability  = "NOT BANKABLE"
        bank_color   = "#f87171"
        bank_reasons = [
            f"DSCR {dscr:.2f} is below 1.00 — savings CANNOT cover loan repayments",
            f"Annual debt service ({sym} {annual_pmt:,.0f}) exceeds net savings ({sym} {net_yr1:,.0f})",
            f"Shortfall of {sym} {annual_pmt - net_yr1:,.0f} per year would require additional income",
            "No commercial bank will finance this project at standard terms",
            "Solutions: increase tariff savings, reduce system cost, extend loan tenor, or increase self-funding",
            f"Breakeven requires savings to increase by {((annual_pmt/net_yr1)-1)*100:.0f}% or cost to fall by {(1-(net_yr1/annual_pmt))*100:.0f}%",
        ]

    if payback <= 8 and npv > 0:
        verdict = "APPROVED"
        v_color = "#34d399"
        verdict_reasons = [
            f"Payback of {payback:.1f} years is within the 8-year benchmark",
            f"Positive NPV of {sym} {npv:,.0f} confirms the project creates value",
            (f"IRR of {irr*100:.1f}% exceeds typical discount rate" if irr else "Strong positive returns"),
            f"25-year cumulative net return: {sym} {cumul_25:,.0f}",
        ]
    elif payback <= 15:
        verdict = "CONDITIONAL"
        v_color = "#fbbf24"
        verdict_reasons = [
            f"Payback of {payback:.1f} years exceeds the 8-year preferred threshold",
            f"NPV is {'positive (' + sym + str(int(npv)) + ')' if npv > 0 else 'negative (' + sym + str(int(npv)) + ') — project may not create value'}",
            "Approval subject to: verified tariff data, full engineering review, financing confirmation",
            "Consider reducing system cost, extending analysis period, or improving tariff assumptions",
            f"If tariff increases by 10%, payback improves to ~{payback*0.91:.1f} years",
        ]
    else:
        verdict = "REJECTED"
        v_color = "#f87171"
        verdict_reasons = [
            f"Payback of {payback:.1f} years exceeds the 15-year maximum threshold",
            f"NPV of {sym} {npv:,.0f} — the project does not create economic value at current assumptions",
            f"Annual savings of {sym} {annual_sav:,.0f} are insufficient relative to the {sym} {total_local:,.0f} investment",
            "The project fails minimum investment return criteria",
            "Recommendations: (1) Reduce system cost, (2) Negotiate better tariff, (3) Reduce load and system size, (4) Seek grant/subsidy funding",
        ]

    return {
        "total_local": total_local,
        "equip_local": equip_local,
        "install_local": install_local,
        "annual_kwh": annual_kwh,
        "annual_sav": annual_sav,
        "om_yr1": om_yr1,
        "net_yr1": net_yr1,
        "payback": payback,
        "npv": npv,
        "irr_pct": irr * 100 if irr else None,
        "roi_pct": roi_pct,
        "breakeven": breakeven,
        "co2_yr": co2_yr,
        "cumul_10": cumul_10,
        "cumul_25": cumul_25,
        "cf_rows": cf_rows,
        "loan_amt": loan_amt,
        "equity": equity,
        "pmt": pmt,
        "annual_pmt": annual_pmt,
        "dscr": dscr,
        "bankability":   bankability,
        "bank_color":    bank_color,
        "bank_reasons":  bank_reasons,
        "verdict":       verdict,
        "v_color":       v_color,
        "verdict_reasons": verdict_reasons,
        "currency": currency,
        "symbol": symbol,
        "tariff": tariff,
    }


def _irr(cashflows, guess=0.10, tol=1e-6, max_iter=100):
    """Compute IRR using Newton-Raphson method."""
    r = guess
    for _ in range(max_iter):
        npv = sum(cf / (1+r)**t for t, cf in enumerate(cashflows))
        dnpv = sum(-t * cf / (1+r)**(t+1) for t, cf in enumerate(cashflows))
        if abs(dnpv) < 1e-12:
            break
        r_new = r - npv / dnpv
        if abs(r_new - r) < tol:
            return r_new
        r = r_new
    return r if -1 < r < 10 else None


def calc_recommendations(eco, d, r):
    """Generate prioritised redesign recommendations to fix rejected/non-bankable projects."""
    if eco["verdict"] == "APPROVED" and eco["bankability"] == "BANKABLE":
        return []

    recs     = []
    sym      = d.get("symbol", "$")
    payback  = eco.get("payback", 99)
    dscr     = eco.get("dscr", 0)
    net_yr1  = eco.get("net_yr1", 0)
    total    = eco.get("total_local", 0)
    ann_pmt  = eco.get("annual_pmt", eco.get("ann_pmt", 0))   # key was renamed; support both
    ann_kwh  = eco.get("annual_kwh", 0)
    tariff   = d.get("tariff", 0)
    autonomy = d.get("autonomy", 1)
    voltage  = d.get("voltage", 48)
    panel_wp = r.get("panel_wp", 400)

    # 1 ─ Reduce system size / load (most impactful for high payback)
    if payback > 10:
        reduce = min(35, max(15, int((payback - 8) / payback * 85)))
        new_cost = total * (1 - reduce / 100)
        new_pb   = new_cost / net_yr1 if net_yr1 > 0 else payback
        recs.append({
            "priority": 1, "icon": "bi-arrows-collapse", "color": "#f59e0b",
            "title":  f"Reduce System Size by {reduce}%",
            "action": f"Implement energy efficiency measures (LED lighting, efficient appliances, load "
                      f"scheduling) to cut daily consumption by {reduce}%, then downsize the PV array "
                      f"and battery bank proportionally.",
            "impact": f"System cost falls to ~{sym} {new_cost:,.0f}. "
                      f"Payback improves from {payback:.1f} yr to ~{new_pb:.1f} yr.",
            "category": "Design",
        })

    loan_amt = eco.get("loan_amt", 0)
    equity   = eco.get("equity", 0)
    pmt      = eco.get("pmt", 0)
    om_yr1   = eco.get("om_yr1", 0)
    co2_yr   = eco.get("co2_yr", 0)

    # 2 ─ Increase equity to achieve DSCR ≥ 1.25
    if dscr < 1.25 and ann_pmt > 0 and loan_amt > 0:
        loan_factor  = ann_pmt / loan_amt
        needed_pmt   = net_yr1 / 1.25
        needed_loan  = needed_pmt / loan_factor if loan_factor > 0 else 0
        new_eq_pct   = max(0, (total - needed_loan) / total * 100) if total > 0 else 0
        new_eq_amt   = total * new_eq_pct / 100
        if new_eq_pct <= 70:
            recs.append({
                "priority": 1, "icon": "bi-cash-stack", "color": "#22c55e",
                "title":  f"Increase Equity Contribution to {new_eq_pct:.0f}%",
                "action": f"Raise own-equity from 30% ({sym} {equity:,.0f}) to "
                          f"{new_eq_pct:.0f}% ({sym} {new_eq_amt:,.0f}) to reduce the loan "
                          f"amount and annual debt service.",
                "impact": f"Annual debt service reduces to {sym} {needed_pmt:,.0f}/yr. "
                          f"DSCR improves to 1.25 — project becomes BANKABLE.",
                "category": "Finance",
            })

    # 3 ─ Extend loan tenor to 10 years
    if 0.7 <= dscr < 1.25:
        r_m   = 0.15 / 12
        n10   = 10 * 12
        pmt10 = loan_amt * (r_m * (1 + r_m)**n10) / ((1 + r_m)**n10 - 1) if r_m and loan_amt else 0
        apmt10 = pmt10 * 12
        d10    = net_yr1 / apmt10 if apmt10 > 0 else 0
        recs.append({
            "priority": 2, "icon": "bi-calendar-range", "color": "#0ea5e9",
            "title":  "Extend Loan Tenor to 10 Years",
            "action": f"Negotiate with lender to extend repayment period from 7 to 10 years. "
                      f"Monthly repayment drops from {sym} {pmt:,.0f} to {sym} {pmt10:,.0f}.",
            "impact": f"Annual debt service reduces to {sym} {apmt10:,.0f}/yr. "
                      f"DSCR improves to {d10:.2f} "
                      f"({'BANKABLE' if d10 >= 1.25 else 'MARGINAL' if d10 >= 1.0 else 'NOT BANKABLE'}).",
            "category": "Finance",
        })

    # 4 ─ Verify / improve electricity tariff
    if tariff < 0.12 and payback > 10 and ann_kwh > 0:
        needed_tariff = (total / 8 + om_yr1) / ann_kwh
        recs.append({
            "priority": 2, "icon": "bi-receipt", "color": "#a78bfa",
            "title":  "Verify Electricity Tariff & Include Diesel Savings",
            "action": f"Confirm current tariff ({sym}{tariff:.3f}/kWh) is the real commercial rate. "
                      f"If displacing diesel generation, add fuel cost savings (typically $0.25–0.40/kWh "
                      f"equivalent). Use peak Time-of-Use (ToU) rate if applicable.",
            "impact": f"A blended effective tariff of {sym}{needed_tariff:.3f}/kWh achieves an 8-year payback. "
                      f"Including diesel offsets typically doubles the effective tariff.",
            "category": "Revenue",
        })

    # 5 ─ Reduce battery autonomy (if > 1 day)
    if autonomy > 1 and payback > 10:
        bat_cost_share = 0.35
        new_cost = total * (1 - bat_cost_share * (autonomy - 1) / autonomy)
        new_pb   = new_cost / net_yr1 if net_yr1 > 0 else payback
        recs.append({
            "priority": 2, "icon": "bi-battery-half", "color": "#f59e0b",
            "title":  f"Reduce Battery Autonomy from {autonomy} to 1 Day",
            "action": f"Design for 1-day battery autonomy instead of {autonomy} days. "
                      f"For grid-connected or hybrid systems this is sufficient. "
                      f"Use a backup generator for extended outages if needed.",
            "impact": f"Battery bank reduces by ~{(1-1/autonomy)*100:.0f}%. "
                      f"System cost falls to ~{sym} {new_cost:,.0f}. "
                      f"Payback improves to ~{new_pb:.1f} yr.",
            "category": "Design",
        })

    # 6 ─ Upgrade panel wattage
    if panel_wp < 500 and payback > 10:
        saving_pct = (500 - panel_wp) / panel_wp * 0.5  # fewer panels → less BOS cost
        new_cost = total * (1 - saving_pct)
        new_pb   = new_cost / net_yr1 if net_yr1 > 0 else payback
        recs.append({
            "priority": 3, "icon": "bi-sun-fill", "color": "#fbbf24",
            "title":  "Upgrade to 500 Wp High-Efficiency Panels",
            "action": f"Switch from {panel_wp} Wp to 500 Wp TOPCon panels. Fewer panels required "
                      f"({r['num_panels']} → ~{int(r['num_panels']*panel_wp/500)} modules), "
                      f"reducing mounting, cabling, and labour costs.",
            "impact": f"Balance-of-system cost saving ~{saving_pct*100:.0f}%. "
                      f"System cost reduces to ~{sym} {new_cost:,.0f}. "
                      f"Payback improves to ~{new_pb:.1f} yr.",
            "category": "Design",
        })

    # 7 ─ Switch to grid-tied (if off-grid)
    if d.get("system_type") == "off-grid" and payback > 12:
        bat_saving = total * 0.35
        new_cost   = total - bat_saving
        new_pb     = new_cost / net_yr1 if net_yr1 > 0 else payback
        recs.append({
            "priority": 3, "icon": "bi-plug-fill", "color": "#34d399",
            "title":  "Consider Grid-Tied / Hybrid Configuration",
            "action": f"If grid connection is available, eliminate the battery bank and switch to "
                      f"grid-tied or hybrid mode. Export surplus energy and draw from the grid "
                      f"at night or in low-solar periods.",
            "impact": f"Removing batteries saves ~{sym} {bat_saving:,.0f} (35% of capital). "
                      f"System cost falls to ~{sym} {new_cost:,.0f}. "
                      f"Payback improves from {payback:.1f} yr to ~{new_pb:.1f} yr.",
            "category": "Design",
        })

    # 8 ─ Apply for grants / concessional finance
    if eco["verdict"] in ("REJECTED", "CONDITIONAL") or eco["bankability"] in ("NOT BANKABLE", "MARGINAL"):
        grant_pct = 20
        new_cost  = total * (1 - grant_pct / 100)
        new_pb    = new_cost / net_yr1 if net_yr1 > 0 else payback
        recs.append({
            "priority": 3, "icon": "bi-bank", "color": "#34d399",
            "title":  "Apply for Grants, Subsidies & Concessional Finance",
            "action": f"Investigate: (a) Government capital grants (15–30% of cost), "
                      f"(b) Development bank loans at 6–9% vs 15% commercial, "
                      f"(c) Carbon credits under Gold Standard / VCS (~{sym}{co2_yr*15:,.0f}/yr), "
                      f"(d) Green bonds or impact investment at preferential rates.",
            "impact": f"A 20% grant reduces capital to {sym} {new_cost:,.0f}, improving payback to "
                      f"~{new_pb:.1f} yr. Concessional rate (8%) improves DSCR by ~0.4.",
            "category": "Finance",
        })

    recs.sort(key=lambda x: x["priority"])
    return recs


def calc_boq(num_panels, num_bat, inv_kw, pv_kw, bat_kwh,
             unit_bat_kwh, chemistry, mppt_a, cost_usd_kwp, fx_usd,
             panel_wp=400, ac_cables=None, voltage=48, num_strings=1):
    """Generate BOQ — real equipment specs, brands, accurate costing."""
    UPLIFT   = 1.20
    chem     = BATTERY_CHEMISTRY.get(chemistry, BATTERY_CHEMISTRY["LiFePO4"])
    panel_usd = (cost_usd_kwp * pv_kw) / num_panels * 0.55
    bat_usd   = unit_bat_kwh * chem["usd_per_kwh"]
    if inv_kw <= 3:   inv_usd = 320
    elif inv_kw <= 5: inv_usd = 450
    elif inv_kw <= 8: inv_usd = 620
    elif inv_kw <=12: inv_usd = 900
    else:             inv_usd = 1300
    mppt_usd = 60 + mppt_a * 1.8

    def local(usd): return usd * fx_usd

    # ── DC cable sizing ───────────────────────────────────────────────────────
    # String cable: 6 mm² is standard for all residential/commercial PV strings
    # (panel Isc ≈ panel_wp/40 A; TÜV-rated 1.8 kV DC, max 17 A per string)
    dc_str_qty = num_panels * 8          # ≈ 4 m pos + 4 m neg per panel
    dc_str_spec = ("6 mm² Twin-core UV-resistant PV Solar Cable, TÜV 2Pfg1169, "
                   "1.8 kV DC, −40 °C to +90 °C, IEC 62930 — red & black")

    # DC main cable (string combiner → DC isolator → inverter)
    panel_isc_a = panel_wp / 40.0
    total_dc_a  = num_strings * panel_isc_a * 1.25
    _DC = [(20,4),(30,6),(45,10),(60,16),(80,25),(120,35),(999,50)]
    dc_main_mm2 = next(s for lim,s in _DC if total_dc_a <= lim)
    dc_main_qty = 35                     # combiner-to-inverter run + slack
    dc_main_spec = (f"{dc_main_mm2} mm² Twin-core UV-resistant PV Solar Cable, "
                    f"TÜV 1.8 kV DC — {num_strings} strings × {panel_isc_a:.0f} A Isc, "
                    f"design current {total_dc_a:.0f} A (incl. 1.25 × safety factor)")

    # Battery DC cable (battery bank → inverter DC bus)
    bat_a   = inv_kw * 1000 / max(voltage, 12) * 1.25
    _BAT = [(40,10),(65,16),(100,25),(150,35),(200,50),(999,70)]
    bat_mm2 = next(s for lim,s in _BAT if bat_a <= lim)
    bat_qty = num_bat * 3 + 5
    bat_spec = (f"{bat_mm2} mm² Flexible Multi-strand Cu, PVC 105 °C, 1 kV DC — "
                f"{voltage} V bus, design current {bat_a:.0f} A, "
                f"ANL fuse-protected per string — red & black")

    # ── Items list (non-cable) ────────────────────────────────────────────────
    items = [
        ("PV Modules — Mono PERC",
         f"{num_panels} × {panel_wp} Wp | {PANEL_SPEC['brands'].split(',')[0].strip()}",
         num_panels, "No.", local(panel_usd)),
        ("Hybrid Inverter / Charger",
         f"{inv_kw:.1f} kW | {inverter_brand(inv_kw).split(',')[0].strip()}",
         1, "No.", local(inv_usd)),
        (f"Battery — {chemistry}",
         f"{unit_bat_kwh:.4g} kWh compact unit | {chem['brands'].split(',')[0].strip()}",
         num_bat, "No.", local(bat_usd)),
        ("MPPT Charge Controller",
         f"{mppt_a} A | Victron BlueSolar / Epever",
         1, "No.", local(mppt_usd)),
        ("PV Mounting Structure",
         "Aluminium rail system + clamps, IEC 61215",
         num_panels, "No.", local(18)),
        ("DC Combiner / String Box",
         f"{min(num_strings,4)}-string, 15 A DC fuses, DC SPD Type 2, IP65, IEC 61173",
         1, "No.", local(48)),
        # ── DC Cables ─────────────────────────────────────────────────────────
        ("DC String Cable — 6 mm²", dc_str_spec, dc_str_qty, "m", local(1.5)),
        (f"DC Main Cable — {dc_main_mm2} mm²", dc_main_spec, dc_main_qty, "m", local(1.8 + dc_main_mm2 * 0.04)),
        (f"Battery DC Cable — {bat_mm2} mm²", bat_spec, bat_qty, "m", local(2.2 + bat_mm2 * 0.05)),
        ("Earthing Cable — 16 mm² G/Y",
         "16 mm² Green/Yellow Cu PVC, main earthing conductor, BS 7430 / IEC 60364-5-54",
         15, "m", local(1.8)),
        ("Bonding Cable — 6 mm² G/Y",
         "6 mm² Green/Yellow Cu PVC, panel frame & equipment bonding, BS 7671 Ch.54",
         int(num_panels * 3), "m", local(1.2)),
        ("DC MCB / Isolator",
         "DC-rated, 1000 V, BS EN 60947-2",
         4, "No.", local(4.0)),
    ]

    # ── AC Cables — per sized circuit ─────────────────────────────────────────
    if ac_cables:
        for c in ac_cables:
            sz  = c["cable_size_mm2"]
            brk = c["breaker_a"]
            vd  = c["vd_percent"]
            Im  = c.get("install_method", "C")
            ph  = c.get("phase", "single")
            Ib  = c.get("design_current", 0)
            cores = "3-core" if ph == "three" else "2-core + E"
            if sz <= 16:
                insul = f"Cu PVC 70 °C, BS EN 50525-2-31, Method {Im}"
            else:
                insul = f"Cu XLPE/SWA/PVC, BS 5467, 0.6/1 kV, Method {Im}"
            spec = (f"{sz} mm² {cores} {insul} | "
                    f"Ib={Ib:.1f} A, {brk} A MCB/RCCB | VD={vd:.2f}%")
            qty  = c["length_m"] + 5
            rate = local(1.2 + sz * 0.06)
            items.append((f"AC Cable — {c['circuit']}", spec, qty, "m", rate))
    else:
        items.append(("AC Cables — All Circuits",
                      "Cu PVC/XLPE, BS EN 50525 / BS 5467 (sizes per cable schedule)",
                      25, "m", local(1.5)))

    items += [
        ("AC RCCB + MCBs",
         "30 mA RCCB (BS EN 61008 Type A) + 6 × MCB (BS EN 60898), 6 kA",
         1, "Set", local(55)),
        ("Surge Protection Device",
         "DC Type 2 (IEC 61643-31, 1000 VDC) + AC Type 2 (BS EN 61643, 230/415 V)",
         2, "No.", local(22)),
        ("Earthing & Bonding Kit",
         "2 × 16 mm dia. Cu earth rod 2.4 m, rod driver, clamps, earth busbar — BS 7430",
         1, "Set", local(35)),
        ("Battery Enclosure / Rack",
         "IP44 powder-coated steel rack, ventilated, lockable",
         1, "No.", local(55)),
        ("Cable Trunking & Conduit",
         "20 mm & 32 mm metallic conduit + 50×50 mm galvanised steel trunking",
         1, "Lot", local(60)),
        ("Hardware, Fixings & Misc",
         "MC4 connectors (IP67, 1000 VDC), cable ties, glands, labels, consumables",
         1, "Lot", local(42)),
    ]

    rows = []
    grand = 0.0
    for no, (desc, spec, qty, unit, basic) in enumerate(items, 1):
        total_r = basic * UPLIFT
        amount  = qty * total_r
        grand  += amount
        rows.append({"no": no, "desc": desc, "spec": spec, "qty": qty,
                     "unit": unit, "basic": basic, "total_r": total_r,
                     "amount": amount})
    return rows, grand


# ─── Routes — Auth ────────────────────────────────────────────────────────────

@app.route("/")
def landing():
    with get_db() as c:
        news = c.execute(
            "SELECT * FROM news_posts WHERE is_published=1 ORDER BY created_at DESC LIMIT 3"
        ).fetchall()
    return render_template("landing.html", user=current_user(),
                           countries=get_countries(), news_posts=news)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if request.method == "POST":
        csrf_protect()
        f = request.form
        ph = generate_password_hash(f["password"])
        try:
            with get_db() as c:
                # All new signups begin on 'free' plan — upgrade later
                c.execute(
                    "INSERT INTO users (username,email,password_hash,name,company,country,plan) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (f["username"], f["email"], ph,
                     f.get("name",""), f.get("company",""),
                     f.get("country",""), "free"))
                uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            session["user_id"] = uid
            session["username"] = f["username"]
            flash("Welcome! Your account is ready.", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("Username or email already registered.", "danger")
    return render_template("auth.html", mode="register",
                           countries=get_countries())


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("60 per hour")
def login():
    if request.method == "POST":
        csrf_protect()
        username = request.form["username"]
        password = request.form["password"]
        with get_db() as c:
            user = c.execute("SELECT * FROM users WHERE username=?",
                             (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ─── Routes — Dashboard ───────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    plan = (user["plan"] or "free").lower()
    uid  = session["user_id"]
    with get_db() as c:
        raw_projects = c.execute(
            "SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC",
            (uid,)).fetchall()
        open_tickets = c.execute(
            "SELECT COUNT(*) FROM tickets WHERE user_id=? AND status='open'",
            (uid,)).fetchone()[0]
        emails_sent  = c.execute(
            "SELECT COUNT(*) FROM email_logs WHERE user_id=? AND status='sent'",
            (uid,)).fetchone()[0]

    # Enrich each project with parsed snapshot data
    projects = []
    total_kwp = 0.0
    total_kwh = 0.0
    for p in raw_projects:
        d   = json.loads(p["data_json"] or "{}")
        r   = d.get("results", {})
        eco = r.get("economics", {})
        # Determine completion stage
        stage = "new"
        if r:
            stage = "results"
        elif d.get("loads"):
            stage = "loads"
        elif d.get("location") or d.get("country"):
            stage = "location"
        total_kwp += r.get("pv_kw", 0)
        total_kwh += r.get("bat_kwh", 0)
        projects.append({
            "id":        p["id"],
            "name":      p["name"],
            "created":   (p["created_at"] or "")[:10],
            "updated":   (p["updated_at"] or "")[:16].replace("T", " "),
            "country":   d.get("country", ""),
            "location":  d.get("location", ""),
            "system_type": d.get("system_type", "off-grid"),
            "phase":     d.get("phase", "single"),
            "pv_kw":     round(r.get("pv_kw", 0), 2),
            "bat_kwh":   round(r.get("bat_kwh", 0), 1),
            "inv_kw":    round(r.get("inv_kw", 0), 1),
            "num_panels":r.get("num_panels", 0),
            "verdict":   eco.get("verdict", ""),
            "bankability":eco.get("bankability", ""),
            "payback":   eco.get("payback", 0),
            "total_local":eco.get("total_local", 0),
            "symbol":    d.get("symbol", "$"),
            "stage":     stage,
        })

    limit    = PLAN_LIMITS.get(plan, 1)
    at_limit = len(projects) >= limit
    return render_template("dashboard.html", user=user, projects=projects,
                           plan=plan, limit=limit, at_limit=at_limit,
                           open_tickets=open_tickets, emails_sent=emails_sent,
                           total_kwp=round(total_kwp, 1),
                           total_kwh=round(total_kwh, 1))


# ─── Routes — Project ─────────────────────────────────────────────────────────

PLAN_LIMITS = {"free": 1, "basic": 5, "professional": 20, "enterprise": 9999}

@app.route("/project/new", methods=["GET", "POST"])
@login_required
def project_new():
    user = current_user()
    plan = (user["plan"] or "free").lower()
    limit = PLAN_LIMITS.get(plan, 1)
    with get_db() as c:
        count = c.execute(
            "SELECT COUNT(*) FROM projects WHERE user_id=?",
            (session["user_id"],)).fetchone()[0]
    if count >= limit:
        flash(
            f"Your {plan.title()} plan allows up to {limit} project{'s' if limit>1 else ''}. "
            f"Upgrade to create more.", "warning")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        csrf_protect()
        name = request.form.get("name", "New Project")
        with get_db() as c:
            c.execute("INSERT INTO projects (user_id, name) VALUES (?,?)",
                      (session["user_id"], name))
            pid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        return redirect(url_for("project_location", pid=pid))
    u = current_user()
    sales_data = None
    if u and u["is_admin"]:
        with get_db() as c:
            sales_data = {
                "new_leads":  c.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0],
                "total_leads":c.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
                "subs":       c.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE status='active'").fetchone()[0],
                "total_rev":  c.execute("SELECT SUM(amount_usd) FROM payments WHERE status='success'").fetchone()[0] or 0,
                "paid_users": c.execute("SELECT COUNT(*) FROM users WHERE plan NOT IN ('free','demo') AND plan IS NOT NULL").fetchone()[0],
                "recent_leads": c.execute("SELECT name,email,company,interest,status,created_at FROM leads ORDER BY created_at DESC LIMIT 5").fetchall(),
            }
    return render_template("project_new.html", user=u,
                           plan=plan, limit=limit, count=count,
                           sales_data=sales_data)


@app.route("/project/<int:pid>/location", methods=["GET", "POST"])
@login_required
def project_location(pid):
    project = get_project(pid)
    if not project:
        flash("Project not found.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        csrf_protect()
        f = request.form
        country = f["country"]
        region  = f["region"]
        sd = get_solar_data(country, region)
        if not sd:
            flash("Invalid location selection.", "danger")
            return redirect(url_for("project_location", pid=pid))
        data = project["data"]
        data.update({
            "country": country, "region": region,
            "psh": sd["psh"], "avg_temp": sd["avg_temp"],
            "tariff": float(f.get("tariff", sd["tariff"])),
            "currency": sd["currency"], "symbol": sd["symbol"],
            "cost_usd_kwp": sd["cost_usd_kwp"], "fx_usd": sd["fx_usd"],
            "system_type": f.get("system_type", "off-grid"),
            "phase":       f.get("phase", "single"),
            "voltage":     int(f.get("voltage", 48)),
            "autonomy":    int(f.get("autonomy", 1)),
            "chemistry":      f.get("chemistry", "LiFePO4"),
            "panel_wp":       int(f.get("panel_wp", 400)),
            "mounting_type":  f.get("mounting_type", "rooftop_pitched"),
        })
        save_project_data(pid, data)
        return redirect(url_for("project_loads", pid=pid))

    return render_template("location.html", user=current_user(),
                           project=project, countries=get_countries(),
                           global_data=GLOBAL_DATA,
                           battery_chemistries=list(BATTERY_CHEMISTRY.keys()),
                           panel_options=PANEL_SPEC["standard_wp"])


@app.route("/project/<int:pid>/loads", methods=["GET", "POST"])
@login_required
def project_loads(pid):
    project = get_project(pid)
    if not project:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        csrf_protect()
        loads = []
        names    = request.form.getlist("load_name[]")
        cats     = request.form.getlist("load_cat[]")
        watts    = request.form.getlist("load_watt[]")
        qtys     = request.form.getlist("load_qty[]")
        hours    = request.form.getlist("load_hours[]")
        critical = request.form.getlist("load_critical[]")

        for i in range(len(names)):
            if not names[i].strip():
                continue
            loads.append({
                "name":     names[i],
                "category": cats[i] if i < len(cats) else "Other",
                "wattage":  float(watts[i]) if i < len(watts) else 0,
                "quantity": float(qtys[i]) if i < len(qtys) else 1,
                "hours":    float(hours[i]) if i < len(hours) else 0,
                "critical": str(i) in critical or names[i] in critical,
            })

        if not loads:
            flash("Please add at least one load.", "warning")
            return redirect(url_for("project_loads", pid=pid))

        data = project["data"]
        data["loads"] = loads

        # Connected peak load (wattage × qty, no hours — simultaneous demand)
        peak_kw = sum(
            float(ld.get("wattage", 0)) * float(ld.get("quantity", 1))
            for ld in loads
        ) / 1000.0

        # Auto phase selection: > 8 kW connected load → 3-phase (BS 7671 / IEC 60364)
        auto_phase = "three" if peak_kw > 8.0 else "single"
        prev_phase = data.get("phase", "single")
        if auto_phase != prev_phase:
            if auto_phase == "three":
                flash(
                    f"Phase automatically set to 3-phase 415V — connected peak load "
                    f"{peak_kw:.1f} kW exceeds the 8 kW single-phase limit. "
                    f"Single-phase limit: 8 kW (IEC 60364 / BS 7671).",
                    "info"
                )
            else:
                flash(
                    f"Phase set to single-phase 230V — connected peak load "
                    f"{peak_kw:.1f} kW is within single-phase range.",
                    "info"
                )
        data["phase"] = auto_phase

        # Run calculations
        daily_kwh = calc_loads(loads)
        psh       = data.get("psh", 5.0)
        temp      = data.get("avg_temp", 28.0)
        autonomy  = data.get("autonomy", 1)
        system_type = data.get("system_type", "off-grid")
        phase     = auto_phase
        tariff    = data.get("tariff", 2.0)
        currency  = data.get("currency", "USD")
        symbol    = data.get("symbol", "$")
        cost_kwp  = data.get("cost_usd_kwp", 900)
        fx        = data.get("fx_usd", 1.0)

        chemistry  = data.get("chemistry", "LiFePO4")
        dc_voltage = data.get("voltage", 48)
        panel_wp   = data.get("panel_wp", 400)

        pv_kw, num_panels, td      = calc_pv(daily_kwh, psh, temp, panel_wp)
        bat_kwh, num_bat, unit_bat = calc_battery(daily_kwh, autonomy, chemistry)
        inv_kw                     = calc_inverter(daily_kwh, peak_kw=peak_kw)
        mppt_a                     = calc_mppt(pv_kw, dc_voltage)
        ac_cables = size_all_cables(inv_kw, pv_kw, system_type, phase,
                                    ambient_c=temp)
        pps        = 2 if dc_voltage <= 24 else 4 if dc_voltage <= 48 else 8
        num_strings = math.ceil(num_panels / pps)
        # BOQ uses actual AC cable sizes and DC string count
        boq_rows, boq_grand        = calc_boq(
            num_panels, num_bat, inv_kw, pv_kw, bat_kwh,
            unit_bat, chemistry, mppt_a, cost_kwp, fx, panel_wp,
            ac_cables=ac_cables, voltage=dc_voltage, num_strings=num_strings)
        economics                  = calc_economics(
            pv_kw, num_panels, bat_kwh, num_bat, inv_kw,
            daily_kwh, tariff, currency, symbol, cost_kwp, fx, autonomy,
            boq_total_local=boq_grand)

        chem_info = BATTERY_CHEMISTRY.get(chemistry, BATTERY_CHEMISTRY["LiFePO4"])
        data["results"] = {
            "daily_kwh":    daily_kwh,
            "pv_kw":        pv_kw,
            "num_panels":   num_panels,
            "panel_wp":     panel_wp,
            "temp_derating":td,
            "bat_kwh":      bat_kwh,
            "num_bat":      num_bat,
            "unit_bat_kwh": unit_bat,
            "chemistry":    chemistry,
            "chem_name":    chem_info["name"],
            "chem_dod":     chem_info["dod"],
            "chem_cycles":  chem_info["cycle_life"],
            "chem_life":    chem_info["lifetime_yr"],
            "chem_brands":  chem_info["brands"],
            "inv_kw":       inv_kw,
            "inv_brand":    inverter_brand(inv_kw),
            "mppt_a":       mppt_a,
            "peak_kw":      round(peak_kw, 2),
            "auto_phase":   auto_phase,
            "panel_spec":   PANEL_SPEC,
            "economics":    economics,
            "boq_rows":     boq_rows,
            "boq_grand":    boq_grand,
            "ac_cables":    ac_cables,
        }
        save_project_data(pid, data)
        return redirect(url_for("project_results", pid=pid))

    cats = ["Lighting", "Cooling", "Appliances", "Electronics",
            "Pumps", "Heating", "Office", "Other"]
    return render_template("loads.html", user=current_user(),
                           project=project, categories=cats)


@app.route("/project/<int:pid>/results")
@login_required
def project_results(pid):
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        flash("Run load calculations first.", "warning")
        return redirect(url_for("project_loads", pid=pid))
    r    = project["data"]["results"]
    recs = calc_recommendations(r["economics"], project["data"], r)
    return render_template("results.html", user=current_user(),
                           project=project, d=project["data"],
                           r=r, recommendations=recs)


# ─── Routes — Reports ─────────────────────────────────────────────────────────

def _plan_gate(pid):
    """Return (project, user, plan) or redirect if project missing/no results."""
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        flash("Run load calculations first.", "warning")
        return None, None, None
    u    = current_user()
    plan = (u["plan"] or "free").lower()
    return project, u, plan


@app.route("/project/<int:pid>/report/inspection")
@login_required
def report_inspection(pid):
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    return render_template("report_inspection.html", user=current_user(),
                           project=project, d=project["data"],
                           r=project["data"]["results"])


@app.route("/project/<int:pid>/report/inspection/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_inspection(pid):
    """PDF export — Field Inspection Report (available on free plan)."""
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d = project["data"]
    r = project["data"]["results"]
    phase  = d.get("phase", "single")
    v_ac   = 415 if phase == "three" else 230

    def _chk():
        return "☐ Pass  ☐ Fail  ☐ N/A"

    def _section(num, title, items):
        rows = f"\n\n### {num}. {title}\n\n"
        rows += "| # | Inspection Item | Pass | Fail | N/A | Remarks |\n"
        rows += "|---|---|:---:|:---:|:---:|---|\n"
        for i, item in items:
            rows += f"| {num}.{i} | {item} | ☐ | ☐ | ☐ | |\n"
        return rows

    ac_cables = r.get("ac_cables", [])
    first_breaker = ac_cables[0]["breaker_a"] if ac_cables else "—"
    first_cable   = ac_cables[0]["cable_size_mm2"] if ac_cables else "—"

    md = f"""# Pre-Installation Site Assessment - {project["name"]}

*Technical Feasibility Consultation - Prepared prior to installation commitment*

**{d.get("region","")}, {d.get("country","")}** | {d.get("system_type","").title()} System | {_fmt(r["pv_kw"],2)} kWp - {_fmt(r["bat_kwh"],2)} kWh - {_fmt(r["inv_kw"],1)} kW

Prepared by: SolarPro Global | Free Consultation Service | BS 7671:2018 - IEC 60364

---

## Proposed System Overview

| Field | Details |
|---|---|
| Client / Site Name | {project["name"]} |
| Location | {d.get("region","")}, {d.get("country","")} |
| System Type | {d.get("system_type","").title()} |
| Phase | {"Three-Phase 415V" if phase=="three" else "Single-Phase 230V"} |
| Daily Energy Demand | {_fmt(r["daily_kwh"],2)} kWh/day |
| Proposed PV Array | {_fmt(r["pv_kw"],2)} kWp ({r["num_panels"]} x {r.get("panel_wp",400)} Wp) |
| Battery Storage | {_fmt(r["bat_kwh"],2)} kWh - {r["num_bat"]} units {r.get("chemistry","LiFePO4")} |
| Inverter | {_fmt(r["inv_kw"],1)} kW |
| Estimated System Cost | {d.get("symbol","$")} {_fmt(r["economics"]["total_local"],0)} |
| Estimated Payback | {_fmt(r["economics"]["payback"],1)} years |

| Consultant / Engineer | | Assessment Date | | Site Visit Date | |
|---|---|---|---|---|---|
| | | | | | |

---
""" + _section(1, "Site Suitability & Solar Resource", [
        (1, f"Location {d.get('region','')}, {d.get('country','')} has adequate solar irradiance (>= 4 PSH/day)"),
        (2, f"Roof/ground area sufficient for {r['num_panels']} panels (approx. {r['num_panels']*2} m2 minimum)"),
        (3, "Panel orientation achievable - equator-facing surface available"),
        (4, "No permanent shading obstruction between 9am-3pm (buildings, trees, towers)"),
        (5, "Roof pitch >= 10 deg or flat roof with tilt framing available"),
        (6, "No planned construction or tree growth likely to cause future shading"),
        (7, "Access to roof/ground area is safe and adequate for installation and maintenance"),
    ]) + _section(2, "Structural & Roof Assessment", [
        (1, "Roof/structure type identified (concrete slab / IBR metal sheet / clay tile / flat membrane)"),
        (2, "Structure age and condition acceptable for 25-year system life"),
        (3, f"Load capacity adequate - can support ~{r['num_panels']*20} kg PV array weight"),
        (4, f"For ground mount: {r['num_panels']*4} m2 land area available, level and stable"),
        (5, "Existing skylights, vents, or services do not conflict with array footprint"),
        (6, "Roof waterproofing in acceptable condition prior to installation"),
        (7, "No asbestos-containing materials identified in roof structure"),
    ]) + _section(3, "Existing Electrical Infrastructure", [
        (1, "Existing main distribution board (MDB) identified and accessible"),
        (2, "MDB has spare capacity / ways for new solar incomer"),
        (3, "Existing earthing / earth rod present - condition to be tested"),
        (4, f"Current utility connection is {'3-phase 415V' if phase=='three' else 'single-phase 230V'} - matches proposed system"),
        (5, "Available space for inverter and battery bank within equipment room"),
        (6, "Equipment room is dry, secure, and ventilated"),
        (7, "Cable routing path from array to equipment room identified and clear"),
        (8, "Existing wiring checked - no obvious overloads or faults before proceeding"),
    ]) + _section(4, "Load & Demand Validation", [
        (1, f"Daily demand {_fmt(r['daily_kwh'],2)} kWh/day verified against actual utility bills"),
        (2, f"Peak connected load {_fmt(r.get('peak_kw',0),2)} kW confirmed - no major loads omitted"),
        (3, "Critical loads (medical, refrigeration, security) identified for backup priority"),
        (4, "Load profile is reasonably consistent - no major seasonal variation"),
        (5, "Future load growth in next 3-5 years estimated and factored into sizing"),
        (6, f"High-draw appliances (A/C, pumps) confirmed compatible with {_fmt(r['inv_kw'],1)} kW inverter"),
    ]) + _section(5, "Financial Feasibility", [
        (1, f"Client aware of estimated system cost: {d.get('symbol','$')} {_fmt(r['economics']['total_local'],0)}"),
        (2, f"Payback period of {_fmt(r['economics']['payback'],1)} years is acceptable to client"),
        (3, "Funding source confirmed (cash / loan / lease / PPA)"),
        (4, "VAT and import duties on equipment considered in budget"),
        (5, "Client understands O&M obligations (panel cleaning, battery checks, annual inspection)"),
        (6, "Grid connection / utility approval process understood"),
        (7, "Building permit for installation investigated"),
    ]) + _section(6, "Grid Connection & Regulatory", [
        (1, f"Utility grid connection available at site"),
        (2, f"Net metering / feed-in tariff policy investigated for {d.get('country','')}"),
        (3, "Anti-islanding protection required - inverter has built-in function"),
        (4, "Local installation code compliance confirmed (BS 7671 / IEC 60364 / national standard)"),
        (5, "Planning authority notified of proposed installation (if required)"),
    ]) + _section(7, "Health, Safety & Access", [
        (1, "Safe roof access route confirmed - scaffolding / MEWP requirements noted"),
        (2, "Electrical isolation of existing installation possible before work begins"),
        (3, "No asbestos, hazardous materials, or restricted zones on site"),
        (4, "Client / occupants can remain during installation or relocation required"),
        (5, "Fire risk assessed - battery room ventilation and extinguisher provision confirmed"),
    ]) + f"""

---

## Consultant Recommendation

**Overall Site Feasibility:** [ ] FEASIBLE  [ ] FEASIBLE WITH CONDITIONS  [ ] NOT FEASIBLE

Next Steps / Conditions:

_______________________________________________

_______________________________________________

_______________________________________________

---

## Assessment Sign-Off

| | Solar Consultant / Engineer | Client / Site Owner |
|---|---|---|
| **Name** | | |
| **Qualification / Contact** | | |
| **Date** | | |
| **Signature** | | |

*Disclaimer: This pre-installation assessment is based on the load schedule provided and does not substitute for a full on-site survey by a qualified engineer. SolarPro Global accepts no liability for decisions made solely on this report.*

---

*Pre-Installation Site Assessment - SolarPro Global | Free Consultation Service | BS 7671:2018 - IEC 60364*
"""

    return _render_pdf(f"Pre-Installation Site Assessment - {project['name']}", md,
                       f"site_assessment_{project['name'].replace(' ','_')}.pdf")


def _paid_only(pid):
    """Gate: redirect free-plan users to upgrade page."""
    u    = current_user()
    plan = (u["plan"] or "free").lower() if u else "free"
    if plan == "free":
        flash("This report is available on Basic plan and above. Upgrade to access all reports.", "warning")
        return redirect(url_for("upgrade"))
    return None


@app.route("/project/<int:pid>/report/pv")
@login_required
def report_pv(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    return render_template("report_pv.html", user=current_user(),
                           project=project, d=project["data"],
                           r=project["data"]["results"])


@app.route("/project/<int:pid>/report/boq")
@login_required
def report_boq(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    return render_template("report_boq.html", user=current_user(),
                           project=project, d=project["data"],
                           r=project["data"]["results"])


@app.route("/project/<int:pid>/report/cable")
@login_required
def report_cable(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    return render_template("report_cable.html", user=current_user(),
                           project=project, d=project["data"],
                           r=project["data"]["results"])


@app.route("/project/<int:pid>/report/economic")
@login_required
def report_economic(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    r   = project["data"]["results"]
    eco = r["economics"]
    recs = calc_recommendations(eco, project["data"], r)
    return render_template("report_economic.html", user=current_user(),
                           project=project, d=project["data"],
                           r=r, eco=eco, recommendations=recs)


@app.route("/project/<int:pid>/report/installation")
@login_required
def report_installation(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d = project["data"]
    r = project["data"]["results"]
    voltage = d.get("voltage", 48)
    num_panels = r["num_panels"]
    pps = 2 if voltage <= 24 else 4 if voltage <= 48 else 8
    num_strings = math.ceil(num_panels / pps)
    last_str_panels = num_panels - (num_strings - 1) * pps
    phase = d.get("phase", "single")
    v_ac = 415 if phase == "three" else 230
    return render_template("report_installation.html",
                           user=current_user(),
                           project=project, d=d, r=r,
                           pps=pps, num_strings=num_strings,
                           last_str_panels=last_str_panels,
                           v_ac=v_ac)


@app.route("/project/<int:pid>/report/proposal")
@login_required
def report_proposal(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    return render_template("report_proposal.html", user=current_user(),
                           project=project, d=project["data"],
                           r=project["data"]["results"],
                           eco=project["data"]["results"]["economics"])


@app.route("/project/<int:pid>/report/energy")
@login_required
def report_energy(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    r   = project["data"]["results"]
    eco = r["economics"]
    d   = project["data"]
    # Monthly generation breakdown (simple seasonal variation ±10%)
    monthly_factors = [0.88,0.90,0.95,1.00,1.05,1.08,1.10,1.08,1.03,0.98,0.92,0.88]
    base_monthly    = r["daily_kwh"] * 30.44
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly = [{"month": m, "kwh": round(base_monthly * f, 1),
                "saving": round(base_monthly * f * d.get("tariff",1), 1)}
               for m, f in zip(months, monthly_factors)]
    trees_equiv = round(eco["co2_yr"] / 21.77, 0)   # avg tree absorbs ~21.77 kg CO2/yr
    cars_equiv  = round(eco["co2_yr"] / 4600, 2)     # avg car ~4.6 tonne CO2/yr
    return render_template("report_energy.html", user=current_user(),
                           project=project, d=d, r=r, eco=eco,
                           monthly=monthly, trees_equiv=trees_equiv,
                           cars_equiv=cars_equiv)


@app.route("/project/<int:pid>/delete", methods=["POST"])
@login_required
def project_delete(pid):
    csrf_protect()
    with get_db() as c:
        c.execute("DELETE FROM projects WHERE id=? AND user_id=?",
                  (pid, session["user_id"]))
    flash("Project deleted successfully.", "success")
    return redirect(url_for("dashboard"))


# ─── API endpoints (login-required, rate-limited) ─────────────────────────────

@app.route("/api/regions/<country>")
@login_required
@limiter.limit("60 per minute")
def api_regions(country):
    # Validate input — only allow known countries
    if country not in GLOBAL_DATA:
        abort(400)
    return jsonify(get_regions(country))


@app.route("/api/solar/<country>/<region>")
@login_required
@limiter.limit("60 per minute")
def api_solar(country, region):
    if country not in GLOBAL_DATA:
        abort(400)
    sd = get_solar_data(country, region)
    if not sd:
        abort(404)
    return jsonify(sd)


# ─── Export endpoints ─────────────────────────────────────────────────────────

def _xl_header(ws, cols, fill_color="1e1e3a", font_color="F59E0B"):
    fill = PatternFill("solid", fgColor=fill_color)
    font = Font(bold=True, color=font_color)
    for col, (header, width) in enumerate(cols, 1):
        c = ws.cell(row=1, column=col, value=header)
        c.fill = fill; c.font = font
        c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[c.column_letter].width = width

def _xl_send(wb, filename):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=filename)


@app.route("/project/<int:pid>/export/excel")
@login_required
@limiter.limit("10 per minute")
def export_excel(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        flash("Run calculations first.", "warning")
        return redirect(url_for("project_results", pid=pid))

    r   = project["data"]["results"]
    eco = r["economics"]
    d   = project["data"]
    sym = d.get("symbol", "$")
    wb  = openpyxl.Workbook()

    # ── Sheet 1: Summary ──────────────────────────────────────────────────────
    ws = wb.active; ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    title_font = Font(bold=True, size=14, color="F59E0B")
    ws["A1"] = "SolarPro Global — Project Summary"; ws["A1"].font = title_font
    ws["A2"] = project["name"]
    ws["A3"] = f"{d.get('region','')}, {d.get('country','')}   |   {d.get('system_type','').title()} System"
    ws["A4"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws.append([])
    headers = [("Parameter","",40),("Value","",25)]
    rows = [
        ("Daily Energy Demand",      f"{r['daily_kwh']:.3f} kWh/day"),
        ("PV Array Size",            f"{r['pv_kw']:.3f} kWp"),
        ("No. of Panels",            f"{r['num_panels']} × {r.get('panel_wp',400)} Wp Mono PERC"),
        ("Battery Chemistry",        r.get('chemistry','LiFePO4')),
        ("Battery Storage",          f"{r['bat_kwh']:.1f} kWh ({r['num_bat']} × {r['unit_bat_kwh']:.2g} kWh units)"),
        ("Inverter Rating",          f"{r['inv_kw']:.2f} kW"),
        ("MPPT Controller",          f"{r.get('mppt_a','—')} A"),
        ("System Cost",              f"{sym} {eco['total_local']:,.0f}"),
        ("Annual Savings",           f"{sym} {eco['annual_sav']:,.0f}"),
        ("Net Annual Benefit (Yr1)", f"{sym} {eco['net_yr1']:,.0f}"),
        ("Simple Payback",           f"{eco['payback']:.1f} years"),
        ("NPV (25yr)",               f"{sym} {eco['npv']:,.0f}"),
        ("IRR",                      f"{eco['irr_pct']:.1f}%" if eco['irr_pct'] else "N/A"),
        ("DSCR",                     f"{eco['dscr']:.2f}"),
        ("Bankability",              eco['bankability']),
        ("Verdict",                  eco['verdict']),
        ("CO2 Reduction",            f"{eco['co2_yr']:.2f} t/year"),
        ("25yr Cumulative Savings",  f"{sym} {eco['cumul_25']:,.0f}"),
    ]
    hfill = PatternFill("solid", fgColor="0f0f22")
    hfont = Font(bold=True, color="9090c0")
    ws.append(["Parameter", "Value"])
    ws[f"A{ws.max_row}"].font = hfont; ws[f"B{ws.max_row}"].font = hfont
    ws[f"A{ws.max_row}"].fill = hfill; ws[f"B{ws.max_row}"].fill = hfill
    ws.column_dimensions["A"].width = 36; ws.column_dimensions["B"].width = 30
    gold = PatternFill("solid", fgColor="1a1a30")
    for param, val in rows:
        ws.append([param, val])
        ws[f"A{ws.max_row}"].fill = gold

    # ── Sheet 2: Load Schedule ────────────────────────────────────────────────
    ws2 = wb.create_sheet("Load Schedule")
    ws2.sheet_view.showGridLines = False
    cols2 = [("Category",14),("Load Name",22),("Wattage (W)",14),
             ("Quantity",10),("Hours/Day",11),("kWh/Day",11),("Critical",10)]
    _xl_header(ws2, cols2)
    for ld in d.get("loads", []):
        kwh = (float(ld.get("wattage",0)) * float(ld.get("quantity",1)) * float(ld.get("hours",0))) / 1000
        ws2.append([ld.get("category",""), ld.get("name",""),
                    float(ld.get("wattage",0)), int(ld.get("quantity",1)),
                    float(ld.get("hours",0)), round(kwh,3),
                    "Yes" if ld.get("critical") else ""])
    ws2.append(["","","","","","TOTAL",round(r["daily_kwh"],3)])
    ws2[f"F{ws2.max_row}"].font = Font(bold=True, color="F59E0B")

    # ── Sheet 3: BOQ ─────────────────────────────────────────────────────────
    ws3 = wb.create_sheet("Bill of Quantities")
    ws3.sheet_view.showGridLines = False
    cols3 = [("No.",5),("Description",28),("Specification",30),
             ("Qty",6),("Unit",7),(f"Unit Rate ({sym})",16),(f"Total ({sym})",16)]
    _xl_header(ws3, cols3)
    for row in r.get("boq_rows",[]):
        ws3.append([row["no"], row["desc"], row["spec"], row["qty"],
                    row["unit"], round(row["total_r"],2), round(row["amount"],2)])
    ws3.append(["","","","","","GRAND TOTAL", round(r["boq_grand"],2)])
    ws3[f"G{ws3.max_row}"].font = Font(bold=True, color="F59E0B")

    # ── Sheet 4: 25-Year Cash Flow ────────────────────────────────────────────
    ws4 = wb.create_sheet("25-Year Cash Flow")
    ws4.sheet_view.showGridLines = False
    cols4 = [("Year",6),(f"Gross Saving ({sym})",18),(f"O&M ({sym})",14),
             (f"Net Benefit ({sym})",18),(f"Cumulative ({sym})",18),(f"NPV Cumul. ({sym})",18)]
    _xl_header(ws4, cols4)
    green_fill = PatternFill("solid", fgColor="052405")
    for cf in eco.get("cf_rows", []):
        ws4.append([cf["yr"], round(cf["gross"],0), round(cf["om"],0),
                    round(cf["net"],0), round(cf["cumul"],0), round(cf["npv_c"],0)])
        if cf["cumul"] >= eco["total_local"]:
            for col in range(1, 7):
                ws4.cell(ws4.max_row, col).fill = green_fill

    return _xl_send(wb, f"SolarPro_{project['name'].replace(' ','_')}_Results.xlsx")


@app.route("/project/<int:pid>/export/csv")
@login_required
@limiter.limit("10 per minute")
def export_csv(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        flash("Run calculations first.", "warning")
        return redirect(url_for("project_results", pid=pid))

    r   = project["data"]["results"]
    eco = r["economics"]
    d   = project["data"]
    sym = d.get("symbol", "$")

    output = io.StringIO()
    w = csv.writer(output)

    w.writerow(["SolarPro Global — Results Export"])
    w.writerow([project["name"], f"{d.get('region','')}, {d.get('country','')}", datetime.now().strftime('%Y-%m-%d')])
    w.writerow([])
    w.writerow(["=== SYSTEM SUMMARY ==="])
    for k,v in [
        ("Daily Demand (kWh/day)", r["daily_kwh"]),
        ("PV Array (kWp)", r["pv_kw"]),
        ("No. of Panels", r["num_panels"]),
        ("Panel Wattage (Wp)", r.get("panel_wp",400)),
        ("Battery Chemistry", r.get("chemistry","LiFePO4")),
        ("Battery Total (kWh)", r["bat_kwh"]),
        ("Battery Units", r["num_bat"]),
        ("Unit Size (kWh)", r["unit_bat_kwh"]),
        ("Inverter (kW)", r["inv_kw"]),
        ("MPPT (A)", r.get("mppt_a","—")),
        (f"System Cost ({sym})", round(eco["total_local"],2)),
        (f"Annual Savings ({sym})", round(eco["annual_sav"],2)),
        ("Payback (years)", round(eco["payback"],1)),
        (f"NPV ({sym})", round(eco["npv"],0)),
        ("IRR (%)", round(eco["irr_pct"],2) if eco["irr_pct"] else "N/A"),
        ("DSCR", round(eco["dscr"],2)),
        ("Bankability", eco["bankability"]),
        ("Verdict", eco["verdict"]),
        ("CO2 Reduction (t/yr)", round(eco["co2_yr"],2)),
    ]:
        w.writerow([k, v])

    w.writerow([]); w.writerow(["=== LOAD SCHEDULE ==="])
    w.writerow(["Category","Name","Wattage (W)","Qty","Hours/Day","kWh/Day","Critical"])
    for ld in d.get("loads", []):
        kwh = (float(ld.get("wattage",0))*float(ld.get("quantity",1))*float(ld.get("hours",0)))/1000
        w.writerow([ld.get("category",""), ld.get("name",""),
                    ld.get("wattage",0), ld.get("quantity",1),
                    ld.get("hours",0), round(kwh,3),
                    "Yes" if ld.get("critical") else "No"])
    w.writerow(["","","","","","TOTAL", round(r["daily_kwh"],3)])

    w.writerow([]); w.writerow(["=== BOQ ==="])
    w.writerow(["No.","Description","Specification","Qty","Unit",f"Rate ({sym})",f"Amount ({sym})"])
    for row in r.get("boq_rows",[]):
        w.writerow([row["no"],row["desc"],row["spec"],row["qty"],
                    row["unit"],round(row["total_r"],2),round(row["amount"],2)])
    w.writerow(["","","","","","Grand Total", round(r["boq_grand"],2)])

    w.writerow([]); w.writerow(["=== 25-YEAR CASH FLOW ==="])
    w.writerow(["Year",f"Gross ({sym})",f"O&M ({sym})",f"Net ({sym})",f"Cumulative ({sym})",f"NPV ({sym})"])
    for cf in eco.get("cf_rows",[]):
        w.writerow([cf["yr"],round(cf["gross"],0),round(cf["om"],0),
                    round(cf["net"],0),round(cf["cumul"],0),round(cf["npv_c"],0)])

    buf = io.BytesIO(output.getvalue().encode("utf-8-sig"))  # utf-8-sig for Excel compat
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                     download_name=f"SolarPro_{project['name'].replace(' ','_')}_Results.csv")


# ─── Template helpers ─────────────────────────────────────────────────────────

@app.template_filter("fmt")
def fmt(v, dec=2):
    try:
        return f"{float(v):,.{dec}f}"
    except Exception:
        return str(v)


@app.template_filter("fmti")
def fmti(v):
    try:
        return f"{int(v):,}"
    except Exception:
        return str(v)


# ─── PDF helper ───────────────────────────────────────────────────────────────

def _render_pdf(title, md_content, filename):
    """Convert markdown string → PDF bytes and return as Flask download."""
    from markdown_pdf import MarkdownPdf, Section

    CSS = """
    body{font-family:'Segoe UI',Arial,sans-serif;color:#111827;font-size:11pt;line-height:1.55;margin:0;padding:0}
    h1{color:#b45309;font-size:17pt;border-bottom:3px solid #f59e0b;padding-bottom:8px;margin-bottom:14px}
    h2{color:#1e3a8a;font-size:13pt;border-bottom:1px solid #bfdbfe;padding-bottom:4px;margin-top:20px}
    h3{color:#374151;font-size:11pt;margin-top:14px}
    table{width:100%;border-collapse:collapse;margin:10px 0;font-size:10pt}
    th{background:#1e3a5f;color:#fff;padding:7px 10px;text-align:left}
    td{border:1px solid #e5e7eb;padding:5px 10px}
    tr:nth-child(even){background:#f8fafc}
    blockquote{background:#f0fdf4;border-left:4px solid #22c55e;padding:10px 16px;margin:8px 0;border-radius:4px}
    .warn{background:#fffbeb;border-left:4px solid #f59e0b;padding:10px 16px;margin:8px 0;border-radius:4px}
    .danger{background:#fef2f2;border-left:4px solid #ef4444;padding:10px 16px;margin:8px 0;border-radius:4px}
    p{margin:5px 0}
    hr{border:none;border-top:1px solid #e5e7eb;margin:14px 0}
    code{background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:10pt}
    """

    pdf = MarkdownPdf(toc_level=2)
    pdf.meta.update({"title": title, "author": "SolarPro Global", "subject": title})

    # Split on top-level H1 so each section starts on a new page
    parts = md_content.split("\n# ")
    pdf.add_section(Section(parts[0], toc=False), user_css=CSS)
    for part in parts[1:]:
        pdf.add_section(Section("# " + part, toc=True), user_css=CSS)

    buf = io.BytesIO()
    pdf.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf",
                     as_attachment=True, download_name=filename)


def _fmt(v, dec=2):
    """Format number for PDF markdown."""
    try:
        if dec == 0:
            return f"{int(round(v)):,}"
        return f"{v:,.{dec}f}"
    except Exception:
        return str(v)


# ─── PDF export routes ─────────────────────────────────────────────────────────

@app.route("/project/<int:pid>/report/boq/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_boq(pid):
    """PDF export — Bill of Quantities & CAPEX."""
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d   = project["data"]
    r   = project["data"]["results"]
    eco = r["economics"]
    sym = d.get("symbol", "$")

    md = f"""# Bill of Quantities (BOQ) & CAPEX — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {d.get("system_type","").title()} System | {_fmt(r["pv_kw"],2)} kWp | {_fmt(r["bat_kwh"],2)} kWh | Currency: {d.get("currency","USD")}

Prepared by: SolarPro Global · BS 7671:2018 · IEC 60364

---

# Bill of Quantities

| No. | Description | Specification | Qty | Unit | Basic Rate ({sym}) | Total Rate ({sym}) | Amount ({sym}) |
|---|---|---|---|---|---|---|---|
"""
    for row in r.get("boq_rows", []):
        spec = str(row["spec"]).replace("|", "·")   # pipes break markdown tables
        md += (f"| {row['no']} | {row['desc']} | {spec} | "
               f"{row['qty']} | {row['unit']} | "
               f"{_fmt(row['basic'],2)} | {_fmt(row['total_r'],2)} | "
               f"**{_fmt(row['amount'],2)}** |\n")

    md += f"""
| | | | | | | **GRAND TOTAL** | **{sym} {_fmt(r['boq_grand'],2)}** |

*Note: Total Rate = Basic Rate × 1.20 (delivery, overheads & profit)*

---

# CAPEX Breakdown

| Item | Amount ({sym}) |
|---|---|
| Equipment Supply | {_fmt(eco.get("equip_local",0),0)} |
| Installation (18%) | {_fmt(eco.get("install_local",0),0)} |
| **Total CAPEX** | **{_fmt(eco.get("total_local",0),0)}** |
| Contingency (10%) | {_fmt(eco.get("total_local",0)*0.1,0)} |
| **Budget (incl. contingency)** | **{_fmt(eco.get("total_local",0)*1.1,0)}** |

---

# System Summary

| Parameter | Value |
|---|---|
| PV Capacity | {_fmt(r["pv_kw"],2)} kWp |
| PV Panels | {r["num_panels"]} × {r.get("panel_wp",400)} Wp Monocrystalline PERC |
| Battery Storage | {_fmt(r["bat_kwh"],2)} kWh — {r["num_bat"]} × {_fmt(r["unit_bat_kwh"],2)} kWh {r.get("chemistry","LiFePO4")} |
| Inverter / Charger | {_fmt(r["inv_kw"],1)} kW {d.get("phase","single").title()}-Phase |
| DC Bus Voltage | {d.get("voltage",48)} V |
| Standard | BS 7671:2018 / IEC 60364 / IEC 61215 |

---

# BOQ Notes

- Rates: Total Rate = Basic Rate × 1.20 (delivery + overheads & profit)
- Quantities subject to detailed design review and site survey
- Cable lengths are estimated — confirm actual lengths on site
- Subject to contractor quotation; excludes site-specific VAT / import duties
- DC cable sizes and AC cable sizes are calculated from actual system design

*Report generated by SolarPro Global · {d.get("region","")}, {d.get("country","")}*
"""
    fname = f"BOQ_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Bill of Quantities — {project['name']}", md, fname)


@app.route("/project/<int:pid>/report/cable/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_cable(pid):
    """PDF export — AC cable sizing & voltage drop calculation working."""
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d = project["data"]
    r = project["data"]["results"]
    phase = d.get("phase", "single")
    v_ac  = 415 if phase == "three" else 230

    md = f"""# AC Cable Sizing & Voltage Drop Report — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {d.get("system_type","").title()} System | {phase.title()} Phase {v_ac} V | Ambient: {d.get("avg_temp",30)}°C

Standard: **BS 7671:2018 / IEC 60364-5-52** | Cable: Copper PVC/XLPE 70°C | PF: 0.90

---

# Design Basis

| Parameter | Value |
|---|---|
| Standard | BS 7671:2018 (18th Edition) / IEC 60364-5-52 |
| Cable Type | Copper conductor, PVC or XLPE 70°C insulation |
| Installation Method | Method C — clipped direct to surface (default) |
| Ambient Temperature | {d.get("avg_temp",30)}°C |
| Power Factor | 0.90 (lagging) |
| VD Formula (single-phase) | VD (V) = mV/A/m × Ib × L / 1000 |
| VD Formula (three-phase) | VD (V) = mV/A/m × 0.866 × Ib × L / 1000 |
| VD Reference | BS 7671 Appendix 4, Tables 4D2B / 4D5B |
| Inverter | {_fmt(r["inv_kw"],1)} kW {phase.title()}-Phase |
| PV Array | {_fmt(r["pv_kw"],2)} kWp |

---

# Circuit Summary

| Circuit | Power (kW) | Vn (V) | Ib (A) | L (m) | Cable (mm²) | Iz (A) | VD (V) | VD (%) | Limit | Check | Breaker |
|---|---|---|---|---|---|---|---|---|---|---|---|
"""
    for c in r.get("ac_cables", []):
        chk = "PASS" if c["vd_ok"] else "FAIL"
        md += (f"| {c['circuit']} | {c['power_kw']} | {c['voltage_v']} | "
               f"{c['design_current']} | {c['length_m']} | **{c['cable_size_mm2']}** | "
               f"{c['cable_capacity']} | {c['vd_volts']:.3f} | {c['vd_percent']:.3f}% | "
               f"{c['vd_limit_pct']}% | **{chk}** | {c['breaker_a']} A |\n")

    md += "\n---\n\n# Voltage Drop Calculation — Step-by-Step Working\n\n"

    for c in r.get("ac_cables", []):
        vd_limit_v = c["vd_limit_pct"] / 100 * c["voltage_v"]
        phase_note = "(×0.866 three-phase factor already applied)" if c["phase"] == "three" else ""
        result_str = "✓ PASS" if c["vd_ok"] else "✗ FAIL — increase cable size"
        md += f"""## {c["circuit"]}

**Cable selected: {c["cable_size_mm2"]} mm² {c["core_type"]}** &nbsp;|&nbsp; {c["cable_capacity"]} A capacity &nbsp;|&nbsp; {c["breaker_a"]} A protective device

### Circuit Parameters

| Parameter | Symbol | Value |
|---|---|---|
| Nominal voltage | Vn | {c["voltage_v"]} V ({c["phase"].title()}-Phase) |
| Load power | P | {c["power_kw"]} kW |
| Design current | Ib | **{c["design_current"]} A** |
| Cable length | L | **{c["length_m"]} m** |
| Installation method | — | Method {c["install_method"]} — {c["install_desc"]} |
| Ambient temperature | Ta | {c["ambient_c"]}°C |
| Temperature factor | Ct | {c["temp_factor"]} |
| Grouping factor | Cg | {c["group_factor"]} |
| Minimum Iz required | Iz_min | {c["i_z_required"]} A |

### Voltage Drop Working

**Step 1 — Tabulated mV/A/m (BS 7671 Appendix 4)**

For {c["cable_size_mm2"]} mm² {c["core_type"]} copper cable:

> mV/A/m = **{c["vd_mv_am"]}** mV/A/m {phase_note}

**Step 2 — Actual voltage drop**

> VD = mV/A/m × Ib × L / 1000
>
> VD = {c["vd_mv_am"]} × {c["design_current"]} × {c["length_m"]} / 1000 = **{c["vd_volts"]:.3f} V**
>
> VD% = ({c["vd_volts"]:.3f} / {c["voltage_v"]}) × 100 = **{c["vd_percent"]:.3f}%**

**Step 3 — Check against permitted limit**

> Permitted limit = {c["vd_limit_pct"]}% of {c["voltage_v"]} V = **{vd_limit_v:.2f} V**
>
> Actual VD = **{c["vd_volts"]:.3f} V** — Limit = {vd_limit_v:.2f} V — **{result_str}**

---

"""

    md += """# Calculation Notes

| Item | Reference |
|---|---|
| VD tabulated values | BS 7671:2018 Appendix 4, Tables 4D2B / 4D5B |
| 3-phase VD factor ×0.866 | = √3/2, IEC 60364-5-52 |
| Temperature correction | BS 7671 Table 4B2 (ref 30°C) |
| Grouping correction | BS 7671 Table 4B1 |
| VD limits | Inverter→DB: 1.5% · Main feeder: 2.5% · Sub-distribution: 3.0% · Grid/Gen: 2.0% |
| Breaker coordination | Next standard size above Ib × 1.05; must not exceed cable Iz |

*All installations must comply with BS 7671:2018 (18th Edition), IEC 60364-5-52, and local regulations.*

*Report generated by SolarPro Global*
"""
    fname = f"AC_Cable_VD_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"AC Cable Sizing & Voltage Drop — {project['name']}", md, fname)


@app.route("/project/<int:pid>/report/energy/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_energy(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    r   = project["data"]["results"]
    eco = r["economics"]
    d   = project["data"]
    sym = d.get("symbol", "$")

    monthly_factors = [0.88,0.90,0.95,1.00,1.05,1.08,1.10,1.08,1.03,0.98,0.92,0.88]
    base_monthly    = r["daily_kwh"] * 30.44
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly = [{"month": m, "kwh": round(base_monthly * f, 1),
                "saving": round(base_monthly * f * d.get("tariff",1), 1)}
               for m, f in zip(months, monthly_factors)]
    trees  = round(eco["co2_yr"] / 21.77, 0)
    cars   = round(eco["co2_yr"] / 4600, 2)

    md = f"""# Energy Impact Analysis — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {d.get("system_type","").title()} System | {d.get("psh",0)} PSH | Generated by SolarPro Global

---

## Key Performance Indicators

| Metric | Value | Unit |
|---|---|---|
| Daily Solar Generation | {_fmt(r["daily_kwh"],2)} | kWh/day |
| Annual Solar Generation | {_fmt(r["daily_kwh"]*365,0)} | kWh/year |
| Annual Savings (Yr 1) | {sym} {_fmt(eco["annual_sav"],0)} | /year |
| CO₂ Reduction | {_fmt(eco["co2_yr"],2)} | tonnes/year |
| Trees Equivalent | {int(trees)} | trees/year |
| Grid Offset | {"100" if d.get("system_type")=="off-grid" else "~80"} | % |

---

# Monthly Energy Generation & Savings

| Month | Generation (kWh) | Savings ({sym}) |
|---|---|---|
"""
    for m in monthly:
        md += f"| {m['month']} | {m['kwh']} | {sym} {m['saving']} |\n"
    md += f"| **ANNUAL TOTAL** | **{_fmt(r['daily_kwh']*365,0)} kWh** | **{sym} {_fmt(eco['annual_sav'],0)}** |\n"

    md += f"""
---

# Energy Savings Summary

| Item | Value |
|---|---|
| Daily Solar Generation | {_fmt(r["daily_kwh"],2)} kWh/day |
| Annual Solar Generation | {_fmt(r["daily_kwh"]*365,0)} kWh/year |
| Electricity Tariff | {sym}{d.get("tariff",0):.3f}/kWh — {d.get("utility","") or "Grid Utility"} |
| Tariff Reference | {d.get("tariff_ref","") or "Published utility schedule"} |
| Gross Annual Savings | {sym} {_fmt(eco["annual_sav"],0)} |
| Annual O&M Cost | {sym} {_fmt(eco["om_yr1"],0)} |
| **Net Annual Benefit** | **{sym} {_fmt(eco["net_yr1"],0)}** |
| Cumulative Savings (10yr) | {sym} {_fmt(eco["cumul_10"],0)} |
| Cumulative Savings (25yr) | {sym} {_fmt(eco["cumul_25"],0)} |
| Simple Payback | {_fmt(eco["payback"],1)} years |

---

# Environmental Impact

| Metric | Value |
|---|---|
| Annual CO₂ Avoided | {_fmt(eco["co2_yr"],2)} tonnes/year |
| 25-Year CO₂ Avoided | {_fmt(eco["co2_yr"]*25,1)} tonnes |
| Equivalent Trees Planted | {int(trees)} trees/year |
| Equivalent Cars Removed | {cars} cars/year |
| Grid Emission Factor | 0.40 kg CO₂/kWh |
| Carbon Status | **Carbon Positive** |

---

# 25-Year Cash Flow Projection

| Year | Gross Saving | O&M | Net Benefit | Cumulative |
|---|---|---|---|---|
"""
    for cf in eco["cf_rows"]:
        flag = " ◄ BREAK-EVEN" if eco.get("breakeven") and cf["yr"] == eco["breakeven"] else ""
        md += f"| {cf['yr']} | {sym}{_fmt(cf['gross'],0)} | {sym}{_fmt(cf['om'],0)} | {sym}{_fmt(cf['net'],0)} | {sym}{_fmt(cf['cumul'],0)}{flag} |\n"

    md += f"\n---\n\n*Report generated by SolarPro Global · BS 7671 · IEC 60364 · IEEE*\n"

    fname = f"Energy_Impact_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Energy Impact Analysis — {project['name']}", md, fname)


@app.route("/project/<int:pid>/report/economic/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_economic(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    r   = project["data"]["results"]
    eco = r["economics"]
    d   = project["data"]
    sym = d.get("symbol", "$")
    recs = calc_recommendations(eco, d, r)

    verdict_icon = "✅ APPROVED" if eco["verdict"]=="APPROVED" else "⚠️ CONDITIONAL" if eco["verdict"]=="CONDITIONAL" else "❌ REJECTED"
    bank_icon    = "✅ BANKABLE" if eco["bankability"]=="BANKABLE" else "⚠️ MARGINAL" if eco["bankability"]=="MARGINAL" else "❌ NOT BANKABLE"

    md = f"""# Economic Analysis — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {_fmt(r["pv_kw"],2)} kWp · {_fmt(r["bat_kwh"],2)} kWh · {_fmt(r["inv_kw"],1)} kW | Currency: {d.get("currency","")}

---

## Project Verdict: {verdict_icon} | Bankability: {bank_icon}

**Payback** {_fmt(eco["payback"],1)} yr | **NPV** {sym} {_fmt(eco["npv"],0)} | **IRR** {f'{eco["irr_pct"]:.1f}%' if eco["irr_pct"] else "N/A"} | **DSCR** {_fmt(eco["dscr"],2)} | **CO₂** {_fmt(eco["co2_yr"],2)} t/yr

### Project Assessment
"""
    for reason in eco["verdict_reasons"]:
        md += f"- {reason}\n"

    if eco["bankability"] != "BANKABLE":
        md += f"\n### Bankability — {eco['bankability']}\n"
        for reason in eco["bank_reasons"]:
            md += f"- {reason}\n"

    md += f"""
---

# Key Financial Metrics

| Metric | Value |
|---|---|
| Total Investment | {sym} {_fmt(eco["total_local"],0)} |
| Annual Saving (Yr 1) | {sym} {_fmt(eco["annual_sav"],0)}/yr |
| Simple Payback | {_fmt(eco["payback"],1)} years |
| NPV (25yr) | {sym} {_fmt(eco["npv"],0)} |
| IRR | {f'{eco["irr_pct"]:.1f}%' if eco["irr_pct"] else "N/A"} |
| ROI (25yr) | {_fmt(eco["roi_pct"],0)}% |
| DSCR | {_fmt(eco["dscr"],2)} |
| CO₂ Saved | {_fmt(eco["co2_yr"],2)} t/yr |

---

# Investment Summary

| Item | Amount |
|---|---|
| Equipment Cost | {sym} {_fmt(eco["equip_local"],0)} |
| Installation (18%) | {sym} {_fmt(eco["install_local"],0)} |
| **Total Capital** | **{sym} {_fmt(eco["total_local"],0)}** |

---

# Energy & Savings

| Item | Value |
|---|---|
| Daily Load | {_fmt(r["daily_kwh"],3)} kWh/day |
| Annual Generation | {_fmt(eco["annual_kwh"],0)} kWh/yr |
| Tariff | {sym}{_fmt(eco["tariff"],3)}/kWh |
| Annual Bill Saving | {sym} {_fmt(eco["annual_sav"],0)}/yr |
| Annual O&M Cost | {sym} {_fmt(eco["om_yr1"],0)}/yr |
| **Net Annual Saving** | **{sym} {_fmt(eco["net_yr1"],0)}/yr** |

---

# Loan & Funding Analysis

| Item | Value |
|---|---|
| Loan Amount (70%) | {sym} {_fmt(eco["loan_amt"],0)} |
| Equity (30%) | {sym} {_fmt(eco["equity"],0)} |
| Interest Rate | 15% p.a. |
| Loan Tenor | 7 years |
| Monthly Repayment | {sym} {_fmt(eco["pmt"],0)}/mo |
| Annual Debt Service | {sym} {_fmt(eco["annual_pmt"],0)}/yr |
| **DSCR** | **{_fmt(eco["dscr"],2)} — {eco["bankability"]}** |

---

# 25-Year Cash Flow Projection

| Year | Gross Saving | O&M | Net Saving | Cumulative |
|---|---|---|---|---|
"""
    for cf in eco["cf_rows"]:
        flag = " ◄ BREAK-EVEN" if eco.get("breakeven") and cf["yr"] == eco["breakeven"] else ""
        md += f"| {cf['yr']} | {sym}{_fmt(cf['gross'],0)} | {sym}{_fmt(cf['om'],0)} | {sym}{_fmt(cf['net'],0)} | {sym}{_fmt(cf['cumul'],0)}{flag} |\n"

    if recs:
        md += f"\n---\n\n# Redesign Recommendations\n\n"
        md += f"The following engineering and financial improvements are recommended to achieve project approval and bankability:\n\n"
        for i, rec in enumerate(recs, 1):
            priority_label = "HIGH PRIORITY" if rec["priority"]==1 else "MEDIUM PRIORITY" if rec["priority"]==2 else "ADVISORY"
            md += f"## {i}. {rec['title']} [{priority_label}] ({rec['category']})\n\n"
            md += f"**Action:** {rec['action']}\n\n"
            md += f"**Expected Impact:** {rec['impact']}\n\n"

    md += f"\n---\n\n*Report generated by SolarPro Global · BS 7671 · IEC 60364 · IEEE*\n"
    md += f"\n*Assumptions: Tariff escalation 8%/yr, Discount rate 12%, O&M 1.2%/yr, Degradation 0.5%/yr, Life 25 years*\n"

    fname = f"Economic_Analysis_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Economic Analysis — {project['name']}", md, fname)


@app.route("/project/<int:pid>/report/installation/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_installation(pid):
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d  = project["data"]
    r  = project["data"]["results"]
    voltage    = d.get("voltage", 48)
    pps        = 2 if voltage <= 24 else 4 if voltage <= 48 else 8
    num_strings = math.ceil(r["num_panels"] / pps)
    last_panels = r["num_panels"] - (num_strings - 1) * pps
    phase  = d.get("phase", "single")
    v_ac   = 415 if phase == "three" else 230
    sym    = d.get("symbol", "$")
    chem   = r.get("chemistry", "LiFePO4")

    mt = d.get("mounting_type", "rooftop_pitched")
    mt_labels = {
        "rooftop_pitched":  "Pitched / Sloped Roof Mount",
        "rooftop_flat":     "Flat Roof Ballast Mount (Concrete Slab)",
        "rooftop_metal":    "Metal Sheet Roof Mount (IBR / Corrugated)",
        "rooftop_membrane": "Membrane / Green Roof Mount (Lightweight Ballast)",
        "ground_fixed":     "Ground-Fixed Mount (Concrete Footing)",
        "ground_tracking":  "Ground-Fixed with Single-Axis Tracking",
    }
    mt_steps = {
        "rooftop_pitched": [
            ("Structural Survey", "Verify rafter/purlin spacing. Mark rafter lines. Confirm roof pitch and row layout with >= 150 mm air gap under modules."),
            ("Mounting Rail Installation", "Fix L-foot brackets to rafters at <= 1200 mm centres using M8 SS bolts. Apply EPDM seal and UV silicone to all penetrations. Run aluminium T-rails."),
            ("Panel Layout and Clamping", "Install panels in portrait rows. Use mid-clamps at <= 400 mm, end-clamps 100-150 mm from panel edge. Torque to 20 Nm."),
            ("DC Wiring", "Route 6 mm2 TUV DC cables through metallic conduit fixed to rails. Connect MC4 pairs per string layout. Label each string at combiner box."),
            ("Weatherproofing", "Water-test all penetrations. Confirm 600 mm roof-edge clearance. Fit bird-proofing mesh around perimeter."),
        ],
        "rooftop_flat": [
            ("Structural Survey", "Verify slab rating (allow 20-25 kg/m2). Check membrane condition. Survey parapets for wind compliance per BS EN 1991-1-4."),
            ("Row Spacing Layout", "Calculate inter-row spacing for <= 2% shading at winter solstice. Mark rows. Maintain 1 m walkway at perimeter and between rows."),
            ("Ballast Frame Installation", "Place aluminium ballast trays at 10-15 deg tilt. No penetrations required. Add HDPE pads under feet. Apply ballast blocks per wind uplift calc."),
            ("Panel Installation and Bonding", "Slide panels into tray clamps. Engage locking clips. Bond all frames to earth busbar via 6 mm2 GY cable."),
            ("DC Cable Tray", "Route cables in UV cable trays. Avoid drainage paths. Fix conduit at <= 500 mm. Use sealed gland at roof penetration."),
        ],
        "rooftop_metal": [
            ("Structural Survey", "Inspect purlins for rust. Confirm purlin centres and sheet condition. Replace corroded sheets before mounting."),
            ("Clamp Installation", "For IBR: non-penetrating rib clamps on raised rib - no drilling. For corrugated: L-bracket with EPDM washer, butyl sealant, SS dome-head screw."),
            ("Rail Alignment", "Fix aluminium rails across purlins. Level with shims. Confirm rail twist < 1 deg/m."),
            ("Panel Clamping", "Install panels landscape to reduce wind uplift. Apply mid/end clamps per spec. Torque check after 24 hours."),
            ("Bonding and Weathering", "Bond all roof components and frames to earth busbar. Check all penetrations with sealant. Inspect from inside for daylight ingress."),
        ],
        "rooftop_membrane": [
            ("Membrane Survey", "Inspect EPDM/TPO/bitumen membrane. Complete any repairs and cure before mounting. Verify slab load >= 15 kg/m2 for ballast."),
            ("Protection Layer", "Lay 5 mm HDPE protection mat over entire array footprint to prevent membrane puncture."),
            ("Ballast Frame Placement", "Use aerodynamic low-profile trays for membrane roofs - no penetrations. Calculate ballast per BS EN 1991-1-4. Minimum 5 deg tilt for self-cleaning."),
            ("Panel Installation and Bonding", "Snap-lock or clamp panels per frame system. Bond all frames to floating earth ring connected to earth spike at parapet."),
            ("Cable Management", "Route DC cables in UV conduit weighted with ballast. Keep clear of drainage. Maintain inspection access path throughout array."),
        ],
        "ground_fixed": [
            ("Site Preparation", "Clear and level footprint (4 m2 per panel). Mark column grid. Confirm no underground services in excavation zone."),
            ("Foundation", "Excavate 600 mm deep x 400 mm dia. pits at 3-4 m centres. Fix M16 HD anchor bolts in shutter. Cast C25/30 concrete. Cure 3 days before loading."),
            ("Steel Frame Erection", "Fix galvanised 100x100 RHS posts to anchor bolts. Plumb and align all columns. Bolt cross-purlin members. Clamp top rails at design tilt angle."),
            ("Panel Installation", "Lift panels with panel handlers - avoid walking on panels. Apply mid/end clamps. Bond each frame with 6 mm2 GY cable to common earth strip."),
            ("DC Wiring and Earthing", "Route string cables in IP67 UV armoured conduit buried 600 mm below grade. Earth rod at each end of array connected to main earth busbar via 16 mm2 GY cable."),
        ],
        "ground_tracking": [
            ("Site Survey and Grading", "Topographic survey. Grade to <= 2% slope. Compact sub-base to 95% Proctor. Bearing capacity >= 100 kN/m2 for piles."),
            ("Pile Installation", "Drive 3 m galvanised piles (100 mm dia.) to refusal with hydraulic pile driver. Cap with baseplate and tolerance shim at grid spacing per tracker layout."),
            ("Tracker Structure Erection", "Assemble torque tube sections on ground. Lift into pillow-block bearings. Align to within 2 mm/m. Install drive motor and actuation arm at mid-span."),
            ("Panel Stringing", "Mount panels landscape on tracker rails. N-S string wiring (east +, west -) per MPPT channel design."),
            ("Tracker Control Commission", "Connect motor to central controller. Set morning/evening stow. Commission east-to-west sweep. Install SCADA/data logger for monitoring."),
        ],
    }
    mt_label = mt_labels.get(mt, "Rooftop Mount")
    mt_method = mt_steps.get(mt, mt_steps["rooftop_pitched"])

    md = f"""# Installation Report - {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {d.get("system_type","").title()} System | {phase.title()} Phase {v_ac}V | {d.get("voltage",48)}V DC

**Mounting Method:** {mt_label}

---

## System Summary

| Component | Specification |
|---|---|
| PV Array | {_fmt(r["pv_kw"],2)} kWp ({r["num_panels"]} × {r.get("panel_wp",400)} Wp Mono PERC) |
| Battery Bank | {_fmt(r["bat_kwh"],2)} kWh ({r["num_bat"]} × {_fmt(r["unit_bat_kwh"],2)} kWh {chem}) |
| Inverter/Charger | {_fmt(r["inv_kw"],1)} kW {phase.title()}-Phase |
| MPPT Rating | {r.get("mppt_a",0)} A |
| AC Voltage | {v_ac} V / 50 Hz |
| DC Bus Voltage | {d.get("voltage",48)} V |

---

# PV Array Configuration

| Parameter | Value |
|---|---|
| Total Panels | {r["num_panels"]} modules |
| Panels per String | {pps} in series |
| Number of Strings | {num_strings} parallel |
| Last String Panels | {last_panels} modules |
| Array Size | {_fmt(r["pv_kw"],2)} kWp |
| String Voc (est.) | {pps*24} V |
| DC Cable (strings) | 6 mm² UV solar cable (TÜV certified) |
| DC Cable (main run) | 10 mm² to isolator |
| Tilt Angle | 10–15° minimum (self-cleaning) |
| Orientation | Equator-facing (south in N. hemisphere) |

---

# Battery Bank

| Parameter | Value |
|---|---|
| Chemistry | {chem} |
| Total Capacity | {_fmt(r["bat_kwh"],2)} kWh |
| Number of Units | {r["num_bat"]} |
| Unit Capacity | {_fmt(r["unit_bat_kwh"],2)} kWh |
| DC Voltage | {d.get("voltage",48)} V |
| Mounting | Ventilated steel rack, ≥ 300mm clearance |
| BMS | Built-in Battery Management System |

---

# AC Distribution (BS 7671)

| Circuit | Protection | Cable | Load |
|---|---|---|---|
| Incoming (Inverter output) | {r["ac_cables"][0]["breaker_a"] if r.get("ac_cables") else "—"}A RCCB 30mA | {r["ac_cables"][0]["cable_size_mm2"] if r.get("ac_cables") else "—"} mm² | {_fmt(r["inv_kw"],1)} kW |
| Lighting & Emergency | 10A MCB | 1.5 mm² | ~1.0 kW |
| Power Sockets | 16A MCB | 2.5 mm² | ~2.0 kW |
| Air Conditioning | 32A MCB | {r["ac_cables"][-1]["cable_size_mm2"] if r.get("ac_cables") else "—"} mm² | ~3.5 kW |
| Water / Borehole Pump | 16A MCB | 2.5 mm² | ~1.5 kW |
| Office Equipment | 16A MCB | 2.5 mm² | ~1.5 kW |

---

# Wire Colour Code (BS 7671 / IEC 60364)

| Conductor | Colour |
|---|---|
| DC Positive (+) | Red |
| DC Negative (−) | Blue |
| AC Line / Phase | Brown |
| AC Neutral | Grey |
| Protective Earth (PE) | Green/Yellow |
| Battery Circuit | Purple |

---

# Installation Methodology

## Mounting Method: {mt_label}

""" + "".join(
    f"### Step {i+1}. {t}\n{d_}\n\n"
    for i, (t, d_) in enumerate(mt_method)
) + f"""
## General Installation Requirements

### PV Array Mounting Rules
- Maintain >= 600 mm from all roof edges (wind uplift zone)
- Allow >= 150 mm gap under panels for airflow (reduces temperature)
- Inter-row shading distance = panel height x tan(solar elevation)
- All panel frames bonded to earth bar with >= 6 mm2 green/yellow cable

## 2. DC Wiring — Combiner to Equipment Room
- All DC cables in metallic conduit or cable tray
- Segregate DC from AC cables — separate conduits or ≥ 50 mm separation
- String fuses rated at 1.25 × Isc in combiner box
- DC isolator must be DC-rated (AC isolators MUST NOT be used on DC circuits)
- DC SPD (Type 2) in combiner box and again at inverter DC input

## 3. Battery Installation
- Mount on purpose-built steel rack, bolted to floor or wall
- Minimum 300 mm clearance from walls and ceiling on all sides
- Ensure mechanical ventilation — {chem} has low gas risk but ventilate regardless
- No ignition sources within 1 m. Class D fire extinguisher within 5 m
- Battery fuse: 1.25 × maximum charge current

## 4. AC Distribution Board
- RCCB 30 mA on incomer (BS EN 61008 Type A)
- Type 2 AC SPD (BS EN 61643) inside DB — connection cable ≤ 0.5 m
- All MCBs coordinated — incomer trips last (discrimination)
- DB top edge ≤ 1.8 m from finished floor level

## 5. Earthing & Bonding (BS 7430)
- TT earthing arrangement — copper earth rod ≥ 2.4 m, driven vertically
- Earth rod ≥ 2 m from building structure
- Electrode resistance ≤ 10 Ω (test with earth clamp meter)
- All metalwork bonded: panel frames, inverter chassis, battery rack, DB enclosure
- Minimum 6 mm² green/yellow bonding cable throughout

## 6. Testing & Commissioning
- Insulation resistance test: ≥ 1 MΩ per IEC 60364-6
- Earth continuity: ≤ 0.1 Ω on all bonding connections
- RCD trip test: ≤ 40 ms at rated current (BS EN 61008)
- Polarity check on all DC circuits before energising inverter
- Functional test of all MCBs, RCCB, and SPDs

---

*All installations must comply with BS 7671:2018 (18th Edition), IEC 60364, IEC 62305 (lightning), and applicable local regulations. Engage a qualified electrical contractor for final installation and commissioning.*

*Report generated by SolarPro Global*
"""
    fname = f"Installation_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Installation Report — {project['name']}", md, fname)


@app.route("/project/<int:pid>/report/workplan/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_workplan(pid):
    """PDF export — Installation Work Plan (material schedule, programme, staffing)."""
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d  = project["data"]
    r  = project["data"]["results"]
    voltage     = d.get("voltage", 48)
    pps         = 2 if voltage <= 24 else 4 if voltage <= 48 else 8
    num_strings = math.ceil(r["num_panels"] / pps)
    chem        = r.get("chemistry", "LiFePO4")
    sym         = d.get("symbol", "$")
    eco         = r["economics"]

    md = f"""# Installation Work Plan — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {d.get("system_type","").title()} System | {_fmt(r["pv_kw"],2)} kWp | {r["num_panels"]} Panels | {_fmt(r["bat_kwh"],2)} kWh Battery

Prepared by: SolarPro Global · BS 7671:2018 · IEC 60364 · IEC 62446

---

# Section 1 — Material & Equipment Schedule

## 1A — PV Array & Mounting

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 1.1 | Solar PV Panels | {r.get("panel_wp",400)} Wp Monocrystalline PERC, Tier 1, Voc ≈ 24 V | {r["num_panels"]} | Modules |
| 1.2 | Aluminium Mounting Rails | 40×40 mm anodised aluminium | {int(r["num_panels"]*1.2)} | m |
| 1.3 | Mid & End Clamps | Stainless steel SS304 | {r["num_panels"]*4} | Sets |
| 1.4 | Roof Mounting Brackets | Galvanised steel, tilt-adjustable | {int(r["num_panels"]*1.5)} | No. |
| 1.5 | DC Solar Cable (strings) | 6 mm² TÜV UV-resistant, red & black | {int(r["num_panels"]*8)} | m |
| 1.6 | MC4 Connectors | IP67, 1000 VDC rated | {r["num_panels"]*4} | Pairs |
| 1.7 | DC Main Cable (combiner→inverter) | 10 mm² DC solar cable | 30 | m |
| 1.8 | Earthing Cable for Panel Frames | 6 mm² green/yellow | {int(r["num_panels"]*3)} | m |

## 1B — DC Combiner & Protection

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 2.1 | DC Combiner Box | IP65, {min(num_strings,4)}-string, lockable | 1 | No. |
| 2.2 | String Fuses | 10A DC PV fuse, 1000 VDC | {num_strings*2} | No. |
| 2.3 | DC Surge Protection Device | Type 2, 1000 VDC, IEC 61643-31 | 1 | No. |
| 2.4 | DC Main Isolator | 3-pole DC-rated, lockable | 1 | No. |
| 2.5 | Metallic Cable Conduit | 20 mm steel conduit | 25 | m |
| 2.6 | Cable Tray / Trunking | 50×50 mm galvanised steel | 10 | m |

## 1C — Inverter, Battery & MPPT

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 3.1 | Hybrid Inverter / Charger | {_fmt(r["inv_kw"],1)} kW, {d.get("voltage",48)}V DC, built-in MPPT {r.get("mppt_a","—")}A | 1 | No. |
| 3.2 | Lithium Battery Units | {_fmt(r["unit_bat_kwh"],2)} kWh {chem}, {d.get("voltage",48)}V, BMS | {r["num_bat"]} | No. |
| 3.3 | Battery Steel Rack | Powder-coated, for {r["num_bat"]} units | {max(1,(r["num_bat"]+1)//2)} | No. |
| 3.4 | Battery DC Fuse (ANL) | 1.25 × max charge current | {r["num_bat"]} | No. |
| 3.5 | Battery DC Cable | 25 mm² flexible, red & black | {r["num_bat"]*4} | m |
| 3.6 | BMS Communication Cable | RS485 / CAN bus | {r["num_bat"]} | Cables |
| 3.7 | Inverter Wall Bracket | Heavy-duty steel | 1 | Set |

## 1D — AC Distribution & Protection

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 4.1 | Main AC Distribution Board | {"18-way" if d.get("phase")=="single" else "12-way 3-ph"}, IP40 | 1 | No. |
| 4.2 | RCCB Incomer | {r["ac_cables"][0]["breaker_a"] if r.get("ac_cables") else 63}A, 30mA, Type A, BS EN 61008 | 1 | No. |
| 4.3 | MCB Lighting | 10A Type B, 6kA | 2 | No. |
| 4.4 | MCB Sockets | 16A Type B, 6kA | 3 | No. |
| 4.5 | MCB Air Conditioning | 32A Type C, 6kA | 1 | No. |
| 4.6 | MCB Pumps / Motors | 16A Type C, 6kA | 2 | No. |
| 4.7 | AC Surge Protection Device | Type 2, 230/415V, BS EN 61643 | 1 | No. |
"""
    for i, c in enumerate(r.get("ac_cables", []), start=8):
        md += f"| 4.{i} | AC Cable — {c['circuit']} | {c['cable_size_mm2']} mm² Cu XLPE/PVC | {c.get('length_m',20)+5} | m |\n"

    md += f"""
## 1E — Earthing, Bonding & Sundries

| # | Description | Qty | Unit |
|---|---|---|---|
| 5.1 | Copper Earth Rod (16 mm dia., 2.4 m) | 2 | No. |
| 5.2 | Earth Rod Clamp & Driver | 2 | Sets |
| 5.3 | Earth Busbar (10-way copper) | 1 | No. |
| 5.4 | Main Earthing Conductor (16 mm² G/Y) | 15 | m |
| 5.5 | Bonding Cables (6 mm² G/Y) | 40 | m |
| 5.6 | Cable Labels (PVC self-laminating) | 200 | No. |
| 5.7 | Cable Ties UV-resistant | 1 | Box (200) |
| 5.8 | Warning / Safety Labels (BS EN 60445) | 1 | Set |
| 5.9 | IP65 Cable Glands (M20–M32) | 20 | No. |
| 5.10 | UV-Resistant Silicone Sealant | 4 | Tubes |

## 1F — Test & Commissioning Instruments

| Instrument | Purpose | Acceptance Standard |
|---|---|---|
| Insulation Resistance Tester (Megger) | Cable insulation integrity | ≥ 1 MΩ (IEC 60364-6) |
| Earth Electrode Resistance Tester | Earth rod resistance | ≤ 10 Ω (BS 7430) |
| Clamp Earth Tester | Non-invasive earth continuity | ≤ 0.1 Ω (BS 7671 Ch.61) |
| Digital Multimeter (1000V DC) | String Voc, polarity | CAT III 1000V |
| DC Clamp Meter (1000V / 60A DC) | String Isc, battery current | CAT III 600V |
| RCD Tester | Trip time verification | ≤ 40 ms (BS EN 61008) |
| Voltage Drop Tester | Full-load volt drop | ≤ 3% (BS 7671 App 4) |
| Thermal Imaging Camera | Hot-spot detection | IEC 62446-3 |

---

# Section 2 — Approach to Installation Work & Programme

## Method Statement Summary

The installation follows a **7-phase methodology** aligned with BS 7671:2018, IEC 60364, and IEC 62446.
Each phase has defined entry criteria, activities, deliverables, and sign-off before the next phase begins.
Total programme: **12 working days** (weather permitting).

| Phase | Activity | Days | Duration |
|---|---|---|---|
| 1 | Mobilisation & Site Preparation | Days 1–2 | 2 days |
| 2 | Civil & Structural Works | Days 2–4 | 3 days |
| 3 | PV Panel Installation | Days 4–6 | 3 days |
| 4 | Equipment Room Fit-Out | Days 5–7 | 3 days |
| 5 | DC & AC Wiring | Days 7–9 | 3 days |
| 6 | Earthing, Bonding & Pre-commissioning Tests | Days 9–10 | 2 days |
| 7 | Commissioning, Testing & Handover | Days 10–12 | 3 days |

## Phase Detail

### Phase 1 — Mobilisation & Site Preparation (Days 1–2)

**Activities:**
- Deliver and inventory all equipment on site
- Set up site compound, secure storage for panels and batteries
- Install temporary power and lighting for working area
- Brief all staff on HSE plan and emergency procedures
- Prepare roof access — scaffold or MEWP
- Mark out equipment room layout and cable routes

**Sign-off outputs:** Signed delivery notes, site induction records, HSE risk assessment signed

### Phase 2 — Civil & Structural Works (Days 2–4)

**Activities:**
- Install roof mounting brackets/L-feet at designed spacing
- Assemble and level aluminium mounting rails; verify tilt angle
- Core through roof/walls for DC cable entry — seal immediately
- Fix conduit supports and tray brackets along cable route
- Install metallic conduit from roof to equipment room

**Sign-off outputs:** Waterproofing test, structural load check (if required), as-installed conduit sketch

### Phase 3 — PV Panel Installation (Days 4–6)

**Activities:**
- Mount panels row-by-row, bottom to top; torque clamps to spec
- Connect in series strings with MC4 connectors; verify polarity
- Install string fuses in combiner box; record fuse ratings
- Run and label DC string cables in conduit

**Sign-off outputs:** String cable labels at both ends, visual inspection — no cracked panels

### Phase 4 — Equipment Room Fit-Out (Days 5–7)

**Activities:**
- Fix inverter wall bracket; mount and level inverter
- Assemble battery rack; anchor to floor or wall
- Install batteries; connect in parallel per wiring diagram
- Connect BMS communication cables; configure settings
- Fix DC isolator and AC DB at correct heights
- Install earth busbar; run main earthing conductor

**Sign-off outputs:** Inverter mounting record, battery connection torque check, room layout photo

### Phase 5 — DC & AC Wiring (Days 7–9)

**Activities:**
- Run DC main cable combiner → inverter; double-check polarity
- Connect battery cables with ANL fuses
- Wire AC output inverter → DB incomer
- Install RCCB, MCBs, SPD in DB
- Run all AC final circuit cables; label both ends at every junction

**Sign-off outputs:** As-installed wiring diagram, cable schedule with actual lengths, labels verified

### Phase 6 — Earthing, Bonding & Pre-commissioning Tests (Days 9–10)

**Activities:**
- Drive earth rods to ≥ 2.4 m depth; connect to earth busbar
- Bond all metalwork — panel frames, inverter, battery rack, DB
- Test earth electrode resistance (≤ 10 Ω before proceeding)
- Insulation resistance test — all circuits ≥ 1 MΩ
- Continuity — all earth/bonding conductors ≤ 0.1 Ω
- Polarity check on all DC strings (signed by two technicians)

**Sign-off outputs:** Earth resistance certificate, IR test schedule, polarity check record

### Phase 7 — Commissioning, Testing & Handover (Days 10–12)

**Activities:**
- Energise inverter; verify AC output voltage and frequency
- Test MPPT tracking; confirm generation on inverter display
- RCD trip time test ≤ 40 ms; MCB overload test per circuit
- Voltage drop test under full load ≤ 3%
- 7-day performance monitoring — generation vs design
- Client handover training; issue O&M manual and warranties

**Sign-off outputs:** Full commissioning test schedule, 7-day monitoring log, Installation Completion Certificate, O&M manual issued

## Programme Notes

- **Total duration:** 12 working days (weather-permitting)
- **Weather hold:** No roof work in rain, lightning, or wind > 25 mph
- **Working hours:** 07:30–17:30 Mon–Fri; 07:30–13:00 Sat if required
- **Parallel working:** Phases 3 and 4 overlap (Days 5–7) — civil and electrical teams work simultaneously

---

# Section 3 — Staffing Plan

## Project Team

| Role | No. | Key Qualifications | Days on Site |
|---|---|---|---|
| Project Engineer / Site Manager | 1 | BEng Electrical, 18th Ed BS 7671, Solar PV cert, IOSH | All 12 days |
| Senior Electrical Technician | 1 | C&G 2365 NVQ L3, 18th Ed + 2391, ECS Gold, Work at Height | All 12 days |
| Electrical Apprentice / Assistant | 1 | NVQ L2 Electrical, Manual Handling, CSCS Green | All 12 days |
| Structural / Civil Technician | 1 | Roof mounting experience, PASMA/IPAF, CSCS | Days 1–6 |
| HSE Officer (part-time) | 1 | NEBOSH General, First Aid at Work | Days 1–2, 9–10 |

**Total peak headcount: 5 persons on site (Days 1–2 and 4–6)**

## Staff Deployment by Phase

| Phase | Activity | Proj. Eng. | Sr. Tech | Apprentice | Civil Tech | HSE Officer |
|---|---|---|---|---|---|---|
| 1 | Mobilisation | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Civil Works | ✓ (part) | — | ✓ | ✓ | ✓ (part) |
| 3 | PV Installation | ✓ | ✓ | ✓ | ✓ | ✓ (part) |
| 4 | Equipment Fit-Out | ✓ | ✓ | ✓ | — | — |
| 5 | DC & AC Wiring | ✓ | ✓ | ✓ | — | — |
| 6 | Earthing & Testing | ✓ | ✓ | ✓ | — | ✓ (part) |
| 7 | Commissioning | ✓ | ✓ | ✓ | — | — |

## Key Responsibilities

### Project Engineer / Site Manager
Responsible for overall technical quality, programme, safety, and client communication.
Signs off each phase, approves all test results, issues the Installation Completion Certificate.

### Senior Electrical Technician
Leads all electrical installation activities. Performs and records all pre-commissioning
and commissioning tests. Configures inverter and BMS settings. Mentors the apprentice.

### Electrical Apprentice / Assistant
Supports wiring, cable pulling, labelling, and containment installation.
Assists the senior technician and updates the material schedule as items are installed.

### Structural / Civil Technician
Installs all roof mounting structure. Responsible for panel mounting, tilt angle accuracy,
and waterproofing of all roof penetrations.

### HSE Officer
Conducts daily toolbox talks. Inspects PPE and access equipment. Maintains site accident log.
Emergency response coordinator.

## Mandatory PPE — All Personnel

- Safety helmet (EN 397) — all roof and overhead work
- Safety boots, steel toe cap, anti-slip (EN ISO 20345)
- High-visibility vest or jacket (EN ISO 20471 Class 2)
- Safety glasses when drilling, cutting, or using chemicals
- Electrical insulated gloves (EN 60903) when working near live equipment
- Full body harness (EN 361) for all work at height > 2 m
- Anti-static wrist strap when handling inverter electronics

## Site Safety Procedures

- Daily toolbox talk before work — attendance signed
- Written risk assessment and method statement on site at all times
- Permit to work before any work on energised equipment
- Two-person rule — no solo working on roof or electrical equipment
- All access equipment inspected daily — defective equipment tagged out
- Emergency evacuation plan posted at site entrance
- First aid kit and CO₂ fire extinguisher on site at all times
- Any near-miss reported within 2 hours

---

*Installation Work Plan — {project["name"]}*
*Generated by SolarPro Global · BS 7671:2018 · IEC 60364 · IEC 62446 · IEC 62305*
"""

    fname = f"WorkPlan_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Installation Work Plan — {project['name']}", md, fname)


@app.route("/project/<int:pid>/report/staffing/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_staffing(pid):
    """PDF export — Staffing Plan only (roles, deployment matrix, responsibilities, PPE)."""
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d  = project["data"]
    r  = project["data"]["results"]
    phase  = d.get("phase", "single")
    v_ac   = 415 if phase == "three" else 230

    md = f"""# Staffing Plan — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {d.get("system_type","").title()} System | {_fmt(r["pv_kw"],2)} kWp | {r["num_panels"]} Panels | {_fmt(r["bat_kwh"],2)} kWh Battery

Prepared by: SolarPro Global · BS 7671:2018 · IEC 60364 · IEC 62446

---

# Project Team

| Role | No. | Key Qualifications | Days on Site |
|---|---|---|---|
| Project Engineer / Site Manager | 1 | BEng Electrical, 18th Ed BS 7671, Solar PV cert, IOSH | All 12 days |
| Senior Electrical Technician | 1 | C&G 2365 NVQ L3, 18th Ed + 2391, ECS Gold, Work at Height | All 12 days |
| Electrical Apprentice / Assistant | 1 | NVQ L2 Electrical, Manual Handling, CSCS Green | All 12 days |
| Structural / Civil Technician | 1 | Roof mounting, PASMA/IPAF, CSCS | Days 1–6 |
| HSE Officer (part-time) | 1 | NEBOSH General, First Aid at Work | Days 1–2, 9–10 |

**Total peak headcount: 5 persons on site (Days 1–2 and 4–6)**

---

# Staff Deployment by Phase

| Phase | Activity | Days | Proj. Eng. | Sr. Tech | Apprentice | Civil Tech | HSE Officer |
|---|---|---|---|---|---|---|---|
| 1 | Mobilisation | 1–2 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Civil Works | 2–4 | ✓ (part) | — | ✓ | ✓ | ✓ (part) |
| 3 | PV Installation | 4–6 | ✓ | ✓ | ✓ | ✓ | ✓ (part) |
| 4 | Equipment Fit-Out | 5–7 | ✓ | ✓ | ✓ | — | — |
| 5 | DC & AC Wiring | 7–9 | ✓ | ✓ | ✓ | — | — |
| 6 | Earthing & Testing | 9–10 | ✓ | ✓ | ✓ | — | ✓ (part) |
| 7 | Commissioning | 10–12 | ✓ | ✓ | ✓ | — | — |

---

# Key Responsibilities

## Project Engineer / Site Manager
Responsible for overall technical quality, programme, safety, and client communication.
Signs off each phase, approves all test results, and issues the Installation Completion Certificate.
Holds valid BS 7671 certification and Solar PV design qualification (MCS or equivalent).

## Senior Electrical Technician
Leads all electrical installation activities. Performs and records all pre-commissioning and
commissioning tests. Configures inverter and BMS settings. Mentors the apprentice throughout.

## Electrical Apprentice / Assistant
Supports wiring, cable pulling, labelling, and containment installation.
Assists the senior technician and updates the material schedule as items are installed.

## Structural / Civil Technician
Installs all roof mounting structure. Responsible for panel mounting, tilt angle accuracy,
and weatherproofing of all roof penetrations. Engaged for Days 1–6.

## HSE Officer (Part-Time / Shared)
Conducts daily toolbox talks. Inspects PPE and access equipment. Maintains site accident log.
Acts as emergency response coordinator.

---

# Mandatory PPE — All Personnel

| Item | Standard |
|---|---|
| Safety helmet | EN 397 — all roof and overhead work |
| Safety boots (steel toe cap, anti-slip) | EN ISO 20345 |
| High-visibility vest / jacket (Class 2) | EN ISO 20471 |
| Safety glasses (drilling, cutting, chemicals) | EN 166 |
| Electrical insulated gloves (live-adjacent work) | EN 60903 |
| Full body harness (work at height > 2 m) | EN 361 |
| Anti-static wrist strap (inverter electronics) | IEC 61340-5 |

---

# Site Safety Procedures

- Daily toolbox talk before work — attendance signed by all personnel
- Written risk assessment and method statement on site at all times
- Permit to work before any work on or near energised equipment
- Two-person rule — no solo working on roof or electrical equipment
- All access equipment inspected daily; defective items tagged out of service
- Emergency evacuation plan posted at site entrance and briefed on Day 1
- First aid kit and CO₂ fire extinguisher on site at all times
- Any near-miss reported within 2 hours; incident report completed within 24 hours

---

*Staffing Plan — {project["name"]}*
*Generated by SolarPro Global · BS 7671:2018 · IEC 62446 · NEBOSH / HSE Guidance*
"""

    fname = f"StaffingPlan_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Staffing Plan — {project['name']}", md, fname)


# ─── Phase 4: Admin panel ─────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        with get_db() as c:
            u = c.execute("SELECT is_admin FROM users WHERE id=?",
                          (session["user_id"],)).fetchone()
        if not u or not u["is_admin"]:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.route("/admin")
@admin_required
def admin_dashboard():
    with get_db() as c:
        users      = c.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        projects   = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        tickets    = c.execute(
            "SELECT t.*, u.username FROM tickets t "
            "LEFT JOIN users u ON t.user_id=u.id "
            "ORDER BY t.updated_at DESC LIMIT 8").fetchall()
        open_t     = c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        total_rev  = c.execute("SELECT COALESCE(SUM(amount_usd),0) FROM payments WHERE status='success'").fetchone()[0]
        new_leads  = c.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
        subs       = c.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE status='active'").fetchone()[0]
        recent_users = c.execute(
            "SELECT id, username, email, plan, created_at, is_admin "
            "FROM users ORDER BY created_at DESC LIMIT 6").fetchall()
        monthly_signups = c.execute(
            "SELECT strftime('%Y-%m', created_at) AS mo, COUNT(*) AS cnt "
            "FROM users GROUP BY mo ORDER BY mo DESC LIMIT 6").fetchall()

    plan_counts = {}
    for u in users:
        p = (u["plan"] or "free").lower()
        plan_counts[p] = plan_counts.get(p, 0) + 1

    paid_users = sum(plan_counts.get(p, 0) for p in ("basic", "professional", "enterprise"))

    return render_template("admin.html", user=current_user(),
                           users=users, projects=projects,
                           tickets=tickets, open_t=open_t,
                           plan_counts=plan_counts,
                           total_rev=total_rev, new_leads=new_leads,
                           subs=subs, paid_users=paid_users,
                           recent_users=recent_users,
                           monthly_signups=list(reversed(list(monthly_signups))))


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        csrf_protect()
        uid    = request.form.get("uid", type=int)
        action = request.form.get("action")
        plan   = request.form.get("plan", "free")
        with get_db() as c:
            if action == "set_plan":
                c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))
                flash(f"Plan updated.", "success")
            elif action == "toggle_admin":
                cur = c.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
                new_val = 0 if cur and cur["is_admin"] else 1
                c.execute("UPDATE users SET is_admin=? WHERE id=?", (new_val, uid))
                flash("Admin status toggled.", "success")
            elif action == "disable":
                c.execute("UPDATE users SET plan='disabled' WHERE id=?", (uid,))
                flash("Account disabled.", "warning")
        return redirect(url_for("admin_users"))
    with get_db() as c:
        users = c.execute(
            "SELECT u.*, (SELECT COUNT(*) FROM projects WHERE user_id=u.id) AS proj_count "
            "FROM users u ORDER BY u.created_at DESC").fetchall()
    return render_template("admin_users.html", user=current_user(),
                           users=users, plan_prices=PLAN_PRICES)


@app.route("/admin/tickets")
@admin_required
def admin_tickets():
    status = request.args.get("status", "all")
    with get_db() as c:
        q = ("SELECT t.*, u.username, u.email "
             "FROM tickets t JOIN users u ON t.user_id=u.id ")
        if status != "all":
            rows = c.execute(q + "WHERE t.status=? ORDER BY t.updated_at DESC", (status,)).fetchall()
        else:
            rows = c.execute(q + "ORDER BY t.updated_at DESC").fetchall()
        counts = {r["status"]: r["cnt"] for r in c.execute(
            "SELECT status, COUNT(*) AS cnt FROM tickets GROUP BY status").fetchall()}
        counts["all"] = sum(counts.values())
    return render_template("admin_tickets.html", user=current_user(),
                           tickets=rows, status_filter=status, counts=counts)


@app.route("/admin/ticket/<int:tid>", methods=["GET", "POST"])
@admin_required
def admin_ticket_detail(tid):
    with get_db() as c:
        ticket = c.execute(
            "SELECT t.*, u.username, u.email, u.plan, u.created_at AS user_joined, u.name AS user_name, u.company "
            "FROM tickets t JOIN users u ON t.user_id=u.id WHERE t.id=?", (tid,)).fetchone()
        if not ticket:
            abort(404)
        replies = c.execute(
            "SELECT r.*, u.username, u.is_admin AS sender_is_admin FROM ticket_replies r "
            "JOIN users u ON r.user_id=u.id WHERE r.ticket_id=? ORDER BY r.created_at",
            (tid,)).fetchall()
        user_ticket_count = c.execute(
            "SELECT COUNT(*) FROM tickets WHERE user_id=?", (ticket["user_id"],)).fetchone()[0]
        prev_ticket = c.execute(
            "SELECT id FROM tickets WHERE id < ? ORDER BY id DESC LIMIT 1", (tid,)).fetchone()
        next_ticket = c.execute(
            "SELECT id FROM tickets WHERE id > ? ORDER BY id ASC LIMIT 1", (tid,)).fetchone()
    if request.method == "POST":
        csrf_protect()
        action = request.form.get("action")
        if action == "reply":
            msg = request.form.get("message", "").strip()
            if msg:
                with get_db() as c:
                    c.execute(
                        "INSERT INTO ticket_replies (ticket_id,user_id,is_admin,message) VALUES (?,?,1,?)",
                        (tid, session["user_id"], msg))
                    c.execute("UPDATE tickets SET status='answered',updated_at=? WHERE id=?",
                              (datetime.now().isoformat(), tid))
                flash("Reply sent.", "success")
        elif action in ("close", "open", "in_progress", "answered"):
            with get_db() as c:
                c.execute("UPDATE tickets SET status=?,updated_at=? WHERE id=?",
                          (action, datetime.now().isoformat(), tid))
            flash(f"Ticket marked {action.replace('_',' ')}.", "success")
        return redirect(url_for("admin_ticket_detail", tid=tid))
    return render_template("admin_ticket_detail.html", user=current_user(),
                           ticket=ticket, replies=replies,
                           user_ticket_count=user_ticket_count,
                           prev_ticket=prev_ticket, next_ticket=next_ticket)


@app.route("/admin/appliances", methods=["GET", "POST"])
@admin_required
def admin_appliances():
    if request.method == "POST":
        csrf_protect()
        action = request.form.get("action")
        with get_db() as c:
            if action == "add":
                c.execute(
                    "INSERT INTO appliances (category,name,default_watt,notes) VALUES (?,?,?,?)",
                    (request.form["category"], request.form["name"],
                     int(request.form["default_watt"]), request.form.get("notes", "")))
                flash("Appliance added.", "success")
            elif action == "delete":
                c.execute("DELETE FROM appliances WHERE id=?",
                          (request.form.get("aid", type=int),))
                flash("Appliance deleted.", "success")
            elif action == "edit":
                c.execute(
                    "UPDATE appliances SET category=?,name=?,default_watt=?,notes=? WHERE id=?",
                    (request.form["category"], request.form["name"],
                     int(request.form["default_watt"]), request.form.get("notes", ""),
                     request.form.get("aid", type=int)))
                flash("Appliance updated.", "success")
        return redirect(url_for("admin_appliances"))
    with get_db() as c:
        apps = c.execute("SELECT * FROM appliances ORDER BY category,name").fetchall()
    categories = sorted(set(a["category"] for a in apps))
    return render_template("admin_appliances.html", user=current_user(),
                           appliances=apps, categories=categories)


# ─── Phase 4: Account / subscription management ───────────────────────────────

def _record_payment(uid, gateway, plan, amount_usd, currency="USD",
                    reference="", status="success"):
    with get_db() as c:
        c.execute(
            "INSERT INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, gateway, plan, amount_usd, currency, reference, status))


@app.route("/account")
@login_required
def account():
    user = current_user()
    plan = (user["plan"] or "free").lower()
    uid  = session["user_id"]
    with get_db() as c:
        proj_count   = c.execute("SELECT COUNT(*) FROM projects WHERE user_id=?", (uid,)).fetchone()[0]
        pay_rows     = c.execute(
            "SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 24", (uid,)).fetchall()
        open_tickets = c.execute(
            "SELECT COUNT(*) FROM tickets WHERE user_id=? AND status='open'", (uid,)).fetchone()[0]
        emails_sent  = c.execute(
            "SELECT COUNT(*) FROM email_logs WHERE user_id=? AND status='sent'", (uid,)).fetchone()[0]
        total_paid   = c.execute(
            "SELECT COALESCE(SUM(amount_usd),0) FROM payments WHERE user_id=? AND status='success'",
            (uid,)).fetchone()[0]
    limit = PLAN_LIMITS.get(plan, 1)
    return render_template("account.html", user=user, plan=plan,
                           proj_count=proj_count, limit=limit,
                           payments=pay_rows, plan_prices=PLAN_PRICES,
                           open_tickets=open_tickets, emails_sent=emails_sent,
                           total_paid=total_paid)


@app.route("/account/cancel", methods=["POST"])
@login_required
def account_cancel():
    csrf_protect()
    user = current_user()
    if (user["plan"] or "free").lower() == "free":
        flash("You are already on the Free plan.", "info")
        return redirect(url_for("account"))
    with get_db() as c:
        c.execute("UPDATE users SET plan='free' WHERE id=?", (session["user_id"],))
    _record_payment(session["user_id"], "manual", "free", 0, status="cancelled")
    flash("Subscription cancelled. You are now on the Free plan.", "info")
    return redirect(url_for("account"))


# ─── Phase 4: Ticketing ───────────────────────────────────────────────────────

@app.route("/tickets", methods=["GET", "POST"])
@login_required
def tickets():
    if request.method == "POST":
        csrf_protect()
        subject  = request.form.get("subject", "").strip()
        message  = request.form.get("message", "").strip()
        priority = request.form.get("priority", "normal")
        if not subject or not message:
            flash("Subject and message are required.", "warning")
        else:
            with get_db() as c:
                c.execute(
                    "INSERT INTO tickets (user_id,subject,message,priority) VALUES (?,?,?,?)",
                    (session["user_id"], subject, message, priority))
            flash("Support ticket submitted. We'll respond within 24 hours.", "success")
        return redirect(url_for("tickets"))
    with get_db() as c:
        rows = c.execute(
            "SELECT * FROM tickets WHERE user_id=? ORDER BY updated_at DESC",
            (session["user_id"],)).fetchall()
    return render_template("tickets.html", user=current_user(), tickets=rows)


@app.route("/ticket/<int:tid>", methods=["GET", "POST"])
@login_required
def ticket_detail(tid):
    with get_db() as c:
        ticket = c.execute(
            "SELECT * FROM tickets WHERE id=? AND user_id=?",
            (tid, session["user_id"])).fetchone()
        if not ticket:
            abort(404)
        replies = c.execute(
            "SELECT r.*, u.username FROM ticket_replies r "
            "JOIN users u ON r.user_id=u.id WHERE r.ticket_id=? ORDER BY r.created_at",
            (tid,)).fetchall()
    if request.method == "POST":
        csrf_protect()
        msg = request.form.get("message", "").strip()
        if msg:
            with get_db() as c:
                c.execute(
                    "INSERT INTO ticket_replies (ticket_id,user_id,is_admin,message) VALUES (?,?,0,?)",
                    (tid, session["user_id"], msg))
                c.execute("UPDATE tickets SET status='open',updated_at=? WHERE id=?",
                          (datetime.now().isoformat(), tid))
            flash("Reply added.", "success")
        return redirect(url_for("ticket_detail", tid=tid))
    return render_template("ticket_detail.html", user=current_user(),
                           ticket=ticket, replies=replies)


# ─── Phase 4: Subscription upgrade & payment ─────────────────────────────────

@app.route("/upgrade")
@login_required
def upgrade():
    user = current_user()
    return render_template("upgrade.html", user=user,
                           plan_prices=PLAN_PRICES,
                           current_plan=(user["plan"] or "free").lower(),
                           stripe_key=bool(STRIPE_SECRET),
                           paystack_key=bool(PAYSTACK_SECRET),
                           paystack_public_key=PAYSTACK_PUBLIC,
                           demo_mode=DEMO_MODE)


@app.route("/upgrade/checkout", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def upgrade_checkout():
    csrf_protect()
    plan     = request.form.get("plan", "").lower()
    gateway  = request.form.get("gateway", "stripe")
    if plan not in PLAN_PRICES:
        flash("Invalid plan selected.", "danger")
        return redirect(url_for("upgrade"))
    price_usd = PLAN_PRICES[plan]["usd"]
    user = current_user()

    if gateway == "stripe" and STRIPE_SECRET:
        try:
            import stripe as _stripe
            _stripe.api_key = STRIPE_SECRET
            price_id = STRIPE_PRICES.get(plan, "")
            if not price_id:
                flash("Stripe price not configured for this plan. Contact support.", "warning")
                return redirect(url_for("upgrade"))
            checkout = _stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="subscription",
                line_items=[{"price": price_id, "quantity": 1}],
                customer_email=user["email"],
                metadata={"user_id": str(user["id"]), "plan": plan},
                success_url=request.host_url.rstrip("/") + url_for("upgrade_success") + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=request.host_url.rstrip("/") + url_for("upgrade"),
            )
            return redirect(checkout.url, 303)
        except Exception as e:
            flash(f"Stripe error: {e}", "danger")
            return redirect(url_for("upgrade"))

    elif gateway == "paystack" and PAYSTACK_SECRET:
        import urllib.request as _ur
        amount_kobo = price_usd * 100 * 100  # USD → Paystack expects NGN kobo; adjust per currency
        payload = json.dumps({
            "email": user["email"],
            "amount": amount_kobo,
            "currency": "USD",
            "metadata": {"user_id": user["id"], "plan": plan},
            "callback_url": request.host_url.rstrip("/") + url_for("paystack_callback"),
        }).encode()
        req = _ur.Request("https://api.paystack.co/transaction/initialize",
                          data=payload, headers={
                              "Authorization": f"Bearer {PAYSTACK_SECRET}",
                              "Content-Type": "application/json"})
        try:
            with _ur.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data.get("status"):
                session["paystack_plan"] = plan
                return redirect(data["data"]["authorization_url"], 303)
            flash("Paystack initialization failed. Try again.", "danger")
        except Exception as e:
            flash(f"Paystack error: {e}", "danger")
        return redirect(url_for("upgrade"))

    # No gateway configured — demo mode
    flash(f"Payment gateway not configured. To activate, set STRIPE_SECRET_KEY or "
          f"PAYSTACK_SECRET_KEY environment variables. "
          f"Contact support@solarproglobal.com to upgrade your plan manually.", "info")
    return redirect(url_for("upgrade"))


@app.route("/upgrade/success")
@login_required
def upgrade_success():
    session_id = request.args.get("session_id", "")
    if STRIPE_SECRET and session_id:
        try:
            import stripe as _stripe
            _stripe.api_key = STRIPE_SECRET
            checkout = _stripe.checkout.Session.retrieve(session_id)
            if checkout.payment_status == "paid":
                plan = checkout.metadata.get("plan", "")
                uid  = int(checkout.metadata.get("user_id", 0))
                if plan and uid == session["user_id"]:
                    with get_db() as c:
                        c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))
                    _record_payment(uid, "stripe", plan,
                                    PLAN_PRICES.get(plan, {}).get("usd", 0),
                                    reference=session_id)
                    flash(f"Subscription activated! Welcome to {PLAN_PRICES[plan]['label']}.", "success")
                    return redirect(url_for("dashboard"))
        except Exception:
            pass
    flash("Payment verified. If your plan has not updated, contact support@solarproglobal.com.", "info")
    return redirect(url_for("dashboard"))


@app.route("/paystack/verify", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def paystack_verify():
    """Called by Paystack inline popup JS after successful payment."""
    csrf_protect()
    ref  = request.form.get("reference", "")
    plan = request.form.get("plan", "").lower()
    if not ref or not PAYSTACK_SECRET or plan not in PLAN_PRICES:
        flash("Payment verification failed — invalid request.", "danger")
        return redirect(url_for("upgrade"))
    import urllib.request as _ur
    req = _ur.Request(f"https://api.paystack.co/transaction/verify/{ref}",
                      headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
    try:
        with _ur.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get("status") and data["data"].get("status") == "success":
            with get_db() as c:
                c.execute("UPDATE users SET plan=? WHERE id=?",
                          (plan, session["user_id"]))
            _record_payment(session["user_id"], "paystack", plan,
                            PLAN_PRICES[plan]["usd"], reference=ref)
            flash(f"Payment confirmed! Welcome to {PLAN_PRICES[plan]['label']}.", "success")
            return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"Verification error: {e}", "danger")
    flash("Payment verification failed. Contact support@solarproglobal.com with reference: " + ref, "warning")
    return redirect(url_for("upgrade"))


@app.route("/paystack/callback")
@login_required
def paystack_callback():
    ref = request.args.get("reference", "")
    plan = session.pop("paystack_plan", "")
    if ref and PAYSTACK_SECRET and plan:
        import urllib.request as _ur
        req = _ur.Request(f"https://api.paystack.co/transaction/verify/{ref}",
                          headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"})
        try:
            with _ur.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data.get("status") and data["data"].get("status") == "success":
                with get_db() as c:
                    c.execute("UPDATE users SET plan=? WHERE id=?",
                              (plan, session["user_id"]))
                _record_payment(session["user_id"], "paystack", plan,
                                PLAN_PRICES.get(plan, {}).get("usd", 0),
                                reference=ref)
                flash(f"Payment confirmed! Welcome to {PLAN_PRICES[plan]['label']}.", "success")
                return redirect(url_for("dashboard"))
        except Exception:
            pass
    flash("Payment verification failed. Contact support@solarproglobal.com with your reference.", "warning")
    return redirect(url_for("upgrade"))


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    if not STRIPE_SECRET:
        return "", 400
    try:
        import stripe as _stripe
        _stripe.api_key = STRIPE_SECRET
        sig = request.headers.get("Stripe-Signature", "")
        event = _stripe.Webhook.construct_event(
            request.get_data(raw=True), sig, STRIPE_WEBHOOK)
        if event["type"] == "checkout.session.completed":
            obj  = event["data"]["object"]
            plan = obj.get("metadata", {}).get("plan", "")
            uid  = int(obj.get("metadata", {}).get("user_id", 0))
            if plan and uid:
                with get_db() as c:
                    c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))
                _record_payment(uid, "stripe", plan,
                                PLAN_PRICES.get(plan, {}).get("usd", 0),
                                reference=obj.get("id", ""))
        elif event["type"] in ("customer.subscription.deleted",
                               "invoice.payment_failed"):
            uid = int(event["data"]["object"].get("metadata", {}).get("user_id", 0))
            if uid:
                with get_db() as c:
                    c.execute("UPDATE users SET plan='free' WHERE id=?", (uid,))
                _record_payment(uid, "stripe", "free", 0, status="cancelled")
    except Exception:
        return "", 400
    return "", 200


# ─── Demo Mode & Upgrade Codes ───────────────────────────────────────────────

@app.route("/upgrade/demo-activate", methods=["POST"])
@login_required
@limiter.limit("5 per hour")
def upgrade_demo_activate():
    """Instantly activate Professional plan for DEMO_DAYS days — no payment needed."""
    csrf_protect()
    if not DEMO_MODE:
        flash("Demo mode is not enabled.", "warning")
        return redirect(url_for("upgrade"))
    user = current_user()
    if (user["plan"] or "free") not in ("free",):
        flash("You already have an active paid plan.", "info")
        return redirect(url_for("dashboard"))
    expires = (datetime.now() + timedelta(days=DEMO_DAYS)).isoformat()
    with get_db() as c:
        c.execute("UPDATE users SET plan='professional', subscription_end=? WHERE id=?",
                  (expires, user["id"]))
    _record_payment(user["id"], "demo", "professional", 0,
                    reference=f"DEMO-{DEMO_DAYS}d")
    flash(f"Demo Professional plan activated for {DEMO_DAYS} days — all features unlocked!", "success")
    return redirect(url_for("dashboard"))


@app.route("/upgrade/redeem", methods=["POST"])
@login_required
def upgrade_redeem_code():
    """Redeem an upgrade code issued by admin."""
    csrf_protect()
    code = request.form.get("code", "").strip().upper()
    if not code:
        flash("Please enter an upgrade code.", "warning")
        return redirect(url_for("upgrade"))
    with get_db() as c:
        row = c.execute("SELECT * FROM upgrade_codes WHERE code=?", (code,)).fetchone()
        if not row:
            flash("Invalid upgrade code.", "danger")
            return redirect(url_for("upgrade"))
        if row["uses"] >= row["max_uses"]:
            flash("This code has already been fully used.", "warning")
            return redirect(url_for("upgrade"))
        if row["expires_at"] and row["expires_at"] < datetime.now().isoformat():
            flash("This code has expired.", "warning")
            return redirect(url_for("upgrade"))
        expires = (datetime.now() + timedelta(days=row["duration_days"])).isoformat()
        c.execute("UPDATE users SET plan=?, subscription_end=? WHERE id=?",
                  (row["plan"], expires, session["user_id"]))
        c.execute("UPDATE upgrade_codes SET uses=uses+1 WHERE id=?", (row["id"],))
    _record_payment(session["user_id"], "code", row["plan"], 0, reference=code)
    flash(f"Code accepted! {row['plan'].title()} plan activated for {row['duration_days']} days.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/codes", methods=["GET", "POST"])
@admin_required
def admin_codes():
    if request.method == "POST":
        csrf_protect()
        action = request.form.get("action")
        if action == "create":
            plan     = request.form.get("plan", "professional")
            duration = int(request.form.get("duration_days", 30))
            max_uses = int(request.form.get("max_uses", 1))
            days_exp = int(request.form.get("expires_in_days", 90))
            code     = secrets.token_hex(4).upper()
            expires  = (datetime.now() + timedelta(days=days_exp)).isoformat()
            with get_db() as c:
                c.execute(
                    "INSERT INTO upgrade_codes (code,plan,duration_days,max_uses,created_by,expires_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (code, plan, duration, max_uses, session["user_id"], expires))
            flash(f"Code created: {code}", "success")
        elif action == "delete":
            cid = request.form.get("cid", type=int)
            with get_db() as c:
                c.execute("DELETE FROM upgrade_codes WHERE id=?", (cid,))
            flash("Code deleted.", "info")
        return redirect(url_for("admin_codes"))
    with get_db() as c:
        codes = c.execute("SELECT * FROM upgrade_codes ORDER BY created_at DESC").fetchall()
    return render_template("admin_codes.html", user=current_user(),
                           codes=codes, plan_prices=PLAN_PRICES)


# ─── Sales & Marketing Module ─────────────────────────────────────────────────

@app.route("/contact", methods=["POST"])
@limiter.limit("10 per hour")
def contact_lead():
    """Public contact form → lead capture."""
    name    = request.form.get("name", "").strip()
    email   = request.form.get("email", "").strip()
    phone   = request.form.get("phone", "").strip()
    company = request.form.get("company", "").strip()
    country = request.form.get("country", "").strip()
    interest= request.form.get("interest", "residential")
    message = request.form.get("message", "").strip()
    if not name or not email:
        flash("Name and email are required.", "warning")
        return redirect(url_for("landing") + "#contact")
    with get_db() as c:
        c.execute(
            "INSERT INTO leads (name,email,phone,company,country,interest,message,source) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, email, phone, company, country, interest, message, "website"))
    flash("Thank you! We'll be in touch within 24 hours.", "success")
    return redirect(url_for("landing") + "#contact")


@app.route("/newsletter/subscribe", methods=["POST"])
@limiter.limit("20 per hour")
def newsletter_subscribe():
    email = request.form.get("email", "").strip()
    name  = request.form.get("name", "").strip()
    if not email:
        flash("Email is required.", "warning")
        return redirect(url_for("landing") + "#newsletter")
    try:
        with get_db() as c:
            c.execute("INSERT OR IGNORE INTO newsletter_subscribers (email,name) VALUES (?,?)",
                      (email, name))
        flash("Subscribed! You'll receive our solar industry updates.", "success")
    except Exception:
        flash("Already subscribed with that email.", "info")
    return redirect(url_for("landing") + "#newsletter")


# ─── Assessment Request (public) ──────────────────────────────────────────────

def _qualify_lead(name, company, phone, system_type, size_kw, budget_usd, message):
    """Rule-based lead scoring → (score 0-100, grade A/B/C/D, notes str)."""
    score = 0
    reasons = []
    # Budget scoring
    b = budget_usd.lower().replace(",","").replace("$","").replace("usd","").strip()
    try:
        bval = float(b.split("-")[0].split("k")[0]) * (1000 if "k" in b else 1)
    except Exception:
        bval = 0
    if bval >= 100000:  score += 35; reasons.append("High budget ($100k+)")
    elif bval >= 50000: score += 25; reasons.append("Good budget ($50k+)")
    elif bval >= 10000: score += 15; reasons.append("Medium budget ($10k+)")
    elif bval > 0:      score += 5;  reasons.append("Low budget")
    # System size
    try: sz = float(size_kw)
    except Exception: sz = 0
    if sz >= 100:    score += 30; reasons.append("Large commercial system (100kW+)")
    elif sz >= 50:   score += 22; reasons.append("Commercial system (50-100kW)")
    elif sz >= 10:   score += 14; reasons.append("SME system (10-50kW)")
    elif sz >= 1:    score += 6;  reasons.append("Residential system")
    # System type
    if system_type in ("commercial", "industrial"): score += 15; reasons.append("Commercial/Industrial priority")
    elif system_type == "hybrid":                   score += 10; reasons.append("Hybrid system")
    # Lead quality signals
    if company.strip(): score += 10; reasons.append("Company name provided")
    if phone.strip():   score += 5;  reasons.append("Phone provided")
    if len(message.strip()) > 50: score += 5; reasons.append("Detailed message")
    score = min(score, 100)
    if score >= 80:   grade = "A"
    elif score >= 60: grade = "B"
    elif score >= 40: grade = "C"
    else:             grade = "D"
    return score, grade, "; ".join(reasons) if reasons else "Unscored"


@app.route("/assess", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def assessment_request():
    """Public assessment request form."""
    if request.method == "POST":
        name        = request.form.get("name", "").strip()
        email       = request.form.get("email", "").strip()
        phone       = request.form.get("phone", "").strip()
        company     = request.form.get("company", "").strip()
        country     = request.form.get("country", "").strip()
        system_type = request.form.get("system_type", "off-grid")
        size_kw     = request.form.get("system_size_kw", "0")
        budget      = request.form.get("budget_usd", "").strip()
        location    = request.form.get("location_desc", "").strip()
        message     = request.form.get("message", "").strip()
        if not name or not email:
            flash("Name and email are required.", "warning")
            return redirect(url_for("assessment_request"))
        score, grade, notes = _qualify_lead(name, company, phone, system_type, size_kw, budget, message)
        try: size_kw_f = float(size_kw)
        except Exception: size_kw_f = 0.0
        with get_db() as c:
            c.execute(
                "INSERT INTO assessment_requests "
                "(name,email,phone,company,country,system_type,system_size_kw,budget_usd,"
                "location_desc,message,ai_score,ai_grade,ai_notes,source) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'website')",
                (name, email, phone, company, country, system_type, size_kw_f,
                 budget, location, message, score, grade, notes))
            # Also add to leads table for unified CRM
            c.execute(
                "INSERT INTO leads (name,email,phone,company,country,interest,message,source,"
                "system_type,system_size_kw,budget_usd,ai_score,ai_grade,ai_notes,pipeline_stage) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (name, email, phone, company, country, system_type, message, "assess_form",
                 system_type, size_kw_f, budget, score, grade, notes,
                 "qualified" if grade in ("A","B") else "new"))
        flash("Thank you! Our team will contact you within 24 hours with your assessment.", "success")
        return redirect(url_for("assessment_request"))
    return render_template("assess.html", user=current_user(), countries=get_countries())


# ─── Installer Registration (public) ──────────────────────────────────────────

@app.route("/installer/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def installer_register():
    """Public installer/subcontractor registration."""
    if request.method == "POST":
        company   = request.form.get("company_name", "").strip()
        contact   = request.form.get("contact_name", "").strip()
        email     = request.form.get("email", "").strip()
        phone     = request.form.get("phone", "").strip()
        country   = request.form.get("country", "").strip()
        regions   = request.form.get("regions", "").strip()
        years     = request.form.get("years_exp", "0")
        staff     = request.form.get("staff_count", "0")
        certs     = request.form.get("certifications", "").strip()
        specs     = request.form.get("specialties", "").strip()
        max_kw    = request.form.get("max_project_kw", "0")
        website   = request.form.get("website", "").strip()
        notes     = request.form.get("notes", "").strip()
        if not company or not email or not contact:
            flash("Company name, contact name, and email are required.", "warning")
            return redirect(url_for("installer_register"))
        try: years_i = int(years)
        except Exception: years_i = 0
        try: staff_i = int(staff)
        except Exception: staff_i = 0
        try: max_kw_f = float(max_kw)
        except Exception: max_kw_f = 0.0
        # Simple grade based on experience
        if years_i >= 10 and staff_i >= 20: grade = "A"
        elif years_i >= 5 and staff_i >= 5: grade = "B"
        elif years_i >= 2: grade = "C"
        else: grade = "D"
        try:
            with get_db() as c:
                c.execute(
                    "INSERT INTO installers (company_name,contact_name,email,phone,country,"
                    "regions,years_exp,staff_count,certifications,specialties,max_project_kw,"
                    "website,notes,ai_grade) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (company, contact, email, phone, country, regions, years_i, staff_i,
                     certs, specs, max_kw_f, website, notes, grade))
            flash("Registration submitted! We'll review your application within 2 business days.", "success")
        except Exception:
            flash("An account with that email already exists.", "warning")
        return redirect(url_for("installer_register"))
    return render_template("installer_register.html", user=current_user(), countries=get_countries())


# ─── Admin: Assessment Requests ───────────────────────────────────────────────

@app.route("/admin/assessments", methods=["GET", "POST"])
@admin_required
def admin_assessments():
    if request.method == "POST":
        csrf_protect()
        aid    = request.form.get("aid", type=int)
        action = request.form.get("action")
        with get_db() as c:
            if action == "update":
                c.execute(
                    "UPDATE assessment_requests SET pipeline_stage=?,assigned_to=?,"
                    "follow_up_date=?,status=?,updated_at=? WHERE id=?",
                    (request.form.get("pipeline_stage"),
                     request.form.get("assigned_to",""),
                     request.form.get("follow_up_date",""),
                     request.form.get("status","open"),
                     datetime.now().isoformat(), aid))
                flash("Assessment request updated.", "success")
            elif action == "delete":
                c.execute("DELETE FROM assessment_requests WHERE id=?", (aid,))
                flash("Deleted.", "info")
        return redirect(url_for("admin_assessments"))
    stage_f = request.args.get("stage", "all")
    with get_db() as c:
        if stage_f != "all":
            rows = c.execute(
                "SELECT * FROM assessment_requests WHERE pipeline_stage=? ORDER BY created_at DESC",
                (stage_f,)).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM assessment_requests ORDER BY created_at DESC").fetchall()
        counts = {}
        for s in ("new","qualified","assessment_sent","proposal_sent","won","lost"):
            counts[s] = c.execute(
                "SELECT COUNT(*) FROM assessment_requests WHERE pipeline_stage=?", (s,)).fetchone()[0]
    return render_template("admin_assessments.html", user=current_user(),
                           requests=rows, stage_filter=stage_f, counts=counts)


# ─── Admin: Installer Management ──────────────────────────────────────────────

@app.route("/admin/installers", methods=["GET", "POST"])
@admin_required
def admin_installers():
    if request.method == "POST":
        csrf_protect()
        iid    = request.form.get("iid", type=int)
        action = request.form.get("action")
        with get_db() as c:
            if action == "approve":
                c.execute("UPDATE installers SET status='approved' WHERE id=?", (iid,))
                flash("Installer approved.", "success")
            elif action == "reject":
                c.execute("UPDATE installers SET status='rejected' WHERE id=?", (iid,))
                flash("Installer rejected.", "info")
            elif action == "delete":
                c.execute("DELETE FROM installers WHERE id=?", (iid,))
                flash("Deleted.", "info")
        return redirect(url_for("admin_installers"))
    status_f = request.args.get("status", "all")
    with get_db() as c:
        if status_f != "all":
            rows = c.execute(
                "SELECT * FROM installers WHERE status=? ORDER BY created_at DESC", (status_f,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM installers ORDER BY created_at DESC").fetchall()
        pending = c.execute("SELECT COUNT(*) FROM installers WHERE status='pending'").fetchone()[0]
        approved = c.execute("SELECT COUNT(*) FROM installers WHERE status='approved'").fetchone()[0]
    return render_template("admin_installers.html", user=current_user(),
                           installers=rows, status_filter=status_f,
                           pending=pending, approved=approved)


# ─── Admin: CRM Pipeline ──────────────────────────────────────────────────────

@app.route("/admin/pipeline")
@admin_required
def admin_pipeline():
    """Kanban-style CRM pipeline across all leads + assessment requests."""
    STAGES = ["new", "qualified", "assessment_sent", "proposal_sent", "won", "lost"]
    with get_db() as c:
        leads_rows  = c.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
        assess_rows = c.execute("SELECT * FROM assessment_requests ORDER BY created_at DESC").fetchall()
    # Normalise assessment_requests rows to look like leads for the Kanban
    all_leads = list(leads_rows)
    for ar in assess_rows:
        # sqlite3.Row → dict, then patch missing keys leads template expects
        d = dict(ar)
        d.setdefault("interest", d.get("system_type",""))
        d.setdefault("notes", "")
        d.setdefault("rec_type", "assess")
        all_leads.append(d)
    by_stage = {s: [] for s in STAGES}
    for lead in all_leads:
        try:   st = lead["pipeline_stage"]
        except Exception: st = "new"
        if st not in STAGES: st = "new"
        by_stage[st].append(lead)
    total = len(all_leads)
    won   = len(by_stage["won"])
    conv  = round(won / total * 100, 1) if total else 0
    return render_template("admin_pipeline.html", user=current_user(),
                           by_stage=by_stage, stages=STAGES, total=total,
                           won=won, conv=conv)


@app.route("/admin/sales")
@admin_required
def admin_sales():
    """Sales & Marketing dashboard — KPIs, leads pipeline, revenue, conversions."""
    with get_db() as c:
        leads      = c.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
        subs       = c.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE status='active'").fetchone()[0]
        users      = c.execute("SELECT plan, COUNT(*) as cnt FROM users GROUP BY plan").fetchall()
        payments   = c.execute(
            "SELECT p.*, u.username, u.email FROM payments p "
            "JOIN users u ON p.user_id=u.id "
            "WHERE p.status='success' ORDER BY p.created_at DESC LIMIT 50").fetchall()
        total_rev  = c.execute("SELECT SUM(amount_usd) FROM payments WHERE status='success'").fetchone()[0] or 0
        news_count = c.execute("SELECT COUNT(*) FROM news_posts WHERE is_published=1").fetchone()[0]
        monthly_signups = c.execute(
            "SELECT strftime('%Y-%m', created_at) as mo, COUNT(*) as cnt "
            "FROM users GROUP BY mo ORDER BY mo DESC LIMIT 6").fetchall()
        assess_count   = c.execute("SELECT COUNT(*) FROM assessment_requests").fetchone()[0]
        assess_open    = c.execute("SELECT COUNT(*) FROM assessment_requests WHERE status='open'").fetchone()[0]
        installers_pending = c.execute("SELECT COUNT(*) FROM installers WHERE status='pending'").fetchone()[0]
        pipeline_won   = c.execute("SELECT COUNT(*) FROM leads WHERE pipeline_stage='won'").fetchone()[0]
        pipeline_total = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    lead_status = {}
    for ld in leads:
        s = ld["status"]
        lead_status[s] = lead_status.get(s, 0) + 1
    pipeline_dist = {}
    for ld in leads:
        s = ld["pipeline_stage"] or "new"
        pipeline_dist[s] = pipeline_dist.get(s, 0) + 1
    plan_dist = {r["plan"]: r["cnt"] for r in users}
    conv = round(pipeline_won / pipeline_total * 100, 1) if pipeline_total else 0
    return render_template("admin_sales.html", user=current_user(),
                           leads=leads, subs=subs, plan_dist=plan_dist,
                           payments=payments, total_rev=total_rev,
                           news_count=news_count, lead_status=lead_status,
                           monthly_signups=monthly_signups,
                           assess_count=assess_count, assess_open=assess_open,
                           installers_pending=installers_pending,
                           pipeline_dist=pipeline_dist, conv=conv)


@app.route("/admin/leads", methods=["GET", "POST"])
@admin_required
def admin_leads():
    if request.method == "POST":
        csrf_protect()
        lid    = request.form.get("lid", type=int)
        action = request.form.get("action")
        with get_db() as c:
            if action == "update_status":
                c.execute(
                    "UPDATE leads SET status=?,notes=?,pipeline_stage=?,follow_up_date=? WHERE id=?",
                    (request.form.get("status"), request.form.get("notes",""),
                     request.form.get("pipeline_stage","new"),
                     request.form.get("follow_up_date",""), lid))
                flash("Lead updated.", "success")
            elif action == "delete":
                c.execute("DELETE FROM leads WHERE id=?", (lid,))
                flash("Lead deleted.", "info")
        return redirect(url_for("admin_leads"))
    status_filter = request.args.get("status", "all")
    with get_db() as c:
        if status_filter != "all":
            rows = c.execute("SELECT * FROM leads WHERE status=? ORDER BY created_at DESC",
                             (status_filter,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
    return render_template("admin_leads.html", user=current_user(),
                           leads=rows, status_filter=status_filter)


@app.route("/admin/news", methods=["GET", "POST"])
@admin_required
def admin_news():
    if request.method == "POST":
        csrf_protect()
        action = request.form.get("action")
        with get_db() as c:
            if action == "create":
                c.execute(
                    "INSERT INTO news_posts (title,content,category,is_published) VALUES (?,?,?,?)",
                    (request.form["title"], request.form["content"],
                     request.form.get("category","industry"),
                     1 if request.form.get("publish") else 0))
                flash("News post created.", "success")
            elif action == "edit":
                nid = request.form.get("nid", type=int)
                c.execute(
                    "UPDATE news_posts SET title=?,content=?,category=?,is_published=?,updated_at=? WHERE id=?",
                    (request.form["title"], request.form["content"],
                     request.form.get("category","industry"),
                     1 if request.form.get("publish") else 0,
                     datetime.now().isoformat(), nid))
                flash("Post updated.", "success")
            elif action == "delete":
                c.execute("DELETE FROM news_posts WHERE id=?",
                          (request.form.get("nid", type=int),))
                flash("Post deleted.", "info")
        return redirect(url_for("admin_news"))
    with get_db() as c:
        posts = c.execute("SELECT * FROM news_posts ORDER BY created_at DESC").fetchall()
    return render_template("admin_news.html", user=current_user(), posts=posts)


@app.route("/admin/newsletter")
@admin_required
def admin_newsletter():
    with get_db() as c:
        subs = c.execute("SELECT * FROM newsletter_subscribers ORDER BY created_at DESC").fetchall()
    return render_template("admin_newsletter.html", user=current_user(), subs=subs)


@app.route("/admin/newsletter/unsub/<int:sid>", methods=["POST"])
@admin_required
def admin_newsletter_unsub(sid):
    csrf_protect()
    with get_db() as c:
        c.execute("UPDATE newsletter_subscribers SET status='unsubscribed' WHERE id=?", (sid,))
    flash("Subscriber removed.", "info")
    return redirect(url_for("admin_newsletter"))


# ─── Procurement Module ───────────────────────────────────────────────────────

@app.route("/procurement")
@login_required
def procurement():
    with get_db() as c:
        suppliers = c.execute("SELECT * FROM suppliers WHERE is_active=1 ORDER BY name").fetchall()
        catalog   = c.execute("SELECT e.*, s.name as sup_name FROM equipment_catalog e "
                              "LEFT JOIN suppliers s ON e.supplier_id=s.id "
                              "WHERE e.is_active=1 ORDER BY e.category, e.name").fetchall()
        categories = list(dict.fromkeys(r["category"] for r in catalog))
    return render_template("procurement.html", user=current_user(),
                           suppliers=suppliers, catalog=catalog, categories=categories)


@app.route("/procurement/suppliers", methods=["GET", "POST"])
@admin_required
def procurement_suppliers():
    if request.method == "POST":
        csrf_protect()
        action = request.form.get("action")
        f = request.form
        with get_db() as c:
            if action == "add":
                c.execute(
                    "INSERT INTO suppliers (name,country,contact_name,phone,email,website,"
                    "categories,lead_time_days,payment_terms,rating,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (f["name"], f.get("country",""), f.get("contact_name",""),
                     f.get("phone",""), f.get("email",""), f.get("website",""),
                     f.get("categories",""), int(f.get("lead_time_days",30)),
                     f.get("payment_terms","TT 30 days"), int(f.get("rating",5)),
                     f.get("notes","")))
                flash("Supplier added.", "success")
            elif action == "edit":
                sid = f.get("sid", type=int)
                c.execute(
                    "UPDATE suppliers SET name=?,country=?,contact_name=?,phone=?,email=?,"
                    "website=?,categories=?,lead_time_days=?,payment_terms=?,rating=?,notes=? WHERE id=?",
                    (f["name"], f.get("country",""), f.get("contact_name",""),
                     f.get("phone",""), f.get("email",""), f.get("website",""),
                     f.get("categories",""), int(f.get("lead_time_days",30)),
                     f.get("payment_terms","TT 30 days"), int(f.get("rating",5)),
                     f.get("notes",""), sid))
                flash("Supplier updated.", "success")
            elif action == "delete":
                c.execute("UPDATE suppliers SET is_active=0 WHERE id=?",
                          (f.get("sid", type=int),))
                flash("Supplier deactivated.", "info")
        return redirect(url_for("procurement_suppliers"))
    with get_db() as c:
        rows = c.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    return render_template("procurement_suppliers.html", user=current_user(), suppliers=rows)


@app.route("/procurement/catalog", methods=["GET", "POST"])
@admin_required
def procurement_catalog():
    if request.method == "POST":
        csrf_protect()
        action = request.form.get("action")
        f = request.form
        with get_db() as c:
            if action == "add":
                c.execute(
                    "INSERT INTO equipment_catalog (category,name,brand,model,spec,unit,"
                    "price_usd,supplier_id,lead_time_days,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f["category"], f["name"], f.get("brand",""), f.get("model",""),
                     f.get("spec",""), f.get("unit","No."), float(f.get("price_usd",0)),
                     int(f.get("supplier_id",0)), int(f.get("lead_time_days",30)),
                     f.get("notes","")))
                flash("Equipment added.", "success")
            elif action == "edit":
                eid = f.get("eid", type=int)
                c.execute(
                    "UPDATE equipment_catalog SET category=?,name=?,brand=?,model=?,spec=?,"
                    "unit=?,price_usd=?,supplier_id=?,lead_time_days=?,notes=? WHERE id=?",
                    (f["category"], f["name"], f.get("brand",""), f.get("model",""),
                     f.get("spec",""), f.get("unit","No."), float(f.get("price_usd",0)),
                     int(f.get("supplier_id",0)), int(f.get("lead_time_days",30)),
                     f.get("notes",""), eid))
                flash("Equipment updated.", "success")
            elif action == "delete":
                c.execute("UPDATE equipment_catalog SET is_active=0 WHERE id=?",
                          (f.get("eid", type=int),))
                flash("Item deactivated.", "info")
        return redirect(url_for("procurement_catalog"))
    with get_db() as c:
        items = c.execute(
            "SELECT e.*, s.name as sup_name FROM equipment_catalog e "
            "LEFT JOIN suppliers s ON e.supplier_id=s.id ORDER BY e.category, e.name").fetchall()
        suppliers = c.execute("SELECT id,name FROM suppliers WHERE is_active=1").fetchall()
    cats = ["PV Modules","Inverters","Batteries","MPPT","Cables",
            "Protection","Earthing","Mounting","Testing","Sundries"]
    return render_template("procurement_catalog.html", user=current_user(),
                           items=items, suppliers=suppliers, categories=cats)


@app.route("/project/<int:pid>/procurement")
@login_required
def project_procurement(pid):
    """Generate a smart procurement plan from the project BOQ, matched to suppliers."""
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        flash("Run calculations first.", "warning")
        return redirect(url_for("project_results", pid=pid))

    r   = project["data"]["results"]
    d   = project["data"]
    sym = d.get("symbol", "$")
    fx  = d.get("fx_usd", 1.0)

    with get_db() as c:
        suppliers = {r2["id"]: dict(r2) for r2 in
                     c.execute("SELECT * FROM suppliers WHERE is_active=1").fetchall()}
        catalog   = c.execute(
            "SELECT * FROM equipment_catalog WHERE is_active=1 ORDER BY category").fetchall()

    # Map BOQ items to catalog / suppliers
    CAT_MAP = {
        "PV": "PV Modules", "Battery": "Batteries", "Inverter": "Inverters",
        "MPPT": "MPPT", "Cable": "Cables", "Earth": "Earthing",
        "Surge": "Protection", "Mounting": "Mounting", "AC RCCB": "Protection",
    }

    plan_rows = []
    grand_usd = 0.0
    for boq in r.get("boq_rows", []):
        desc = boq["desc"]
        # Find category match
        cat = next((v for k, v in CAT_MAP.items() if k.lower() in desc.lower()), "Sundries")
        # Find best catalog match
        match = next((c2 for c2 in catalog if c2["category"] == cat), None)
        sup   = suppliers.get(match["supplier_id"]) if match else None
        unit_usd  = match["price_usd"] if match else boq["total_r"] / fx
        total_usd = unit_usd * boq["qty"]
        grand_usd += total_usd
        plan_rows.append({
            "no":        boq["no"],
            "desc":      desc,
            "spec":      boq["spec"],
            "qty":       boq["qty"],
            "unit":      boq["unit"],
            "category":  cat,
            "catalog":   match["name"] if match else "— specify on quotation",
            "brand":     match["brand"] if match else "",
            "supplier":  sup["name"] if sup else "Open market / RFQ",
            "supplier_id": sup["id"] if sup else 0,
            "lead_days": match["lead_time_days"] if match else 30,
            "unit_usd":  unit_usd,
            "total_usd": total_usd,
            "total_local": total_usd * fx,
        })

    # Group by supplier for purchase orders
    by_supplier = {}
    for row in plan_rows:
        key = row["supplier"]
        by_supplier.setdefault(key, {"supplier": key, "items": [], "total_usd": 0.0})
        by_supplier[key]["items"].append(row)
        by_supplier[key]["total_usd"] += row["total_usd"]

    return render_template("procurement_plan.html", user=current_user(),
                           project=project, d=d, r=r, sym=sym, fx=fx,
                           plan_rows=plan_rows, grand_usd=grand_usd,
                           by_supplier=list(by_supplier.values()),
                           suppliers=suppliers)


@app.route("/project/<int:pid>/procurement/pdf")
@login_required
@limiter.limit("10 per minute")
def export_pdf_procurement(pid):
    """PDF Procurement Plan — maps BOQ to suppliers, generates sourcing schedule."""
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    r   = project["data"]["results"]
    d   = project["data"]
    sym = d.get("symbol", "$")
    fx  = d.get("fx_usd", 1.0)

    with get_db() as c:
        suppliers = {r2["id"]: dict(r2) for r2 in
                     c.execute("SELECT * FROM suppliers WHERE is_active=1").fetchall()}
        catalog   = list(c.execute("SELECT * FROM equipment_catalog WHERE is_active=1").fetchall())

    CAT_MAP = {"PV": "PV Modules","Battery": "Batteries","Inverter": "Inverters",
               "MPPT": "MPPT","Cable": "Cables","Earth": "Earthing",
               "Surge": "Protection","Mounting": "Mounting","AC RCCB": "Protection"}

    rows = []
    grand_usd = 0.0
    for boq in r.get("boq_rows", []):
        desc  = boq["desc"]
        cat   = next((v for k, v in CAT_MAP.items() if k.lower() in desc.lower()), "Sundries")
        match = next((c2 for c2 in catalog if c2["category"] == cat), None)
        sup   = suppliers.get(match["supplier_id"]) if match else None
        unit_usd  = match["price_usd"] if match else boq["total_r"] / fx
        total_usd = unit_usd * boq["qty"]
        grand_usd += total_usd
        rows.append((boq["no"], desc, boq["qty"], boq["unit"],
                     match["brand"] if match else "—",
                     sup["name"] if sup else "RFQ",
                     match["lead_time_days"] if match else 30,
                     unit_usd, total_usd))

    md = f"""# Procurement Plan — {project["name"]}

**{d.get("region","")}, {d.get("country","")}** | {_fmt(r["pv_kw"],2)} kWp | {d.get("system_type","").title()} System

Prepared by: SolarPro Global | Currency: USD (local rates apply × {fx})

---

# Equipment Sourcing Schedule

| No. | Description | Qty | Unit | Brand | Supplier | Lead (days) | Unit USD | Total USD |
|---|---|---|---|---|---|---|---|---|
"""
    for no, desc, qty, unit, brand, sup, lead, u_usd, t_usd in rows:
        md += f"| {no} | {desc} | {qty} | {unit} | {brand} | {sup} | {lead} | ${_fmt(u_usd,2)} | **${_fmt(t_usd,2)}** |\n"

    md += f"""
| | | | | | | | **GRAND TOTAL** | **${_fmt(grand_usd,2)}** |

---

# Procurement Notes

- Lead times are indicative — confirm with suppliers on order placement
- All equipment must meet IEC 61215, IEC 62109, IEC 62619, BS 7671 as applicable
- Request formal technical data sheets (TDS) and test certificates before approval
- Payment terms subject to commercial negotiation with each supplier
- Allow 10% contingency budget for freight, customs, and incidentals

---

# Key Suppliers

"""
    seen = set()
    for _, _, _, _, _, sup_name, lead, _, _ in rows:
        if sup_name not in seen and sup_name != "RFQ":
            seen.add(sup_name)
            sup_obj = next((s for s in suppliers.values() if s["name"] == sup_name), None)
            if sup_obj:
                md += f"**{sup_name}** | {sup_obj.get('country','')} | {sup_obj.get('email','')} | Lead: {lead} days | Terms: {sup_obj.get('payment_terms','TT 30 days')}\n\n"

    md += f"\n---\n\n*Procurement Plan generated by SolarPro Global · {project['name']}*\n"
    fname = f"Procurement_{project['name'].replace(' ','_')}.pdf"
    return _render_pdf(f"Procurement Plan — {project['name']}", md, fname)


# ─── Email Report Sending ─────────────────────────────────────────────────────

@app.route("/project/<int:pid>/email", methods=["GET", "POST"])
@login_required
def project_email(pid):
    """Send a PDF report to recipients via SMTP."""
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        flash("Run calculations first.", "warning")
        return redirect(url_for("project_results", pid=pid))

    REPORT_OPTIONS = [
        ("BOQ Report",          url_for("export_pdf_boq",        pid=pid)),
        ("Economic Analysis",   url_for("export_pdf_economic",    pid=pid)),
        ("Energy Impact",       url_for("export_pdf_energy",      pid=pid)),
        ("AC Cable Schedule",   url_for("export_pdf_cable",       pid=pid)),
        ("Installation Plan",   url_for("export_pdf_installation",pid=pid)),
        ("Staffing Plan",       url_for("export_pdf_staffing",    pid=pid)),
        ("Site Assessment",     url_for("export_pdf_inspection",  pid=pid)),
    ]

    if request.method == "POST":
        csrf_protect()
        recipients = [e.strip() for e in request.form.get("recipients","").split(",") if e.strip()]
        subject    = request.form.get("subject","").strip() or f"Solar Project Report — {project['name']}"
        body_text  = request.form.get("body","").strip()
        report_key = request.form.get("report", "")

        if not recipients:
            flash("Enter at least one recipient email.", "warning")
            return redirect(url_for("project_email", pid=pid))

        if not SMTP_HOST or not SMTP_USER:
            # Log attempt but inform user SMTP not configured
            with get_db() as c:
                c.execute(
                    "INSERT INTO email_logs (user_id,project_id,recipients,subject,status,error_msg) "
                    "VALUES (?,?,?,?,?,?)",
                    (session["user_id"], pid, ",".join(recipients), subject,
                     "failed", "SMTP not configured — set SMTP_HOST, SMTP_USER, SMTP_PASS in .env"))
            flash(
                "SMTP not configured. Add SMTP_HOST / SMTP_USER / SMTP_PASS to your .env file. "
                "Your Gmail, Outlook, or any free SMTP works.", "warning")
            return redirect(url_for("project_email", pid=pid))

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart()
            msg["From"]    = SMTP_FROM
            msg["To"]      = ", ".join(recipients)
            msg["Subject"] = subject
            msg.attach(MIMEText(body_text or
                f"Please find the solar project report for {project['name']} attached.\n\n"
                f"Generated by SolarPro Global.", "plain"))

            if SMTP_TLS:
                srv = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
                srv.ehlo()
                srv.starttls()
            else:
                srv = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_FROM, recipients, msg.as_string())
            srv.quit()

            with get_db() as c:
                c.execute(
                    "INSERT INTO email_logs (user_id,project_id,recipients,subject,status) "
                    "VALUES (?,?,?,?,?)",
                    (session["user_id"], pid, ",".join(recipients), subject, "sent"))
            flash(f"Email sent to: {', '.join(recipients)}", "success")
        except Exception as ex:
            with get_db() as c:
                c.execute(
                    "INSERT INTO email_logs (user_id,project_id,recipients,subject,status,error_msg) "
                    "VALUES (?,?,?,?,?,?)",
                    (session["user_id"], pid, ",".join(recipients), subject, "failed", str(ex)))
            flash(f"Email failed: {ex}", "danger")

        return redirect(url_for("project_email", pid=pid))

    user = current_user()
    with get_db() as c:
        logs = c.execute(
            "SELECT * FROM email_logs WHERE project_id=? ORDER BY created_at DESC LIMIT 10",
            (pid,)).fetchall()
    smtp_ok = bool(SMTP_HOST and SMTP_USER)
    return render_template("email_report.html", user=user, project=project,
                           d=project["data"], report_options=REPORT_OPTIONS,
                           smtp_ok=smtp_ok, logs=logs)


# ─── DOCX Export ─────────────────────────────────────────────────────────────

@app.route("/project/<int:pid>/export/docx")
@login_required
@limiter.limit("10 per minute")
def export_docx(pid):
    """Full Word document report — Summary + Load Schedule + BOQ + Financial + Cable."""
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        flash("Run calculations first.", "warning")
        return redirect(url_for("project_results", pid=pid))

    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    r   = project["data"]["results"]
    d   = project["data"]
    eco = r["economics"]
    sym = d.get("symbol", "$")

    doc = Document()

    # ── Page layout ────────────────────────────────────────────────────────────
    section = doc.sections[0]
    section.page_width  = Inches(8.27)
    section.page_height = Inches(11.69)
    section.left_margin = section.right_margin = Inches(1.0)
    section.top_margin  = section.bottom_margin = Inches(0.9)

    GOLD  = RGBColor(0xF5, 0x9E, 0x0B)
    DARK  = RGBColor(0x1E, 0x3A, 0x8A)
    GREY  = RGBColor(0x6B, 0x72, 0x80)

    def _heading(text, level=1, color=DARK):
        p = doc.add_heading(text, level=level)
        p.runs[0].font.color.rgb = color
        return p

    def _para(text, bold=False, size=10):
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)
        return p

    def _table_row(tbl, values, bold=False, shade=None):
        row = tbl.add_row()
        for i, v in enumerate(values):
            cell = row.cells[i]
            cell.text = str(v)
            for run in cell.paragraphs[0].runs:
                run.bold = bold
                run.font.size = Pt(9)
            if shade:
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:fill"), shade)
                shd.set(qn("w:val"), "clear")
                tcPr.append(shd)

    # ── Title page ────────────────────────────────────────────────────────────
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = t.add_run("SolarPro Global")
    run.bold = True; run.font.size = Pt(22); run.font.color.rgb = GOLD

    doc.add_paragraph()
    t2 = doc.add_paragraph()
    t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = t2.add_run(project["name"])
    run2.bold = True; run2.font.size = Pt(16); run2.font.color.rgb = DARK

    t3 = doc.add_paragraph()
    t3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t3.add_run(f"Solar PV System Design Report\n"
               f"{d.get('region','')}, {d.get('country','')}\n"
               f"Generated: {datetime.now().strftime('%d %B %Y')}")

    doc.add_page_break()

    # ── 1. Project Summary ────────────────────────────────────────────────────
    _heading("1. Project Summary")
    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = "Table Grid"
    _table_row(tbl, ["Parameter", "Value"], bold=True, shade="1E3A8A")
    for k, v in [
        ("Location",         f"{d.get('region','')}, {d.get('country','')}"),
        ("System Type",      d.get("system_type","").title()),
        ("Phase",            "Three-Phase 415V" if d.get("phase")=="three" else "Single-Phase 230V"),
        ("Daily Demand",     f"{r['daily_kwh']:.3f} kWh/day"),
        ("PV Array",         f"{r['pv_kw']:.3f} kWp ({r['num_panels']} × {r.get('panel_wp',400)} Wp)"),
        ("Battery",          f"{r['bat_kwh']:.2f} kWh ({r['num_bat']} × {r['unit_bat_kwh']:.2g} kWh {r.get('chemistry','')})"),
        ("Inverter",         f"{r['inv_kw']:.1f} kW"),
        ("System Cost",      f"{sym} {eco['total_local']:,.0f}"),
        ("Simple Payback",   f"{eco['payback']:.1f} years"),
        ("NPV (25yr)",       f"{sym} {eco['npv']:,.0f}"),
        ("IRR",              f"{eco['irr_pct']:.1f}%" if eco["irr_pct"] else "N/A"),
        ("DSCR",             f"{eco['dscr']:.2f}"),
        ("Bankability",      eco["bankability"]),
        ("Verdict",          eco["verdict"]),
        ("CO₂ Reduction",    f"{eco['co2_yr']:.2f} t/year"),
    ]:
        _table_row(tbl, [k, v])

    doc.add_paragraph()

    # ── 2. Load Schedule ─────────────────────────────────────────────────────
    _heading("2. Electrical Load Schedule")
    tbl2 = doc.add_table(rows=1, cols=7)
    tbl2.style = "Table Grid"
    _table_row(tbl2, ["Category","Load Name","W","Qty","Hrs/Day","kWh/Day","Critical"],
               bold=True, shade="1E3A8A")
    tot = 0.0
    for ld in d.get("loads", []):
        kwh = float(ld.get("wattage",0))*float(ld.get("quantity",1))*float(ld.get("hours",0))/1000
        tot += kwh
        _table_row(tbl2, [ld.get("category",""), ld.get("name",""),
                          ld.get("wattage",0), ld.get("quantity",1),
                          ld.get("hours",0), f"{kwh:.3f}",
                          "Yes" if ld.get("critical") else ""])
    _table_row(tbl2, ["","","","","","TOTAL",f"{tot:.3f} kWh/day"], bold=True)
    doc.add_paragraph()

    # ── 3. Bill of Quantities ─────────────────────────────────────────────────
    _heading("3. Bill of Quantities (BOQ)")
    tbl3 = doc.add_table(rows=1, cols=6)
    tbl3.style = "Table Grid"
    _table_row(tbl3, ["No.","Description","Qty","Unit",f"Rate ({sym})",f"Amount ({sym})"],
               bold=True, shade="1E3A8A")
    for row in r.get("boq_rows", []):
        _table_row(tbl3, [row["no"], row["desc"], row["qty"], row["unit"],
                          f"{row['total_r']:.2f}", f"{row['amount']:.2f}"])
    _table_row(tbl3, ["","","","","GRAND TOTAL", f"{sym} {r.get('boq_grand',0):.2f}"],
               bold=True, shade="F59E0B")
    doc.add_paragraph()

    # ── 4. Financial Analysis ─────────────────────────────────────────────────
    _heading("4. Financial Engineering & Economic Analysis")
    tbl4 = doc.add_table(rows=1, cols=2)
    tbl4.style = "Table Grid"
    _table_row(tbl4, ["Metric","Value"], bold=True, shade="1E3A8A")
    for k, v in [
        ("Total Investment",        f"{sym} {eco['total_local']:,.0f}"),
        ("Annual Generation",       f"{eco['annual_kwh']:,.0f} kWh/yr"),
        ("Gross Annual Saving",     f"{sym} {eco['annual_sav']:,.0f}/yr"),
        ("Net Annual Benefit (Y1)", f"{sym} {eco['net_yr1']:,.0f}/yr"),
        ("Simple Payback",          f"{eco['payback']:.1f} years"),
        ("NPV (25yr, 12% disc.)",   f"{sym} {eco['npv']:,.0f}"),
        ("IRR",                     f"{eco['irr_pct']:.1f}%" if eco["irr_pct"] else "N/A"),
        ("ROI (25yr)",              f"{eco['roi_pct']:.0f}%"),
        ("Loan Amount (70%)",       f"{sym} {eco['loan_amt']:,.0f}"),
        ("Monthly Repayment",       f"{sym} {eco['pmt']:,.0f}"),
        ("DSCR",                    f"{eco['dscr']:.2f}"),
        ("Bankability",             eco["bankability"]),
        ("Verdict",                 eco["verdict"]),
        ("CO₂ Savings",             f"{eco['co2_yr']:.2f} t/year"),
        ("25-yr Cumulative Saving", f"{sym} {eco['cumul_25']:,.0f}"),
    ]:
        _table_row(tbl4, [k, v])

    doc.add_paragraph()
    _heading("4.1 Cash Flow Projection (25 Years)", level=2)
    tbl5 = doc.add_table(rows=1, cols=5)
    tbl5.style = "Table Grid"
    _table_row(tbl5, ["Year",f"Gross ({sym})",f"O&M ({sym})",f"Net ({sym})",f"Cumulative ({sym})"],
               bold=True, shade="1E3A8A")
    for cf in eco.get("cf_rows", []):
        flag = " ← BREAK-EVEN" if eco.get("breakeven") and cf["yr"]==eco["breakeven"] else ""
        _table_row(tbl5, [cf["yr"], f"{cf['gross']:,.0f}", f"{cf['om']:,.0f}",
                          f"{cf['net']:,.0f}", f"{cf['cumul']:,.0f}{flag}"])
    doc.add_paragraph()

    # ── 5. AC Cable Schedule ──────────────────────────────────────────────────
    _heading("5. AC Cable Sizing Schedule")
    tbl6 = doc.add_table(rows=1, cols=7)
    tbl6.style = "Table Grid"
    _table_row(tbl6, ["Circuit","Power (kW)","Ib (A)","L (m)","Cable (mm²)","VD (%)","Breaker"],
               bold=True, shade="1E3A8A")
    for c2 in r.get("ac_cables", []):
        _table_row(tbl6, [c2["circuit"], c2["power_kw"], c2["design_current"],
                          c2["length_m"], f"{c2['cable_size_mm2']} mm²",
                          f"{c2['vd_percent']:.2f}%", f"{c2['breaker_a']} A"])
    doc.add_paragraph()

    _para("Standard: BS 7671:2018 / IEC 60364-5-52 | Temperature derating and grouping factors applied.",
          size=9)
    _para(f"Report generated by SolarPro Global — {datetime.now().strftime('%d %B %Y')}", size=9)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    fname = f"SolarPro_{project['name'].replace(' ','_')}_FullReport.docx"
    return send_file(buf,
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     as_attachment=True, download_name=fname)


# ─── SaaS Platform Stats API (admin) ─────────────────────────────────────────

@app.route("/admin/platform")
@admin_required
def admin_platform():
    """SaaS platform metrics — MRR, churn, active users, project pipeline."""
    with get_db() as c:
        users       = c.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        total_users = len(users)
        paid_users  = sum(1 for u in users if (u["plan"] or "free") not in ("free","disabled"))
        plan_dist   = {}
        for u in users:
            p = (u["plan"] or "free").lower()
            plan_dist[p] = plan_dist.get(p, 0) + 1

        total_rev   = c.execute("SELECT SUM(amount_usd) FROM payments WHERE status='success'").fetchone()[0] or 0
        proj_count  = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        ticket_open = c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        leads_new   = c.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
        subs_count  = c.execute("SELECT COUNT(*) FROM newsletter_subscribers WHERE status='active'").fetchone()[0]
        email_sent  = c.execute("SELECT COUNT(*) FROM email_logs WHERE status='sent'").fetchone()[0]

        # Monthly revenue
        monthly_rev = c.execute(
            "SELECT strftime('%Y-%m', created_at) as mo, SUM(amount_usd) as rev "
            "FROM payments WHERE status='success' GROUP BY mo ORDER BY mo DESC LIMIT 12").fetchall()

        # MRR estimate — sum of current paid plan monthly prices
        MRR = sum(PLAN_PRICES.get((u["plan"] or "free").lower(), {}).get("usd", 0)
                  for u in users if (u["plan"] or "free") not in ("free","disabled","demo"))

        recent_users = users[:10]
        payments     = c.execute(
            "SELECT p.*, u.username FROM payments p JOIN users u ON p.user_id=u.id "
            "WHERE p.status='success' ORDER BY p.created_at DESC LIMIT 20").fetchall()

    return render_template("admin_platform.html", user=current_user(),
                           total_users=total_users, paid_users=paid_users,
                           plan_dist=plan_dist, total_rev=total_rev,
                           proj_count=proj_count, ticket_open=ticket_open,
                           leads_new=leads_new, subs_count=subs_count,
                           email_sent=email_sent, monthly_rev=monthly_rev,
                           MRR=MRR, recent_users=recent_users, payments=payments,
                           plan_prices=PLAN_PRICES)


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(403)
def err_403(e):
    return render_template("error.html", code=403,
        title="Access Denied",
        message="You don't have permission to access this page. "
                "If you submitted a form, please go back and try again."), 403

@app.errorhandler(404)
def err_404(e):
    return render_template("error.html", code=404,
        title="Page Not Found",
        message="The page you're looking for doesn't exist or has been moved."), 404

@app.errorhandler(429)
def err_429(e):
    return render_template("error.html", code=429,
        title="Too Many Requests",
        message="You've made too many requests in a short time. "
                "Please wait a moment and try again."), 429

@app.errorhandler(500)
def err_500(e):
    return render_template("error.html", code=500,
        title="Internal Server Error",
        message="Something went wrong on our end. "
                "Please go back to the dashboard and try again."), 500


# ─── Client Prospecting Agent ─────────────────────────────────────────────────

@app.route("/admin/agent")
@admin_required
def admin_agent():
    with get_db() as c:
        saved = c.execute(
            "SELECT * FROM leads WHERE source='agent' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        total_saved = c.execute(
            "SELECT COUNT(*) FROM leads WHERE source='agent'"
        ).fetchone()[0]
    return render_template("admin_agent.html", user=current_user(),
                           saved_leads=saved, total_saved=total_saved,
                           has_ai=bool(os.environ.get("ANTHROPIC_API_KEY")))


@app.route("/admin/agent/run", methods=["POST"])
@admin_required
@limiter.limit("20 per hour")
def admin_agent_run():
    csrf_protect()
    country   = request.form.get("country", "").strip()
    sector    = request.form.get("sector", "Commercial")
    system_kw = request.form.get("system_kw", "10-100")
    budget    = request.form.get("budget", "$5,000-$100,000")
    focus     = request.form.get("focus", "").strip()
    count     = min(int(request.form.get("count", 8)), 12)

    loc       = country if country else "Ghana"
    loc_q     = f'"{loc}"'
    loc_label = loc

    # ── Step 1: Deep multi-source search ─────────────────────────────────────────
    search_results = []
    search_error   = None

    # ── Country aliases: include major cities so results aren't missed ────────
    COUNTRY_CITIES = {
        "ghana":        ["ghana", "ghanaian", "accra", "kumasi", "takoradi", "tema",
                         "tamale", "cape coast", "sunyani", "wa", "ho", "koforidua",
                         "bolgatanga", ".gh"],
        "nigeria":      ["nigeria", "nigerian", "lagos", "abuja", "kano", "ibadan",
                         "port harcourt", "enugu", "kaduna", "benin city", ".ng"],
        "kenya":        ["kenya", "kenyan", "nairobi", "mombasa", "kisumu", "nakuru", ".ke"],
        "south africa": ["south africa", "johannesburg", "cape town", "durban",
                         "pretoria", "gauteng", ".za"],
        "tanzania":     ["tanzania", "dar es salaam", "dodoma", "arusha", ".tz"],
        "zambia":       ["zambia", "lusaka", "ndola", "kitwe", ".zm"],
        "ethiopia":     ["ethiopia", "addis ababa", "dire dawa", ".et"],
        "senegal":      ["senegal", "dakar", ".sn"],
        "cameroon":     ["cameroon", "douala", "yaounde", ".cm"],
        "uganda":       ["uganda", "kampala", ".ug"],
        "rwanda":       ["rwanda", "kigali", ".rw"],
        "uk":           ["united kingdom", "england", "scotland", "wales", "london",
                         "birmingham", "manchester", ".uk", ".co.uk"],
        "usa":          ["united states", "america", ".gov", ".edu"],
        "india":        ["india", "indian", "mumbai", "delhi", "bangalore", ".in"],
    }
    loc_lower   = loc.lower()
    loc_aliases = COUNTRY_CITIES.get(loc_lower, [loc_lower])

    try:
        from ddgs import DDGS

        # ── Portal groups ──────────────────────────────────────────────────────
        UN_PORTALS = (
            "site:ungm.org OR site:devex.com OR site:reliefweb.int "
            "OR site:dgmarket.com OR site:tendersinfo.com"
        )
        DFI_PORTALS = (
            "site:worldbank.org OR site:afdb.org OR site:ifc.org "
            "OR site:esmap.org OR site:geapp.org"
        )
        AFRICA_PORTALS = (
            "site:africatenders.com OR site:tendersontime.com "
            "OR site:globaltenders.com OR site:ecreee.org"
        )
        # ── Ghana-specific national institutions ───────────────────────────────
        GH_INSTITUTIONS = (
            "site:energycom.gov.gh OR site:moe.gov.gh OR site:purc.com.gh "
            "OR site:ghana.gov.gh OR site:vra.com OR site:gridcogh.com "
            "OR site:nedcoghana.com OR site:ppaghana.org OR site:eda.gov.gh"
        )
        GH_SOCIAL_SECTOR = (
            "site:ges.gov.gh OR site:moh.gov.gh OR site:ghs.gov.gh "
            "OR site:mofa.gov.gh OR site:mlgrd.gov.gh"
        )
        # ── Job board and social domains ───────────────────────────────────────
        JOB_DOMAINS   = ["jobberman.com", "myjobmag.com", "brightermonday.com",
                         "ghanaiansjobs.com", "jobsinghana.com", "indeed.com",
                         "jobsgha.com", "joblistghana.com"]
        SOCIAL_DOMAINS = ["facebook.com", "linkedin.com", "twitter.com", "x.com"]

        queries = [
            # === A: Formal procurement — quoted rfp phrases ==================
            f'"tender for" solar installation {loc_q} 2025 2026',
            f'"invitation to bid" solar PV {loc_q} 2025 2026',
            f'"request for proposals" solar {loc_q} 2025 2026',
            f'"expression of interest" solar {loc_q} installation 2025 2026',
            f'"call for tenders" solar {loc_q} 2025 2026',
            f'"request for quotation" solar PV {loc_q} 2025 2026',
            f'"tender notice" solar {loc_q} 2025 2026',
            f'"invitation to tender" solar {loc_q} 2025 2026',
            f'({UN_PORTALS}) solar {loc_q} tender OR ITB OR RFP 2025 2026',
            f'({DFI_PORTALS}) solar {loc_q} tender OR "invitation to bid" 2025 2026',
            f'({AFRICA_PORTALS}) solar {loc_q} tender OR RFP 2025 2026',
            # === B: National institutions & utilities ========================
            f'({GH_INSTITUTIONS}) solar tender OR procurement OR RFP 2025 2026',
            f'({GH_SOCIAL_SECTOR}) solar tender OR procurement 2025 2026',
            f'{loc_q} "VRA" OR "ECG" OR "NEDCo" OR "GRIDCo" solar tender OR RFP 2025 2026',
            f'{loc_q} public procurement authority solar installation 2025 2026',
            # === C: Regional coordinating councils & district assemblies =====
            f'{loc_q} "regional coordinating council" solar tender OR procurement 2025 2026',
            f'{loc_q} "district assembly" solar installation tender OR contract 2025 2026',
            f'{loc_q} "metropolitan assembly" solar tender OR installation 2025 2026',
            f'{loc_q} local government solar installation tender OR RFP 2025 2026',
            # === D: Private sector — hospitals, hotels, factories, schools ===
            f'{loc_q} hospital OR clinic solar installation tender OR RFP 2025 2026',
            f'{loc_q} school OR university solar installation tender OR contract 2025 2026',
            f'{loc_q} hotel OR factory OR warehouse solar installation tender 2025 2026',
            f'{loc_q} farm OR agri solar irrigation tender OR installation 2025 2026',
            f'{loc_q} church OR mosque OR community solar installation tender 2025 2026',
            # === E: Social media — homeowners & businesses ==================
            f'site:facebook.com {loc_q} solar "looking for installer" OR "need solar" OR "solar quote" 2025',
            f'site:facebook.com {loc_q} solar "recommend" OR "how much" OR "who installs" 2025',
            f'site:facebook.com {loc_q} solar "dumsor" OR "ECG" OR "light bill" OR "generator" 2025',
            f'site:facebook.com {loc_q} "solar panels" "contact" OR "WhatsApp" OR "call" 2025',
            f'site:linkedin.com {loc_q} solar "contractor" OR "seeking" OR "project" OR "tender" 2025',
            # === F: Job boards — installer hiring = active project ===========
            f'site:jobberman.com solar {loc_q} installer OR technician OR engineer 2025',
            f'site:myjobmag.com solar {loc_q} installer OR technician 2025',
            f'site:brightermonday.com.gh solar installer OR technician 2025',
            f'{loc_q} "solar technician" OR "solar installer" OR "solar engineer" job vacancy 2025',
            # === G: Open web — power problems driving solar demand ===========
            f'{loc_q} "solar backup" OR "solar inverter" "supply and install" 2025 2026',
            f'{loc_q} "off-grid solar" installation contractor OR tender 2025 2026',
            f'{loc_q} "solar panels" "supply and install" OR "design and install" 2025 2026',
            f'{loc_q} "rooftop solar" installation quote OR tender OR contract 2025 2026',
        ]
        if focus:
            queries.insert(0, f'{loc_q} "{focus}" solar installation tender OR "looking for" OR RFP OR quote 2025 2026')

        # ── Domains to always skip (news, analytics, pure editorial) ─────────
        skip_domains = [
            "pv-magazine", "pvtech", "reuters.com", "bloomberg.com",
            "wikipedia.org", "youtube.com", "tiktok.com",
            "solarpowerworldonline", "greentechmedia", "renewableenergyworld",
            "pv-tech.org", "cleantechnica.com", "energymonitor.ai",
            "spglobal.com", "woodmac.com",
            "theguardian.com", "bbc.com", "cnn.com", "aljazeera.com",
            "businessghana.com", "ghanaweb.com", "myjoyonline.com",
            "modernghana.com", "ghanaiantimes.com", "graphic.com.gh",
            "punchng.com", "vanguardngr.com", "thecable.ng", "premiumtimesng.com",
            "nairametrics.com", "businessday.ng",
            "zawya.com", "menafn.com", "arabnews.com",
            "esi-africa.com", "theafricareport.com", "energy-pedia.com",
            "irena.org/news", "afdb.org/en/news", "worldbank.org/en/news",
            "adb.org/news", "adb.org/results", "ifc.org/en/stories",
        ]
        # ── News/editorial URL path patterns ──────────────────────────────────
        news_url_paths = [
            "/news/", "/news-release", "/press-release", "/press/",
            "/blog/", "/article/", "/articles/",
            "/story/", "/stories/", "/newsroom/", "/en/news",
            "/feature/", "/highlights/", "/publication/",
            "/project-story", "/success-story", "/case-study",
            "worldbank.org/en/results", "afdb.org/en/news",
        ]
        # ── Category/index page patterns ─────────────────────────────────────
        listing_patterns = [
            "global-solar-tenders", "/tenders/search", "/tenders/adminShow",
            "globaltenders.com/gh/", "tendersontime.com/ghana-tenders/page",
            "developmentaid.org/tenders/search", "devex.com/funding/r?report=grant",
        ]
        # ── Completed-project title patterns (past tense = not open) ─────────
        news_title_words = [
            "awarded", "wins contract", "signs agreement", "signed agreement",
            "completes", "completed", "inaugurates", "inaugurated",
            "commissioned", "connected to grid", "goes live",
            "breaks ground", "broke ground", "milestone",
        ]
        # ── Procurement signals for formal sources ────────────────────────────
        rfp_keywords = [
            "tender", "rfp", "itb", "eoi",
            "invitation to bid", "invitation to tender",
            "request for proposal", "request for proposals",
            "request for quotation", "expression of interest",
            "call for tenders", "call for bids", "call for proposals",
            "tender notice", "procurement notice", "contract notice",
            "solicitation", "prequalif", "bidding document",
            "installation works", "epc contract", "works contract",
        ]
        # ── Opportunity signals for social/job/open-web sources ───────────────
        opportunity_keywords = [
            "solar", "install", "installer", "installation", "technician",
            "contractor", "supply", "design", "panel", "pv", "quote",
            "looking for", "need", "seeking", "required", "wanted",
            "vacancy", "hiring", "job", "project", "engineer",
        ]
        # ── Solar keyword gate ────────────────────────────────────────────────
        solar_keywords = [
            "solar", "photovoltaic", "pv system", "solar pv",
            "solar power", "solar energy", "solar plant", "solar farm",
            "mini grid", "minigrid", "off-grid solar", "renewable energy",
            "solar installation",
        ]

        def _real_url(raw):
            if not raw:
                return raw
            from urllib.parse import urlparse, parse_qs, unquote
            p = urlparse(raw)
            if "duckduckgo.com" in p.netloc:
                qs = parse_qs(p.query)
                for key in ("uddg", "u"):
                    if key in qs:
                        return unquote(qs[key][0])
            return raw

        def _is_social(url):
            return any(d in url for d in SOCIAL_DOMAINS)

        def _is_job_board(url):
            return any(d in url for d in JOB_DOMAINS)

        with DDGS() as ddgs:
            for q in queries:
                try:
                    for r in ddgs.text(q, max_results=10, safesearch="off"):
                        url   = _real_url(r.get("href", ""))
                        body  = r.get("body", "").lower()
                        title = r.get("title", "").lower()
                        # 1. Skip always-blocked news/editorial domains
                        if any(d in url for d in skip_domains):
                            continue
                        # 2. Skip news/editorial URL paths (not for social media)
                        url_lower = url.lower()
                        if not _is_social(url):
                            if any(p in url_lower for p in news_url_paths):
                                continue
                        # 3. Skip category/index listing pages
                        if any(p in url_lower for p in listing_patterns):
                            continue
                        # 4. Skip completed-project titles (past tense)
                        if any(w in title for w in news_title_words):
                            continue
                        # 5. Country or one of its major cities must appear in title, body, or URL
                        combined = title + " " + body + " " + url_lower
                        if not any(alias in combined for alias in loc_aliases):
                            continue
                        # 5b. Solar keyword required in title or body
                        if not any(kw in title or kw in body for kw in solar_keywords):
                            continue
                        # 6. Source-aware gate
                        if _is_social(url) or _is_job_board(url):
                            # Social/job: opportunity signal anywhere in title or body
                            if not any(kw in title or kw in body for kw in opportunity_keywords):
                                continue
                        else:
                            # Formal/government/portals: rfp keyword MUST be in TITLE
                            # Narratives and initiative pages never name themselves as tenders
                            if not any(kw in title for kw in rfp_keywords):
                                continue
                        # 7. Deduplicate
                        if url and not any(x.get("href") == url for x in search_results):
                            r["href"] = url
                            search_results.append(r)
                except Exception:
                    continue
                if len(search_results) >= 50:
                    break
    except Exception as e:
        search_error = str(e)

    # ── Step 2: Claude analyses real search results → structured prospects ───────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and search_results:
        try:
            import anthropic as _ant
            client = _ant.Anthropic(api_key=api_key)
            snippets = "\n\n".join(
                f"[{i+1}] TITLE: {r.get('title','')}\nURL: {r.get('href','')}\nSNIPPET: {r.get('body','')[:400]}"
                for i, r in enumerate(search_results[:12])
            )
            prompt = f"""You are a solar PV procurement intelligence analyst. You have been given real search results from tender portals and procurement databases. Extract ONLY genuine RFPs, tenders, and solicitations — not news articles.

Search criteria:
- Location: {loc_label}
- Sector: {sector}
- System size: {system_kw} kW
- Budget: {budget}
- Focus: {focus or 'general'}

REAL procurement search results:

{snippets}

STRICT RULES:
1. ONLY extract results that are genuine RFPs, tenders, invitations to bid, expressions of interest, or contract notices for solar/energy projects
2. SKIP any result that is a news article, blog post, or general information page
3. source_url = exact URL from the result, copied verbatim — do not modify or shorten
4. source_title = exact title, copied verbatim
5. company_name = the issuing organisation (government body, utility, NGO, bank) — NOT a made-up name
6. deadline = submission deadline if mentioned, else ""
7. tender_ref = reference number if stated, else ""
8. If a field is not stated in the result, use "" or 0 — never invent data
9. source_snippet = copy the most relevant sentence verbatim, max 300 chars

Return up to {count} results. Return ONLY valid JSON, no markdown:
{{
  "prospects": [
    {{
      "company_name": "Issuing organisation from result",
      "type": "RFP / Tender / EOI / ITB / Contract Notice",
      "location": "exact country/city from the result text — do NOT use the search country if the result says a different country",
      "estimated_kw": 0,
      "estimated_usd": 0,
      "pain_points": [],
      "pitch": "one sentence describing what they are procuring, from the result",
      "contact_strategy": "Submit bid by deadline via portal — see source link",
      "decision_maker": "procurement contact if named, else ''",
      "priority": "high if deadline within 60 days or large value, medium otherwise",
      "source_url": "https://exact-url-from-result.com/path",
      "source_title": "Exact title from result",
      "source_snippet": "verbatim key sentence from result body",
      "deadline": "",
      "tender_ref": "",
      "verified": true
    }}
  ]
}}"""
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:])
                if raw.endswith("```"):
                    raw = raw[:-3]
            data = json.loads(raw)
            return jsonify({"ok": True, "prospects": data["prospects"],
                            "source": "web+claude", "result_count": len(search_results)})
        except Exception as e:
            pass  # fall through to raw results

    # ── Step 3: Template extraction (no AI key) ──────────────────────────────────
    def _classify_source(url):
        u = url.lower()
        if any(d in u for d in ["facebook.com", "twitter.com", "x.com"]):
            return "Social Media Lead"
        if "linkedin.com" in u:
            return "LinkedIn Lead"
        if any(d in u for d in ["jobberman.com", "myjobmag.com", "brightermonday.com",
                                  "indeed.com", "jobsinghana.com", "ghanaiansjobs.com"]):
            return "Job Board — Active Project"
        if any(d in u for d in [".gov.gh", ".gov.ng", ".gov.ke", "gov.", "district",
                                  "assembly", "council", "ministry"]):
            return "Government / Public Sector"
        if any(d in u for d in ["ungm.org", "devex.com", "worldbank.org", "afdb.org",
                                  "reliefweb.int", "dgmarket.com", "tendersontime.com",
                                  "globaltenders.com", "africatenders.com"]):
            return "Tender Portal"
        return "Commercial / Private Sector"

    def _contact_strategy(source_type, url):
        if source_type == "Social Media Lead":
            return "Respond directly to the post — offer free site assessment and quote"
        if source_type == "LinkedIn Lead":
            return "Connect on LinkedIn, message offering a no-obligation solar audit"
        if source_type == "Job Board — Active Project":
            return "Company is hiring for a solar project — contact HR/procurement directly"
        if source_type == "Government / Public Sector":
            return "Submit formal expression of interest or bid via the government procurement portal"
        if source_type == "Tender Portal":
            return "Download tender documents and submit bid before closing date"
        return "Contact via source link — offer free survey and detailed quotation"

    def _infer_type(title, body):
        t = (title + " " + body).lower()
        if any(w in t for w in ["tender", "rfp", "itb", "invitation to bid", "call for"]):
            return "Tender / RFP"
        if any(w in t for w in ["expression of interest", "eoi", "prequalif"]):
            return "Expression of Interest"
        if any(w in t for w in ["job", "vacancy", "hiring", "technician", "installer"]):
            return "Job Post — Active Project"
        if any(w in t for w in ["looking for", "need", "quote", "recommend", "how much"]):
            return "Social Media — Seeking Installer"
        return "Solar Project Opportunity"

    if search_results:
        prospects = []
        for r in search_results[:count]:
            title   = r.get("title", "")
            url     = r.get("href", "")
            snippet = r.get("body", "")
            src_type = _classify_source(url)
            prospects.append({
                "company_name":    title[:80] if title else "Unknown",
                "type":            _infer_type(title, snippet),
                "location":        loc,
                "estimated_kw":    0,
                "estimated_usd":   0,
                "pain_points":     [src_type],
                "pitch":           snippet[:250] if snippet else "",
                "contact_strategy": _contact_strategy(src_type, url),
                "decision_maker":  "See source",
                "priority":        "medium",
                "source_url":      url,
                "source_title":    title,
                "source_snippet":  snippet[:300],
                "verified":        True,
            })
        return jsonify({"ok": True, "prospects": prospects,
                        "source": "web_search", "result_count": len(search_results)})

    # ── Step 4: Last resort — inform user search failed ─────────────────────────
    return jsonify({"ok": False,
                    "error": f"Web search returned no results. {search_error or ''} "
                             "Try different search criteria or add an ANTHROPIC_API_KEY."})


@app.route("/admin/agent/save", methods=["POST"])
@admin_required
def admin_agent_save():
    csrf_protect()
    name     = request.form.get("name", "").strip()
    company  = request.form.get("company", "").strip()
    country  = request.form.get("country", "").strip()
    interest = request.form.get("interest", "solar").strip()
    notes    = request.form.get("notes", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name required"}), 400
    with get_db() as c:
        existing = c.execute(
            "SELECT id FROM leads WHERE company=? AND source='agent'", (company,)
        ).fetchone()
        if existing:
            return jsonify({"ok": False, "error": "Already saved"}), 409
        c.execute(
            "INSERT INTO leads (name,email,phone,company,country,interest,message,source,status) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (name, "", "", company, country, interest, notes, "agent", "new")
        )
    return jsonify({"ok": True})


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
