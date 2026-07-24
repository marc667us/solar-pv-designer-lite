"""Tests for new_pwa_routes.py (installable PWA: manifest + service worker)."""

from __future__ import annotations

import json
import os

import pytest
from flask import Flask

import new_pwa_routes as pwa


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    pwa.register_pwa(app)
    return app.test_client()


def test_manifest_is_valid_and_complete(client):
    r = client.get("/manifest.json")
    assert r.status_code == 200
    assert "application/manifest+json" in r.headers["Content-Type"]
    m = json.loads(r.data)
    for k in ("name", "short_name", "start_url", "scope", "display",
              "background_color", "theme_color", "icons"):
        assert k in m, k
    assert m["display"] == "standalone"
    assert m["theme_color"] == "#f59e0b"
    sizes = {i["sizes"] for i in m["icons"]}
    assert "192x192" in sizes and "512x512" in sizes
    assert any(i.get("purpose") == "maskable" for i in m["icons"])


def test_service_worker_headers_and_safety(client):
    r = client.get("/service-worker.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["Content-Type"]
    assert r.headers.get("Service-Worker-Allowed") == "/"      # root scope allowed
    body = r.data.decode()
    assert "addEventListener('fetch'" in body
    # SAFETY invariants: never touch non-GET, never cache auth/payment routes.
    assert "req.method !== 'GET'" in body
    for guarded in ("/api", "/admin", "/auth", "/paystack", "/stripe", "/upgrade"):
        assert guarded in body, guarded
    # navigations must be network-first (live page wins)
    assert "req.mode === 'navigate'" in body
    assert "fetch(req).catch" in body


def test_offline_page_renders(client):
    r = client.get("/offline")
    assert r.status_code == 200
    assert b"offline" in r.data.lower()


def test_icons_exist_with_correct_sizes():
    from PIL import Image
    base = os.path.join(os.path.dirname(__file__), "static", "icons")
    assert Image.open(os.path.join(base, "icon-192.png")).size == (192, 192)
    assert Image.open(os.path.join(base, "icon-512.png")).size == (512, 512)
    assert Image.open(os.path.join(base, "icon-maskable-512.png")).size == (512, 512)


def test_registration_is_idempotent():
    app = Flask(__name__)
    pwa.register_pwa(app)
    pwa.register_pwa(app)   # must not raise on double registration
    assert "pwa_manifest" in app.view_functions
