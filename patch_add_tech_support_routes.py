"""
Splice the technical_support role (decorator + 2 admin promote/demote routes +
/support dashboard) from new_tech_support_routes.py into web_app.py, just
before `if __name__ == "__main__":`.

Idempotent: skips if the marker function name is already present.
"""
import sys

PATH = "web_app.py"
SRC  = "new_tech_support_routes.py"
MARKER_FN = b"def tech_support_role_required("

data = open(PATH, "rb").read()
if MARKER_FN in data:
    print("[patch] tech_support_role_required already present — skip")
    sys.exit(0)

new_code = open(SRC, "rb").read()
# Force CRLF to match web_app.py line endings
new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
if pos < 0:
    sys.exit('[patch] could not locate `if __name__ == "__main__":` anchor')

data2 = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
open(PATH, "wb").write(data2)
print(f"[patch] web_app.py updated ({len(data2) - len(data):+d} bytes spliced before main-guard)")
