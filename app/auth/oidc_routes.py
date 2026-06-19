"""
Keycloak OIDC routes for SolarPro (Phase 5 of the migration plan).

Three routes, parallel-run safe:

    GET  /auth/login    -- Start the Authorization Code + PKCE flow.
                           Generates a code_verifier, state, nonce; stashes
                           them in the Flask session; 302s to Keycloak.

    GET  /auth/callback -- Keycloak redirects here with `code` + `state`.
                           Validate state, exchange code for tokens via
                           PKCE, verify id_token, drop the refresh token
                           into an HttpOnly cookie, populate Flask
                           session["user"], 302 to `next` or /dashboard.

    POST /auth/logout   -- Read the refresh token cookie, POST to Keycloak
                           end-session, wipe cookies + session, 302 to /.

Parallel-run model
------------------

When `KEYCLOAK_ENABLED` is unset / false, **every route in this Blueprint
redirects to the legacy /login form** (with `?legacy=1` so it bypasses
any future "redirect to Keycloak" stub). This makes the routes safe to
deploy long before the cutover -- a misclicked /auth/login lands the
user at the existing form instead of a broken redirect to a Keycloak
that isn't running.

Configuration (read from env at request time so tests can monkey-patch):

    KEYCLOAK_ENABLED              master switch, default off
    KEYCLOAK_ISSUER               same env Phase 2 middleware reads
    KEYCLOAK_CLIENT_ID            default "solarpro-web" (public client)
    KEYCLOAK_REDIRECT_URI         absolute URL of /auth/callback;
                                  derived from request.host_url if unset
    KEYCLOAK_POST_LOGOUT_URI      where to send users after logout;
                                  default "/"
    KEYCLOAK_RT_COOKIE_NAME       default "solarpro_rt"
    KEYCLOAK_RT_COOKIE_DOMAIN     default unset (current host)
    KEYCLOAK_AUDIENCE             same env Phase 2 middleware reads;
                                  default "solarpro-api"

Security choices (per plan §11.1 + §11.3)

  * PKCE S256 -- required for public clients.
  * `state` -- 32 bytes of entropy; held in `session["_kc_state"]`.
  * `nonce` -- ditto, held in `session["_kc_nonce"]`, checked against the
    id_token's nonce claim after token exchange.
  * Refresh token -- HttpOnly + Secure + SameSite=Lax cookie. Never in
    JavaScript-accessible storage.
  * Access token -- Flask session ONLY (server-side); not echoed to JS.
  * State, nonce, code_verifier cleared from session immediately after
    use to limit replay window.

Tests
-----

`tests/security/test_oidc_routes.py` mocks the Keycloak token endpoint
+ `verify_jwt` so the suite exercises every branch without a running
Keycloak. The four happy/sad paths + the KC-off pass-through are
covered; see that file for the matrix.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from typing import Optional, Tuple
from urllib.parse import urlencode, urljoin

import requests
from flask import (
    Blueprint, current_app, jsonify, make_response, redirect,
    request, session, url_for,
)

from app.security.keycloak_middleware import verify_jwt, JWTError


log = logging.getLogger(__name__)


oidc_bp = Blueprint("oidc", __name__, url_prefix="/auth")


# ── Config helpers ──────────────────────────────────────────────────────

def _keycloak_enabled() -> bool:
    return os.environ.get("KEYCLOAK_ENABLED", "").lower() in (
        "1", "true", "yes", "on",
    )


def _issuer() -> str:
    return os.environ.get("KEYCLOAK_ISSUER", "").rstrip("/")


def _authorize_url() -> str:
    return f"{_issuer()}/protocol/openid-connect/auth"


def _token_endpoint() -> str:
    return f"{_issuer()}/protocol/openid-connect/token"


def _end_session_endpoint() -> str:
    return f"{_issuer()}/protocol/openid-connect/logout"


def _client_id() -> str:
    return os.environ.get("KEYCLOAK_CLIENT_ID", "solarpro-web")


def _redirect_uri() -> str:
    """Absolute URL of /auth/callback. Prefer the explicit env so the
    Keycloak client's `redirectUris` list can be tighter than `*`.
    Fall back to the request host so dev tunnels work."""
    explicit = os.environ.get("KEYCLOAK_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    return urljoin(request.host_url, "/auth/callback")


def _post_logout_uri() -> str:
    return os.environ.get("KEYCLOAK_POST_LOGOUT_URI", "/")


def _rt_cookie_name() -> str:
    return os.environ.get("KEYCLOAK_RT_COOKIE_NAME", "solarpro_rt")


def _rt_cookie_domain() -> Optional[str]:
    v = os.environ.get("KEYCLOAK_RT_COOKIE_DOMAIN", "").strip()
    return v or None


def _audience() -> str:
    return os.environ.get("KEYCLOAK_AUDIENCE", "solarpro-api")


# ── PKCE + state ────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    """URL-safe base64 without padding -- per RFC 7636."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_pkce_pair() -> Tuple[str, str]:
    """(verifier, challenge) for code_challenge_method=S256."""
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _make_state() -> str:
    return _b64url(secrets.token_bytes(16))


