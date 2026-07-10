"""Database readiness, decoupled from process startup.

WHY THIS MODULE EXISTS
----------------------
`wsgi.py` used to call `init_db()` at import time. gunicorn imports the WSGI
module *before* it binds `$PORT`, so anything `init_db()` raised killed the
process before it could listen on a socket.

On 2026-07-09 the free-tier Render Postgres hit its 30-day expiry and was
suspended. Its internal hostname stopped resolving, so `init_db()` raised

    psycopg2.OperationalError: could not translate host name
    "dpg-d8k7kpmgvqtc73biiga0-a" to address

at import, gunicorn never bound `$PORT`, and Render restarted the service in a
permanent loop. A database outage became a *total* outage: the app could not
serve even a static page, and Keycloak -- whose schema lives in the same
database -- went down with it.

The rule this module encodes:

    Process liveness must never depend on the database.

TWO FAILURE MODES, NOT ONE
--------------------------
It is not enough to catch exceptions. A database can also *hang*: DNS that never
answers, a TCP connect into a blackhole, a server that accepts and then stalls.
An exception is fast; a hang is not. So the boot attempt is bounded by a wall
clock, not merely wrapped in try/except -- it runs on a worker thread which the
importing thread joins for at most BOOT_TIMEOUT_SECONDS. If the database has not
answered by then, the process binds its port anyway and the attempt continues in
the background.

For the same reason no request ever blocks on initialisation. The request hook
only *triggers* a retry; it never waits for one. Render restarts an instance
after 60 seconds of consecutive health-check failures, so if a slow retry could
stall `/api/ping`, an outage would still take the service down -- exactly the
loop this module exists to break.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not short-circuit requests with a blanket 503 while degraded. That would
fail the health check and trigger the same restart loop. Routes that need the
database fail individually, which is correct; `/api/ping` keeps answering 200,
which keeps the instance alive long enough to recover on its own.
"""

import logging
import math
import os
import threading
import time

log = logging.getLogger(__name__)


