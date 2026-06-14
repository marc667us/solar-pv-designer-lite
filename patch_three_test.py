"""Inject the /three-test sanity route into web_app.py."""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW = "new_three_test_route.py"


def patch():
    src = open(TARGET, "rb").read()
    if b"def three_test" in src:
        print("[skip] /three-test already wired")
        return 0
    new_code = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    anchor = b'if __name__ == "__main__":'
    pos = src.rfind(anchor)
    if pos < 0:
        print("[fail] __main__ anchor missing")
        return 2
    open(TARGET, "wb").write(src[:pos] + new_code + b"\r\n\r\n" + src[pos:])
    print("[ok] injected /three-test route")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