# ── Legacy fallback ─────────────────────────────────────────────────────

def _legacy_login_redirect():
    """When KEYCLOAK_ENABLED is off, /auth/login points at the existing
    form. `?legacy=1` is the marc667us emergency channel (plan §11.1)."""
    return redirect("/login?legacy=1")


# ── Route handlers ──────────────────────────────────────────────────────

@oidc_bp.route("/login", methods=["GET"])
def auth_login():
    """Begin the Authorization Code + PKCE flow."""
    if not _keycloak_enabled():
        return _legacy_login_redirect()

    issuer = _issuer()
    if not issuer:
        log.error("KEYCLOAK_ISSUER not set; cannot start OIDC flow.")
        return jsonify(error="OIDC_NOT_CONFIGURED"), 503

    verifier, challenge = _make_pkce_pair()
    state = _make_state()
    nonce = _make_state()
    next_url = request.args.get("next") or "/dashboard"

    # Stash the proofs server-side; the URL only carries state + the
    # SHA-256 challenge (not the verifier).
    session["_kc_state"] = state
    session["_kc_nonce"] = nonce
    session["_kc_verifier"] = verifier
    session["_kc_next"] = next_url

    params = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return redirect(f"{_authorize_url()}?{urlencode(params)}")


@oidc_bp.route("/callback", methods=["GET"])
def auth_callback():
    """Token exchange + session/cookie set."""
    if not _keycloak_enabled():
        return _legacy_login_redirect()

    err = request.args.get("error")
    if err:
        log.warning("OIDC error response from Keycloak: %s", err)
        return jsonify(error="OIDC_ERROR", reason=err), 400

    code = request.args.get("code", "").strip()
    state = request.args.get("state", "").strip()
    if not code or not state:
        return jsonify(error="OIDC_MISSING_CODE_OR_STATE"), 400

    expected_state = session.pop("_kc_state", None)
    expected_nonce = session.pop("_kc_nonce", None)
    verifier = session.pop("_kc_verifier", None)
    next_url = session.pop("_kc_next", "/dashboard")

    if not expected_state or state != expected_state:
        log.warning("OIDC state mismatch: url=%r session=%r", state, expected_state)
        return jsonify(error="OIDC_STATE_MISMATCH"), 400
    if not verifier:
        log.warning("OIDC verifier missing from session; aborting.")
        return jsonify(error="OIDC_VERIFIER_MISSING"), 400

    # Token exchange. Public client; no client_secret. PKCE proves the
    # request originated from the same browser that started the flow.
    try:
        resp = requests.post(
            _token_endpoint(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
                "client_id": _client_id(),
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
            timeout=5.0,
        )
    except requests.RequestException as e:
        log.error("OIDC token exchange network error: %s", e)
        return jsonify(error="OIDC_TOKEN_NETWORK", reason=str(e)), 502

    if resp.status_code != 200:
        log.warning("OIDC token exchange %s: %s", resp.status_code, resp.text[:300])
        return jsonify(error="OIDC_TOKEN_FAILED",
                       status=resp.status_code, body=resp.text[:300]), 400

    try:
        payload = resp.json()
    except ValueError:
        return jsonify(error="OIDC_TOKEN_NONJSON"), 502

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    id_token = payload.get("id_token")
    if not access_token or not refresh_token or not id_token:
        return jsonify(error="OIDC_TOKEN_INCOMPLETE"), 502

    # Verify id_token signature + nonce. Use the existing middleware
    # so JWKS caching + issuer/audience checks are consistent across
    # the codebase.
    try:
        # id_token's audience is the client_id, not solarpro-api.
        claims = verify_jwt(id_token, audience=_client_id())
    except JWTError as e:
        log.warning("OIDC id_token failed verification: %s", e)
        return jsonify(error="OIDC_ID_TOKEN_INVALID", reason=str(e)), 400

    if expected_nonce and claims.get("nonce") != expected_nonce:
        log.warning("OIDC nonce mismatch (session=%r token=%r)",
                    expected_nonce, claims.get("nonce"))
        return jsonify(error="OIDC_NONCE_MISMATCH"), 400

    # Hydrate Flask session with the bits the UI needs. Per plan §11.3
    # the access token lives in memory (server-side session) but never
    # gets echoed to JavaScript.
    session["access_token"] = access_token
    session["user"] = {
        "sub": claims.get("sub"),
        "preferred_username": claims.get("preferred_username"),
        "email": claims.get("email"),
        "name": claims.get("name"),
        "tenant_id": claims.get("tenant_id"),
        "roles": (claims.get("realm_access") or {}).get("roles") or [],
    }

    # Refresh token in HttpOnly cookie. Inaccessible to JavaScript;
    # SameSite=Lax keeps it CSRF-safe across same-site nav.
    response = make_response(redirect(next_url))
    is_secure = request.is_secure or (
        os.environ.get("FORCE_SECURE_COOKIES", "").lower() in ("1", "true")
    )
    response.set_cookie(
        _rt_cookie_name(),
        refresh_token,
        max_age=int(payload.get("refresh_expires_in") or 3600),
        httponly=True,
        secure=is_secure,
        samesite="Lax",
        domain=_rt_cookie_domain(),
        path="/",
    )
    return response


@oidc_bp.route("/logout", methods=["POST", "GET"])
def auth_logout():
    """End the Keycloak session + wipe local cookies + session.

    GET is supported in addition to POST so a plain link can trigger
    logout in the legacy templates; the action is CSRF-safe because it
    only nukes session state, not any user data."""
    if not _keycloak_enabled():
        session.clear()
        return redirect(_post_logout_uri())

    refresh_token = request.cookies.get(_rt_cookie_name())
    if refresh_token:
        try:
            requests.post(
                _end_session_endpoint(),
                data={
                    "client_id": _client_id(),
                    "refresh_token": refresh_token,
                },
                timeout=5.0,
            )
        except requests.RequestException as e:
            # Logout best-effort -- even if Keycloak is unreachable we
            # still wipe local state so the browser is no longer
            # holding a valid session.
            log.warning("OIDC end-session call failed (continuing): %s", e)

    session.clear()
    response = make_response(redirect(_post_logout_uri()))
    response.delete_cookie(
        _rt_cookie_name(),
        domain=_rt_cookie_domain(),
        path="/",
    )
    return response


@oidc_bp.route("/refresh", methods=["POST"])
def auth_refresh():
    """Mint a fresh access token from the refresh cookie.

    Frontend calls this when X-Token-Expires-In drops below 90 seconds
    (plan §9.3). The new refresh token rotates the cookie."""
    if not _keycloak_enabled():
        return jsonify(error="KEYCLOAK_DISABLED"), 503

    refresh_token = request.cookies.get(_rt_cookie_name())
    if not refresh_token:
        return jsonify(error="OIDC_NO_REFRESH_TOKEN"), 401

    try:
        resp = requests.post(
            _token_endpoint(),
            data={
                "grant_type": "refresh_token",
                "client_id": _client_id(),
                "refresh_token": refresh_token,
            },
            timeout=5.0,
        )
    except requests.RequestException as e:
        return jsonify(error="OIDC_REFRESH_NETWORK", reason=str(e)), 502

    if resp.status_code != 200:
        return jsonify(error="OIDC_REFRESH_FAILED",
                       status=resp.status_code, body=resp.text[:300]), 401

    try:
        payload = resp.json()
    except ValueError:
        return jsonify(error="OIDC_REFRESH_NONJSON"), 502

    access_token = payload.get("access_token")
    new_refresh = payload.get("refresh_token")
    if not access_token:
        return jsonify(error="OIDC_REFRESH_INCOMPLETE"), 502

    session["access_token"] = access_token
    response = make_response(jsonify(
        ok=True,
        expires_in=payload.get("expires_in"),
    ))
    if new_refresh:
        is_secure = request.is_secure or (
            os.environ.get("FORCE_SECURE_COOKIES", "").lower() in ("1", "true")
        )
        response.set_cookie(
            _rt_cookie_name(),
            new_refresh,
            max_age=int(payload.get("refresh_expires_in") or 3600),
            httponly=True,
            secure=is_secure,
            samesite="Lax",
            domain=_rt_cookie_domain(),
            path="/",
        )
    return response


# ── Public entry point ──────────────────────────────────────────────────

def register_oidc(app) -> None:
    """Mount the Blueprint on a Flask app. Idempotent.

    Call this once from `web_app.py` right after the app is created.
    The Blueprint is safe to mount even when `KEYCLOAK_ENABLED` is off
    -- every route falls through to the legacy form in that case.
    """
    if "oidc" in app.blueprints:
        return
    app.register_blueprint(oidc_bp)
