"""One-shot byte patch for web_app.py to remove hardcoded seed passwords.

Phase 0.1 of the 2026-06-08 quality-gate schedule.

What this does:
- Replaces the two hardcoded plaintext passwords in _SEED_USERS with
  os.environ lookups via a _seed_pwd() helper.
- Helper raises RuntimeError at seed time if the env var is unset,
  so the app cannot boot into a known-credential state by accident.

Why a byte patch and not a normal Edit:
- web_app.py has CRLF line endings + Windows-1252 mojibake.
  Editing it via a text tool corrupts the byte layout (per project
  CLAUDE.md "CRITICAL — Editing web_app.py").

Idempotent: if the old literals are already gone, the script reports
"no-op" and exits 0 so re-running is safe.
"""
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()

# --- 1. Inject _seed_pwd() helper just before the _SEED_USERS list -----------
# Anchor on the literal "_SEED_USERS = [" preceded by its indent so we land
# at the right place. Pattern verified unique once in the file.

HELPER_TARGET = b"    _SEED_USERS = [\r\n"
HELPER_NEW = (
    b"    def _seed_pwd(env_var):\r\n"
    b"        # Source seed passwords from env so the repo never carries a live credential.\r\n"
    b"        v = os.environ.get(env_var)\r\n"
    b"        if not v:\r\n"
    b"            raise RuntimeError(env_var + \" env var required for initial user seed (see SolarPro_Schedule_2026-06-08.md Phase 0.1)\")\r\n"
    b"        return v\r\n"
    b"    _SEED_USERS = [\r\n"
)

n_target = data.count(HELPER_TARGET)
n_helper_already = data.count(b"    def _seed_pwd(env_var):\r\n")

if n_helper_already >= 1:
    print("Helper already present — skipping helper insertion (idempotent path).")
elif n_target == 1:
    data = data.replace(HELPER_TARGET, HELPER_NEW, 1)
    print("Inserted _seed_pwd() helper.")
else:
    print(f"FATAL: helper anchor matched {n_target} times (expected 1).")
    sys.exit(2)

# --- 2. Replace admin password literal ---------------------------------------
ADMIN_OLD = b'"Administrator", "SolarAdmin2026!", "enterprise"'
ADMIN_NEW = b'"Administrator", _seed_pwd("SOLARPRO_ADMIN_PASSWORD"), "enterprise"'

if data.count(ADMIN_OLD) == 1:
    data = data.replace(ADMIN_OLD, ADMIN_NEW, 1)
    print("Replaced admin password literal.")
elif data.count(ADMIN_NEW) >= 1:
    print("Admin already env-sourced — skipping.")
else:
    print(f"FATAL: admin password anchor matched {data.count(ADMIN_OLD)} times (expected 1).")
    sys.exit(3)

# --- 3. Replace marc667us owner password literal -----------------------------
# The literal "marc667us" appears as BOTH username and password on the same
# line; the anchor pins to the surrounding context to hit only the password.
OWNER_OLD = b'"Marc",          "marc667us",       "enterprise"'
OWNER_NEW = b'"Marc",          _seed_pwd("SOLARPRO_OWNER_PASSWORD"),       "enterprise"'

if data.count(OWNER_OLD) == 1:
    data = data.replace(OWNER_OLD, OWNER_NEW, 1)
    print("Replaced marc667us password literal.")
elif data.count(OWNER_NEW) >= 1:
    print("marc667us already env-sourced — skipping.")
else:
    print(f"FATAL: owner password anchor matched {data.count(OWNER_OLD)} times (expected 1).")
    sys.exit(4)

open(PATH, "wb").write(data)
print("DONE. web_app.py written with credential-rotation patch.")
