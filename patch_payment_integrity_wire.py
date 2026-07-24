# Byte-level patch (web_app.py is CRLF + mojibake -- never Edit directly).
#
# Slice 1 wiring: route _record_payment through the payment integrity layer.
#   1. import new_payment_integrity as _pi
#   2. INSERT -> INSERT OR IGNORE (DB-level idempotency w/ ux_payments_reference)
#      + capture whether a row was actually inserted (rowcount)
#      + append an evidence-ledger row + an audit event (both best-effort)
#   3. gate the receipt email on _inserted, so a duplicate/retried webhook can
#      never send a second receipt.
#
# Every change is asserted to match exactly once; the file must byte-compile.

import py_compile

PATH = "web_app.py"
data = open(PATH, "rb").read()

# ── 1. import ────────────────────────────────────────────────────────────────
IMP_OLD = b"import secrets_broker as _sb  # Phase 1: audit + tier + Vault-ready secret reads\r\n"
IMP_NEW = IMP_OLD + b"import new_payment_integrity as _pi  # payment integrity + evidence ledger (Slice 1)\r\n"
assert data.count(IMP_OLD) == 1, "import anchor not unique/found"
data = data.replace(IMP_OLD, IMP_NEW)

# ── 2. INSERT + evidence + audit ─────────────────────────────────────────────
INS_OLD = (
    b'    with get_db() as c:\r\n'
    b'        c.execute(\r\n'
    b'            "INSERT INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status) "\r\n'
    b'            "VALUES (?,?,?,?,?,?,?)",\r\n'
    b'            (uid, gateway, plan, amount_usd, currency, reference, status))\r\n'
    b'        user_row = c.execute("SELECT email, username FROM users WHERE id=?", (uid,)).fetchone()\r\n'
)
INS_NEW = (
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
assert data.count(INS_OLD) == 1, "INSERT block not unique/found"
data = data.replace(INS_OLD, INS_NEW)

# ── 3. gate the receipt on _inserted ─────────────────────────────────────────
GUARD_OLD = b'    if status == "success" and amount_usd and user_row:\r\n'
GUARD_NEW = b'    if _inserted and status == "success" and amount_usd and user_row:\r\n'
assert data.count(GUARD_OLD) == 1, "receipt guard not unique/found"
data = data.replace(GUARD_OLD, GUARD_NEW)

open(PATH, "wb").write(data)
py_compile.compile(PATH, doraise=True)
print("OK: wired _record_payment through payment integrity layer; byte-compiles clean.")
