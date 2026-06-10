def init_db():
    # ── Backend detection ──────────────────────────────────────────────
    # When DATABASE_URL is set the mirror-SQLite migration owns the
    # table + column shape (migrations/001_mirror_sqlite.sql). The
    # SQLite-only DDL paths below would either fail (AUTOINCREMENT) or
    # abort the Postgres transaction (ALTER on an existing column).
    # The seed phase further down runs on BOTH backends — it inserts
    # rows, doesn't touch schema.
    _is_postgres = bool(os.environ.get("DATABASE_URL"))

    if not _is_postgres:
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
            -- Referral program columns (REFERRAL_BACKFILL_DONE marker for idempotency)
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referee_id  INTEGER NOT NULL UNIQUE,
                signup_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                upgraded_at TEXT,
                plan_at_upgrade TEXT,
                reward_status   TEXT DEFAULT 'pending',
                FOREIGN KEY (referrer_id) REFERENCES users(id),
                FOREIGN KEY (referee_id)  REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name    TEXT NOT NULL,
                stage   TEXT DEFAULT 'new',
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
            CREATE TABLE IF NOT EXISTS monitor_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT UNIQUE NOT NULL,
                title       TEXT DEFAULT '',
                snippet     TEXT DEFAULT '',
                country     TEXT DEFAULT '',
                source_type TEXT DEFAULT '',
                is_new      INTEGER DEFAULT 1,
                found_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS monitor_state (
                id               INTEGER PRIMARY KEY CHECK (id = 1),
                last_scan        TEXT DEFAULT '',
                last_count       INTEGER DEFAULT 0,
                is_running       INTEGER DEFAULT 0,
                scan_interval    INTEGER DEFAULT 120,
                notify_email     INTEGER DEFAULT 0,
                last_agent_run   TEXT DEFAULT '',
                agent_run_count  INTEGER DEFAULT 0
            );
            INSERT OR IGNORE INTO monitor_state (id) VALUES (1);
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                token      TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                used       INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS helpline_learned_kb (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                agent      TEXT DEFAULT 'helpline',
                question   TEXT NOT NULL,
                answer     TEXT NOT NULL,
                use_count  INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS beta_signups (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                email       TEXT UNIQUE NOT NULL,
                company     TEXT DEFAULT '',
                role        TEXT DEFAULT '',
                status      TEXT DEFAULT 'pending',
                invited_at  TEXT DEFAULT '',
                notes       TEXT DEFAULT '',
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS beta_feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER DEFAULT NULL,
                username    TEXT DEFAULT '',
                email       TEXT DEFAULT '',
                type        TEXT DEFAULT 'general',
                message     TEXT NOT NULL,
                page        TEXT DEFAULT '',
                status      TEXT DEFAULT 'new',
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER DEFAULT NULL,
                username    TEXT DEFAULT '',
                action      TEXT NOT NULL,
                ip_address  TEXT DEFAULT '',
                details     TEXT DEFAULT '',
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS login_failures (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL,
                ip_address  TEXT NOT NULL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)
        # Migrate older DBs — ignore if column already exists.
        # SQLite swallows the duplicate-column error via try/except. Postgres
        # would abort the transaction on the first dup, so we gate the whole
        # block — the mirror migration already has these columns baked in.
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
            # projects lifecycle stage column
            "ALTER TABLE projects ADD COLUMN stage TEXT DEFAULT 'new'",
            # monitor_state: configurable interval + email notifications
            "ALTER TABLE monitor_state ADD COLUMN scan_interval INTEGER DEFAULT 120",
            "ALTER TABLE monitor_state ADD COLUMN notify_email INTEGER DEFAULT 0",
            "ALTER TABLE monitor_state ADD COLUMN last_agent_run TEXT DEFAULT ''",
            "ALTER TABLE monitor_state ADD COLUMN agent_run_count INTEGER DEFAULT 0",
            # Assessment intake v2 columns
            "ALTER TABLE assessment_requests ADD COLUMN assessment_ref TEXT DEFAULT ''",
            "ALTER TABLE assessment_requests ADD COLUMN building_desc TEXT DEFAULT ''",
            "ALTER TABLE assessment_requests ADD COLUMN building_size TEXT DEFAULT ''",
            "ALTER TABLE assessment_requests ADD COLUMN num_floors INTEGER DEFAULT 0",
            "ALTER TABLE assessment_requests ADD COLUMN building_type TEXT DEFAULT ''",
            "ALTER TABLE assessment_requests ADD COLUMN pipeline_stage TEXT DEFAULT 'assessment_submitted'",
            "ALTER TABLE assessment_requests ADD COLUMN region TEXT DEFAULT ''",
            # User roles (job function — separate from plan/billing tier)
            "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'customer'",
        ]:
            try:
                with get_db() as c:
                    c.execute(stmt)
            except Exception:
                pass
        # Migrate: org profile columns on users
        for col, defval in [
            ("org_name",    "''"),
            ("org_address", "''"),
            ("org_email",   "''"),
            ("org_phone",   "''"),
            ("org_website", "''"),
            ("timezone",    "'UTC'"),
            ("org_whatsapp","''"),
        ]:
            try:
                with get_db() as c:
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT {defval}")
            except Exception:
                pass
        # Migrate: date/time + per-user SMTP settings
        for col, defval in [
            ("date_format", "'DD/MM/YYYY'"),
            ("time_format", "'24h'"),
            ("smtp_host",   "''"),
            ("smtp_port",   "'587'"),
            ("smtp_user",   "''"),
            ("smtp_pass",   "''"),
            ("smtp_from",   "''"),
            ("smtp_tls",    "'starttls'"),
            ("resend_api_key", "''"),
        ]:
            try:
                with get_db() as c:
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT {defval}")
            except Exception:
                pass

    # ── Seed phase — runs on BOTH backends ─────────────────────────────
    # All operations below are row-level INSERT/UPDATE/SELECT, not DDL,
    # and work identically on SQLite + Postgres through the adapter.

    # Seed default users — ensure admin and owner accounts always exist
    def _seed_pwd(env_var):
        # Phase 1: route via secrets_broker (audit + tier + Vault-ready).
        # DEGRADED tier with built-in env warm-up preserves the existing
        # "env var required" guarantee while landing audit trail and the
        # Vault cutover path.
        _PATH_MAP = {
            "SOLARPRO_ADMIN_PASSWORD": ("seed/admin",     "password"),
            "SOLARPRO_OWNER_PASSWORD": ("seed/marc667us", "password"),
        }
        v = None
        mapping = _PATH_MAP.get(env_var)
        if mapping:
            path, field = mapping
            try:
                v = _sb.get(path, tier="DEGRADED")[field]
            except Exception:
                v = None
        if not v:
            v = os.environ.get(env_var)
        if not v:
            raise RuntimeError(env_var + " env var required for initial user seed (see SolarPro_Schedule_2026-06-08.md Phase 0.1)")
        return v
    _SEED_USERS = [
        ("admin",    "admin@solarpro.global", "Administrator", _seed_pwd("SOLARPRO_ADMIN_PASSWORD"), "enterprise", 1),
        ("marc667us","marc667us@yahoo.com",   "Marc",          _seed_pwd("SOLARPRO_OWNER_PASSWORD"),       "enterprise", 1),
    ]
    with get_db() as c:
        for uname, email, name, pwd, plan, is_admin in _SEED_USERS:
            exists = c.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
            if not exists:
                c.execute(
                    "INSERT INTO users (username,email,name,password_hash,plan,is_admin) "
                    "VALUES (?,?,?,?,?,?)",
                    (uname, email, name, generate_password_hash(pwd), plan, is_admin))

    # Referral-program columns: SQLite still uses ALTER TABLE for schema
    # evolution; Postgres has them baked in via the mirror migration.
    # Gate just the DDL — the UPDATE/SELECT backfill that follows runs
    # on both.
    if not _is_postgres:
        with get_db() as _c:
            try: _c.execute("ALTER TABLE users ADD COLUMN referral_code TEXT")
            except Exception: pass
            try: _c.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
            except Exception: pass
            try: _c.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
            except Exception: pass
            try: _c.execute("ALTER TABLE users ADD COLUMN email_verify_token TEXT")
            except Exception: pass

    # Referral-program backfill — runs on BOTH backends (row-level only).
    import secrets as _sec
    with get_db() as _c:
        # Backfill: any pre-existing user becomes verified (do not lock them out).
        try: _c.execute("UPDATE users SET email_verified=1 WHERE email_verified IS NULL OR email_verified=0")
        except Exception: pass
        # Backfill codes for any user that lacks one
        _missing = _c.execute("SELECT id FROM users WHERE referral_code IS NULL OR referral_code = ''").fetchall()
        for _row in _missing:
            while True:
                _code = _sec.token_urlsafe(6).replace('_','').replace('-','')[:8].upper()
                if not _c.execute("SELECT 1 FROM users WHERE referral_code = ?", (_code,)).fetchone():
                    _c.execute("UPDATE users SET referral_code = ? WHERE id = ?", (_code, _row[0]))
                    break

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
                ("Cables","DC Solar Cable 6mmÂ² (100m)","General","TUV 6mmÂ²","6mmÂ² TÃœV 1.8kV DC solar cable, UV-rated","Roll",85, sup.get("RS Components",0),14),
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
