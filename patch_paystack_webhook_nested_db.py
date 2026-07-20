"""
Byte-level patch: the Paystack webhook silently loses payments.

THE FAULT
    paystack_webhook calls _record_payment() INSIDE its `with get_db() as c:`
    block. _record_payment opens its OWN connection, so this nests a second
    connection on the same database. SQLite answers "database is locked", the
    handler's own `except Exception: pass` swallows it, and it returns 200.

    So Paystack is told "processed successfully" while the user is NOT
    upgraded and NO payment row is written -- and because the response is
    200, Paystack marks the event delivered and NEVER RETRIES. The payment is
    silently lost.

    Proven locally: a correctly-signed charge.success event returns 200, the
    user's plan stays "free", and payments has 0 rows.

HONESTY ABOUT WHERE THIS CAME FROM
    This path was unreachable until earlier today. The webhook had been dead
    since 86eadc2 because of a get_data(raw=True) TypeError, which escaped as
    a 500 -- and a 500 at least made Paystack RETRY. Fixing get_data made the
    handler reachable and so exposed this second, deeper fault, converting a
    loud failure into a silent one. Both fixes belonged in one change; the
    first shipped without this one because the end-to-end path was never
    exercised. It is now, by test_paystack_webhook.py.

    Production runs Postgres, where two connections to different tables would
    probably not deadlock, so live may well have been unaffected. "Probably"
    is not a basis for leaving a payment path like this: the fix below is
    correct on both engines.

THE FIX
    Move _record_payment() OUTSIDE the `with` block so the first connection
    is closed before the second is opened. Same restructure applied to the
    Stripe webhook in patch_stripe_webhook_revive.py.

INPUT : web_app.py in the CWD
OUTPUT: web_app.py rewritten in place. Idempotent.
"""

import sys

PATH = "web_app.py"

OLD = (
    b'            if uid and plan and ref:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    # Reject duplicate references\r\n'
    b'                    dup = c.execute("SELECT id FROM payments WHERE reference=?",\r\n'
    b'                                    (ref,)).fetchone()\r\n'
    b'                    if not dup:\r\n'
    b'                        c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))\r\n'
    b'                        _record_payment(uid, "paystack", plan, amount, reference=ref)\r\n'
)

NEW = (
    b'            if uid and plan and ref:\r\n'
    b'                # _record_payment() opens its OWN connection, so it must run\r\n'
    b'                # AFTER this one closes. Calling it INSIDE the `with` nests a\r\n'
    b'                # second connection on the same database; SQLite answers\r\n'
    b'                # "database is locked", the except-clause below swallows it,\r\n'
    b'                # and the handler returns 200 -- telling Paystack the event was\r\n'
    b'                # processed while the upgrade silently did not happen. A 200\r\n'
    b'                # also stops Paystack retrying, so the payment is lost for good.\r\n'
    b'                with get_db() as c:\r\n'
    b'                    # Reject duplicate references\r\n'
    b'                    dup = c.execute("SELECT id FROM payments WHERE reference=?",\r\n'
    b'                                    (ref,)).fetchone()\r\n'
    b'                    if not dup:\r\n'
    b'                        c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))\r\n'
    b'                if not dup:\r\n'
    b'                    _record_payment(uid, "paystack", plan, amount, reference=ref)\r\n'
)


def main() -> int:
    data = open(PATH, "rb").read()
    if NEW in data:
        print("SKIP: already applied")
        return 0
    count = data.count(OLD)
    if count != 1:
        print(f"FAIL: expected exactly 1 match, found {count}")
        return 1
    open(PATH, "wb").write(data.replace(OLD, NEW))
    print("OK: paystack _record_payment moved outside the db transaction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
