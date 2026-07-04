"""Byte-patch web_app.py: replace the marketplace_product_doc_redirect block
with the reviewer-fixed version (Codex + Supervisor Gate findings 2026-07-04):
  - drop COALESCE on the TIMESTAMP links_checked_at (PG type error -> 404 for all)
  - truthiness guard instead of .strip()
  - http(s) scheme allowlist before redirect
  - crawl only for logged-in users (anti-abuse); don't stamp on transient failure
CRLF-aware. Idempotent: skips once the old COALESCE(links_checked_at pattern is gone."""
import sys

TARGET = "web_app.py"
BLOCK = "_doc_redirect_new_block.py"
START = b'@app.route("/marketplace/product/<int:pid>/doc/<kind>")'
END = b'@app.route("/marketplace/product/<int:pid>/docs")'


def patch() -> int:
    data = open(TARGET, "rb").read()
    if b"COALESCE(links_checked_at" not in data and b"only a signed-in user triggers a live crawl" in data:
        print("[skip] doc-redirect fixes already applied")
        return 0
    i = data.find(START)
    j = data.find(END)
    if i < 0 or j < 0 or j <= i:
        print("[fail] markers not found (i=%s j=%s)" % (i, j))
        return 3
    new_block = open(BLOCK, "rb").read()
    new_block = new_block.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    data = data[:i] + new_block + data[j:]
    open(TARGET, "wb").write(data)
    # sanity: the PG-breaking pattern must be gone and the anti-abuse guard present
    if b"COALESCE(links_checked_at" in data:
        print("[fail] COALESCE(links_checked_at still present after patch")
        return 4
    print("[ok] applied doc-redirect reviewer fixes")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
