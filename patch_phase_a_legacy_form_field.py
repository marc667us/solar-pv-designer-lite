"""Phase A hardening: honor request.form["legacy"] in addition to
request.args["legacy"]. Some browser/automation paths drop the query
string when submitting a form whose action attribute is unset; a
hidden `legacy` input survives the round-trip cleanly.
"""
import sys

path = "web_app.py"
data = open(path, "rb").read()
orig_len = len(data)

# All four Phase A guards read request.args["legacy"]. Replace each
# with a helper that checks both args + form.
old_signature = b'        and request.args.get("legacy") != "1":\r\n'
new_signature = b'        and (request.args.get("legacy") != "1" and request.form.get("legacy") != "1"):\r\n'

count = data.count(old_signature)
if count != 4:
    print(f"FAIL: expected 4 hits of Phase A guard suffix, got {count}")
    sys.exit(1)
data = data.replace(old_signature, new_signature)

open(path, "wb").write(data)
print(f"OK: web_app.py {orig_len} -> {len(data)} bytes (+{len(data)-orig_len})")
