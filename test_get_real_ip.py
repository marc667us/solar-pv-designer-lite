"""Tests for the _get_real_ip() X-Forwarded-For spoof fix.

Proves the rate-limit / lockout key is derived from the trusted (rightmost,
proxy-appended) X-Forwarded-For entry, not the client-controlled leftmost one.
Run: python -m pytest test_get_real_ip.py -q
"""
import os
import importlib


def _fresh_app(monkeypatch, **env):
    """Import web_app with a controlled environment so behind_proxy resolves
    deterministically. web_app builds the limiter at import time, but
    _get_real_ip reads os.environ live on each call, so we only need the app
    object + a request context."""
    for k in ("RENDER", "TRUST_PROXY_HEADERS", "TRUSTED_PROXY_HOPS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import web_app
    return web_app


def _ip(web_app, xff=None, remote="9.9.9.9"):
    headers = {"X-Forwarded-For": xff} if xff is not None else {}
    with web_app.app.test_request_context(
        "/", headers=headers, environ_base={"REMOTE_ADDR": remote}
    ):
        return web_app._get_real_ip()


def test_behind_proxy_takes_rightmost_trusted_hop(monkeypatch):
    wa = _fresh_app(monkeypatch, RENDER="true")  # 1 trusted hop (default)
    # attacker spoofs 1.1.1.1; Render appends the real client 203.0.113.7
    assert _ip(wa, "1.1.1.1, 203.0.113.7") == "203.0.113.7"


def test_spoof_only_header_clamps_to_client(monkeypatch):
    wa = _fresh_app(monkeypatch, RENDER="true")
    # only a spoofed value present (no proxy hop appended yet) -> clamp to it,
    # never index out of range
    assert _ip(wa, "1.1.1.1") == "1.1.1.1"


def test_two_trusted_hops_skips_two_from_right(monkeypatch):
    wa = _fresh_app(monkeypatch, RENDER="true", TRUSTED_PROXY_HOPS="2")
    # client, cloudflare-added-client, render-added-cloudflare
    assert _ip(wa, "1.1.1.1, 203.0.113.7, 172.16.0.1") == "203.0.113.7"


def test_not_behind_proxy_ignores_xff(monkeypatch):
    wa = _fresh_app(monkeypatch)  # no RENDER / TRUST_PROXY_HEADERS
    assert _ip(wa, "1.1.1.1, 203.0.113.7", remote="9.9.9.9") == "9.9.9.9"


def test_no_xff_falls_back_to_remote_addr(monkeypatch):
    wa = _fresh_app(monkeypatch, RENDER="true")
    assert _ip(wa, None, remote="9.9.9.9") == "9.9.9.9"


def test_bad_hops_env_defaults_to_one(monkeypatch):
    wa = _fresh_app(monkeypatch, RENDER="true", TRUSTED_PROXY_HOPS="not-a-number")
    assert _ip(wa, "1.1.1.1, 203.0.113.7") == "203.0.113.7"


def test_hops_exceeds_chain_falls_back_to_rightmost_not_leftmost(monkeypatch):
    # Operator misconfigures more hops than the real chain has. The safe
    # fallback is the rightmost (nearest-proxy) entry, never the spoofable
    # leftmost one.
    wa = _fresh_app(monkeypatch, RENDER="true", TRUSTED_PROXY_HOPS="5")
    assert _ip(wa, "1.1.1.1, 203.0.113.7") == "203.0.113.7"
