# ─── Admin Backup / Restore (encrypted, off-box) ─────────────────────────────
# Added 2026-07-06 (owner queued feature #2, re-scoped). Owner directive: build
# backup + restore as an in-app feature and DO NOT keep the vault on the local
# machine (unsafe). So backups are generated in-process, encrypted with an
# admin-supplied passphrase, and STREAMED to the admin's browser as a download —
# nothing is written to server/local disk. Restore takes that file back.
#
# The running app already holds DATABASE_URL in its env, so it dumps its OWN
# database with no external credential needed. A pure-Python logical dump is used
# (no pg_dump binary dependency), portable across Postgres and SQLite.
#
# Spliced verbatim into web_app.py before `if __name__ == "__main__":`, so
# get_db, os, json, io, base64, datetime, session, request, redirect, url_for,
# flash, jsonify, send_file, abort, render_template, admin_required, csrf_protect,
# current_user, log_audit, app are all in scope.

_BACKUP_MAGIC = b"SOLARBAK1"       # format/version header
_BACKUP_KDF_ITERS = 200_000        # PBKDF2 iterations
_BACKUP_EXT = ".solarbak"


def _backup_is_pg():
    return (os.environ.get("DATABASE_URL") or "").startswith(
        ("postgres://", "postgresql://"))


def _backup_derive_key(passphrase, salt):
    """Derive a Fernet key from the admin passphrase + per-backup salt."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64 as _b64
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=_BACKUP_KDF_ITERS)
    return _b64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _backup_json_default(o):
    """JSON encoder for DB value types that aren't natively serialisable."""
    import base64 as _b64
    import datetime as _dt
    import decimal as _dec
    if isinstance(o, (_dt.datetime, _dt.date, _dt.time)):
        return {"__t": "iso", "v": o.isoformat()}
    if isinstance(o, _dec.Decimal):
        return {"__t": "dec", "v": str(o)}
    if isinstance(o, (bytes, bytearray, memoryview)):
        return {"__t": "b64", "v": _b64.b64encode(bytes(o)).decode("ascii")}
    return str(o)


def _backup_decode_value(v):
    """Inverse of _backup_json_default for restore. Tagged dicts -> python."""
    import base64 as _b64
    import decimal as _dec
    if isinstance(v, dict) and "__t" in v and "v" in v:
        t = v["__t"]
        if t == "iso":
            return v["v"]           # ISO string; both backends accept it
        if t == "dec":
            return _dec.Decimal(v["v"])
        if t == "b64":
            return _b64.b64decode(v["v"])
    return v


def _bq(ident):
    """Safely double-quote an SQL identifier (mixed-case / reserved names)."""
    return '"' + str(ident).replace('"', '""') + '"'


def _backup_list_tables(c):
    """All user tables in the current database (excludes system tables)."""
    if _backup_is_pg():
        rows = c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "ORDER BY tablename").fetchall()
    else:
        rows = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def _backup_table_columns(c, t):
    """Live column names for table ``t`` (source of truth for restore — never
    trust identifiers from the uploaded file). ``t`` must already be a known
    live table name."""
    if _backup_is_pg():
        rows = c.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=? ORDER BY ordinal_position",
            (t,)).fetchall()
        return [r[0] for r in rows]
    rows = c.execute("PRAGMA table_info(" + _bq(t) + ")").fetchall()
    return [r[1] for r in rows]   # (cid, name, type, notnull, dflt, pk)


