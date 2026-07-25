"""Make the brand tier of the doc-redirect PRODUCT-SPECIFIC and KIND-AWARE.

WHY (owner 2026-07-25: "fix the datasheet and literature links on the product card"):
measured on live, /marketplace/product/{524,526,527,528,529,530}/doc/datasheet AND
.../doc/literature ALL redirected to the same https://www.se.com/ww/en/download/ --
a generic portal, identical for both kinds and for every Schneider product, with no
product context. The brand tier calls library_for(brand), which sees neither the model
nor the kind.

Inputs:  web_app.py (bytes; CRLF + mojibake + BOM -- byte-spliced, never Edit-ed)
Output:  the `if _lib: return redirect(_lib)` branch now first tries
         product_doc_search_for(brand, model, kind) -- a search scoped to the
         manufacturer's OWN domain for THIS model and THIS kind -- and only falls back
         to the generic library entry point when there is no usable model.

Resolution order after this patch (honesty preserved -- still never a guessed PDF):
  1. exact cached datasheet/literature URL      (unchanged)
  2. manufacturer-domain search for this model  (NEW -- product-specific, kind-aware)
  3. manufacturer documentation entry point     (when no model is known)
  4. open web search with filetype:pdf          (unchanged last resort)

Syntax notes:
  - anchored on the exact 2-line brand-tier branch, asserted unique
  - the import is done inside the branch, mirroring the existing local-import style there
  - idempotent: re-running is a no-op once the marker is present
"""

SRC = "web_app.py"

ANCHOR = (
    b"    if _lib:\r\n"
    b"        return redirect(_lib)\r\n"
)

REPLACEMENT = (
    b"    if _lib:\r\n"
    b"        # PRODUCT-SPECIFIC FIRST. The bare library URL is the same page for every\r\n"
    b"        # product of that brand and for BOTH kinds, so it answered \"where do this\r\n"
    b"        # vendor's documents live\" when the user asked \"where is THIS product's\r\n"
    b"        # datasheet\". Scope the search to the manufacturer's own domain instead;\r\n"
    b"        # still never asserts a specific PDF is the right one.\r\n"
    b"        try:\r\n"
    b"            from brand_doc_library import product_doc_search_for as _brand_search\r\n"
    b"            _scoped = _brand_search(row.get(\"brand\") or \"\",\r\n"
    b"                                    row.get(\"model\") or row.get(\"name\") or \"\",\r\n"
    b"                                    kind)\r\n"
    b"        except Exception:\r\n"
    b"            _scoped = \"\"\r\n"
    b"        if _scoped:\r\n"
    b"            return redirect(_scoped)\r\n"
    b"        return redirect(_lib)\r\n"
)


def main():
    data = open(SRC, "rb").read()

    if b"_brand_search" in data:
        print("SKIP: product-scoped brand search already wired (idempotent no-op)")
        return

    n = data.count(ANCHOR)
    if n != 1:
        raise SystemExit(f"ABORT: anchor found {n} times, expected exactly 1")

    data = data.replace(ANCHOR, REPLACEMENT)
    open(SRC, "wb").write(data)
    print("OK: brand tier is now product-specific and kind-aware")


if __name__ == "__main__":
    main()
