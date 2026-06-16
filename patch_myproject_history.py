"""Add the My Project result-history feature + agent self-delete.

Owner instruction (2026-06-16):
  "stop the agent from dumping its walk through results on the dashboard,
   the agent must delete its result on success after being [able] to
   create and calculate and get reports, no [more] holding on to results.
   Rather give the user this feature so that the logged-in user sees his
   result history in his dashboard with link + history searchable. Call
   the folder 'myproject' and remove the old 'my project'."

Three coordinated web_app.py changes:

A) New shading_history table in init_db -- one row per successful save.
B) project_shading POST handler: after save_project_data, append a row
   to shading_history then strip agent_v2 + agent_summary from
   data["shading"] so the project record no longer carries the
   walkthrough.
C) New /myproject route + helper that lists every shading_history row
   for the logged-in user with full-text search across project name +
   location + agent narrative, plus a factor-bucket filter.

The companion templates/myproject.html is created separately.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
MARK = b"# myproject result-history feature (2026-06-16)"


# ─────────────────────────────────────────────────────────────────────
# Block A — add shading_history table inside init_db's big SQL string.
# Anchored on the existing login_failures table so we insert just
# AFTER it but BEFORE the closing triple-quote of the executescript.
# ─────────────────────────────────────────────────────────────────────

OLD_A = (
    b'            CREATE TABLE IF NOT EXISTS login_failures (\r\n'
    b'                id          INTEGER PRIMARY KEY AUTOINCREMENT,\r\n'
    b'                username    TEXT NOT NULL,\r\n'
    b'                ip_address  TEXT NOT NULL,\r\n'
    b'                created_at  TEXT DEFAULT CURRENT_TIMESTAMP\r\n'
    b'            );\r\n'
    b'            """)\r\n'
)

NEW_A = (
    b'            CREATE TABLE IF NOT EXISTS login_failures (\r\n'
    b'                id          INTEGER PRIMARY KEY AUTOINCREMENT,\r\n'
    b'                username    TEXT NOT NULL,\r\n'
    b'                ip_address  TEXT NOT NULL,\r\n'
    b'                created_at  TEXT DEFAULT CURRENT_TIMESTAMP\r\n'
    b'            );\r\n'
    b'            -- myproject result-history feature (2026-06-16).\r\n'
    b'            -- One row per successful shading save. Agent narrative\r\n'
    b'            -- migrates to here on save; project record no longer\r\n'
    b'            -- carries the walkthrough (per owner spec).\r\n'
    b'            CREATE TABLE IF NOT EXISTS shading_history (\r\n'
    b'                id              INTEGER PRIMARY KEY AUTOINCREMENT,\r\n'
    b'                user_id         INTEGER NOT NULL,\r\n'
    b'                username        TEXT DEFAULT \'\',\r\n'
    b'                project_id      INTEGER NOT NULL,\r\n'
    b'                project_name    TEXT DEFAULT \'\',\r\n'
    b'                location        TEXT DEFAULT \'\',\r\n'
    b'                mount_type      TEXT DEFAULT \'\',\r\n'
    b'                factor          REAL DEFAULT 1.0,\r\n'
    b'                label           TEXT DEFAULT \'\',\r\n'
    b'                loss_pct        REAL DEFAULT 0,\r\n'
    b'                agent_narrative TEXT DEFAULT \'\',\r\n'
    b'                agent_version   TEXT DEFAULT \'\',\r\n'
    b'                obstructions_n  INTEGER DEFAULT 0,\r\n'
    b'                created_at      TEXT DEFAULT CURRENT_TIMESTAMP\r\n'
    b'            );\r\n'
    b'            CREATE INDEX IF NOT EXISTS idx_shading_history_user\r\n'
    b'                ON shading_history(user_id, created_at DESC);\r\n'
    b'            CREATE INDEX IF NOT EXISTS idx_shading_history_project\r\n'
    b'                ON shading_history(project_id, created_at DESC);\r\n'
    b'            """)\r\n'
)


