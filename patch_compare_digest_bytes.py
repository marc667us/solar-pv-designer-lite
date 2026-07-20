"""
Byte-level patch: compare_digest must compare BYTES, not str.

WHY
    `hmac.compare_digest` raises TypeError when handed a str containing
    non-ASCII. Both call sites below take one half of the comparison from an
    attacker-controlled HTTP header, and WSGI decodes headers as latin-1 --
    so any byte 0x80-0xFF arrives as a non-ASCII character. A garbage header
    therefore produces an UNHANDLED 500 instead of an honest 401/400.

    Verified: hmac.compare_digest('\xff\xfe', 'secret')
              -> TypeError: comparing strings with non-ASCII characters
              hmac.compare_digest(b'..', b'..') -> returns False correctly.

    This is the same fault that took out the CDC drain via a BOM-corrupted
    secret (see new_cdc_drain_routes.py:192). Fixed there already; these two
    are the remaining live instances inside web_app.py.

SITES
    1. paystack_webhook   -- `sig` from the X-Paystack-Signature header
    2. _soc_ingest_authorized -- `got` from the Authorization header
       (the spliced copy of new_soc_slice1.py; the source module is fixed
       separately, but web_app.py is what actually serves)

WHY A BYTE PATCH
    web_app.py is CRLF + mojibake (UTF-8 dashes stored as Windows-1252). Text
    editors rewrite those bytes and corrupt the file, so every change here is
    a literal byte replacement. See CLAUDE.md "CRITICAL -- Editing web_app.py".

INPUT : web_app.py in the CWD
OUTPUT: web_app.py rewritten in place; prints one line per replacement.
        Idempotent -- re-running finds the new text already present and
        makes no change.
"""

import sys

PATH = "web_app.py"

# (label, old_bytes, new_bytes). CRLF is used explicitly because the file's
# line endings must be preserved exactly.
PATCHES = [
    (
        "paystack_webhook signature compare",
        b'    if not _hmac.compare_digest(sig, expected):\r\n',
        b'    # COMPARE BYTES, NOT str. compare_digest RAISES TypeError on a str\r\n'
        b'    # holding non-ASCII, and `sig` is attacker-controlled (WSGI decodes\r\n'
        b'    # headers latin-1, so any byte 0x80-0xFF arrives non-ASCII). Comparing\r\n'
        b'    # str turns a garbage X-Paystack-Signature header into an unhandled\r\n'
        b'    # 500 instead of the intended 400.\r\n'
        b'    if not _hmac.compare_digest(sig.encode("utf-8"),\r\n'
        b'                                expected.encode("utf-8")):\r\n',
    ),
    (
        "_soc_ingest_authorized bearer compare",
        b'    return _soc_hmac.compare_digest(got, want)\r\n',
        b'    # COMPARE BYTES, NOT str: compare_digest RAISES TypeError on non-ASCII\r\n'
        b'    # str, and `got` is attacker-controlled via the Authorization header.\r\n'
        b'    # Comparing str turns a garbage header into an unhandled 500, not a 401.\r\n'
        b'    return _soc_hmac.compare_digest(got.encode("utf-8"),\r\n'
        b'                                    want.encode("utf-8"))\r\n',
    ),
]


def main() -> int:
    data = open(PATH, "rb").read()
    original_len = len(data)
    changed = 0

    for label, old, new in PATCHES:
        if new in data:
            print(f"  SKIP (already applied): {label}")
            continue
        count = data.count(old)
        if count != 1:
            # Refuse to guess. Zero means the target moved; more than one means
            # an ambiguous splice and we would patch the wrong copy.
            print(f"  FAIL: {label} -- expected exactly 1 match, found {count}")
            return 1
        data = data.replace(old, new)
        changed += 1
        print(f"  OK: {label}")

    if changed:
        open(PATH, "wb").write(data)
        print(f"wrote {PATH} ({original_len} -> {len(data)} bytes)")
    else:
        print("nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
