"""Fix latent bug in /admin/agent/run page-fetch: api_manager returns
`url` but the agent reads `r.get("href")`. The fetch silently received
an empty URL and never populated `full_content`, starving the LLM filter
of real document text. Idempotent byte-patch."""
from pathlib import Path
import sys

TARGET = Path(__file__).parent / "web_app.py"
SENTINEL = b'# growth-href-url-fix-applied'

# The needle is the line that pulls url out of the search result inside
# _fetch_page. Replace with a version that accepts both key names.
OLD = b'def _fetch_page(r):\r\n            url = r.get("href", "")\r\n'
NEW = (b'def _fetch_page(r):\r\n'
       b'            # ' + SENTINEL + b'\r\n'
       b'            url = r.get("url") or r.get("href", "")\r\n')

# LF variant in case the existing line endings have been normalised
OLD_LF = OLD.replace(b"\r\n", b"\n")
NEW_LF = NEW.replace(b"\r\n", b"\n")


def main() -> int:
    src = TARGET.read_bytes()
    if SENTINEL in src:
        print("[skip] href->url key fix already applied"); return 0
    if OLD in src:
        TARGET.write_bytes(src.replace(OLD, NEW, 1))
        print("[ok] _fetch_page now reads `url` then `href` (CRLF)")
        return 0
    if OLD_LF in src:
        TARGET.write_bytes(src.replace(OLD_LF, NEW_LF, 1))
        print("[ok] _fetch_page now reads `url` then `href` (LF)")
        return 0
    print("[fail] needle not found — _fetch_page signature may have shifted")
    return 2


if __name__ == "__main__":
    sys.exit(main())
