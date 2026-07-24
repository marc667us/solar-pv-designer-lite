"""PWA surface: web app manifest + service worker (installable web app).

Adds:
    GET /manifest.json     -> the Web App Manifest (installability + icons)
    GET /service-worker.js -> a DELIBERATELY CONSERVATIVE service worker
    GET /offline           -> the offline fallback page the SW serves

WHY THE SERVICE WORKER IS MINIMAL (this is a LIVE PAYMENTS app)
    A buggy SW can serve stale pages, leak one user's cached page to another, or
    mangle POST/auth/payment flows. So this SW:
      * intercepts GET only -- never POST/auth/payment, and passes those through;
      * NEVER caches dynamic/auth/payment routes (/api, /admin, /auth, /login,
        /logout, /paystack, /stripe, /me, /staff, /enterprise, /billing, ...);
      * navigations are network-FIRST -- the live page always wins; the cache is
        only consulted when the network fails, and then it serves a static
        /offline page (never a cached authenticated page);
      * only truly-static assets under /static/ are cache-first.
    That is enough to make the app installable without risking the app itself.

Registered from wsgi.py (web_app.py is CRLF+mojibake, never edited directly),
boot-resilient like the other new_* surfaces.
"""

from __future__ import annotations

import json

from flask import Response, render_template_string

_MANIFEST = {
    "name": "SolarPro Global — PV Solar Design",
    "short_name": "SolarPro",
    "description": "Intelligent global PV solar system design, BOQ, financing & procurement.",
    "id": "/?source=pwa",
    "start_url": "/?source=pwa",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait-primary",
    "background_color": "#0a0a14",
    "theme_color": "#f59e0b",
    "categories": ["business", "productivity", "utilities"],
    "icons": [
        {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

# Bump CACHE_VERSION whenever the SW logic or precached shell changes so old
# caches are discarded on activate.
_SERVICE_WORKER = r"""
const CACHE = 'solarpro-pwa-v1';
const PRECACHE = ['/offline', '/manifest.json',
                  '/static/icons/icon-192.png', '/static/icons/icon-512.png'];
// Route prefixes that must NEVER be cached or intercepted from cache -- dynamic,
// per-user, or money/auth paths. The live network is always used for these.
const NO_CACHE = ['/api', '/admin', '/auth', '/login', '/logout', '/register',
                  '/paystack', '/stripe', '/upgrade', '/me/', '/staff', '/billing',
                  '/enterprise', '/large-scale-solar', '/reset-password', '/forgot-password'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  // Only ever touch GET requests on our own origin. Everything else (POST,
  // cross-origin, etc.) goes straight to the network, untouched.
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (NO_CACHE.some((p) => url.pathname.startsWith(p))) return;  // dynamic/auth/payment -> network only

  // Static assets: cache-first (safe -- immutable-ish files).
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res && res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
        return res;
      }).catch(() => hit))
    );
    return;
  }

  // Navigations: network-FIRST. The live page always wins; only when the
  // network fails do we show the static offline page (never a cached auth page).
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).catch(() => caches.match('/offline')));
    return;
  }
  // Anything else GET: plain network passthrough.
});
"""

_OFFLINE_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Offline — SolarPro</title>
<style>
 body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:#0a0a14;color:#e2e2f0;font-family:system-ui,-apple-system,sans-serif;text-align:center}
 .box{max-width:420px;padding:32px}
 img{width:96px;height:96px} h1{color:#f59e0b;margin:16px 0 8px}
 p{color:#9a9ac0;line-height:1.5} a{color:#f59e0b}
</style></head><body>
<div class="box">
  <img src="/static/icons/icon-192.png" alt="SolarPro">
  <h1>You're offline</h1>
  <p>SolarPro needs a connection for live design, pricing and account data.
     Reconnect and try again.</p>
  <p><a href="/" onclick="location.reload();return false;">Retry</a></p>
</div></body></html>"""


def register_pwa(app):
    """Attach the PWA routes. Idempotent against double registration."""

    if "pwa_manifest" not in app.view_functions:
        @app.route("/manifest.json")
        def pwa_manifest():
            return Response(json.dumps(_MANIFEST), mimetype="application/manifest+json")

    if "pwa_service_worker" not in app.view_functions:
        @app.route("/service-worker.js")
        def pwa_service_worker():
            resp = Response(_SERVICE_WORKER, mimetype="application/javascript")
            # Allow a root-scope SW even though it is served from /service-worker.js.
            resp.headers["Service-Worker-Allowed"] = "/"
            # The SW itself must not be cached by the browser for long, or logic
            # updates never ship.
            resp.headers["Cache-Control"] = "no-cache"
            return resp

    if "pwa_offline" not in app.view_functions:
        @app.route("/offline")
        def pwa_offline():
            return render_template_string(_OFFLINE_HTML)
