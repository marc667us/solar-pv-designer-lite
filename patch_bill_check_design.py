# Pattern B splice: insert the Check-My-Bill -> Design auto-handoff routes into
# web_app.py just before `if __name__ == "__main__":`. CRLF-aware, idempotent.
data = open("web_app.py", "rb").read()

GUARD = b"def bill_check_design():"
if GUARD in data:
    print("SKIP: bill_check_design already present in web_app.py")
else:
    new_code = open("new_bill_check_design_routes.py", "rb").read()
    # Normalise to CRLF to match web_app.py line endings.
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    TARGET = b'if __name__ == "__main__":'
    pos = data.rfind(TARGET)
    if pos == -1:
        raise SystemExit("FAIL: could not find __main__ guard in web_app.py")
    data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
    open("web_app.py", "wb").write(data)
    print("OK: inserted bill-check design routes at byte", pos)
