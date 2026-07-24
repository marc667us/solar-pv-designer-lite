# Byte-level patch (web_app.py is CRLF + mojibake -- never Edit directly).
#
# Codex HIGH fix (slice 1): isolate schema-ensure, evidence and audit onto their
# OWN DB connections so a failure there can never poison the payment's
# transaction. On Postgres, a swallowed SQL error inside an open transaction
# leaves it aborted (InFailedSqlTransaction) -- so sharing the payment's
# connection meant a schema/evidence hiccup could make the payment itself fail,
# or roll back an already-inserted payment on commit. Payments must never
# regress. Each concern now runs in its own `with get_db()` block, wrapped so
# best-effort truly means best-effort.
#
# Asserts the target matches exactly once and the file byte-compiles.

import py_compile

PATH = "web_app.py"
data = open(PATH, "rb").read()

OLD = (
    b'    _inserted = True\r\n'
    b'    with get_db() as c:\r\n'
    b'        try:\r\n'
    b'            _pi.ensure_payment_integrity_schema(c, bool(os.environ.get("DATABASE_URL")))\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'        # INSERT OR IGNORE + the ux_payments_reference unique index give\r\n'
    b'        # DB-level idempotency: a duplicate gateway reference cannot create\r\n'
    b'        # a second payment row even under a webhook-retry race. db_adapter\r\n'
    b'        # translates OR IGNORE to ON CONFLICT DO NOTHING on Postgres.\r\n'
    b'        _cur = c.execute(\r\n'
    b'            "INSERT OR IGNORE INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status) "\r\n'
    b'            "VALUES (?,?,?,?,?,?,?)",\r\n'
    b'            (uid, gateway, plan, amount_usd, currency, reference, status))\r\n'
    b'        try:\r\n'
    b'            _inserted = (_cur.rowcount != 0)\r\n'
    b'        except Exception:\r\n'
    b'            _inserted = True\r\n'
    b'        user_row = c.execute("SELECT email, username FROM users WHERE id=?", (uid,)).fetchone()\r\n'
    b'        # Evidence ledger + audit trail (best-effort; never breaks a payment).\r\n'
    b'        try:\r\n'
    b'            _client_ip = _get_real_ip()\r\n'
    b'        except Exception:\r\n'
    b'            _client_ip = ""\r\n'
    b'        _pi.record_payment_event(\r\n'
    b'            c, reference=reference, gateway=gateway,\r\n'
    b'            event_type=("payment_recorded" if _inserted else "duplicate_blocked"),\r\n'
    b'            user_id=uid, amount_usd=amount_usd, signature_verified=True,\r\n'
    b'            client_ip=_client_ip,\r\n'
    b'            payload={"plan": plan, "currency": currency, "status": status})\r\n'
    b'    try:\r\n'
    b'        _write_audit_event(\r\n'
    b'            "payment_recorded" if _inserted else "payment_duplicate_blocked",\r\n'
    b'            user_id=uid,\r\n'
    b'            details=json.dumps({"gateway": gateway, "plan": plan,\r\n'
    b'                                "amount_usd": amount_usd, "reference": reference}))\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
)

NEW = (
    b'    # 1. Ensure the evidence schema on ITS OWN connection. On Postgres a\r\n'
    b'    #    failed DDL (e.g. CREATE UNIQUE INDEX) aborts the whole transaction,\r\n'
    b'    #    so this MUST NOT share the payment transaction -- otherwise a schema\r\n'
    b'    #    hiccup could make the payment itself fail (Codex HIGH, slice 1).\r\n'
    b'    try:\r\n'
    b'        with get_db() as _sc:\r\n'
    b'            _pi.ensure_payment_integrity_schema(_sc, bool(os.environ.get("DATABASE_URL")))\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
    b'    # 2. The payment write, in a clean transaction of its own. INSERT OR\r\n'
    b'    #    IGNORE + the ux_payments_reference unique index give DB-level\r\n'
    b'    #    idempotency for real gateway payments: a duplicate reference cannot\r\n'
    b'    #    create a second row even under a webhook-retry race. db_adapter\r\n'
    b'    #    translates OR IGNORE to ON CONFLICT DO NOTHING on Postgres.\r\n'
    b'    _inserted = True\r\n'
    b'    with get_db() as c:\r\n'
    b'        _cur = c.execute(\r\n'
    b'            "INSERT OR IGNORE INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status) "\r\n'
    b'            "VALUES (?,?,?,?,?,?,?)",\r\n'
    b'            (uid, gateway, plan, amount_usd, currency, reference, status))\r\n'
    b'        try:\r\n'
    b'            _inserted = (_cur.rowcount != 0)\r\n'
    b'        except Exception:\r\n'
    b'            _inserted = True\r\n'
    b'        user_row = c.execute("SELECT email, username FROM users WHERE id=?", (uid,)).fetchone()\r\n'
    b'    # 3. Evidence ledger + audit on SEPARATE connections -- best-effort and\r\n'
    b'    #    isolated, so a failure here can never poison the committed payment.\r\n'
    b'    try:\r\n'
    b'        _client_ip = _get_real_ip()\r\n'
    b'    except Exception:\r\n'
    b'        _client_ip = ""\r\n'
    b'    try:\r\n'
    b'        with get_db() as _ec:\r\n'
    b'            _pi.record_payment_event(\r\n'
    b'                _ec, reference=reference, gateway=gateway,\r\n'
    b'                event_type=("payment_recorded" if _inserted else "duplicate_blocked"),\r\n'
    b'                user_id=uid, amount_usd=amount_usd, signature_verified=True,\r\n'
    b'                client_ip=_client_ip,\r\n'
    b'                payload={"plan": plan, "currency": currency, "status": status})\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
    b'    try:\r\n'
    b'        _write_audit_event(\r\n'
    b'            "payment_recorded" if _inserted else "payment_duplicate_blocked",\r\n'
    b'            user_id=uid,\r\n'
    b'            details=json.dumps({"gateway": gateway, "plan": plan,\r\n'
    b'                                "amount_usd": amount_usd, "reference": reference}))\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
)

assert data.count(OLD) == 1, "target block not unique/found"
data = data.replace(OLD, NEW)
open(PATH, "wb").write(data)
py_compile.compile(PATH, doraise=True)
print("OK: isolated schema/evidence/audit onto separate connections; byte-compiles clean.")
