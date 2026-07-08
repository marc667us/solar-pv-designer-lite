"""Digital Twin asset-manifest tests (Phase 7).

Enforces the zero-cost / no-lock-in rule: the studio template and every dt-*.js
module must reference ONLY self-hosted / vendored assets -- no external CDN,
no commercial API, no paid engine.
"""
from __future__ import annotations

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "templates", "capital_investment", "digital_twin.html")
JS_DIR = os.path.join(ROOT, "static", "capital_investment", "dt")

# Hosts that would introduce an external dependency or cost.
FORBIDDEN = re.compile(
    r"https?://(?!localhost)[^\"'\s)]*"
    r"(cdn|unpkg|jsdelivr|cdnjs|googleapis|gstatic|esm\.sh|skypack|"
    r"threejs\.org|jquery|bootstrapcdn|fontawesome)",
    re.I,
)


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def test_js_modules_exist():
    expected = [
        "dt-state.js", "dt-materials.js", "dt-scene-builder.js", "dt-selection.js",
        "dt-sun.js", "dt-cameras.js", "dt-simulation-modes.js",
        "dt-shadow-analysis.js", "dt-parameter-panel.js", "dt-ai-actions.js",
        "dt-exports.js", "dt-main.js",
    ]
    for name in expected:
        assert os.path.exists(os.path.join(JS_DIR, name)), f"missing {name}"


def test_no_external_cdn_in_template():
    txt = _read(TEMPLATE)
    hits = FORBIDDEN.findall(txt)
    assert not hits, f"external CDN reference in template: {hits}"
    # Three.js must be the vendored self-hosted copy.
    assert "/static/vendor/three-r147-umd/three.min.js" in txt


def test_no_external_cdn_in_js_modules():
    for path in glob.glob(os.path.join(JS_DIR, "*.js")):
        txt = _read(path)
        hits = FORBIDDEN.findall(txt)
        assert not hits, f"external CDN reference in {os.path.basename(path)}: {hits}"


def test_no_paid_llm_or_api_keys_embedded():
    for path in glob.glob(os.path.join(JS_DIR, "*.js")) + [TEMPLATE]:
        txt = _read(path).lower()
        for bad in ("api_key", "apikey=", "sk-", "openai.com", "anthropic.com"):
            assert bad not in txt, f"suspicious token '{bad}' in {os.path.basename(path)}"
