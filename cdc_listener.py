"""CDC slice 4 -- the BROADCAST half of the change feed. SHIPS DARK.

Slices 1-3 built the DURABLE half: triggers capture into `cdc_outbox`, a cron drains it and
raises one admin alert per pass. That is the "alerted" half of the owner's 2026-07-13 ask.
This is the "and updated" half.

WHY A DRAINER CANNOT DO THIS JOB
--------------------------------
Every gunicorn worker holds its OWN `_MARKETPLACE_CACHE` dict. A drainer runs inside one
worker, so clearing the cache there leaves every other worker exactly as stale -- while making
the logs read as though invalidation happened. Migration 036 separates the channels for this
reason: durable side-effects go in the outbox and are claimed ONCE; cache invalidation is a
BROADCAST and must travel over `pg_notify`, which every LISTENer receives.

`cdc_capture()` already emits it -- `PERFORM pg_notify('cdc', table || ':' || op || ':' || pk)`
(036 line ~164). The payload is a POINTER, never the row, because pg_notify caps at 8000 bytes.
Nothing has been listening, so every one of those notifications has been discarded. This adds
the listener.

pg_notify IS FIRE-AND-FORGET. A notification delivered while nobody is listening is gone
forever. That is survivable HERE and only here: a missed invalidation costs at most
`_MARKETPLACE_CACHE_TTL` (60s) of staleness for anonymous /marketplace visitors, never a
permanent lie. It is precisely why durable work went in a table instead.

IT SHIPS DARK, BEHIND A KILL SWITCH, AND THAT IS THE POINT
----------------------------------------------------------
This is the first thing in this codebase to hold a long-lived database connection and the
first to run a permanent background loop that touches Postgres. Measured 2026-07-19 before
writing it: max_connections=103, 11 in use, 90 free -- so one connection is affordable. But
"affordable" is not "proven", so the loop does not start unless `admin_settings` says so.
Default is OFF; the flag read FAILS CLOSED.

NOTHING HERE MAY EVER TAKE THE APP DOWN. The rules come from boot_state.py and wsgi.py:
  * this module must not raise at import;
  * creating or starting a Thread can itself raise (RuntimeError: can't start new thread,
    under memory pressure on a 512MB instance) and that must be caught, not propagated --
    an exception escaping at import means gunicorn never binds $PORT and Render restart-loops;
  * the listener must NOT assume a working database at start time. boot_state may still be
    retrying when this starts, so the loop connects on its own schedule with backoff and
    never blocks import.

WORKER TOPOLOGY -- AND WHY STARTING AT IMPORT IS NOT ENOUGH
-----------------------------------------------------------
Render runs `gunicorn --worker-class gthread --workers 1 --threads 4`, with NO `--preload`.
The obvious conclusion is that each worker imports this module itself, so a thread started at
import lives in the worker. THAT CONCLUSION IS WRONG HERE, and the first dark deploy proved it:
the serving process reported a thread that had entered the loop, never unwound, and was absent
from `threading.enumerate()` -- the signature of a process that was FORKED after import.

So the listener does not rely on the import-time thread surviving. `ensure_running()` is called
from a `before_request` hook and re-spawns the thread whenever the serving process finds it has
none -- detected by comparing `os.getpid()` against the pid that created it, which is the one
check a forked child cannot pass by accident. The import-time `start()` remains, but its real
job is to CAPTURE DEPENDENCIES; the guarantee comes from the request path.

Unlike `web_app._monitor_thread` -- which starts unconditionally at import with NO double-start
guard and is safe only by accident of `--workers 1` -- this module refuses to start twice in one
process, and the guard is pid-aware so a fork gets its own listener rather than inheriting a
dead one.
"""

import logging
import os
import random
import select
import threading
import time

_log = logging.getLogger(__name__)

# The channel cdc_capture() publishes on. Must match migration 036.
_CHANNEL = "cdc"

