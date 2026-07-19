"""Insert a manufacturer-documentation tier ahead of the web-search fallback.

See brand_doc_library.py for why: the automated link finder is broken (DDG 202s, Bing returns
undecoded redirect wrappers whose decoded targets are unrelated ads), so ~93% of products fall
straight through to a Google search. A product with no exact datasheet should first be offered
its MANUFACTURER'S OWN documentation library -- a true statement, one click from the answer --
before being handed a search box.

Order of honesty: exact datasheet -> manufacturer library -> web search. Never a guessed PDF.

web_app.py is CRLF + mojibake, so this is a byte-level splice, never an Edit. Idempotent.
"""
SRC = "web_app.py"

OLD = (
    b'    import urllib.parse as _up\r\n'
    b'    kind_terms = "brochure literature" if kind == "literature" else "datasheet specification"\r\n'
)

NEW = (
    b'    # MANUFACTURER DOCUMENTATION LIBRARY -- tried before a web search.\r\n'
    b'    # The automated finder cannot resolve these (see brand_doc_library.py: DuckDuckGo\r\n'
    b'    # answers the scraper with HTTP 202, and Bing returns redirect wrappers whose\r\n'
    b'    # decoded targets are unrelated ads), so without this ~93% of products go straight\r\n'
    b'    # to a search box. The brand\'s own documentation site is a TRUE statement about\r\n'
    b'    # where the document lives, which a guessed PDF is not -- and a wrong datasheet on\r\n'
    b'    # an electrical component is something a person could specify or install from.\r\n'
    b'    try:\r\n'
    b'        from brand_doc_library import library_for as _brand_lib\r\n'
    b'        _lib = _brand_lib(row.get("brand") or "")\r\n'
    b'    except Exception:\r\n'
    b'        _lib = ""\r\n'
    b'    if _lib:\r\n'
    b'        return redirect(_lib)\r\n'
    b'    import urllib.parse as _up\r\n'
    b'    kind_terms = "brochure literature" if kind == "literature" else "datasheet specification"\r\n'
)

MARKER = b"MANUFACTURER DOCUMENTATION LIBRARY -- tried before a web search."


def main():
    data = open(SRC, "rb").read()
    if MARKER in data:
        print("already patched -- nothing to do")
        return 0
    if data.count(OLD) != 1:
        print(f"REFUSING: expected exactly 1 match, found {data.count(OLD)}")
        return 1
    open(SRC, "wb").write(data.replace(OLD, NEW))
    print("patched: manufacturer library now precedes the search fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
