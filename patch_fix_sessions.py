"""Fix admin_ops_security_sessions: replace fragile with-context + column-sensitive query with robust try/except."""
import subprocess, sys

path = 'web_app.py'
data = open(path, 'rb').read()

OLD = (
    b'def admin_ops_security_sessions():\r\n'
    b'    """List active sessions (from users table)."""\r\n'
    b'    with get_db() as c:\r\n'
    b'        active = c.execute(\r\n'
    b'            "SELECT id, username, plan, last_login FROM users "\r\n'
    b'            "WHERE last_login IS NOT NULL ORDER BY last_login DESC LIMIT 50"\r\n'
    b'        ).fetchall() if _table_exists(c, "users") else []\r\n'
    b'    return jsonify({"active_sessions": [dict(r) for r in active]})'
)

NEW = (
    b'def admin_ops_security_sessions():\r\n'
    b'    # List recent logins from users table (column-safe)\r\n'
    b'    try:\r\n'
    b'        conn = get_db()\r\n'
    b'        if not _table_exists(conn, "users"):\r\n'
    b'            conn.close()\r\n'
    b'            return jsonify({"status": "ok", "active_sessions": [], "message": "users table not found"})\r\n'
    b'        # Discover available columns\r\n'
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

assert data.find(OLD) != -1, "Target function not found — check bytes"
data = data.replace(OLD, NEW, 1)
open(path, 'wb').write(data)
print("File size: {:,} bytes".format(len(data)))

r = subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True, text=True)
if r.returncode == 0:
    print("Syntax OK")
else:
    print("SYNTAX ERROR:", r.stderr)
    sys.exit(1)