# ─────────────────────────────────────────────────────────────────────
# Block B — in project_shading POST, after save_project_data(pid, data):
# insert a history row, then strip the agent narrative from the project
# record so the dashboard no longer holds it.
# ─────────────────────────────────────────────────────────────────────

OLD_B = (
    b'        data["shading"] = _apply_shading_factor(\r\n'
    b'            project, obstructions, base_shading=data["shading"])\r\n'
    b'        factor = data["shading"]["factor"]\r\n'
    b'        save_project_data(pid, data)\r\n'
)

NEW_B = (
    b'        data["shading"] = _apply_shading_factor(\r\n'
    b'            project, obstructions, base_shading=data["shading"])\r\n'
    b'        factor = data["shading"]["factor"]\r\n'
    b'        save_project_data(pid, data)\r\n'
    b'        # myproject result-history feature (2026-06-16):\r\n'
    b'        # Append the agent narrative to shading_history then strip it\r\n'
    b'        # from the project record so the dashboard stops dumping the\r\n'
    b'        # walkthrough. The factor + bucket label stay on the project\r\n'
    b'        # so loads/calc continues to work.\r\n'
    b'        try:\r\n'
    b'            _sh = data.get("shading", {}) or {}\r\n'
    b'            _narr = _sh.get("agent_summary", "") or ""\r\n'
    b'            with get_db() as _c:\r\n'
    b'                _c.execute(\r\n'
    b'                    "INSERT INTO shading_history "\r\n'
    b'                    "(user_id, username, project_id, project_name, location, "\r\n'
    b'                    " mount_type, factor, label, loss_pct, agent_narrative, "\r\n'
    b'                    " agent_version, obstructions_n) "\r\n'
    b'                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",\r\n'
    b'                    (session.get("user_id") or 0,\r\n'
    b'                     session.get("username", "") or "",\r\n'
    b'                     pid,\r\n'
    b'                     project.get("name", "") or "",\r\n'
    b'                     (str(data.get("region","") or "") + ", " +\r\n'
    b'                      str(data.get("country","") or "")).strip(", "),\r\n'
    b'                     _sh.get("mount_type", "") or "",\r\n'
    b'                     float(_sh.get("factor") or 1.0),\r\n'
    b'                     _sh.get("label", "") or "",\r\n'
    b'                     float(_sh.get("loss_pct") or 0),\r\n'
    b'                     _narr[:4000],\r\n'
    b'                     _sh.get("agent_version", "") or "",\r\n'
    b'                     len(obstructions or [])))\r\n'
    b'        except Exception as _hist_err:\r\n'
    b'            try:\r\n'
    b'                app.logger.warning(\r\n'
    b'                    "shading_history insert failed: %s", _hist_err)\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
    b'        # Strip agent walkthrough from project record (owner spec:\r\n'
    b'        # "the agent must delete its result on success ... no holding\r\n'
    b'        # on to results"). Keep factor/label/loss_pct so loads works.\r\n'
    b'        try:\r\n'
    b'            _sh2 = data.get("shading") or {}\r\n'
    b'            for _k in ("agent_v2", "agent_summary", "per_obstruction",\r\n'
    b'                       "combined_severity"):\r\n'
    b'                _sh2.pop(_k, None)\r\n'
    b'            data["shading"] = _sh2\r\n'
    b'            save_project_data(pid, data)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
)


# ─────────────────────────────────────────────────────────────────────
# Block C — new /myproject route. Inserted just before the
# `if __name__ == "__main__"` guard at end of file.
# ─────────────────────────────────────────────────────────────────────

ANCHOR_C = b'if __name__ == "__main__":\r\n'

