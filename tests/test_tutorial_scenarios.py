"""Integrity tests for the Tutorial & Demo Engine's scenario definitions.

The engine loads /static/tutorial/scenarios/<flask-endpoint>.json. If a route is
renamed, the tutorial silently stops loading -- these tests fail loudly instead.

Run: python -m pytest tests/test_tutorial_scenarios.py -q
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = os.path.join(ROOT, "static", "tutorial", "scenarios")
sys.path.insert(0, ROOT)

REQUIRED_STEP_KEYS = {"stepNumber", "title", "description", "voiceScript",
                      "captionText", "targetSelector", "action", "fallbackMessage"}
ALLOWED_ACTIONS = {"moveCursor", "hover", "click", "doubleClick", "typeText",
                   "selectOption", "scroll", "zoom", "pan", "rotate3D", "wait",
                   "navigate", "highlightOnly"}


def _files() -> list[str]:
    return sorted(f for f in os.listdir(SCEN)
                  if f.endswith(".json") and f != "index.json")


def _load(name: str) -> dict:
    with open(os.path.join(SCEN, name), encoding="utf-8") as f:
        return json.load(f)


def test_scenarios_exist():
    """At least the core modules ship a tutorial."""
    assert len(_files()) >= 8


@pytest.mark.parametrize("name", _files())
def test_scenario_shape(name):
    """Every scenario has the fields the engine reads, and sane steps."""
    doc = _load(name)
    assert doc["pageId"] == name[:-5], "pageId must equal the filename stem"
    for key in ("tutorialId", "title", "module", "description", "version",
                "language", "estimatedDuration", "steps"):
        assert key in doc, f"{name}: missing {key}"
    assert doc["steps"], f"{name}: no steps"
    for i, s in enumerate(doc["steps"]):
        missing = REQUIRED_STEP_KEYS - set(s)
        assert not missing, f"{name} step {i + 1}: missing {missing}"
        assert s["stepNumber"] == i + 1
        assert s["action"] in ALLOWED_ACTIONS, f"{name}: bad action {s['action']}"
        # A step that types must supply the text; a dispatched click must be opt-in.
        if s["action"] == "typeText":
            assert s.get("typeText"), f"{name} step {i + 1}: typeText with no text"
        assert isinstance(s.get("dispatch", False), bool)


@pytest.mark.parametrize("name", _files())
def test_page_id_is_a_real_endpoint(name):
    """A scenario keyed to a dead endpoint would never load -- catch the rename."""
    import web_app
    endpoints = {r.endpoint for r in web_app.app.url_map.iter_rules()}
    assert _load(name)["pageId"] in endpoints, f"{name}: no such Flask endpoint"


def test_index_matches_files():
    """index.json is the coverage manifest the admin surface reads."""
    with open(os.path.join(SCEN, "index.json"), encoding="utf-8") as f:
        idx = json.load(f)
    listed = {t["pageId"] for t in idx["tutorials"]}
    on_disk = {n[:-5] for n in _files()}
    assert listed == on_disk


def test_no_destructive_dispatch():
    """Tutorials must never auto-click a destructive control on real data."""
    banned = ("delete", "remove", "clear", "reset", "revoke", "wipe", "destroy")
    for name in _files():
        for s in _load(name)["steps"]:
            if s.get("dispatch"):
                sel = (s.get("targetSelector") or "").lower()
                title = (s.get("title") or "").lower()
                assert not any(b in sel or b in title for b in banned), \
                    f"{name}: dispatched click on a destructive-looking target"