# admin_settings key. Absent => "0" => dark.
FLAG_KEY = "cdc_listener_enabled"

# How often the loop re-reads the kill switch. The flag is how an operator turns this OFF
# without a deploy, so it must be re-read on a schedule -- but not on every wakeup, because
# each read is a fresh connection + admin-GUC round trip.
_FLAG_POLL_SECONDS = 30.0

# How long select() blocks before waking to re-check the flag and the stop event. Bounded so
# a disabled or stopping listener reacts promptly instead of sitting in the kernel.
_SELECT_TIMEOUT = 5.0

# Reconnect backoff. Capped so a long outage does not stretch to an unbounded retry gap.
_BACKOFF_START = 1.0
_BACKOFF_MAX = 60.0

# After this many CONSECUTIVE failed connects, raise one admin alert. Not on the first
# failure: a single reconnect during a Render deploy or a free-tier sleep is normal and
# alerting on it would train the reader to ignore the alert.
_ALERT_AFTER_CONSECUTIVE_FAILURES = 5

_lock = threading.Lock()
_thread = None
_stop = threading.Event()

# THE PID THAT OWNS `_thread`.
#
# This is the fix for the fault the first dark deploy exposed, and it is worth stating plainly
# because the evidence was initially misread. Live status showed `loop_entered: true` (a thread
# really did enter the loop) with `loop_exit: null` and `loop_exited_at: null` (its `finally`
# NEVER ran) and no `cdc-listener` in `threading.enumerate()`. A thread cannot both fail to
# unwind and be absent -- unless the PROCESS was forked: the child inherits all of memory (so
# `loop_entered` and `started_at` survive, and `_thread` is a stale Thread object whose
# is_alive() is False) but inherits NO threads, so the `finally` never runs anywhere.
#
# I could not find the forker -- no gunicorn.conf.py, no --preload in the live start command,
# nothing in this codebase calls os.fork. That question is left open ON PURPOSE, because the
# fix must not depend on the answer: whether it is fork, a preload path, or gunicorn recycling
# a worker, the requirement is the same -- THE PROCESS THAT SERVES REQUESTS MUST HAVE ITS OWN
# LISTENER, and it must notice by itself when it does not.
#
# Comparing the recorded pid against os.getpid() is the canonical fork detector: after a fork
# the child's pid differs, which is true even when the inherited Thread object still LOOKS
# plausible. Relying on is_alive() alone would be subtler and would miss a child that inherited
# a Thread object still marked alive.
_owner_pid = None

# Dependencies captured by start(), so ensure_running() can respawn without them being passed
# again from the request path.
_deps = {}

# Respawn rate limit. If starting the thread keeps failing (memory pressure), retrying on
# EVERY request would turn a degraded feature into a busy loop on the request path.
_RESPAWN_MIN_INTERVAL = 30.0
_last_spawn_attempt = 0.0

# Observability. THIS IS NOT OPTIONAL DECORATION: Render's free tier hides runtime logs, so
# without a readable status a dead listener is indistinguishable from an idle one -- the exact
# silent failure this project keeps getting bitten by. Surfaced through the authenticated
# drain endpoint so no new public surface is added.
_state = {
    "supported": None,      # False when not Postgres / psycopg2 missing
    "enabled": None,        # last value of the kill switch
    "thread_alive": False,
    "connected": False,
    "notifications": 0,     # pg_notify messages received
    "invalidations": 0,     # times the cache was actually cleared
    "reconnects": 0,
    "consecutive_failures": 0,
    "last_error": "",
    "last_event_at": None,  # epoch seconds
    "started_at": None,
    # Set by the _loop wrapper. Distinguishes "never ran" from "ran and died", which the
    # first dark deploy could not tell apart.
    "loop_entered": False,
    "loop_exit": None,          # None=still running | "clean" | "died"
    "loop_exited_at": None,
    # Bumped by ensure_running() when it finds this process has no live listener -- e.g.
    # after a fork. A steadily climbing value means something is repeatedly killing it.
    "respawns": 0,
}


