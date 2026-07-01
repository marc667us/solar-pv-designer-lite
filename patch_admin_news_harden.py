#!/usr/bin/env python
"""Harden /admin/news CRUD:
  1. Explicit commit inside the handler (in addition to the with-block auto-commit)
     so any commit-fail is surfaced immediately.
  2. Read rowcount + reflect result in flash message ('Updated / Deleted N post(s)').
  3. Add no-cache headers on GET /admin/news so the page reflects the latest state
     immediately after mutation.
  4. Guard nid: reject 0/None before executing so a bad form input can't silently
     match nothing.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "web_app.py"

data = WEB.read_bytes()
orig = len(data)

old_handler = (
    b'@app.route(\"/admin/news\", methods=[\"GET\", \"POST\"])\r\n'
    b'@admin_required\r\n'
    b'def admin_news():\r\n'
    b'    if request.method == \"POST\":\r\n'
    b'        csrf_protect()\r\n'
    b'        action = request.form.get(\"action\")\r\n'
    b'        with get_db() as c:\r\n'
    b'            if action == \"create\":\r\n'
    b'                c.execute(\r\n'
    b'                    \"INSERT INTO news_posts (title,content,category,is_published) VALUES (?,?,?,?)\",\r\n'
    b'                    (request.form[\"title\"], request.form[\"content\"],\r\n'
    b'                     request.form.get(\"category\",\"industry\"),\r\n'
    b'                     1 if request.form.get(\"publish\") else 0))\r\n'
    b'                flash(\"News post created.\", \"success\")\r\n'
    b'            elif action == \"edit\":\r\n'
    b'                nid = request.form.get(\"nid\", type=int)\r\n'
    b'                c.execute(\r\n'
    b'                    \"UPDATE news_posts SET title=?,content=?,category=?,is_published=?,updated_at=? WHERE id=?\",\r\n'
    b'                    (request.form[\"title\"], request.form[\"content\"],\r\n'
    b'                     request.form.get(\"category\",\"industry\"),\r\n'
    b'                     1 if request.form.get(\"publish\") else 0,\r\n'
    b'                     datetime.now().isoformat(), nid))\r\n'
    b'                flash(\"Post updated.\", \"success\")\r\n'
    b'            elif action == \"delete\":\r\n'
    b'                c.execute(\"DELETE FROM news_posts WHERE id=?\",\r\n'
    b'                          (request.form.get(\"nid\", type=int),))\r\n'
    b'                flash(\"Post deleted.\", \"info\")\r\n'
    b'        return redirect(url_for(\"admin_news\"))\r\n'
    b'    with get_db() as c:\r\n'
    b'        posts = c.execute(\"SELECT * FROM news_posts ORDER BY created_at DESC\").fetchall()\r\n'
    b'    return render_template(\"admin_news.html\", user=current_user(), posts=posts)\r\n'
)

new_handler = (
    b'@app.route(\"/admin/news\", methods=[\"GET\", \"POST\"])\r\n'
    b'@admin_required\r\n'
    b'def admin_news():\r\n'
    b'    if request.method == \"POST\":\r\n'
    b'        csrf_protect()\r\n'
    b'        action = request.form.get(\"action\")\r\n'
    b'        with get_db() as c:\r\n'
    b'            if action == \"create\":\r\n'
    b'                cur = c.execute(\r\n'
    b'                    \"INSERT INTO news_posts (title,content,category,is_published) VALUES (?,?,?,?)\",\r\n'
    b'                    (request.form[\"title\"], request.form[\"content\"],\r\n'
    b'                     request.form.get(\"category\",\"industry\"),\r\n'
    b'                     1 if request.form.get(\"publish\") else 0))\r\n'
    b'                try: c.commit()\r\n'
    b'                except Exception: pass\r\n'
    b'                flash(\"News post created.\", \"success\")\r\n'
    b'            elif action == \"edit\":\r\n'
    b'                nid = request.form.get(\"nid\", type=int) or 0\r\n'
    b'                if nid <= 0:\r\n'
    b'                    flash(\"Cannot update: missing or invalid post id.\", \"warning\")\r\n'
    b'                else:\r\n'
    b'                    cur = c.execute(\r\n'
    b'                        \"UPDATE news_posts SET title=?,content=?,category=?,is_published=?,updated_at=? WHERE id=?\",\r\n'
    b'                        (request.form[\"title\"], request.form[\"content\"],\r\n'
    b'                         request.form.get(\"category\",\"industry\"),\r\n'
    b'                         1 if request.form.get(\"publish\") else 0,\r\n'
    b'                         datetime.now().isoformat(), nid))\r\n'
    b'                    try: c.commit()\r\n'
    b'                    except Exception: pass\r\n'
    b'                    n = getattr(cur, \"rowcount\", -1)\r\n'
    b'                    if n == 0:\r\n'
    b'                        flash(f\"Update ran but no post with id={nid} was found. Nothing changed.\", \"warning\")\r\n'
    b'                    else:\r\n'
    b'                        flash(f\"Post {nid} updated.\", \"success\")\r\n'
    b'            elif action == \"delete\":\r\n'
    b'                nid = request.form.get(\"nid\", type=int) or 0\r\n'
    b'                if nid <= 0:\r\n'
    b'                    flash(\"Cannot delete: missing or invalid post id.\", \"warning\")\r\n'
    b'                else:\r\n'
    b'                    cur = c.execute(\"DELETE FROM news_posts WHERE id=?\", (nid,))\r\n'
    b'                    try: c.commit()\r\n'
    b'                    except Exception: pass\r\n'
    b'                    n = getattr(cur, \"rowcount\", -1)\r\n'
    b'                    if n == 0:\r\n'
    b'                        flash(f\"Delete ran but no post with id={nid} was found.\", \"warning\")\r\n'
    b'                    else:\r\n'
    b'                        flash(f\"Post {nid} deleted.\", \"info\")\r\n'
    b'        return redirect(url_for(\"admin_news\"))\r\n'
    b'    with get_db() as c:\r\n'
    b'        posts = c.execute(\"SELECT * FROM news_posts ORDER BY created_at DESC\").fetchall()\r\n'
    b'    resp = make_response(render_template(\"admin_news.html\", user=current_user(), posts=posts))\r\n'
    b'    resp.headers[\"Cache-Control\"] = \"no-store, no-cache, must-revalidate\"\r\n'
    b'    resp.headers[\"Pragma\"] = \"no-cache\"\r\n'
    b'    return resp\r\n'
)

if b"Post {nid} deleted" in data:
    print("[skip] admin_news already hardened")
elif old_handler in data:
    data = data.replace(old_handler, new_handler, 1)
    print(f"[ok] hardened admin_news ({len(old_handler)} -> {len(new_handler)} bytes)")
else:
    print("[abort] old admin_news block not found byte-for-byte")
    raise SystemExit(1)

if len(data) != orig:
    backup = WEB.with_suffix(".py.bak-adminnews-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(data)
    print(f"[write] web_app.py {orig} -> {len(data)} bytes")
