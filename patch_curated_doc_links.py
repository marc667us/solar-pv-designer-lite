# patch_curated_doc_links.py
# Splices new_curated_doc_links.py into web_app.py (Pattern B, CRLF-aware) and
# wires _seed_curated_doc_links() into BOTH seed paths of
# _ensure_marketplace_tables() (Postgres path + SQLite path) so curated official
# datasheet/literature URLs land on cold start for either backend.
# Idempotent: exits early if already patched.

data = open("web_app.py", "rb").read()

if b"def _seed_curated_doc_links" in data:
    print("already patched (module present) -- no-op")
    raise SystemExit(0)

# 1. Insert the module block before the __main__ guard.
new_code = open("new_curated_doc_links.py", "rb").read()
new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
assert pos > 0, "anchor __main__ not found"
data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]

# 2. Wire the call into the Postgres path (8-space indent, before `return`).
pg_old = (
    b"        # 2026-06-22 (session C): library expansion on Postgres too.\r\n"
    b"        try: _seed_library_expansion()\r\n"
    b"        except Exception: pass\r\n"
    b"        return"
)
pg_new = (
    b"        # 2026-06-22 (session C): library expansion on Postgres too.\r\n"
    b"        try: _seed_library_expansion()\r\n"
    b"        except Exception: pass\r\n"
    b"        # 2026-07-04: curated official datasheet/literature URLs (solar).\r\n"
    b"        try: _seed_curated_doc_links()\r\n"
    b"        except Exception: pass\r\n"
    b"        return"
)
assert data.count(pg_old) == 1, "postgres-path anchor not unique: %d" % data.count(pg_old)
data = data.replace(pg_old, pg_new)

# 3. Wire the call into the SQLite path (4-space indent).
sq_old = (
    b"    # 2026-06-22 (session C): library expansion seed.\r\n"
    b"    try: _seed_library_expansion()\r\n"
    b"    except Exception: pass\r\n"
    b"\r\n"
    b"\r\ndef _seed_market"
)
sq_new = (
    b"    # 2026-06-22 (session C): library expansion seed.\r\n"
    b"    try: _seed_library_expansion()\r\n"
    b"    except Exception: pass\r\n"
    b"    # 2026-07-04: curated official datasheet/literature URLs (solar).\r\n"
    b"    try: _seed_curated_doc_links()\r\n"
    b"    except Exception: pass\r\n"
    b"\r\n"
    b"\r\ndef _seed_market"
)
assert data.count(sq_old) == 1, "sqlite-path anchor not unique: %d" % data.count(sq_old)
data = data.replace(sq_old, sq_new)

open("web_app.py", "wb").write(data)
print("patched: module inserted + wired into both seed paths")
