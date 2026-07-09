"""Integrity tests for the Tutorial & Demo Engine's scenario definitions.

The engine loads /static/tutorial/scenarios/<flask-endpoint>.json. If a route is
renamed the tutorial silently stops loading, so these tests fail loudly instead.
They also enforce the owner's three rules:

  * a tutorial walks EVERY screen of its feature (nav steps, resolvable targets)
  * EVERY screen shows cursor movement (targeted steps use a cursor action)
  * a tutorial never auto-clicks a destructive control on real data

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
CURSOR_ACTIONS = {"moveCursor", "hover", "click", "doubleClick", "typeText",
                  "selectOption", "drag", "drop", "rotate3D", "zoom", "pan"}
ALLOWED_ACTIONS = CURSOR_ACTIONS | {"scroll", "wait", "navigate", "highlightOnly"}


def _files() -> list[str]:
    return sorted(f for f in os.listdir(SCEN)
                  if f.endswith(".json") and f != "index.json")


def _load(name: str) -> dict:
    with open(os.path.join(SCEN, name), encoding="utf-8") as f:
        return json.load(f)


def _published() -> list[str]:
    """Scenarios a user can actually see (the engine skips drafts)."""
    return [n for n in _files() if not _load(n).get("draft")]


def test_scenarios_exist():
    """Every major module ships a tutorial."""
    assert len(_files()) >= 25


@pytest.mark.parametrize("name", _files())
def test_scenario_shape(name):
    """Every scenario has the fields the engine reads, and sane steps."""
    doc = _load(name)
    assert doc["pageId"] == name[:-5], "pageId must equal the filename stem"
    for key in ("tutorialId", "title", "module", "description", "version",
                "language", "estimatedDuration", "screens", "steps"):
        assert key in doc, f"{name}: missing {key}"
    assert doc["steps"], f"{name}: no steps"
    for i, s in enumerate(doc["steps"]):
        missing = REQUIRED_STEP_KEYS - set(s)
        assert not missing, f"{name} step {i + 1}: missing {missing}"
        assert s["stepNumber"] == i + 1
        assert s["action"] in ALLOWED_ACTIONS, f"{name}: bad action {s['action']}"
        if s["action"] == "typeText":
            assert s.get("typeText"), f"{name} step {i + 1}: typeText with no text"
        assert isinstance(s.get("dispatch", False), bool)


@pytest.mark.parametrize("name", _files())
def test_every_targeted_step_moves_the_cursor(name):
    """Owner rule: each screen shows cursor movement.

    A step that points at a control must use a cursor action (or be a navigate
    step, which also drives the cursor to the link before hopping). Only a
    target-less whole-page remark may be highlightOnly.
    """
    for s in _load(name)["steps"]:
        if s["targetSelector"]:
            assert s["action"] in CURSOR_ACTIONS | {"navigate", "scroll"}, \
                f"{name} step {s['stepNumber']}: targeted step does not move the cursor"
        else:
            # A hop to a static URL has no on-page target to travel to.
            assert s["action"] in {"highlightOnly", "wait", "scroll", "navigate"}


@pytest.mark.parametrize("name", _files())
def test_navigate_steps_are_resolvable(name):
    """Owner rule: a tour reaches every screen -- so each hop has a destination."""
    for s in _load(name)["steps"]:
        if s["action"] == "navigate":
            assert s.get("href") or s.get("hrefFromSelector"), \
                f"{name} step {s['stepNumber']}: navigate with no href/hrefFromSelector"
            assert not (s.get("href") and s.get("hrefFromSelector")), \
                f"{name} step {s['stepNumber']}: navigate has both href and hrefFromSelector"


def test_multi_screen_flows_exist():
    """The big features must be walked end to end, not described from one page."""
    flows = {n[:-5]: _load(n) for n in _files()}
    for page in ("marketplace_public", "boms_list", "capital_investment_landing",
                 "capital_investment_project"):
        doc = flows[page]
        assert len(doc["screens"]) >= 2, f"{page}: expected a multi-screen flow"
        assert any(s["action"] == "navigate" for s in doc["steps"]), \
            f"{page}: a multi-screen flow needs a navigate step"


@pytest.mark.parametrize("name", _files())
def test_page_id_and_covers_are_real_endpoints(name):
    """A scenario keyed (or pointing) at a dead endpoint would never load."""
    import web_app
    endpoints = {r.endpoint for r in web_app.app.url_map.iter_rules()}
    doc = _load(name)
    assert doc["pageId"] in endpoints, f"{name}: no such Flask endpoint"
    for ep in doc.get("covers", []):
        assert ep in endpoints, f"{name}: covers dead endpoint {ep}"


def test_index_matches_published_files():
    """index.json is the manifest of hand-authored tutorials (drafts excluded)."""
    with open(os.path.join(SCEN, "index.json"), encoding="utf-8") as f:
        idx = json.load(f)
    listed = {t["pageId"] for t in idx["tutorials"]}
    on_disk = {n[:-5] for n in _published()}
    assert listed == on_disk


def test_no_destructive_dispatch():
    """Tutorials must never auto-click a destructive control on real data."""
    banned = ("delete", "remove", "clear", "reset", "revoke", "wipe", "destroy",
              "cancel")
    for name in _files():
        for s in _load(name)["steps"]:
            if s.get("dispatch"):
                sel = (s.get("targetSelector") or "").lower()
                title = (s.get("title") or "").lower()
                assert not any(b in sel or b in title for b in banned), \
                    f"{name}: dispatched click on a destructive-looking target"


def test_published_tutorials_have_no_placeholder_narration():
    """A user must never read TODO text.

    Drafts (machine-generated from a page's controls by sync_tutorials.py --write)
    are allowed on disk: they make coverage visible and the engine refuses to play
    them. Anything NOT marked draft is user-facing and must be finished.
    """
    for name in _published():
        blob = json.dumps(_load(name))
        assert "TODO" not in blob, f"{name}: TODO narration in a published tutorial"


def test_drafts_are_marked_and_have_steps():
    """A draft is backlog, so it must be honestly labelled and actually useful."""
    for name in _files():
        doc = _load(name)
        if doc.get("draft"):
            assert doc["steps"], f"{name}: empty draft teaches nothing"
            assert doc["draft"] is True


def test_feature_coverage_ratchet():
    """A NEW or CHANGED feature must grow a tutorial.

    Every user-facing feature page must be covered -- directly, or by a flow that
    navigates to it, or by being listed in the committed backlog. The backlog is a
    ratchet: an unlisted gap fails the build, so a feature added tomorrow cannot
    ship without its tutorial. (Backlog entries mostly need a record id to render,
    which is why the generator could not draft them automatically.)
    """
    from scripts.sync_tutorials import feature_endpoints, scenario_files
    import web_app

    with open(os.path.join(ROOT, "static", "tutorial", "backlog.json"),
              encoding="utf-8") as f:
        backlog = set(json.load(f)["endpoints"])

    scen = scenario_files()
    covered = set(scen)
    for doc in scen.values():
        covered.update(doc.get("covers") or [])
    feats = set(feature_endpoints(web_app.app))

    new_gaps = sorted(feats - covered - backlog)
    assert not new_gaps, (
        f"feature page(s) with no tutorial and not in the backlog: {new_gaps}. "
        f"Add a scenario in scripts/build_tutorial_scenarios.py, or run "
        f"scripts/sync_tutorials.py --write to draft one."
    )


def test_backlog_does_not_hide_covered_pages():
    """Once a page gets a tutorial it must leave the backlog (the ratchet tightens)."""
    from scripts.sync_tutorials import scenario_files

    with open(os.path.join(ROOT, "static", "tutorial", "backlog.json"),
              encoding="utf-8") as f:
        backlog = set(json.load(f)["endpoints"])

    scen = scenario_files()
    covered = set(scen)
    for doc in scen.values():
        covered.update(doc.get("covers") or [])
    stale = sorted(backlog & covered)
    assert not stale, f"backlog lists pages that now have a tutorial: {stale}"
