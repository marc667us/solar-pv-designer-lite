"""
Byte-level patch: revive the Stripe webhook. THREE defects, fixed together.

The webhook has never processed an event since the commit that created it
(86eadc2). Fixing any one of these alone still leaves it broken or unsafe,
which is why they land as one change.

DEFECT 1 -- `request.get_data(raw=True)`
    werkzeug's signature is get_data(cache, as_text, parse_form_data); there
    is no `raw` kwarg, so this raised TypeError on EVERY request. The
    handler's own `except Exception: return "", 400` swallowed it, so Stripe
    saw a silent 400 rather than the 500 its Paystack twin produced.

DEFECT 2 -- `.get()` on a StripeObject
    Found only by driving a REAL signed event through the handler. After
    construct_event, `event["data"]["object"]` is a `StripeObject`, and in
    stripe 15.x that is NOT a dict subclass: its __getattr__ maps attribute
    lookups to KEYS, so `obj.get("metadata", {})` looks up a key named "get",
    misses, and raises `AttributeError: get`. Every metadata read in this
    handler used `.get()`, so fixing DEFECT 1 alone would have shipped a
    webhook that still failed on every event -- just later in the function.

    Fix: keep construct_event for what it is actually for -- verifying the
    signature, which still raises on a bad one -- then json.loads the
    ALREADY-VERIFIED raw body. That yields plain dicts, so every existing
    `.get()` call works exactly as written. Parsing after verification is
    safe; parsing before would not be.

DEFECT 3 -- no reference dedupe
    Stripe RETRIES a webhook until it receives a 2xx, and this handler
    returns 400 on any exception. A fault occurring after the users UPDATE
    would be retried and would record the payment twice -- and
    _record_payment sends a payment-confirmation EMAIL on success, so the
    customer would be emailed twice too. Reviving the handler without this
    guard would have been actively worse than leaving it dead.

WHY THE DEDUPE KEY IS CORRECT (verified, not assumed)
    For `checkout.session.completed`, event["data"]["object"] IS the checkout
    Session, so its id is the SAME value /upgrade/success already records as
    `reference` (web_app.py:8103). The guard therefore also dedupes the
    webhook against the browser-callback path, exactly as the Paystack
    webhook does.

    The cancellation branch has no natural reference, so it now records the
    Stripe EVENT id (evt_...) -- unique per event, and the canonical Stripe
    idempotency key. It previously passed no reference at all, which made
    dedupe impossible.

IF STRIPE IS NOT CONFIGURED
    The handler returns 400 at its first line when STRIPE_SECRET is unset, so
    on an install that does not use Stripe this changes nothing observable.

INPUT : web_app.py in the CWD
OUTPUT: web_app.py rewritten in place. Idempotent.
"""

import sys

PATH = "web_app.py"

OLD = (
    b'        event = _stripe.Webhook.construct_event(\r\n'
    b'            request.get_data(raw=True), sig, STRIPE_WEBHOOK)\r\n'
    b'        if event["type"] == "checkout.session.completed":\r\n'
    b'            obj  = event["data"]["object"]\r\n'
    b'            plan = obj.get("metadata", {}).get("plan", "")\r\n'
    b'            uid  = int(obj.get("metadata", {}).get("user_id", 0))\r\n'
    b'            if plan and uid:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))\r\n'
    b'                _record_payment(uid, "stripe", plan,\r\n'
    b'                                PLAN_PRICES.get(plan, {}).get("usd", 0),\r\n'
    b'                                reference=obj.get("id", ""))\r\n'
    b'        elif event["type"] in ("customer.subscription.deleted",\r\n'
    b'                               "invoice.payment_failed"):\r\n'
    b'            uid = int(event["data"]["object"].get("metadata", {}).get("user_id", 0))\r\n'
    b'            if uid:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    c.execute("UPDATE users SET plan=\'free\' WHERE id=?", (uid,))\r\n'
    b'                _record_payment(uid, "stripe", "free", 0, status="cancelled")\r\n'
)

