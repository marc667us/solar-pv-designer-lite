"""
Phase 1a binary patch: route web_app.py's seed_pwd + PAYSTACK_SECRET through
secrets_broker.py.

Why a binary patch:
  web_app.py is CRLF + Windows-1252 mojibake + UTF-8 BOM. The Edit tool
  introduces curly quotes that corrupt the file. So we read bytes, do
  byte-level replace, write bytes. Idempotent (safe to re-run).

Three surgical patches:
  P1) Add `import secrets_broker as _sb` right after the api_manager import.
  P2) PAYSTACK_SECRET module-level load -> broker.get with env fallback.
  P3) _seed_pwd() helper -> broker.get with env fallback.

All patches preserve broker semantics (DEGRADED tier with env fallthrough),
so the running app continues to work without Vault, gaining audit + future-
Vault-readiness for free.
"""
from pathlib import Path
import sys

WEB = Path(__file__).parent.parent / "web_app.py"
data = WEB.read_bytes()
orig_size = len(data)

# ── Patch 1: import secrets_broker ───────────────────────────────────────────
P1_OLD = b'from api_manager import api as _api\r\n'
P1_NEW = (
    b'from api_manager import api as _api\r\n'
    b'import secrets_broker as _sb  # Phase 1: audit + tier + Vault-ready secret reads\r\n'
)
if P1_OLD in data and P1_NEW not in data:
    data = data.replace(P1_OLD, P1_NEW, 1)
    print("[patch 1] secrets_broker import added")
elif P1_NEW in data:
    print("[patch 1] already applied")
else:
    print("[patch 1] ERROR: anchor not found"); sys.exit(2)

# ── Patch 2: PAYSTACK_SECRET module-level load via broker ───────────────────
P2_OLD = b'PAYSTACK_SECRET  = os.environ.get("PAYSTACK_SECRET_KEY", "")\r\n'
P2_NEW = (
    b'# Phase 1: route PAYSTACK_SECRET through secrets_broker for audit + future Vault.\r\n'
    b'# DEGRADED tier means: try Vault, fall through to env warm-up automatically.\r\n'
    b'try:\r\n'
    b'    PAYSTACK_SECRET = _sb.get("payment/paystack", tier="DEGRADED")["secret"]\r\n'
    b'except Exception:\r\n'
    b'    PAYSTACK_SECRET = os.environ.get("PAYSTACK_SECRET_KEY", "")\r\n'
)
if P2_OLD in data and P2_NEW not in data:
    data = data.replace(P2_OLD, P2_NEW, 1)
    print("[patch 2] PAYSTACK_SECRET routed via broker")
elif P2_NEW in data:
    print("[patch 2] already applied")
else:
    print("[patch 2] ERROR: anchor not found"); sys.exit(3)

# ── Patch 3: _seed_pwd() via broker ─────────────────────────────────────────
P3_OLD = (
    b'    def _seed_pwd(env_var):\r\n'
    b'        # Source seed passwords from env so the repo never carries a live credential.\r\n'
    b'        v = os.environ.get(env_var)\r\n'
    b'        if not v:\r\n'
    b'            raise RuntimeError(env_var + " env var required for initial user seed (see SolarPro_Schedule_2026-06-08.md Phase 0.1)")\r\n'
    b'        return v\r\n'
)
P3_NEW = (
    b'    def _seed_pwd(env_var):\r\n'
    b'        # Phase 1: route via secrets_broker (audit + tier + Vault-ready).\r\n'
    b'        # DEGRADED tier with built-in env warm-up preserves the existing\r\n'
    b'        # "env var required" guarantee while landing audit trail and the\r\n'
    b'        # Vault cutover path.\r\n'
    b'        _PATH_MAP = {\r\n'
    b'            "SOLARPRO_ADMIN_PASSWORD": ("seed/admin",     "password"),\r\n'
    b'            "SOLARPRO_OWNER_PASSWORD": ("seed/marc667us", "password"),\r\n'
    b'        }\r\n'
    b'        v = None\r\n'
    b'        mapping = _PATH_MAP.get(env_var)\r\n'
    b'        if mapping:\r\n'
    b'            path, field = mapping\r\n'
    b'            try:\r\n'
    b'                v = _sb.get(path, tier="DEGRADED")[field]\r\n'
    b'            except Exception:\r\n'
    b'                v = None\r\n'
    b'        if not v:\r\n'
    b'            v = os.environ.get(env_var)\r\n'
    b'        if not v:\r\n'
    b'            raise RuntimeError(env_var + " env var required for initial user seed (see SolarPro_Schedule_2026-06-08.md Phase 0.1)")\r\n'
    b'        return v\r\n'
)
if P3_OLD in data and P3_NEW not in data:
    data = data.replace(P3_OLD, P3_NEW, 1)
    print("[patch 3] _seed_pwd routed via broker")
elif P3_NEW in data:
    print("[patch 3] already applied")
else:
    print("[patch 3] ERROR: anchor not found"); sys.exit(4)

# Sanity: still CRLF only
crlf = data.count(b'\r\n')
lf   = data.count(b'\n') - crlf
if lf != 0:
    print(f"[abort] bare LFs present after patch: {lf}"); sys.exit(5)

# Backup + write
bak = WEB.with_suffix(WEB.suffix + ".bak_phase1a")
if not bak.exists():
    bak.write_bytes(WEB.read_bytes())
    print(f"[backup] {bak.name} written ({orig_size} bytes)")
WEB.write_bytes(data)
print(f"[write]  web_app.py: {orig_size} -> {len(data)} bytes (CRLF preserved)")