def status():
    """A snapshot of the listener's state. Never raises.

    NOT A CONSISTENT SNAPSHOT, deliberately (Codex LOW, 2026-07-19). The loop mutates
    `_state` without a lock, so fields here can come from marginally different instants.
    That is accepted rather than fixed: this is diagnostics, individual assignments are
    atomic under CPython so nothing can be corrupted or half-written, and taking a lock on
    every counter bump in the hot path would cost more than the inconsistency does. Read
    these numbers as "roughly now", not as a transaction.
    """
    try:
        snap = dict(_state)
        snap["thread_alive"] = bool(_thread is not None and _thread.is_alive())
        # DIAGNOSTICS, added 2026-07-20 after the first dark deploy reported started_at set,
        # last_error empty, enabled null and thread_alive false -- i.e. the thread started and
        # then vanished without ever reading the flag. Two hypotheses (fork, double-start)
        # were both wrong on inspection, so these report the two facts that distinguish every
        # remaining one instead of guessing a third time:
        #   stop_set  -- was the loop's exit condition already true when it first checked?
        #   threads   -- is a cdc-listener thread present in THIS process at all? (which also
        #                shows whether the process serving this request is the one that ran
        #                start(), and whether gunicorn recycled the worker underneath us)
        snap["stop_set"] = bool(_stop.is_set())
        snap["threads"] = sorted(t.name for t in threading.enumerate() if t.is_alive())
        snap["pid"] = os.getpid()
        return snap
    except Exception:                                  # pragma: no cover - paranoia
        return {"error": "status unavailable"}


def _is_postgres():
    """Matches get_db()'s detection exactly -- `sqlite:///...` is NOT Postgres."""
    return (os.environ.get("DATABASE_URL") or "").startswith(
        ("postgres://", "postgresql://"))


def _psycopg2_available():
    """Is the driver importable in this process?

    A named helper rather than an inline try/import so tests can substitute it: psycopg2 is
    NOT installed on the Windows dev box, so without this seam every test of the thread's
    behaviour would exit early at the import check and silently assert nothing.
    """
    try:
        import psycopg2  # noqa: F401
        return True
    except Exception:                                  # noqa: BLE001
        return False


def _dsn():
    """The listener opens its OWN psycopg2 connection rather than using
    db_adapter.open_postgres().

    Not a duplication for its own sake: `_PgConnAdapter` exposes no passthrough to the raw
    connection, so `.poll()` and `.notifies` -- the entire notification API -- are unreachable
    through it. The URL normalisation, PGSSLMODE default and connect_timeout below mirror
    open_postgres deliberately so the two cannot drift apart in how they reach the server.
    """
    url = os.environ.get("DATABASE_URL") or ""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def _connect():
    """Open an autocommit connection and LISTEN. Raises on failure -- the caller retries."""
    import psycopg2
    from psycopg2 import extensions

    raw = os.environ.get("PG_CONNECT_TIMEOUT")
    try:
        timeout = int(float(raw)) if raw else 10
    except (TypeError, ValueError, OverflowError):
        timeout = 10
    if timeout < 2:                     # libpq reads 0 as "wait forever"
        timeout = 10

    conn = psycopg2.connect(
        _dsn(),
        sslmode=os.environ.get("PGSSLMODE", "require"),
        connect_timeout=timeout,
    )

    # EVERYTHING AFTER connect() IS INSIDE try/except THAT CLOSES conn (Codex MEDIUM,
    # 2026-07-19). The caller only assigns its own `conn` when this function RETURNS, so its
    # `finally` cannot clean up a connection that was opened here and then abandoned by a
    # raise in set_isolation_level / cursor / execute. Every such raise would leak one socket,
    # and this runs in a reconnect loop -- so a persistent fault would leak one connection per
    # backoff cycle until the server's 103 slots were gone.
    try:
        # LISTEN only delivers outside a transaction block. Without autocommit psycopg2 opens
        # an implicit transaction on the first execute and notifications would never arrive --
        # and an idle-in-transaction connection also pins resources on a free-tier server.
        conn.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        try:
            cur.execute("LISTEN " + _CHANNEL + ";")
        finally:
            cur.close()
        return conn
    except Exception:
        try:
            conn.close()
        except Exception:                              # noqa: BLE001
            pass
        raise


