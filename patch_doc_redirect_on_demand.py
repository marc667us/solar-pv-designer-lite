"""Byte-patch web_app.py: replace the marketplace_product_doc_redirect route
with the on-demand resolve+cache version (owner 2026-07-04). CRLF-aware, per
the web_app.py editing rules. Idempotent."""
import sys

TARGET = "web_app.py"
BLOCK = "_doc_redirect_new_block.py"
START = b'@app.route("/marketplace/product/<int:pid>/doc/<kind>")'
END = b'@app.route("/marketplace/product/<int:pid>/docs")'


def patch() -> int:
    data = open(TARGET, "rb").read()
    if b"_resolve_and_cache_doc_url" in data:
        print("[skip] on-demand doc resolver already present")
        return 0
    i = data.find(START)
    j = data.find(END)
    if i < 0 or j < 0 or j <= i:
        print("[fail] markers not found (i=%s j=%s)" % (i, j))
        return 3
    new_block = open(BLOCK, "rb").read()
    # normalise to CRLF to match web_app.py line endings
    new_block = new_block.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    data = data[:i] + new_block + data[j:]
    open(TARGET, "wb").write(data)
    print("[ok] replaced marketplace_product_doc_redirect with on-demand resolver")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