def _backup_build_dump():
    """Return the full logical dump as a JSON-encoded bytes object.

    Attempts to disable row-level security for this session so the backup
    captures EVERY tenant's rows. If a table cannot be read, the WHOLE backup
    FAILS (raises) rather than silently shipping an incomplete file — a
    partial backup discovered during disaster recovery is worse than none."""
    tables = {}
    is_pg = _backup_is_pg()
    rls_disabled = None                      # None on sqlite; True/False on pg
    with get_db() as c:
        if is_pg:
            try:
                c.execute("SET row_security = off")
                rls_disabled = True
            except Exception:
                rls_disabled = False
        names = _backup_list_tables(c)
        for t in names:
            cur = c.execute("SELECT * FROM " + _bq(t))   # errors propagate = fail loud
            cols = [d[0] for d in (cur.description or [])]
            rows = [{cols[i]: r[i] for i in range(len(cols))} for r in cur.fetchall()]
            tables[t] = {"columns": cols, "rows": rows}
    meta = {
        "format": "solarbak1",
        "backend": "postgres" if is_pg else "sqlite",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "table_count": len(tables),
        # False => forced RLS may have scoped this dump to one tenant; a complete
        # cross-tenant backup then requires a DB role with BYPASSRLS.
        "rls_disabled": rls_disabled,
        "row_counts": {t: len(v["rows"]) for t, v in tables.items()},
    }
    payload = {"meta": meta, "tables": tables}
    return json.dumps(payload, default=_backup_json_default).encode("utf-8"), meta


def _backup_encrypt(plaintext, passphrase):
    """magic || salt(16) || Fernet token. Passphrase never stored."""
    from cryptography.fernet import Fernet
    salt = os.urandom(16)
    token = Fernet(_backup_derive_key(passphrase, salt)).encrypt(plaintext)
    return _BACKUP_MAGIC + salt + token


def _backup_decrypt(blob, passphrase):
    """Reverse of _backup_encrypt. Raises on bad magic or wrong passphrase."""
    from cryptography.fernet import Fernet
    if not blob.startswith(_BACKUP_MAGIC):
        raise ValueError("Not a SolarPro backup file.")
    body = blob[len(_BACKUP_MAGIC):]
    salt, token = body[:16], body[16:]
    return Fernet(_backup_derive_key(passphrase, salt)).decrypt(token)


def _backup_restore(dump, actor_id=None):
    """Restore the dump into the live database inside ONE transaction — on any
    error the whole thing rolls back (get_db() context-manager: sqlite3 and
    psycopg2 both rollback on exception, commit on clean exit).

    All identifiers used in SQL come from the LIVE schema, never from the
    uploaded file: only tables that exist live are restored, and only their
    columns that exist live. FK enforcement is disabled for the load so table
    order is irrelevant; Postgres identity sequences are re-synced afterwards."""
    tables = (dump or {}).get("tables") or {}
    is_pg = _backup_is_pg()
    restored, total_rows, skipped = 0, 0, []
    with get_db() as c:
        if is_pg:
            try:
                c.execute("SET row_security = off")
            except Exception:
                pass
            try:
                c.execute("SET session_replication_role = 'replica'")  # disable FK/triggers
            except Exception:
                pass
        live_tables = set(_backup_list_tables(c))
        for t, tv in tables.items():
            if t not in live_tables:               # unknown / stale table -> skip
                skipped.append(t)
                continue
            live_cols = _backup_table_columns(c, t)
            file_cols = tv.get("columns") or []
            cols = [col for col in file_cols if col in live_cols]  # validated intersection
            if not cols:
                skipped.append(t)
                continue
            rows = tv.get("rows") or []
            c.execute("DELETE FROM " + _bq(t))
            if rows:
                collist = ",".join(_bq(col) for col in cols)
                ph = ",".join(["?"] * len(cols))
                sql = "INSERT INTO " + _bq(t) + " (" + collist + ") VALUES (" + ph + ")"
                for r in rows:
                    c.execute(sql, [_backup_decode_value(r.get(col)) for col in cols])
                    total_rows += 1
            restored += 1
        if is_pg:
            # Re-sync SERIAL/identity sequences to MAX(id) so future inserts
            # don't collide with restored explicit ids. Only touch tables that
            # actually own a serial sequence (avoids errors that abort the txn).
            for t in tables:
                if t not in live_tables or "id" not in _backup_table_columns(c, t):
                    continue
                seqrow = c.execute(
                    "SELECT pg_get_serial_sequence(?, 'id')", (t,)).fetchone()
                seq = seqrow[0] if seqrow else None
                if seq:
                    c.execute(
                        "SELECT setval(?, COALESCE((SELECT MAX(id) FROM " + _bq(t) + "), 1))",
                        (seq,))
            try:
                c.execute("SET session_replication_role = 'origin'")
            except Exception:
                pass
    try:
        log_audit(action="database_restore", user_id=actor_id, status="success")
    except Exception:
        pass
    return {"tables_restored": restored, "rows_restored": total_rows, "skipped": skipped}