def _loop(flag_is_on, invalidate, notify_admin):
    """Thread entry point. Records WHY the loop ever stops.

    Added 2026-07-20 because the dark deploy produced a thread that started
    (`started_at` set, `last_error` empty) and then vanished before its first statement --
    `stop_set` false and no `cdc-listener` in the live thread list. The loop below is written
    not to raise, so something was escaping it, and Python prints unhandled THREAD exceptions
    to stderr, which Render's free tier HIDES. So the death is captured here instead of being
    inferred: `except BaseException` because whatever escaped was evidently not caught by the
    inner `except Exception`.

    This wrapper is the difference between "the thread is gone" and "the thread is gone
    BECAUSE x". Only the latter is actionable.
    """
    _state["loop_entered"] = True
    try:
        _loop_body(flag_is_on, invalidate, notify_admin)
        _state["loop_exit"] = "clean"
    except BaseException as e:                         # noqa: BLE001 - see docstring
        _state["loop_exit"] = "died"
        _state["last_error"] = (
            "loop died: %s: %s" % (type(e).__name__, e))[:300]
        _log.error("cdc listener loop died: %s: %s", type(e).__name__, e)
    finally:
        _state["loop_exited_at"] = time.time()
        _state["connected"] = False


def _loop_body(flag_is_on, invalidate, notify_admin):
    """The listener. Runs until _stop is set. Must never raise out of this frame."""
    backoff = _BACKOFF_START
    last_flag_check = 0.0
    enabled = False

    while not _stop.is_set():
        now = time.monotonic()
        if (now - last_flag_check) >= _FLAG_POLL_SECONDS:
            enabled = flag_is_on()
            _state["enabled"] = enabled
            last_flag_check = now

        if not enabled:
            # Dark. Hold no connection at all while switched off -- an idle connection kept
            # "just in case" is exactly the free-tier resource this is trying to be careful
            # with, and it would make the kill switch a half-measure.
            _state["connected"] = False
            _stop.wait(_FLAG_POLL_SECONDS)
            continue

        conn = None
        try:
            # RE-READ THE SWITCH IMMEDIATELY BEFORE CONNECTING (Codex MEDIUM, 2026-07-19).
            # `enabled` above can be up to _FLAG_POLL_SECONDS stale, and the backoff wait at
            # the bottom of this loop can be a further 60s. Without this check, an operator
            # who flips the switch OFF during a reconnect backoff would watch the listener
            # open a connection anyway -- which contradicts the promise that it holds no
            # connection while switched off, and makes the kill switch feel unreliable at
            # exactly the moment someone is reaching for it.
            enabled = flag_is_on()
            _state["enabled"] = enabled
            last_flag_check = time.monotonic()
            if not enabled:
                continue

            conn = _connect()
            _state["connected"] = True
            _state["consecutive_failures"] = 0
            backoff = _BACKOFF_START

            while not _stop.is_set():
                # Bounded wait, so the flag and stop event are still checked while idle.
                try:
                    ready = select.select([conn], [], [], _SELECT_TIMEOUT)[0]
                except (OSError, ValueError) as e:
                    # Socket died under us -> reconnect. RECORDED, not silent (Codex LOW,
                    # 2026-07-19): this is a genuine reconnect path, and leaving it out of
                    # the counters would make status() under-report exactly the churn an
                    # operator is looking for -- on a free tier that hides runtime logs,
                    # status() is the only window there is.
                    _state["reconnects"] += 1
                    _state["last_error"] = ("select: " + str(e))[:200]
                    break

                if (time.monotonic() - last_flag_check) >= _FLAG_POLL_SECONDS:
                    enabled = flag_is_on()
                    _state["enabled"] = enabled
                    last_flag_check = time.monotonic()
                    if not enabled:
                        break                   # switched off -> drop the connection

                if not ready:
                    continue

                conn.poll()

                # COALESCE. A bulk catalogue sweep delivers hundreds of notifications; the
                # response to all of them is the same single clear(), so drain the queue
                # first and invalidate ONCE. Clearing per message would be correct but
                # wasteful, and would inflate the counter into something unreadable.
                count = 0
                while conn.notifies:
                    conn.notifies.pop(0)
                    count += 1

                if count:
                    _state["notifications"] += count
                    _state["last_event_at"] = time.time()
                    try:
                        invalidate()
                        _state["invalidations"] += 1
                    except Exception as e:      # noqa: BLE001
                        # A failed invalidation is bounded by the cache TTL; it must not kill
                        # the listener, or one bad clear would stop all future ones.
                        _state["last_error"] = ("invalidate: " + str(e))[:200]
                        _log.warning("cdc listener: invalidate failed: %s", e)

        except Exception as e:                  # noqa: BLE001 -- the loop must survive
            _state["connected"] = False
            _state["reconnects"] += 1
            _state["consecutive_failures"] += 1
            _state["last_error"] = str(e)[:200]
            _log.warning("cdc listener: connection failed (%s), retrying",
                         type(e).__name__)

            # Alert only once the failures look persistent, and fingerprint it so a long
            # outage does not flood the inbox.
            if _state["consecutive_failures"] == _ALERT_AFTER_CONSECUTIVE_FAILURES:
                try:
                    if notify_admin is not None:
                        notify_admin(
                            "cdc", "warning",
                            "CDC listener cannot reach the database",
                            "%d consecutive connection failures. Marketplace cache "
                            "invalidation is not broadcasting; staleness is bounded by the "
                            "60s cache TTL, so this is degraded, not broken."
                            % _state["consecutive_failures"],
                            fingerprint="cdc_listener_down",
                            dedupe_minutes=180,
                        )
                except Exception:               # noqa: BLE001
                    pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:               # noqa: BLE001
                    pass
            _state["connected"] = False

        if _stop.is_set():
            break

        if enabled:
            # Jitter so that several workers (should the worker count ever rise) do not
            # reconnect in lockstep and hammer the server at the same instant.
            _stop.wait(backoff + random.uniform(0, backoff * 0.25))
            backoff = min(backoff * 2, _BACKOFF_MAX)

    _state["connected"] = False


