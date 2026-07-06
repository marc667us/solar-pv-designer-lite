# Pattern B splice: insert the /admin/indicators/clear "Clear All" route before
# the __main__ guard. CRLF-normalised, idempotent, fail-loud.
data = open("web_app.py", "rb").read()

if b'def admin_indicators_clear(' in data:
    print("SKIP: admin_indicators_clear already present")
    raise SystemExit(0)

new_code = open("new_admin_indicators_clear_route.py", "rb").read()
new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
if pos < 0:
    raise SystemExit("FAIL: could not find __main__ guard anchor")

data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
open("web_app.py", "wb").write(data)
print("WROTE web_app.py (admin_indicators_clear spliced)")
