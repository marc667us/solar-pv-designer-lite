"""Tests for the encrypted, off-box Admin Backup / Restore (owner feature #2).

Covers: encrypt/decrypt round-trip + wrong passphrase; dump shape; a surgical
single-table restore round-trip; route RBAC + CSRF + passphrase + confirm gate;
the create route streams a real encrypted blob (verified by decrypting it)."""
from __future__ import annotations

import importlib.util
import json
import time
import uuid
from pathlib import Path

import pytest

_RUN = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _u(label):
    _SEQ[0] += 1
    return f"bak_{label}{_SEQ[0]}_{_RUN}"[:32]


@pytest.fixture(scope="module")
def app():
    import os
    os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
    os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")
    spec = importlib.util.spec_from_file_location(
        "web_app", Path(__file__).resolve().parent / "web_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.limiter.enabled = False
    except Exception:
        pass
    return mod


@pytest.fixture
def client(app):
    return app.app.test_client()


def _mk_user(app, is_admin=0):
    uname = _u("a" if is_admin else "u")
    with app.app.app_context():
        from web_app import get_db, generate_password_hash, _gen_referral_code
        with get_db() as c:
            c.execute(
                "INSERT INTO users (username,email,password_hash,name,plan,is_admin,referral_code) "
                "VALUES (?,?,?,?,?,?,?)",
                (uname, uname + "@t.test", generate_password_hash("pw"),
                 "T", "business", is_admin, _gen_referral_code()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _as(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "tok"


# ── Encryption round-trip ────────────────────────────────────────────────────
def test_encrypt_decrypt_roundtrip(app):
    blob = app._backup_encrypt(b'{"hello":"world"}', "correct horse battery")
    assert blob.startswith(app._BACKUP_MAGIC)
    out = app._backup_decrypt(blob, "correct horse battery")
    assert out == b'{"hello":"world"}'


def test_decrypt_wrong_passphrase_raises(app):
    blob = app._backup_encrypt(b"secret", "right-pass")
    with pytest.raises(Exception):
        app._backup_decrypt(blob, "wrong-pass")


def test_decrypt_rejects_non_backup(app):
    with pytest.raises(Exception):
        app._backup_decrypt(b"not a backup file at all", "x")


# ── Dump shape ───────────────────────────────────────────────────────────────
def test_build_dump_shape(app):
    with app.app.app_context():
        raw, meta = app._backup_build_dump()
    payload = json.loads(raw.decode("utf-8"))
    assert "meta" in payload and "tables" in payload
    assert payload["meta"]["table_count"] == len(payload["tables"])
    assert "users" in payload["tables"]  # a known table is captured


# ── Surgical single-table restore round-trip ─────────────────────────────────
def test_restore_roundtrip_single_table(app):
    marker = "BACKUP MARKER " + _RUN
    with app.app.app_context():
        from web_app import get_db
        app._admin_notify("test", "info", marker)
        # Full dump, then keep ONLY admin_notifications so restore is surgical.
        raw, _ = app._backup_build_dump()
        full = json.loads(raw.decode("utf-8"))
        dump = {"tables": {"admin_notifications": full["tables"]["admin_notifications"]}}
        # Wipe notifications, then restore from the dump.
        with get_db() as c:
            c.execute("DELETE FROM admin_notifications")
        with get_db() as c:
            gone = c.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE title=?", (marker,)).fetchone()[0]
        assert gone == 0
        res = app._backup_restore(dump)
        with get_db() as c:
            back = c.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE title=?", (marker,)).fetchone()[0]
    assert res["tables_restored"] == 1
    assert back == 1  # marker row restored


# ── Restore validates identifiers against the live schema ────────────────────
def test_restore_skips_unknown_and_malicious_tables(app):
    with app.app.app_context():
        dump = {"tables": {
            'evil"; DROP TABLE users; --': {"columns": ["x"], "rows": [{"x": 1}]},
            "no_such_table_xyz": {"columns": ["a"], "rows": [{"a": 1}]},
        }}
        res = app._backup_restore(dump)
        # both are non-live -> skipped, nothing executed; users table intact
        from web_app import get_db
        with get_db() as c:
            users_ok = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
    assert res["tables_restored"] == 0
    assert set(res["skipped"]) == {'evil"; DROP TABLE users; --', "no_such_table_xyz"}
    assert users_ok is not None  # users table was NOT dropped


def test_restore_filters_unknown_columns(app):
    with app.app.app_context():
        from web_app import get_db
        # admin_notifications is live; include a bogus column that must be dropped
        raw, _ = app._backup_build_dump()
        full = json.loads(raw.decode("utf-8"))
        tv = full["tables"]["admin_notifications"]
        tv = {"columns": tv["columns"] + ["bogus_col"],
              "rows": [dict(r, bogus_col="x") for r in tv["rows"]]}
        res = app._backup_restore({"tables": {"admin_notifications": tv}})
    assert res["tables_restored"] == 1  # restored despite the bogus column


# ── Route RBAC ───────────────────────────────────────────────────────────────
def test_backup_page_rbac(app, client):
    admin = _mk_user(app, is_admin=1)
    _as(client, admin)
    assert client.get("/admin/backup").status_code == 200
    non = _mk_user(app, is_admin=0)
    _as(client, non)
    assert client.get("/admin/backup").status_code == 403
    with client.session_transaction() as s:
        s.clear()
    assert client.get("/admin/backup").status_code in (301, 302)


# ── Create route: streams a real encrypted, decryptable backup ───────────────
def test_create_streams_encrypted_backup(app, client):
    admin = _mk_user(app, is_admin=1)
    _as(client, admin)
    # CSRF required
    assert client.post("/admin/backup/create", data={"passphrase": "longenough1"}).status_code == 403
    # short passphrase -> redirect, no download
    r = client.post("/admin/backup/create",
                    data={"_csrf": "tok", "passphrase": "short"})
    assert r.status_code in (301, 302)
    # valid -> octet-stream download that decrypts back to a dump
    r = client.post("/admin/backup/create",
                    data={"_csrf": "tok", "passphrase": "longenough1"})
    assert r.status_code == 200
    assert r.data.startswith(app._BACKUP_MAGIC)
    plain = app._backup_decrypt(r.data, "longenough1")
    assert b'"tables"' in plain


# ── Restore route: confirm gate + passphrase ─────────────────────────────────
def test_restore_requires_confirm_and_csrf(app, client):
    import io
    admin = _mk_user(app, is_admin=1)
    _as(client, admin)
    good = app._backup_encrypt(b'{"tables":{}}', "pass1234")
    # CSRF
    assert client.post("/admin/backup/restore").status_code == 403
    # no confirm -> redirect, nothing happens
    r = client.post("/admin/backup/restore", data={
        "_csrf": "tok", "passphrase": "pass1234", "confirm": "",
        "backup_file": (io.BytesIO(good), "b.solarbak")},
        content_type="multipart/form-data")
    assert r.status_code in (301, 302)
    # wrong passphrase -> error redirect
    r = client.post("/admin/backup/restore", data={
        "_csrf": "tok", "passphrase": "WRONG", "confirm": "RESTORE",
        "backup_file": (io.BytesIO(good), "b.solarbak")},
        content_type="multipart/form-data")
    assert r.status_code in (301, 302)