def _spawn_locked():
    """Create and start the listener thread. Caller MUST hold _lock. Never raises."""
    global _thread, _owner_pid, _last_spawn_attempt

    _last_spawn_attempt = time.monotonic()

    def _flag_is_on():
        try:
            return _deps["read_flag"](_deps["get_db"], FLAG_KEY, "0").strip() == "1"
        except Exception:                            # noqa: BLE001
            return False                             # FAIL CLOSED

    # Reset the per-thread diagnostics so the NEW thread's fate is readable rather than
    # showing the previous (or inherited) thread's.
    _state["loop_entered"] = False
    _state["loop_exit"] = None
    _state["loop_exited_at"] = None

    _stop.clear()
    try:
        # Creating or starting a Thread can itself raise -- see the module docstring.
        t = threading.Thread(
            target=_loop,
            args=(_flag_is_on, _deps.get("invalidate"), _deps.get("notify_admin")),
            name="cdc-listener",
            daemon=True,                             # must never hold up interpreter shutdown
        )
        t.start()
    except Exception as e:                           # noqa: BLE001
        _state["last_error"] = ("spawn: " + str(e))[:200]
        _log.error("cdc listener could not be spawned (app still serving): %s", e)
        return

    _thread = t
    _owner_pid = os.getpid()
    _state["started_at"] = time.time()


