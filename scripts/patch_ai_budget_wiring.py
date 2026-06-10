"""
Byte-safe patcher: wires ai_budget caps into web_app.py.

Per project CLAUDE.md:
  - web_app.py has CRLF + mojibake; Edit tool corrupts it.
  - Use byte-level patching, preserve CRLF, idempotent.

Three patches applied:
  A. /api/assistant/chat — pass user_id + endpoint to api.ai.chat()
  B. /admin/agent/run    — record_usage after a successful AI call
  C. /api/ai/quota       — new route inserted before `if __name__ == "__main__":`

Re-running is safe: each patch checks for a marker first.
"""

from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBAPP = ROOT / "web_app.py"
NEW_ROUTE = ROOT / "new_ai_budget_routes.py"


def main() -> int:
    data = WEBAPP.read_bytes()
    original = data
    patched_count = 0

    # ── Patch A: assistant_chat ──────────────────────────────────────────────
    old_a = (b"reply, _ai_provider = _api.ai.chat(msgs, system=system, "
             b"max_tokens=500)")
    new_a = (b"reply, _ai_provider = _api.ai.chat(msgs, system=system, "
             b"max_tokens=500,\r\n"
             b"                                            user_id=session.get(\"user_id\"),\r\n"
             b"                                            endpoint=\"/api/assistant/chat\")")
    if new_a in data:
        print("[A] already patched (assistant_chat)")
    elif old_a in data:
        if data.count(old_a) != 1:
            print(f"[A] ERROR: anchor matched {data.count(old_a)} times, expected 1")
            return 2
        data = data.replace(old_a, new_a, 1)
        patched_count += 1
        print("[A] patched assistant_chat user_id+endpoint")
    else:
        print("[A] ERROR: anchor not found")
        return 2

    # ── Patch B: admin_agent_run record_usage ────────────────────────────────
    # Anchor: the unique successful-return jsonify in admin_agent_run.
    old_b = (b"            data = json.loads(raw)\r\n"
             b"            return jsonify({\"ok\": True, \"prospects\": data[\"prospects\"],\r\n"
             b"                            \"source\": ai_source, \"result_count\": len(search_results)})")
    marker_b = b"# AI_BUDGET_LEDGER_MARKER_AGENT"
    new_b = (b"            data = json.loads(raw)\r\n"
             b"            # AI_BUDGET_LEDGER_MARKER_AGENT - record one ledger row per\r\n"
             b"            # successful prospecting-agent run so admin spend is visible.\r\n"
             b"            try:\r\n"
             b"                import ai_budget as _ab_agent\r\n"
             b"                _src = ai_source or \"\"\r\n"
             b"                if \"openrouter\" in _src:\r\n"
             b"                    _prov, _mdl = \"openrouter\", _src.split(\"(\")[-1].rstrip(\")\")\r\n"
             b"                elif \"ollama\" in _src:\r\n"
             b"                    _prov, _mdl = \"ollama\", os.environ.get(\"OLLAMA_MODEL\", \"\")\r\n"
             b"                elif \"github\" in _src:\r\n"
             b"                    _prov, _mdl = \"github_models\", \"gpt-4.1-mini\"\r\n"
             b"                elif \"claude\" in _src:\r\n"
             b"                    _prov, _mdl = \"claude\", \"claude-opus-4-7\"\r\n"
             b"                else:\r\n"
             b"                    _prov, _mdl = \"unknown\", \"\"\r\n"
             b"                _ab_agent.record_usage(\r\n"
             b"                    user_id=session.get(\"user_id\"),\r\n"
             b"                    provider=_prov, model=_mdl,\r\n"
             b"                    prompt_tokens=_ab_agent.estimate_tokens(prompt),\r\n"
             b"                    completion_tokens=_ab_agent.estimate_tokens(raw or \"\"),\r\n"
             b"                    endpoint=\"/admin/agent/run\")\r\n"
             b"            except Exception:\r\n"
             b"                pass\r\n"
             b"            return jsonify({\"ok\": True, \"prospects\": data[\"prospects\"],\r\n"
             b"                            \"source\": ai_source, \"result_count\": len(search_results)})")
    if marker_b in data:
        print("[B] already patched (admin_agent_run)")
    elif old_b in data:
        if data.count(old_b) != 1:
            print(f"[B] ERROR: anchor matched {data.count(old_b)} times, expected 1")
            return 2
        data = data.replace(old_b, new_b, 1)
        patched_count += 1
        print("[B] patched admin_agent_run ledger")
    else:
        print("[B] ERROR: anchor not found")
        return 2

    # ── Patch C: insert /api/ai/quota route ──────────────────────────────────
    marker_c = b"def api_ai_quota():"
    if marker_c in data:
        print("[C] already patched (/api/ai/quota)")
    else:
        new_code = NEW_ROUTE.read_bytes()
        # Normalize to CRLF (file may have been authored LF).
        new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        target = b"if __name__ == \"__main__\":"
        pos = data.rfind(target)
        if pos == -1:
            print("[C] ERROR: '__main__' anchor not found")
            return 2
        data = data[:pos] + new_code_crlf + b"\r\n" + data[pos:]
        patched_count += 1
        print("[C] inserted /api/ai/quota route")

    if data == original:
        print("\nNo changes — all patches already applied.")
        return 0

    # Atomic write: tmp then replace.
    backup = WEBAPP.with_suffix(".py.bak_ai_budget")
    if not backup.exists():
        backup.write_bytes(original)
        print(f"Backup written: {backup.name}")
    WEBAPP.write_bytes(data)
    print(f"\nApplied {patched_count} patch(es). web_app.py size: "
          f"{len(original):,} -> {len(data):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