NEW = (
    b'        # get_data() takes (cache, as_text, parse_form_data) -- there is NO\r\n'
    b'        # `raw` kwarg. `raw=True` raised TypeError on EVERY call, and the\r\n'
    b'        # except-clause below turned that into a silent 400, so Stripe has\r\n'
    b'        # never had an event processed since 86eadc2. Bytes are required: the\r\n'
    b'        # signature is computed over the raw body.\r\n'
    b'        raw_body = request.get_data(cache=False, as_text=False)\r\n'
    b'\r\n'
    b'        # VERIFY the signature with the SDK -- this still raises on a bad or\r\n'
    b'        # missing signature, which the except-clause turns into a 400.\r\n'
    b'        _stripe.Webhook.construct_event(raw_body, sig, STRIPE_WEBHOOK)\r\n'
    b'\r\n'
    b'        # ...then read the ALREADY-VERIFIED body as plain JSON. construct_event\r\n'
    b'        # returns StripeObjects, and in stripe 15.x StripeObject is NOT a dict\r\n'
    b'        # subclass: its __getattr__ maps attribute lookups to KEYS, so\r\n'
    b'        # obj.get("metadata", {}) looks up a key literally named "get", misses,\r\n'
    b'        # and raises AttributeError. Every metadata read below uses .get(), so\r\n'
    b'        # parsing to plain dicts is what makes them work. Parsing AFTER\r\n'
    b'        # verification is safe; parsing before it would not be.\r\n'
    b'        event = json.loads(raw_body)\r\n'
    b'\r\n'
    b'        if event["type"] == "checkout.session.completed":\r\n'
    b'            obj  = event["data"]["object"]\r\n'
    b'            plan = obj.get("metadata", {}).get("plan", "")\r\n'
    b'            uid  = int(obj.get("metadata", {}).get("user_id", 0))\r\n'
    b'            ref  = obj.get("id", "")\r\n'
    b'            if plan and uid:\r\n'
    b'                # DEDUPE. Stripe RETRIES until it gets a 2xx, and this handler\r\n'
    b'                # returns 400 on any exception -- so a fault after the UPDATE\r\n'
    b'                # would be retried and would record the payment twice, and\r\n'
    b'                # _record_payment emails the customer on success.\r\n'
    b'                #\r\n'
    b'                # `ref` is the checkout Session id -- the SAME value\r\n'
    b'                # /upgrade/success records -- so this also dedupes against the\r\n'
    b'                # browser-callback path, exactly as the Paystack webhook does.\r\n'
    b'                #\r\n'
    b'                # _record_payment() opens its OWN connection, so it must run\r\n'
    b'                # AFTER this one closes. Calling it INSIDE the `with` nests a\r\n'
    b'                # second connection on the same database and SQLite answers\r\n'
    b'                # "database is locked" -- proven against this handler locally.\r\n'
    b'                with get_db() as c:\r\n'
    b'                    dup = c.execute("SELECT id FROM payments WHERE reference=?",\r\n'
    b'                                    (ref,)).fetchone() if ref else None\r\n'
    b'                    if not dup:\r\n'
    b'                        c.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))\r\n'
    b'                if not dup:\r\n'
    b'                    _record_payment(uid, "stripe", plan,\r\n'
    b'                                    PLAN_PRICES.get(plan, {}).get("usd", 0),\r\n'
    b'                                    reference=ref)\r\n'
    b'        elif event["type"] in ("customer.subscription.deleted",\r\n'
    b'                               "invoice.payment_failed"):\r\n'
    b'            uid = int(event["data"]["object"].get("metadata", {}).get("user_id", 0))\r\n'
    b'            # This branch has no natural reference, so key on the Stripe EVENT\r\n'
    b'            # id (evt_...), which is unique per event and is the canonical\r\n'
    b'            # Stripe idempotency key. It previously passed no reference at all,\r\n'
    b'            # which made dedupe impossible and left retries free to pile up rows.\r\n'
    b'            ref = event.get("id", "")\r\n'
    b'            if uid:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    dup = c.execute("SELECT id FROM payments WHERE reference=?",\r\n'
    b'                                    (ref,)).fetchone() if ref else None\r\n'
    b'                    if not dup:\r\n'
    b'                        c.execute("UPDATE users SET plan=\'free\' WHERE id=?", (uid,))\r\n'
    b'                if not dup:\r\n'
    b'                    _record_payment(uid, "stripe", "free", 0,\r\n'
    b'                                    reference=ref, status="cancelled")\r\n'
)


def main() -> int:
    data = open(PATH, "rb").read()
    if NEW in data:
        print("SKIP: already applied")
        return 0
    count = data.count(OLD)
    if count != 1:
        print(f"FAIL: expected exactly 1 match for the stripe block, found {count}")
        return 1
    open(PATH, "wb").write(data.replace(OLD, NEW))
    print("OK: stripe webhook revived (get_data + StripeObject parsing + dedupe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