def ensure_running():
    """Make sure THIS process has a live listener. Cheap. Never raises.

    Called from a before_request hook, so it runs on the request path and its fast path must
    cost almost nothing: two comparisons and an is_alive() flag read, no I/O, no lock.

    This is what actually makes the listener work. Starting a thread at import is not enough --
    the process that imported the module is demonstrably not always the process that ends up
    serving requests (see the _owner_pid note above). Rather than depend on a particular
    gunicorn topology, the serving process notices it has no listener and starts one.
    """
    try:
        if (_thread is not None
                and _owner_pid == os.getpid()
                and _thread.is_alive()):
            return                                   # fast path: the overwhelmingly common one

        if _state.get("supported") is False:
            return                                   # SQLite / no driver: nothing to run

        # Rate-limited, because a persistently failing spawn must not be retried per request.
        if (time.monotonic() - _last_spawn_attempt) < _RESPAWN_MIN_INTERVAL:
            return

        with _lock:
            # Re-check under the lock: several request threads can arrive here together
            # (gthread runs 4), and without this they would each spawn a listener.
            if (_thread is not None
                    and _owner_pid == os.getpid()
                    and _thread.is_alive()):
                return
            if (time.monotonic() - _last_spawn_attempt) < _RESPAWN_MIN_INTERVAL:
                return
            _state["respawns"] = _state.get("respawns", 0) + 1
            _spawn_locked()
    except Exception as e:                           # noqa: BLE001
        # This runs on the request path. It must never turn a listener problem into a 500.
        try:
            _state["last_error"] = ("ensure: " + str(e))[:200]
        except Exception:                            # noqa: BLE001
            pass


def start(get_db=None, invalidate=None, notify_admin=None, read_flag=None):
    """Register the listener's dependencies and start it. NEVER RAISES. Returns status.

    Called from wsgi.py at import. Every failure path degrades the FEATURE and leaves the app
    serving, because an exception escaping this call would stop gunicorn binding $PORT --
    which is how the 2026-07-09 Postgres expiry became a total outage.

    NOTE THAT STARTING HERE IS NO LONGER LOAD-BEARING. The thread it starts may not survive
    into the process that serves requests (see the _owner_pid note above), so the guarantee
    comes from ensure_running() on the request path instead. What this call is genuinely for
    is capturing the DEPENDENCIES, which are only available at import: ensure_running() is
    called from a before_request hook that has no way to supply them.
    """
    try:
        if not _is_postgres():
            # SQLite has no LISTEN/NOTIFY. Nothing to do, and saying so is better than a
            # thread that wakes forever to discover the same thing.
            _state["supported"] = False
            _state["last_error"] = "not postgres"
            return status()

        if not _psycopg2_available():
            _state["supported"] = False
            _state["last_error"] = "psycopg2 unavailable"
            return status()

        _state["supported"] = True
        _deps["get_db"] = get_db
        _deps["invalidate"] = invalidate
        _deps["notify_admin"] = notify_admin
        _deps["read_flag"] = read_flag

        with _lock:
            if (_thread is not None
                    and _owner_pid == os.getpid()
                    and _thread.is_alive()):
                # Single-start guard, now pid-aware. web_app._monitor_thread has no guard at
                # all and is safe only by accident of --workers 1; a second listener would
                # mean a second permanent connection and duplicated invalidations.
                return status()
            _spawn_locked()
        return status()

    except Exception as e:                       # noqa: BLE001 - see docstring
        _state["last_error"] = ("start: " + str(e))[:200]
        _log.error("cdc listener failed to start (app still serving): %s", e)
        return status()


def stop(timeout=2.0):
    """Signal the loop to exit. Used by tests; never raises."""
    try:
        _stop.set()
        t = _thread
        if t is not None and t.is_alive():
            t.join(timeout)
    except Exception:                            # noqa: BLE001
        pass
