"""
Phase B patch — splice _bill_check_routes.py into web_app.py just before
`if __name__ == "__main__":`. Idempotent: refuses to splice twice.
"""
from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()

MARKER = b"# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 Check My Electricity Bill \xe2\x80\x94 feature"
if MARKER in data:
    print("ALREADY SPLICED — refusing to re-insert. Edit _bill_check_routes.py and rerun resplicer if you must.")
    raise SystemExit(0)

new_code = Path("_bill_check_routes.py").read_bytes()
# normalise to CRLF to match web_app.py line endings
new_code = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
if pos < 0:
    raise SystemExit("FAIL: could not find `if __name__ == \"__main__\":` in web_app.py")

# Insert just before TARGET line (which is at line-start)
patched = data[:pos] + new_code + b"\r\n\r\n" + data[pos:]

P.write_bytes(patched)
print(f"OK spliced {len(new_code)} bytes at offset {pos}. file now {len(patched)} bytes.")
