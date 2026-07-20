"""
Behavioural tests for the /api/v1 alias surface.

These build a REAL Flask app with stand-in source routes rather than
importing web_app (which SystemExits without production env). That is enough
to exercise everything this module actually decides: whether it registers,
what endpoint names it creates, that url_for on the ORIGINAL endpoint is
unchanged, and that a missing source route degrades instead of exploding.
"""

from __future__ import annotations

import os

import pytest
from flask import Flask, jsonify, url_for

import new_api_v1_routes as v1


def _app() -> Flask:
    """A minimal app carrying stand-ins for the four aliased endpoints."""
    app = Flask(__name__)
    app.config["SERVER_NAME"] = "test.local"

    @app.route("/api/solar_regions/<country>", endpoint="api_solar_regions_public")
    def regions(country):
        return jsonify(country=country)

    @app.route("/api/solar_data/<country>/<region>", endpoint="api_solar_data_public")
    def data(country, region):
        return jsonify(country=country, region=region)

    @app.route("/api/purc-tariffs", endpoint="api_purc_tariffs")
    def tariffs():
        return jsonify(ok=True)

    @app.route("/api/demand-factors", endpoint="api_demand_factors")
    def factors():
        return jsonify(ok=True)

    return app


@pytest.fixture
def dark(monkeypatch):
    monkeypatch.delenv("API_V1_ENABLED", raising=False)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("API_V1_ENABLED", "1")


# ── the dark default ─────────────────────────────────────────────────────

def test_ships_dark_by_default(dark):
    """First deploy must register NOTHING. The env var is opt-in."""
    app = _app()
    before = {r.rule for r in app.url_map.iter_rules()}
    summary = v1.register(app)
    after = {r.rule for r in app.url_map.iter_rules()}

    assert summary["enabled"] is False
    assert summary["registered"] == []
    assert before == after, "a dark deploy must not add any rule"


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  "])
def test_only_explicit_truthy_values_enable(monkeypatch, value):
    monkeypatch.setenv("API_V1_ENABLED", value)
    assert v1.enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_truthy_values_enable(monkeypatch, value):
    monkeypatch.setenv("API_V1_ENABLED", value)
    assert v1.enabled() is True


# ── enabled behaviour ────────────────────────────────────────────────────

def test_registers_every_alias_when_enabled(live):
    app = _app()
    summary = v1.register(app)

    assert summary["enabled"] is True
    assert summary["missing"] == []
    rules = {r.rule for r in app.url_map.iter_rules()}
    for _e, _s, v1_path in v1.ALIASES:
        assert v1_path in rules, f"{v1_path} not registered"
    assert v1.V1_PREFIX in rules, "manifest route missing"


def test_aliases_serve_the_same_handler(live):
    app = _app()
    v1.register(app)
    c = app.test_client()

    assert c.get("/api/purc-tariffs").get_json() == c.get("/api/v1/purc-tariffs").get_json()
    assert (c.get("/api/solar_regions/GH").get_json()
            == c.get("/api/v1/solar-regions/GH").get_json())


def test_unversioned_paths_still_work(live):
    """The whole promise of this change: nothing existing is disturbed."""
    app = _app()
    v1.register(app)
    c = app.test_client()

    for path in ("/api/purc-tariffs", "/api/demand-factors",
                 "/api/solar_regions/GH", "/api/solar_data/GH/Ashanti"):
        assert c.get(path).status_code == 200, f"{path} broke"


def test_url_for_on_original_endpoint_is_unchanged(live):
    """The failure mode Codex warned about.

    Reusing the source endpoint name would let werkzeug build EITHER rule, so
    templates could silently start emitting /api/v1/... . A distinct v1_
    endpoint keeps url_for deterministic.
    """
    app = _app()
    v1.register(app)

    def path_of(endpoint, **kw):
        # SERVER_NAME is set on the test app, so url_for builds an absolute
        # URL. Only the path is under test here.
        from urllib.parse import urlparse
        return urlparse(url_for(endpoint, **kw)).path

    with app.app_context():
        assert path_of("api_purc_tariffs") == "/api/purc-tariffs"
        assert path_of("api_solar_regions_public", country="GH") == "/api/solar_regions/GH"
        # ...and the alias is reachable under its own name.
        assert path_of("v1_api_purc_tariffs") == "/api/v1/purc-tariffs"


