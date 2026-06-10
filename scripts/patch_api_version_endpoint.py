"""
Beta prep — insert /api/version endpoint right after /api/ping in
web_app.py. Returns {version, commit, build_time} so beta evaluators +
ops can confirm which build they're hitting.

Byte-patch because of web_app.py's CRLF + mojibake constraint.
"""
from __future__ import annotations
import os, sys

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "web_app.py")

# Insert AFTER the closing of api_ping. Anchor on the existing pong return line.
ANCHOR = b'return jsonify({"pong": True, "timestamp": datetime.utcnow().isoformat() + "Z"}), 200\r\n'

NEW_ENDPOINT = b'''

@app.route("/api/version")
@limiter.exempt
def api_version():
    """Build identity for beta evaluators + ops. Returns the VERSION file
    contents + git commit SHA + a UTC build timestamp.

    The VERSION file is a single-line plain-text semver string updated by
    hand at each tag (e.g. 0.9.0-beta.1). The commit SHA is read at import
    time from the RENDER_GIT_COMMIT env var which Render sets on every
    build; falls back to "unknown" on local runs without that env."""
    _root = os.path.dirname(os.path.abspath(__file__))
    try:
        _ver = open(os.path.join(_root, "VERSION"), "r", encoding="utf-8").read().strip()
    except Exception:
        _ver = "unknown"
    return jsonify({
        "version":     _ver,
        "commit":      os.environ.get("RENDER_GIT_COMMIT", "unknown")[:12],
        "build_time":  os.environ.get("RENDER_BUILD_TIME", ""),
        "channel":     "beta",
    }), 200

'''


def main() -> int:
    data = open(TARGET, "rb").read()
    if data.count(ANCHOR) != 1:
        print(f"ERROR: ping anchor matched {data.count(ANCHOR)}x (expected 1)",
              file=sys.stderr)
        return 2
    if b"/api/version" in data:
        print("WARN: /api/version already in file — bailing out idempotently")
        return 0
    new_endpoint_crlf = NEW_ENDPOINT.replace(b"\n", b"\r\n")
    patched = data.replace(ANCHOR, ANCHOR + new_endpoint_crlf, 1)
    open(TARGET, "wb").write(patched)
    print(f"OK inserted /api/version endpoint ({len(new_endpoint_crlf)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
