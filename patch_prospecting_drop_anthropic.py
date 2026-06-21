# patch_prospecting_drop_anthropic.py
# Owner directive 2026-06-21: "agent requet failed, dont use antropic api".
# Matches the standing [[feedback-zero-cost-apis]] rule.
#
# Strips the Anthropic Claude fallback block from the prospecting agent's
# provider chain. Chain after this patch:
#   1. OpenRouter (free models)
#   2. Ollama
#   3. GitHub Models
#   (Anthropic removed -- was step 4)
#
# Also strips the api_key check from `_has_any_ai` so Anthropic env doesn't
# inflate the "can we run the agent" gate.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

OLD = (
    b'            # \xe2\x94\x80\xe2\x94\x80 4. Anthropic Claude (last resort \xe2\x80\x94 saves API credits) \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\r\n'
    b'            if api_key and raw is None:\r\n'
    b'                try:\r\n'
    b'                    import anthropic as _ant\r\n'
    b'                    client = _ant.Anthropic(api_key=api_key)\r\n'
    b'                    msg    = client.messages.create(\r\n'
    b'                        model="claude-opus-4-7", max_tokens=4000,\r\n'
    b'                        messages=[{"role": "user", "content": prompt}]\r\n'
    b'                    )\r\n'
    b'                    raw = msg.content[0].text.strip()\r\n'
    b'                    ai_source = "web+claude"\r\n'
    b'                except Exception as _oe_ant:\r\n'
    b'                    _provider_errors.append(f"Claude: {_oe_ant}")\r\n'
    b'\r\n'
)
NEW = (
    b'            # Owner directive 2026-06-21: "dont use antropic api".\r\n'
    b'            # Anthropic Claude fallback removed from the prospecting chain.\r\n'
    b'            # Chain is OpenRouter free -> Ollama -> GitHub Models -> fail.\r\n'
    b'\r\n'
)

if OLD in data:
    data = data.replace(OLD, NEW)
    print("OK  Anthropic fallback removed from prospecting chain")
elif b'"dont use antropic api"' in data:
    print("Already patched")
else:
    print("WARN  Anthropic block anchor not found")

# Also pull api_key out of the _has_any_ai gate so Anthropic env doesn't
# falsely advertise availability.
OLD_GATE = (
    b'    _has_any_ai = bool(or_key or api_key or gh_token or os.environ.get("OLLAMA_URL"))\r\n'
)
NEW_GATE = (
    b'    # Owner: no Anthropic. _has_any_ai checks only OpenRouter / GH Models / Ollama.\r\n'
    b'    _has_any_ai = bool(or_key or gh_token or os.environ.get("OLLAMA_URL"))\r\n'
)
if OLD_GATE in data:
    data = data.replace(OLD_GATE, NEW_GATE)
    print("OK  _has_any_ai gate no longer counts ANTHROPIC_API_KEY")

TARGET.write_bytes(data)
print("OK")
