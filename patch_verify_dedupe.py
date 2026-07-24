# Byte-level patch (web_app.py is CRLF + mojibake -- never Edit directly).
#
# Belt-and-suspenders idempotency on the two BROWSER-CALLBACK payment paths
# (Slice-1 follow-up). The webhooks already dedupe on the reference, and the
# new ux_payments_reference unique index blocks a duplicate payment ROW at the
# DB -- but /paystack/verify and /upgrade/success re-ran the plan UPDATE (and
# the receipt-sending _record_payment) unconditionally on a replayed callback.
# Guard both: if a payment with this reference is already recorded, skip the
# upgrade + record entirely (the user still sees the success flash -- they did
# pay). This makes a replayed verify a true no-op, not just a harmless re-write.
#
# Asserts each block matches exactly once; the file must byte-compile.

import py_compile

PATH = "web_app.py"
data = open(PATH, "rb").read()

# ── Paystack /verify ─────────────────────────────────────────────────────────
PS_OLD = (
    b'with get_db() as c:\r\n'
    b'                    c.execute("UPDATE users SET plan=? WHERE id=?",\r\n'
    b'                              (plan, session["user_id"]))\r\n'
    b'                _record_payment(session["user_id"], "paystack", plan,\r\n'
    b'                                PLAN_PRICES.get(plan, {}).get("usd", 0),\r\n'
    b'                                reference=ref)'
)
PS_NEW = (
    b'with get_db() as c:\r\n'
    b'                    _already = c.execute(\r\n'
    b'                        "SELECT 1 FROM payments WHERE reference=?", (ref,)).fetchone() is not None\r\n'
    b'                    if not _already:\r\n'
    b'                        c.execute("UPDATE users SET plan=? WHERE id=?",\r\n'
    b'                                  (plan, session["user_id"]))\r\n'
    b'                if not _already:\r\n'
    b'                    _record_payment(session["user_id"], "paystack", plan,\r\n'
    b'                                    PLAN_PRICES.get(plan, {}).get("usd", 0),\r\n'
    b'                                    reference=ref)'
)
assert data.count(PS_OLD) == 1, "paystack verify block not unique/found"
data = data.replace(PS_OLD, PS_NEW)

# ── Stripe /upgrade/success ──────────────────────────────────────────────────
ST_OLD = (
    b'with get_db() as c:\r\n'
    b'                        c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))\r\n'
    b'                    _record_payment(uid, "stripe", plan,\r\n'
    b'                                    PLAN_PRICES.get(plan, {}).get("usd", 0),\r\n'
    b'                                    reference=session_id)'
)
ST_NEW = (
    b'with get_db() as c:\r\n'
    b'                        _already = c.execute(\r\n'
    b'                            "SELECT 1 FROM payments WHERE reference=?", (session_id,)).fetchone() is not None\r\n'
    b'                        if not _already:\r\n'
    b'                            c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))\r\n'
    b'                    if not _already:\r\n'
    b'                        _record_payment(uid, "stripe", plan,\r\n'
    b'                                        PLAN_PRICES.get(plan, {}).get("usd", 0),\r\n'
    b'                                        reference=session_id)'
)
assert data.count(ST_OLD) == 1, "stripe upgrade_success block not unique/found"
data = data.replace(ST_OLD, ST_NEW)

open(PATH, "wb").write(data)
py_compile.compile(PATH, doraise=True)
print("OK: both browser-callback paths now skip the upgrade on a replayed reference; byte-compiles clean.")