def test_manifest_lists_the_surface(live):
    app = _app()
    v1.register(app)
    body = app.test_client().get(v1.V1_PREFIX).get_json()

    assert body["version"] == "v1"
    assert set(body["endpoints"]) == {v1_path for _e, _s, v1_path in v1.ALIASES}
    assert "not deprecated" in body["note"].lower()


# ── failure modes ────────────────────────────────────────────────────────

def test_missing_source_endpoint_is_reported_not_raised(live):
    """A renamed source route must degrade, not take down the app.

    register() runs at import inside wsgi.py, so raising here would be an
    outage -- and a versioning alias is never worth that.
    """
    app = Flask(__name__)  # deliberately EMPTY: no source routes at all

    summary = v1.register(app)  # must not raise

    assert sorted(summary["missing"]) == sorted(e for e, _s, _v in v1.ALIASES)
    assert summary["registered"] == []
    # No manifest either -- advertising an empty surface would be a lie.
    assert v1.V1_PREFIX not in {r.rule for r in app.url_map.iter_rules()}


def test_double_registration_is_idempotent(live):
    """wsgi.py can be imported more than once; a second pass must not raise
    (Flask rejects re-registering an endpoint) nor duplicate rules."""
    app = _app()
    v1.register(app)
    first = sorted(r.rule for r in app.url_map.iter_rules())

    second = v1.register(app)  # must not raise

    assert sorted(r.rule for r in app.url_map.iter_rules()) == first
    assert second["registered"] == [], "second pass should register nothing new"


def test_alias_inherits_the_rate_limit_but_gets_its_own_bucket():
    """Pin the MEASURED limiter behaviour behind the endpoint-naming choice.

    Two facts, both verified against Flask-Limiter 4.1.1 rather than assumed:

      1. The alias IS rate limited -- @limiter.limit travels with the view
         function, so aliasing does not create an unlimited back door. This is
         the important one; if it ever stopped being true, the alias would be
         a way around the limit entirely.
      2. It uses its OWN bucket, so a caller working both paths gets double
         the budget. Accepted here (read-only public reference data), and the
         reason this test exists is so nobody extends the pattern to a
         mutating endpoint believing the bucket is shared.
    """
    from flask_limiter import Limiter

    app = Flask(__name__)
    lim = Limiter(lambda: "1.2.3.4", app=app,
                  default_limits=["1000 per hour"], storage_uri="memory://")

    @app.route("/api/thing", endpoint="thing")
    @lim.limit("5 per minute")
    def thing():
        return jsonify(ok=True)

    app.add_url_rule("/api/v1/thing", endpoint="v1_thing",
                     view_func=app.view_functions["thing"], methods=["GET"])

    c = app.test_client()
    original = [c.get("/api/thing").status_code for _ in range(7)]
    alias = [c.get("/api/v1/thing").status_code for _ in range(7)]

    assert original == [200] * 5 + [429, 429], f"source limit changed: {original}"
    assert 429 in alias, (
        "the v1 alias is NOT rate limited at all -- aliasing has become a way "
        f"around @limiter.limit entirely: {alias}"
    )
    assert alias[0] == 200, (
        "the alias now SHARES the source bucket. That is stricter than "
        "documented, so it is safe -- but update the docstring in "
        "new_api_v1_routes.py, which says the buckets are separate."
    )


def test_declared_paths_match_aliases():
    """declared_paths() is what the route-auth ratchet consumes, so it must
    not drift from what register() actually creates."""
    declared = set(v1.declared_paths())
    expected = {f"GET {v1_path}" for _e, _s, v1_path in v1.ALIASES}
    expected.add(f"GET {v1.V1_PREFIX}")
    assert declared == expected