INSERT_C = (
    b'# myproject result-history feature (2026-06-16) -- the new \'My Project\'\r\n'
    b'# folder per owner spec. Replaces the old dashboard project-list section.\r\n'
    b'@app.route("/myproject")\r\n'
    b'@login_required\r\n'
    b'def myproject_list():\r\n'
    b'    """Searchable history of every shading run the logged-in user has\r\n'
    b'    saved. Query params:\r\n'
    b'      q       -- full-text search over project name + location + narrative\r\n'
    b'      bucket  -- filter by factor bucket (light/moderate/significant/...)\r\n'
    b'      since   -- ISO date; only rows on or after this date\r\n'
    b'    """\r\n'
    b'    q       = (request.args.get("q") or "").strip()[:200]\r\n'
    b'    bucket  = (request.args.get("bucket") or "").strip()[:40]\r\n'
    b'    since   = (request.args.get("since") or "").strip()[:20]\r\n'
    b'    uid     = session.get("user_id") or 0\r\n'
    b'    sql = ("SELECT id, project_id, project_name, location, mount_type, "\r\n'
    b'           "factor, label, loss_pct, agent_narrative, agent_version, "\r\n'
    b'           "obstructions_n, created_at "\r\n'
    b'           "FROM shading_history WHERE user_id = ?")\r\n'
    b'    params = [uid]\r\n'
    b'    if q:\r\n'
    b'        sql += (" AND (project_name LIKE ? OR location LIKE ? "\r\n'
    b'                "OR agent_narrative LIKE ?)")\r\n'
    b'        like = "%" + q + "%"\r\n'
    b'        params.extend([like, like, like])\r\n'
    b'    if bucket:\r\n'
    b'        sql += " AND label = ?"\r\n'
    b'        params.append(bucket)\r\n'
    b'    if since:\r\n'
    b'        sql += " AND created_at >= ?"\r\n'
    b'        params.append(since)\r\n'
    b'    sql += " ORDER BY created_at DESC LIMIT 500"\r\n'
    b'    rows = []\r\n'
    b'    try:\r\n'
    b'        with get_db() as c:\r\n'
    b'            cur = c.execute(sql, params)\r\n'
    b'            cols = [d[0] for d in cur.description]\r\n'
    b'            rows = [dict(zip(cols, r)) for r in cur.fetchall()]\r\n'
    b'    except Exception as _e:\r\n'
    b'        try:\r\n'
    b'            app.logger.warning("myproject_list query failed: %s", _e)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    bucket_choices = [b[0] for b in SHADING_BUCKETS] if "SHADING_BUCKETS" in globals() else \\\r\n'
    b'        ["No shading", "Very light", "Light", "Moderate",\r\n'
    b'         "Significant", "Heavy", "Severe", "Very severe"]\r\n'
    b'    return render_template("myproject.html",\r\n'
    b'                           user=current_user(),\r\n'
    b'                           rows=rows,\r\n'
    b'                           q=q, bucket=bucket, since=since,\r\n'
    b'                           bucket_choices=bucket_choices)\r\n'
    b'\r\n'
    b'\r\n'
)


PATCHES = [
    ("shading_history table in init_db",
     "replace", OLD_A, NEW_A),
    ("project_shading POST: history insert + agent strip",
     "replace", OLD_B, NEW_B),
    ("/myproject route",
     "insert_before", ANCHOR_C, INSERT_C),
]


def patch():
    src = open(TARGET, "rb").read()
    if MARK in src:
        print("[skip] myproject history already wired")
        return 0
    out = src
    for label, mode, old, new in PATCHES:
        if mode == "insert_before":
            idx = out.rfind(old)
            if idx < 0:
                print(f"[fail] anchor not found for: {label}")
                return 2
            out = out[:idx] + new + out[idx:]
            print(f"[ok] inserted: {label}")
        elif mode == "replace":
            if old not in out:
                print(f"[fail] OLD bytes not found for: {label}")
                return 3
            count = out.count(old)
            if count > 1:
                print(f"[fail] OLD bytes appear {count} times for: {label}")
                return 4
            out = out.replace(old, new, 1)
            print(f"[ok] replaced: {label}")
    open(TARGET, "wb").write(out)
    print(f"[done] {len(PATCHES)} patches applied")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
