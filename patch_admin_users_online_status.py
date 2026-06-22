#!/usr/bin/env python3
"""patch_admin_users_online_status.py -- 2026-06-22.

/admin/users now passes an `online_ids` set + `online_window_secs` to the
template so each row can show a green dot if active in the window, else
'Offline' + 'last seen Xm ago'. Uses the existing _online_users() helper.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    needle = (
        b"    with get_db() as c:\r\n"
        b"        users = c.execute(\r\n"
        b"            \"SELECT u.*, (SELECT COUNT(*) FROM projects WHERE user_id=u.id) AS proj_count \"\r\n"
        b"            \"FROM users u ORDER BY u.created_at DESC\").fetchall()\r\n"
        b"    return render_template(\"admin_users.html\", user=current_user(),\r\n"
        b"                           users=users, plan_prices=PLAN_PRICES)\r\n"
    )
    repl = (
        b"    with get_db() as c:\r\n"
        b"        users = c.execute(\r\n"
        b"            \"SELECT u.*, (SELECT COUNT(*) FROM projects WHERE user_id=u.id) AS proj_count \"\r\n"
        b"            \"FROM users u ORDER BY u.created_at DESC\").fetchall()\r\n"
        b"    # 2026-06-22 (session B): online indicator -- gather ids active in the window.\r\n"
        b"    try:\r\n"
        b"        _on = _online_users()\r\n"
        b"        _online_ids = {int(u.get(\"id\") or 0) for u in _on}\r\n"
        b"        _online_map = {int(u.get(\"id\") or 0): int(u.get(\"since_seconds\") or 0) for u in _on}\r\n"
        b"        _online_window = _ONLINE_WINDOW_SECS\r\n"
        b"    except Exception:\r\n"
        b"        _online_ids = set(); _online_map = {}; _online_window = 300\r\n"
        b"    return render_template(\"admin_users.html\", user=current_user(),\r\n"
        b"                           users=users, plan_prices=PLAN_PRICES,\r\n"
        b"                           online_ids=_online_ids, online_map=_online_map,\r\n"
        b"                           online_window_secs=_online_window)\r\n"
    )
    if needle in data:
        data = data.replace(needle, repl, 1)
        print("admin_users route now passes online_ids + online_map.")
    elif b"_online_ids = {int(u.get(\"id\") or 0) for u in _on}" in data:
        print("admin_users already patched.")
        return
    else:
        print("admin_users anchor NOT FOUND -- aborting.")
        sys.exit(2)
    with open(PATH, "wb") as fh:
        fh.write(data)
    print(f"wrote {PATH}")


if __name__ == "__main__":
    main()
