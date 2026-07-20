"""
Byte-level patch: the Paystack webhook has NEVER worked.

THE BUG
    web_app.py's paystack_webhook calls `request.get_data(raw=True)`.
    Werkzeug's signature is get_data(cache=True, as_text=False,
    parse_form_data=False) -- there is NO `raw` parameter. The call raises
    TypeError on EVERY request, before the signature check is even reached,
    so Paystack's push events have always produced HTTP 500.

    Introduced in 86eadc2, the very commit that added the webhook, so this
    has been dead since birth. Every other get_data() caller in the repo
    passes correct kwargs (e.g. new_keycloak_events_route.py:17).

    Found by probing the DEPLOYED app with a non-ASCII signature header
    while verifying an unrelated fix: three sibling endpoints returned 401
    and this one returned 500. The source-level tests could not have caught
    it -- they assert how the comparison is written, not that the handler
    survives to reach it.

WHY IT MATTERS
    /paystack/verify (the inline-popup JS callback) is the ONLY working
    confirmation path. The webhook is the async backstop for when the
    browser closes before that callback fires. Those payments are currently
    never confirmed -- the user is charged and their plan is not upgraded.

WHY ENABLING IT IS SAFE
    The handler is idempotent: it does
        SELECT id FROM payments WHERE reference=?
    and skips when the reference is already present. /paystack/verify
    records the SAME Paystack reference (web_app.py:8143 -> _record_payment
    with reference=ref), so a payment already confirmed by the JS callback
    is skipped, not double-credited.

NOT FIXED HERE
    The Stripe webhook has the identical `get_data(raw=True)` typo, but its
    handler has NO reference dedupe, so switching it on would let Stripe's
    automatic retries double-record. It needs the dedupe guard first and is
    tracked separately. Stripe fails closed today (400 inside its try/except),
    unlike Paystack's 500.

INPUT : web_app.py in the CWD
OUTPUT: web_app.py rewritten in place. Idempotent.
"""

import sys

PATH = "web_app.py"

# Only the PAYSTACK occurrence. The Stripe one is left alone deliberately --
# matching on the surrounding line makes that unambiguous.
OLD = b'    body = request.get_data(raw=True)\r\n'
NEW = (
    b'    # get_data() takes (cache, as_text, parse_form_data) -- there is NO `raw`\r\n'
    b'    # kwarg. `raw=True` raised TypeError on EVERY call, so this webhook returned\r\n'
    b'    # 500 to Paystack from the day it was written (86eadc2) and no push event was\r\n'
    b'    # ever processed. Bytes are required here because the HMAC is computed over\r\n'
    b'    # the raw body, so as_text must stay False.\r\n'
    b'    body = request.get_data(cache=False, as_text=False)\r\n'
)


def main() -> int:
    data = open(PATH, "rb").read()
    if NEW in data:
        print("SKIP: already applied")
        return 0
    count = data.count(OLD)
    if count != 1:
        print(f"FAIL: expected exactly 1 match for the paystack body read, found {count}")
        return 1
    open(PATH, "wb").write(data.replace(OLD, NEW))
    print("OK: paystack_webhook body read fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
