"""
Patch web_app.py:
1. Fix admin_ops_security_sessions (500 error due to context manager + missing columns)
2. Add email status + email test endpoints
"""
import subprocess, sys

path = 'web_app.py'
data = open(path, 'rb').read()
email_routes = open('email_ops_routes.py', 'rb').read()

# --- Fix 1: sessions function ---
OLD_SESSIONS = (
    b'def admin_ops_security_sessions():\r\n'
    b'    """List active sessions (from users table)."""\r\n'
    b'    with get_db() as c:\r\n'
    b'        active = c.execute(\r\n'
    b'            "SELECT id, username, plan, last_login FROM users "\r\n'
    b'            "WHERE last_login IS NOT NULL ORDER BY last_login DESC LIMIT 50"\r\n'
    b'        ).fetchall() if _table_exists(c, "users") else []\r\n'
    b'    return jsonify({"active_sessions": [dict(r) for r in active]})'
)

NEW_SESSIONS = (
    b'def admin_ops_security_sessions():\r\n'
    b'    # List recent users/sessions from users table (column-safe)\r\n'
    b'    try:\r\n'
    b'        conn = get_db()\r\n'
    b'        if not _table_exists(conn, "users"):\r\n'
    b'            conn.close()\r\n'
    b'            return jsonify({"status": "ok", "active_sessions": [], "message": "users table not found"})\r\n'
    b'        cols = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]\r\n'
    b'        sel_cols = ["id", "username"]\r\n'
    b'        if "plan" in cols:       sel_cols.append("plan")\r\n'
    b'        if "last_login" in cols: sel_cols.append("last_login")\r\n'
    b'        if "created_at" in cols: sel_cols.append("created_at")\r\n'
    b'        if "is_admin" in cols:   sel_cols.append("is_admin")\r\n'
    b'        order_col = "last_login" if "last_login" in cols else "id"\r\n'
    b'        sql = "SELECT %s FROM users ORDER BY %s DESC LIMIT 50" % (", ".join(sel_cols), order_col)\r\n'
    b'        rows = conn.execute(sql).fetchall()\r\n'
    b'        conn.close()\r\n'
    b'        sessions = []\r\n'
    b'        for r in rows:\r\n'
    b'            try:\r\n'
    b'                sessions.append(dict(r))\r\n'
    b'            except Exception:\r\n'
    b'                sessions.append(dict(zip(sel_cols, tuple(r))))\r\n'
    b'        return jsonify({"status": "ok", "active_sessions": sessions, "count": len(sessions)})\r\n'
    b'    except Exception as e:\r\n'
    b'        return jsonify({"status": "error", "message": str(e)}), 500'
)

if data.find(OLD_SESSIONS) != -1:
    data = data.replace(OLD_SESSIONS, NEW_SESSIONS, 1)
    print("Sessions fix applied")
else:
    print("WARNING: sessions target not found — may already be patched")

# --- Fix 2: insert email routes before if __name__ ---
TARGET = b'\r\n\r\n\r\nif __name__ == "__main__":'
assert data.find(TARGET) != -1, "insertion target not found"

email_crlf = email_routes.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
data = data.replace(TARGET, b'\r\n' + email_crlf + TARGET)
print("Email routes inserted")

open(path, 'wb').write(data)
print("File size: {:,} bytes".format(len(data)))

r = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK")
else:
    print("SYNTAX ERROR:", r.stderr)
    sys.exit(1)
