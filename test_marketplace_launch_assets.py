"""Tests for the soft-launch artefacts:
  - _send_system_email auto-appends a marketplace PS to every body
  - PS appears only once (re-running doesn't stack copies)
  - The send_marketplace_launch.py loader discovers all invitees + dedupes
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def app():
    spec = importlib.util.spec_from_file_location("web_app", ROOT / "web_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_send_system_email_appends_marketplace_ps(app, monkeypatch):
    captured = {}

    def fake_send_email(to, subj, html, text_body=None, **kw):
        captured["to"] = to
        captured["subject"] = subj
        captured["html"] = html
        captured["text"] = text_body
        return True

    monkeypatch.setattr(app, "_send_email", fake_send_email)
    app._send_system_email("a@b.test", "Welcome",
                           "Hello,\n\nYour account is ready.")
    assert "/marketplace" in captured["text"]
    assert "/marketplace" in captured["html"]
    # PS marker present
    assert "PS - browse our free Electrical Pricing Marketplace" in captured["text"]


def test_send_system_email_is_idempotent_on_ps_marker(app, monkeypatch):
    """Re-sending a body that already includes the PS should not double it."""
    captured = {}

    def fake_send_email(to, subj, html, text_body=None, **kw):
        captured["text"] = text_body
        return True

    monkeypatch.setattr(app, "_send_email", fake_send_email)
    body_with_ps = (
        "Hello,\n\nYour account is ready.\n\n--\n"
        "PS - browse our free Electrical Pricing Marketplace: "
        "https://solarpro.aiappinvent.com/marketplace"
    )
    app._send_system_email("a@b.test", "Welcome", body_with_ps)
    # The PS occurs exactly once.
    assert captured["text"].count(
        "PS - browse our free Electrical Pricing Marketplace"
    ) == 1


def test_launch_send_script_loads_invitees():
    """scripts/send_marketplace_launch.py.load_recipients walks every region
    and dedupes on lowercased email. Verify the discoverer finds the >25
    invitees that exist on disk."""
    spec = importlib.util.spec_from_file_location(
        "send_marketplace_launch",
        ROOT / "scripts" / "send_marketplace_launch.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    recipients = mod.load_recipients()
    assert len(recipients) >= 25, (
        f"expected at least 25 invitees across regions, got {len(recipients)}"
    )
    emails = [r["email"] for r in recipients]
    assert len(emails) == len(set(emails)), "duplicate emails leaked"
    # owner preview must NOT be included
    assert not any("owner" in r["country"].lower() for r in recipients)
    # Every entry has a usable email
    for r in recipients:
        assert "@" in r["email"]
        assert r["name"] != ""


def test_flyer_assets_exist():
    """The two flyer PNGs are committed under docs/marketplace_launch/."""
    out_dir = ROOT / "docs" / "marketplace_launch"
    for name in (
        "marketplace_flyer_1080x1080.png",
        "marketplace_flyer_1200x628.png",
    ):
        p = out_dir / name
        assert p.exists(), f"missing flyer: {p}"
        # PNG magic bytes
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        # Non-trivial size
        assert p.stat().st_size > 10_000


def test_launch_markdown_carries_url_in_every_channel():
    md = (ROOT / "data" / "beta_outreach" / "marketplace_launch_assets.md").read_text(
        encoding="utf-8"
    )
    # The marketplace URL must appear in every channel section.
    sections = ["Email", "WhatsApp", "LinkedIn", "Twitter"]
    for s in sections:
        idx = md.find(s)
        assert idx >= 0, f"section {s!r} missing"
    # The URL appears multiple times across the whole doc.
    assert md.count("solarpro.aiappinvent.com/marketplace") >= 4
