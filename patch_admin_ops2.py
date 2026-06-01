"""
Binary patch: add new admin operations routes to web_app.py
Reads route code from new_ops_routes.py and inserts before if __name__ block
"""
import subprocess, sys

path = 'web_app.py'
routes_path = 'new_ops_routes.py'

data = open(path, 'rb').read()
new_code = open(routes_path, 'rb').read()

# Convert LF to CRLF to match the file's line endings
new_code_crlf = new_code.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')

TARGET = b'\r\n\r\n\r\nif __name__ == "__main__":'
assert data.find(TARGET) != -1, "Could not find insertion target"

data = data.replace(TARGET, b'\r\n' + new_code_crlf + TARGET)
open(path, 'wb').write(data)
print("File size: {:,} bytes".format(len(data)))

r = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK")
else:
    print("SYNTAX ERROR:", r.stderr)
    sys.exit(1)
