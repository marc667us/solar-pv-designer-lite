"""
Phase polish patch: scrub Claude/Anthropic mentions in user-facing strings
inside web_app.py.

Scope is narrow on purpose:
  - Replace "Claude" provider label shown in admin_agent KPI with "Primary AI"
  - Replace "Web Search + Claude AI" src_label with "Web Search + AI"
  - Leave _ant.Anthropic(...) API calls alone (those are real code)
  - Leave comments alone (internal)
  - Leave privacy.html Anthropic disclosure alone (legal requirement)

Why a binary patch:
  web_app.py is CRLF + Windows-1252 mojibake. Edit-tool curly quotes corrupt
  the file. Idempotent (safe to re-run; will report 'already applied').
"""
from pathlib import Path
import sys

WEB = Path(__file__).parent.parent / "web_app.py"
data = WEB.read_bytes()
orig_size = len(data)

# ── P1: _ai_label "Claude" -> "Primary AI" ──────────────────────────────────
P1_OLD = b'                   else "Claude" if _has_claude\r\n'
P1_NEW = b'                   else "Primary AI" if _has_claude\r\n'

if P1_OLD in data:
    data = data.replace(P1_OLD, P1_NEW, 1)
    print("[patch 1] _ai_label 'Claude' -> 'Primary AI'")
elif P1_NEW in data:
    print("[patch 1] already applied")
else:
    print("[patch 1] ERROR: anchor not found"); sys.exit(2)

# ── P2: src_label "Web Search + Claude AI" -> "Web Search + AI" ────────────
P2_OLD = b'            src_label = "Web Search + Claude AI"\r\n'
P2_NEW = b'            src_label = "Web Search + AI"\r\n'

if P2_OLD in data:
    data = data.replace(P2_OLD, P2_NEW, 1)
    print("[patch 2] src_label scrubbed")
elif P2_NEW in data:
    print("[patch 2] already applied")
else:
    print("[patch 2] ERROR: anchor not found"); sys.exit(3)

# Sanity: still CRLF only
crlf = data.count(b'\r\n')
lf   = data.count(b'\n') - crlf
if lf != 0:
    print(f"[abort] bare LFs present after patch: {lf}"); sys.exit(4)

bak = WEB.with_suffix(WEB.suffix + ".bak_scrub_anthropic")
if not bak.exists():
    bak.write_bytes(WEB.read_bytes())
    print(f"[backup] {bak.name} written")
WEB.write_bytes(data)
print(f"[write]  web_app.py: {orig_size} -> {len(data)} bytes (CRLF preserved)")