def _env_float(name, default, minimum=0.0):
    """Read a float from the environment, never raising.

    This module's whole purpose is to keep the process alive through bad
    conditions; crashing at import because someone typed `DB_INIT_RETRY_SECONDS=""`
    would be a poor way to honour that. NaN and inf are rejected too -- they are
    parseable floats that would poison thread.join() and the retry arithmetic.

    `minimum` exists because zero is a legal float with a pathological meaning
    here: DB_INIT_STUCK_SECONDS=0 and DB_INIT_RETRY_SECONDS=0 together would
    start a fresh init thread on *every request* against a down database.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        log.warning("%s=%r is not a number; using default %s", name, raw, default)
        return default
    if not math.isfinite(value) or value < minimum:
        log.warning("%s=%r is not a finite number >= %s; using default %s",
                    name, raw, minimum, default)
        return default
    return value


# How long the importing thread waits for the first attempt before giving up and
# letting gunicorn bind the port. A healthy database answers in milliseconds, so
# this bound is invisible in normal operation and only pays out during an outage.
BOOT_TIMEOUT_SECONDS = _env_float("DB_INIT_BOOT_TIMEOUT_SECONDS", 10.0, minimum=0.1)

# Minimum gap between initialisation attempts. Requests arrive far more often
# than the database changes state. The keep-warm cron pings /api/ping every 5
# minutes, which drives recovery even with zero real traffic.
RETRY_INTERVAL_SECONDS = _env_float("DB_INIT_RETRY_SECONDS", 15.0, minimum=0.1)

# After this long, an in-flight attempt is presumed stuck and a fresh one is
# allowed to start alongside it.
#
# Single-flight must not become single-forever. If an attempt were guarded by a
# lock held for its whole duration, an init_db() that never returns would block
# every future retry: the app would bind its port, report "will retry", and then
# never actually retry -- silently unable to heal even after the database came
# back. db_adapter now passes connect_timeout so a hang is bounded, but this
# module must not *depend* on any caller's timeout to keep its own promise.
STUCK_ATTEMPT_SECONDS = _env_float("DB_INIT_STUCK_SECONDS", 60.0, minimum=1.0)

# Paths that must keep answering while the database is down.
#
# /api/ping is Render's healthCheckPath: if it ever fails for 60 consecutive
# seconds Render restarts the instance, which is the crash-loop this module
# exists to prevent. /api/health/boot is how an operator sees *why* we are
# degraded. Everything else needs the database and should say so honestly with a
# 503 rather than 500 from a half-built schema.
_ALWAYS_AVAILABLE_PATHS = ("/api/ping", "/api/version", "/api/health")
# /api/health/* is exempt as a family: a health probe that is itself blocked by a
# health gate tells an operator nothing. Those endpoints report their own errors.
# The trailing slash matters -- a bare "/api/health" prefix would also exempt an
# unrelated future route such as /api/healthcheck or /api/health-admin.
_ALWAYS_AVAILABLE_PREFIXES = ("/static/", "/api/health/")

# Guards the _state dict only. Never held across init_db().
_state_lock = threading.Lock()

# Lock-free fast path. Assignment to a module global is atomic under the GIL, and
# once True this never goes back to False, so the before_request hook that runs
# on EVERY request can read it without serialising on _state_lock.
_ready_fast = False

_state = {
    "ready": False,        # has init_db() completed successfully?
    "attempts": 0,
    "last_attempt": 0.0,   # monotonic clock, set when an attempt begins
    "last_error": None,    # str, surfaced by the boot health endpoint
    "ready_since": None,
    "inflight": 0,         # attempts currently running
    # Monotonic clock of the MOST RECENT attempt, not the oldest. start_attempt()
    # re-anchors it on every supersession so that a stuck attempt costs at most
    # one extra thread per STUCK_ATTEMPT_SECONDS rather than one per request.
    "inflight_since": 0.0,
}


def snapshot():
    """Return a copy of the current boot state. Safe from any thread."""
    with _state_lock:
        s = dict(_state)
    s["initializing"] = s["inflight"] > 0
    s["retry_interval_seconds"] = RETRY_INTERVAL_SECONDS
    s["boot_timeout_seconds"] = BOOT_TIMEOUT_SECONDS
    s["stuck_attempt_seconds"] = STUCK_ATTEMPT_SECONDS
    return s


def is_ready():
    # Read the lock-free flag. It only ever transitions False -> True, so a
    # stale False costs at most one extra (throttled, non-blocking) retry check.
    return _ready_fast


def _attempt(init_db, attempt):
    """Run init_db() exactly once on a worker thread. Never raises.

    The caller has already accounted for this attempt in _state. The finally
    block is the ONLY place `inflight` is decremented, so a raising init_db(),
    a raising logger, or a KeyboardInterrupt cannot leave the counter wedged.
    """
    try:
        try:
            init_db()
        except Exception as exc:  # noqa: BLE001 -- boot must survive anything
            message = "{}: {}".format(type(exc).__name__, exc)
            with _state_lock:
                # A superseded attempt may unwind long after a newer one has
                # already succeeded. Do not resurrect its error, or
                # /api/health/boot would report database_ready:true beside a
                # stale failure and send an on-call engineer chasing a ghost.
                stale = _state["ready"]
                if not stale:
                    _state["last_error"] = message
            log.warning(
                "init_db() attempt %d failed%s: %s",
                attempt,
                " (superseded; database already ready)" if stale
                else "; serving DEGRADED, will retry",
                message,
            )
            return

        global _ready_fast
        with _state_lock:
            # Likewise, the first attempt to finish owns ready_since.
            if not _state["ready"]:
                _state["ready"] = True
                _state["last_error"] = None
                _state["ready_since"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
            # Publish the fast flag INSIDE the lock. If it were set after the
            # lock released, a request landing in that window would read
            # is_ready()==False, then start_attempt() would decline (it sees
            # _state["ready"]), and the gate would serve a 503 for a database
            # that is in fact ready.
            _ready_fast = True
        log.info("init_db() succeeded on attempt %d; database ready", attempt)
    finally:
        _release_inflight()


def _release_inflight():
    """Give back one in-flight slot. Must pair with every increment."""
    with _state_lock:
        _state["inflight"] -= 1
        if _state["inflight"] <= 0:
            _state["inflight"] = 0
            _state["inflight_since"] = 0.0


def start_attempt(init_db, force=False):
    """Kick off an initialisation attempt on a background thread.

    Returns the Thread if one was started, else None. NEVER BLOCKS: if the
    database is ready, or a healthy attempt is already in flight, or the retry
    throttle has not elapsed, it returns immediately. That property is what lets
    the request hook call it on the hot path without ever delaying /api/ping.

    An attempt older than STUCK_ATTEMPT_SECONDS is presumed hung and no longer
    blocks a fresh one. Python cannot kill the stale thread, so it is abandoned;
    it will unwind on its own eventually and decrement the counter. Abandoning a
    stuck thread is strictly better than never retrying: at most one extra
    thread is created per stuck window, and the process stays able to heal.
    """
    if is_ready():
        return None

    now = time.monotonic()
    with _state_lock:
        if _state["ready"]:                 # raced with a finishing attempt
            return None

        inflight = _state["inflight"]
        if inflight > 0 and (now - _state["inflight_since"]) < STUCK_ATTEMPT_SECONDS:
            return None                     # a healthy attempt is already running

        if not force and (now - _state["last_attempt"]) < RETRY_INTERVAL_SECONDS:
            return None                     # throttled

        if inflight > 0:
            log.warning(
                "init_db() attempt has been running %.0fs and is presumed stuck; "
                "starting another so the app can still recover",
                now - _state["inflight_since"],
            )

        _state["attempts"] += 1
        _state["last_attempt"] = now
        # Restart the stuck window from THIS attempt. If it kept pointing at the
        # oldest abandoned thread, every subsequent request would see "stuck"
        # again and spawn yet another thread -- trading a wedge for a leak.
        # Anchoring on the newest attempt bounds thread creation to one per
        # STUCK_ATTEMPT_SECONDS.
        _state["inflight_since"] = now
        _state["inflight"] = inflight + 1
        attempt = _state["attempts"]

    # Creating or starting a thread can fail -- `RuntimeError: can't start new
    # thread` under thread/memory exhaustion on a 512MB instance. This function
    # is called from before_request on EVERY request, so an escaping exception
    # would turn /api/ping into a 500, fail Render's health check for 60s, and
    # restart the instance: precisely the loop this module prevents. It is also
    # called during module import, where an escaping exception stops gunicorn
    # from ever binding $PORT. It must therefore never raise.
    try:
        thread = threading.Thread(
            target=_attempt, args=(init_db, attempt), name="db-init", daemon=True,
        )
        thread.start()
    except Exception as exc:  # noqa: BLE001 -- see above; must not propagate
        message = "could not start db-init thread: {}: {}".format(
            type(exc).__name__, exc
        )
        with _state_lock:
            if not _state["ready"]:
                _state["last_error"] = message
        _release_inflight()          # the slot we took above
        log.warning("%s; will retry", message)
        return None

    return thread


def attach(app, init_db):
    """Wire bounded, self-healing database initialisation into a Flask app.

    Call once from the WSGI entrypoint.
    """
    from flask import jsonify, request  # resolved once, not per request

    # Bounded first attempt. On a healthy boot this joins in milliseconds and
    # the app is ready before the first request, exactly as before. On an
    # unhealthy one we stop waiting and let gunicorn bind the port; the thread
    # keeps working in the background.
    thread = start_attempt(init_db, force=True)
    if thread is not None:
        thread.join(BOOT_TIMEOUT_SECONDS)

    if not is_ready():
        log.error(
            "database not ready after %.1fs; binding port and serving DEGRADED. "
            "Retries continue every %.1fs (a stuck attempt is superseded after "
            "%.0fs). See /api/health/boot",
            BOOT_TIMEOUT_SECONDS, RETRY_INTERVAL_SECONDS, STUCK_ATTEMPT_SECONDS,
        )

    def _ensure_db_ready():  # noqa: ANN202
        if is_ready():
            return None

        # Must never block. start_attempt() returns immediately in every case,
        # and never raises.
        start_attempt(init_db)

        # A concurrent attempt may have just succeeded. Re-check rather than
        # serve a 503 for a database that is now ready.
        if is_ready():
            return None

        path = request.path
        if path in _ALWAYS_AVAILABLE_PATHS or path.startswith(_ALWAYS_AVAILABLE_PREFIXES):
            return None

        # Everything else needs the database. Before this module existed,
        # init_db() had always completed before the socket opened, so no request
        # could observe a half-built schema. Now that we bind first, say so
        # honestly: a 503 with Retry-After is a truthful "not yet", where a 500
        # from `relation "projects" does not exist` is a lie about what broke.
        response = jsonify({
            "error": "SERVICE_UNAVAILABLE",
            "message": "The database is not ready yet. Please retry shortly.",
        })
        response.status_code = 503
        response.headers["Retry-After"] = str(int(RETRY_INTERVAL_SECONDS) or 1)
        return response

    # Run FIRST, ahead of every hook web_app registered at its own import.
    # web_app's `_bump_last_seen` (web_app.py:28659) issues a query on each
    # request for logged-in users. Registered normally, our gate would sit behind
    # it, and every request during an outage would first burn the full
    # connect_timeout inside that hook. Flask executes before_request functions in
    # registration order, so insert at the head rather than appending.
    app.before_request_funcs.setdefault(None, []).insert(0, _ensure_db_ready)

    @app.route("/api/health/boot")
    def _boot_health():  # noqa: ANN202
        s = snapshot()
        # 200 ready / 503 degraded. Deliberately NOT the Render healthCheckPath:
        # that points at /api/ping, so a database outage cannot restart-loop the
        # instance. This endpoint is for humans and dashboards.
        return jsonify({
            "database_ready": s["ready"],
            "status": "ok" if s["ready"] else "degraded",
            "initializing": s["initializing"],
            "attempts": s["attempts"],
            "last_error": s["last_error"],
            "ready_since": s["ready_since"],
            "retry_interval_seconds": s["retry_interval_seconds"],
            "boot_timeout_seconds": s["boot_timeout_seconds"],
        }), (200 if s["ready"] else 503)

    return app
