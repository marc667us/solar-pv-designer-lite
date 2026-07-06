# Pattern B splice: insert the Lighting & Fan Circuit Schedule engine + route
# (new_circuit_schedule_routes.py) before the `if __name__ == "__main__":` guard.
# CRLF-normalised. Idempotent + fail-loud.
data = open("web_app.py", "rb").read()

if b'def _circuit_schedule(' in data:
    print("SKIP: circuit schedule already present")
    raise SystemExit(0)

new_code = open("new_circuit_schedule_routes.py", "rb").read()
new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
if pos < 0:
    raise SystemExit("FAIL: could not find __main__ guard anchor")

data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
open("web_app.py", "wb").write(data)
print("WROTE web_app.py (circuit schedule spliced)")
