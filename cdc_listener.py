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

WORKER TOPOLOGY. Render runs `--workers 1` with NO `--preload` (the latter is deliberate:
threads do not survive fork()). Because each worker imports independently, starting the thread
at import time is correct and it really does exist in the worker. One worker means one
listener connection today; the single-start guard below keeps that true if the worker count
ever rises, per process.

Unlike `web_app._monitor_thread` -- which starts unconditionally at import with NO
double-start guard and is safe only by accident of `--workers 1` -- this module refuses to
start twice in one process.
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


def start(get_db=None, invalidate=None, notify_admin=None, read_flag=None):
    """Start the listener thread. NEVER RAISES. Returns the status snapshot.

    Called from wsgi.py at import. Every failure path here degrades the FEATURE and leaves
    the app serving, because an exception escaping this call would stop gunicorn binding
    $PORT -- which is how the 2026-07-09 Postgres expiry became a total outage.
    """
    global _thread
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

        with _lock:
            if _thread is not None and _thread.is_alive():
                # Single-start guard. web_app._monitor_thread has none and is safe only by
                # accident of --workers 1; a second listener would mean a second permanent
                # connection and duplicated invalidations.
                return status()

            def _flag_is_on():
                try:
                    return read_flag(get_db, FLAG_KEY, "0").strip() == "1"
                except Exception:                # noqa: BLE001
                    return False                 # FAIL CLOSED

            _stop.clear()
            # Creating or starting a Thread can itself raise under memory pressure. Caught
            # here for the reason in this module's docstring.
            _thread = threading.Thread(
                target=_loop,
                args=(_flag_is_on, invalidate, notify_admin),
                name="cdc-listener",
                daemon=True,                     # must never hold up interpreter shutdown
            )
            _thread.start()
            _state["started_at"] = time.time()
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
