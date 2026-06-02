"""
Replace BOTH email routes with updated versions from new_email_routes.py
Uses the same file-read approach that worked for new_ops_routes.py
"""
import subprocess, sys, re

path = 'web_app.py'
new_routes_path = 'new_email_routes.py'

data = open(path, 'rb').read()
new_code = open(new_routes_path, 'rb').read()
new_code_crlf = new_code.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')

# Find the start of admin_ops_email_status (the first email route)
start_marker = b'@app.route("/admin/ops/email/status")'
start = data.find(start_marker)
if start == -1:
    print("ERROR: email status route not found")
    sys.exit(1)
print("Found email status route at:", start)

# Find where the email/test function ends (next @app.route or if __name__)
end_markers = [b'\r\n@app.route', b'\r\nif __name__']
end = len(data)
for marker in end_markers:
    pos = data.find(marker, start + 100)
    if pos != -1 and pos < end:
        end = pos
print("End of email routes at:", end)
print("Replacing", end - start, "bytes")

# Replace
data = data[:start] + new_code_crlf.lstrip() + data[end:]
open(path, 'wb').write(data)
print("File size: {:,} bytes".format(len(data)))

r = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK")
else:
    print("SYNTAX ERROR:", r.stderr)
    sys.exit(1)