@app.route("/admin/backup")
@admin_required
def admin_backup():
    """Backup / Restore console."""
    return render_template("admin_backup.html", user=current_user(),
                           backend=("PostgreSQL" if _backup_is_pg() else "SQLite"))


@app.route("/admin/backup/create", methods=["POST"])
@admin_required
def admin_backup_create():
    """Generate an encrypted logical backup and stream it as a download.
    Nothing is written to server/local disk (owner directive)."""
    csrf_protect()
    passphrase = request.form.get("passphrase") or ""
    if len(passphrase) < 8:
        flash("Choose a backup passphrase of at least 8 characters. It is NOT "
              "stored anywhere — keep it safe; without it the backup cannot be "
              "restored.", "warning")
        return redirect(url_for("admin_backup"))
    try:
        plaintext, meta = _backup_build_dump()
        blob = _backup_encrypt(plaintext, passphrase)
    except Exception:
        app.logger.exception("admin_backup_create failed")
        flash("Backup failed. Check the logs.", "danger")
        return redirect(url_for("admin_backup"))
    try:
        log_audit(action="database_backup", user_id=session.get("user_id"),
                  status="success")
    except Exception:
        pass
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return send_file(
        io.BytesIO(blob), as_attachment=True,
        download_name="solarpro_backup_%s%s" % (ts, _BACKUP_EXT),
        mimetype="application/octet-stream")


@app.route("/admin/backup/restore", methods=["POST"])
@admin_required
def admin_backup_restore():
    """Restore an uploaded encrypted backup. DESTRUCTIVE — gated on a typed
    confirmation plus the passphrase."""
    csrf_protect()
    if (request.form.get("confirm") or "").strip() != "RESTORE":
        flash("Restore not confirmed. Type RESTORE to proceed — this REPLACES "
              "all current data.", "warning")
        return redirect(url_for("admin_backup"))
    passphrase = request.form.get("passphrase") or ""
    f = request.files.get("backup_file")
    if not f or not f.filename:
        flash("Choose a backup file to restore.", "warning")
        return redirect(url_for("admin_backup"))
    # Bound the upload so a huge file can't exhaust worker memory.
    max_bytes = 128 * 1024 * 1024
    if request.content_length and request.content_length > max_bytes:
        flash("Backup file too large (max 128 MB).", "danger")
        return redirect(url_for("admin_backup"))
    try:
        blob = f.read(max_bytes + 1)
        if len(blob) > max_bytes:
            flash("Backup file too large (max 128 MB).", "danger")
            return redirect(url_for("admin_backup"))
        plaintext = _backup_decrypt(blob, passphrase)
        dump = json.loads(plaintext.decode("utf-8"))
    except Exception:
        flash("Could not decrypt the backup — wrong passphrase or corrupted "
              "file.", "danger")
        return redirect(url_for("admin_backup"))
    if not isinstance(dump, dict) or "tables" not in dump:
        flash("Unrecognised backup format.", "danger")
        return redirect(url_for("admin_backup"))
    try:
        result = _backup_restore(dump, actor_id=session.get("user_id"))
    except Exception:
        app.logger.exception("admin_backup_restore failed")
        flash("Restore FAILED and was rolled back — no data was changed.", "danger")
        return redirect(url_for("admin_backup"))
    msg = "Restore complete: %d tables, %d rows." % (
        result["tables_restored"], result["rows_restored"])
    if result.get("skipped"):
        msg += " Skipped %d table(s) not in the current schema: %s." % (
            len(result["skipped"]), ", ".join(result["skipped"][:8]))
    flash(msg, "success")
    return redirect(url_for("admin_backup"))
