"""
Splice the new marketplace_product_detail route from
new_marketplace_product_detail.py into web_app.py, just before the
`if __name__ == "__main__":` guard.
"""
import sys

PATH = "web_app.py"
SRC  = "new_marketplace_product_detail.py"

data = open(PATH, "rb").read()
if b"def marketplace_product_detail(" in data:
    print("[skip] marketplace_product_detail already present")
    sys.exit(0)

new_code = open(SRC, "rb").read()
new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
if pos < 0:
    sys.exit('[abort] cannot find main guard anchor')

data2 = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
open(PATH, "wb").write(data2)
print(f"[done] web_app.py {len(data2)-len(data):+d} bytes")
