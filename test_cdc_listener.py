"""Tests for the CDC pg_notify listener (slice 4).

WHAT THESE PROVE. There is no local Postgres (no psycopg2, no Docker, no psql), so nothing
here exercises a real LISTEN. What they DO pin is everything that could hurt: that the module
ships dark, that the kill switch fails closed, that `start()` cannot raise no matter how badly
its dependencies misbehave, and that it refuses to start twice. Those are the properties that
matter for a background thread holding a permanent database connection -- the notification
plumbing itself is proven live, in the dark-then-enable rollout.

Run: python -m pytest test_cdc_listener.py -q
"""
import os
import threading
import time

import pytest

import cdc_listener


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Each test gets a clean module state and a stopped thread.

    psycopg2 is NOT installed on this dev box, so `_psycopg2_available` is stubbed True by
    default -- otherwise start() would bail at the driver check and every behavioural test
    below would pass while asserting nothing. The tests that care about the driver being
    ABSENT override it themselves.
    """
    monkeypatch.setattr(cdc_listener, "_psycopg2_available", lambda: True)
    cdc_listener.stop()
    cdc_listener._thread = None
    cdc_listener._owner_pid = None
    cdc_listener._last_spawn_attempt = 0.0
    cdc_listener._deps.clear()
    cdc_listener._stop.clear()
    for k, v in {
        "supported": None, "enabled": None, "connected": False,
        "notifications": 0, "invalidations": 0, "reconnects": 0,
        "consecutive_failures": 0, "last_error": "", "last_event_at": None,
        "started_at": None,
    }.items():
        cdc_listener._state[k] = v
    yield
    cdc_listener.stop()
    cdc_listener._thread = None


# ── It must not run where it cannot work ─────────────────────────────────────────────────

def test_sqlite_is_unsupported_and_starts_no_thread(monkeypatch):
    """SQLite has no LISTEN/NOTIFY. Saying so beats a thread that wakes forever to rediscover
    the same fact."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///solar.db")
    st = cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "1")
    assert st["supported"] is False
    assert cdc_listener._thread is None


def test_unset_database_url_is_unsupported(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    st = cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "1")
    assert st["supported"] is False


# ── start() must NEVER raise: an exception here stops gunicorn binding $PORT ─────────────

def test_start_never_raises_even_if_every_dependency_explodes(monkeypatch):
    """boot_state's contract: nothing on the import path may raise. A broken listener must
    degrade to 'feature missing', never to 'site down'."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")

    def _boom(*a, **k):
        raise RuntimeError("everything is on fire")

    monkeypatch.setattr(threading, "Thread", _boom)
    st = cdc_listener.start(get_db=_boom, invalidate=_boom, read_flag=_boom)
    assert "start:" in st["last_error"] or st["last_error"]


def test_start_survives_thread_start_failure(monkeypatch):
    """`RuntimeError: can't start new thread` is a real outcome on a 512MB instance."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")

    class _DeadThread:
        def __init__(self, *a, **k):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

        def is_alive(self):
            return False

    monkeypatch.setattr(threading, "Thread", _DeadThread)
    st = cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "0")
    assert st["last_error"]          # recorded, not raised


# ── The kill switch ──────────────────────────────────────────────────────────────────────

def test_flag_defaults_to_off_and_holds_no_connection(monkeypatch):
    """Dark by default. While off it must hold NO connection -- an idle one kept 'just in
    case' would make the kill switch a half-measure on a free-tier server."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    connects = []
    monkeypatch.setattr(cdc_listener, "_connect",
                        lambda: connects.append(1) or (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)

    cdc_listener.start(get_db=None, invalidate=None,
                       read_flag=lambda *a, **k: "0")     # OFF
    time.sleep(0.25)

    assert connects == []
    assert cdc_listener._state["connected"] is False


def test_a_raising_flag_read_fails_CLOSED(monkeypatch):
    """Any error reading the switch must leave the module dark, never light it up."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    connects = []
    monkeypatch.setattr(cdc_listener, "_connect",
                        lambda: connects.append(1) or (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)

    def _broken_flag(*a, **k):
        raise RuntimeError("admin_settings unreachable")

    cdc_listener.start(get_db=None, invalidate=None, read_flag=_broken_flag)
    time.sleep(0.25)

    assert connects == []
    assert cdc_listener._state["enabled"] is False


def test_a_non_1_flag_value_is_off(monkeypatch):
    """Only "1" enables. "true"/"yes"/"" must not."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    for value in ("0", "", "true", "yes", "on", "enabled"):
        cdc_listener._state["enabled"] = None
        connects = []
        monkeypatch.setattr(
            cdc_listener, "_connect",
            lambda: connects.append(1) or (_ for _ in ()).throw(AssertionError))
        monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)
        cdc_listener.stop()
        cdc_listener._thread = None
        cdc_listener._stop.clear()
        cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: value)
        time.sleep(0.15)
        assert connects == [], "flag value %r must not enable the listener" % value
        cdc_listener.stop()


def test_flag_flipped_off_during_backoff_prevents_the_next_connect(monkeypatch):
    """REGRESSION FOR THE KILL-SWITCH RACE (Codex MEDIUM, 2026-07-19).

    `enabled` can be up to _FLAG_POLL_SECONDS stale, and a reconnect backoff adds up to 60s
    more. Before the fix, an operator flipping the switch OFF during a backoff would watch
    the listener open a connection anyway. The switch must be re-read immediately before
    every connect.

    Here the first connect fails (starting a backoff) and the flag goes off in the meantime;
    there must never be a second connect.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 30.0)   # deliberately stale
    monkeypatch.setattr(cdc_listener, "_BACKOFF_START", 0.05)

    attempts = []

    def _failing_connect():
        attempts.append(1)
        raise RuntimeError("server unreachable")

    monkeypatch.setattr(cdc_listener, "_connect", _failing_connect)

    flag = {"value": "1"}
    monkeypatch.setattr(cdc_listener, "_ALERT_AFTER_CONSECUTIVE_FAILURES", 10 ** 6)

    cdc_listener.start(get_db=None, invalidate=None,
                       read_flag=lambda *a, **k: flag["value"])

    # Let exactly one connect attempt happen, then switch off during the backoff.
    time.sleep(0.12)
    flag["value"] = "0"
    before = len(attempts)
    time.sleep(0.5)

    assert before >= 1, "expected at least one connect attempt while enabled"
    assert len(attempts) == before, (
        "listener connected again after the switch was turned off during backoff")


# ── Single-start guard (which web_app._monitor_thread does NOT have) ─────────────────────

def test_start_twice_does_not_create_a_second_thread(monkeypatch):
    """A second listener would mean a second permanent connection and duplicated
    invalidations."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)

    cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "0")
    first = cdc_listener._thread
    cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "0")
    second = cdc_listener._thread

    assert first is second
    # Count the listener threads BY NAME (Codex LOW, 2026-07-19). The earlier assertion was
    # `threading.active_count() >= 1`, which is true of any Python process that ever ran --
    # it would have passed with no listener at all, or with five of them.
    listeners = [t for t in threading.enumerate() if t.name == "cdc-listener" and t.is_alive()]
    assert len(listeners) == 1


# ── The thread must be a daemon, or it holds up interpreter shutdown ─────────────────────

def test_listener_thread_is_a_daemon(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)
    cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "0")
    assert cdc_listener._thread.daemon is True


# ── status() is the only window into this thing on a free tier that hides logs ───────────

def test_status_never_raises_and_reports_liveness(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)
    cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "0")
    st = cdc_listener.status()
    assert st["thread_alive"] is True
    assert st["supported"] is True
    for key in ("notifications", "invalidations", "reconnects", "connected", "enabled"):
        assert key in st


def test_channel_matches_migration_036():
    """cdc_capture() does `pg_notify('cdc', ...)`. A mismatch here would be a listener that
    works perfectly and hears nothing."""
    assert cdc_listener._CHANNEL == "cdc"


def test_missing_psycopg2_is_unsupported_and_starts_no_thread(monkeypatch):
    """The driver really is absent on the dev box; this pins the behaviour rather than
    letting it silently short-circuit the rest of the suite."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setattr(cdc_listener, "_psycopg2_available", lambda: False)
    st = cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "1")
    assert st["supported"] is False
    assert st["last_error"] == "psycopg2 unavailable"
    assert cdc_listener._thread is None


# ── ensure_running(): the actual fix for the fork problem ────────────────────────────────

def test_ensure_running_respawns_when_the_pid_changed(monkeypatch):
    """THE REGRESSION TEST FOR THE SLICE-4 FAULT (2026-07-20).

    Live status showed loop_entered=true with loop_exit=null and no cdc-listener thread: the
    process had been forked after import, inheriting the module's MEMORY (so `_thread` looked
    plausible) but none of its THREADS. A pid comparison is the one check a forked child
    cannot pass by accident.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)
    cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "0")
    first = cdc_listener._thread
    assert first is not None

    # Simulate being the forked CHILD: same module state, different pid.
    monkeypatch.setattr(cdc_listener, "_owner_pid", cdc_listener._owner_pid + 1)
    cdc_listener._last_spawn_attempt = 0.0          # bypass the rate limit for the test

    cdc_listener.ensure_running()

    assert cdc_listener._thread is not first, "a forked child must spawn its OWN listener"
    assert cdc_listener._thread.is_alive()
    assert cdc_listener._owner_pid == os.getpid()


def test_ensure_running_is_a_noop_when_the_listener_is_healthy(monkeypatch):
    """It runs on EVERY request, so the common path must not respawn or take the lock."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setattr(cdc_listener, "_FLAG_POLL_SECONDS", 0.05)
    cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "0")
    first = cdc_listener._thread
    before = cdc_listener._state.get("respawns", 0)

    for _ in range(50):
        cdc_listener.ensure_running()

    assert cdc_listener._thread is first
    assert cdc_listener._state.get("respawns", 0) == before


def test_ensure_running_rate_limits_a_failing_spawn(monkeypatch):
    """A spawn that keeps failing must not be retried on every request."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    cdc_listener._state["supported"] = True
    cdc_listener._deps.update({"get_db": None, "read_flag": lambda *a, **k: "0",
                               "invalidate": None, "notify_admin": None})
    cdc_listener._thread = None
    cdc_listener._owner_pid = None
    cdc_listener._last_spawn_attempt = 0.0

    attempts = []

    class _DeadThread:
        def __init__(self, *a, **k):
            attempts.append(1)

        def start(self):
            raise RuntimeError("can't start new thread")

        def is_alive(self):
            return False

    monkeypatch.setattr(threading, "Thread", _DeadThread)

    for _ in range(20):
        cdc_listener.ensure_running()

    assert len(attempts) == 1, "a failing spawn must be rate-limited, not retried per request"


def test_ensure_running_never_raises_into_the_request_path(monkeypatch):
    """It is a before_request hook: a listener fault must never become a 500."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    cdc_listener._state["supported"] = True
    cdc_listener._thread = None
    cdc_listener._owner_pid = None
    cdc_listener._last_spawn_attempt = 0.0

    def _boom(*a, **k):
        raise RuntimeError("everything is on fire")

    monkeypatch.setattr(cdc_listener, "_spawn_locked", _boom)
    cdc_listener.ensure_running()          # must not raise


def test_ensure_running_does_nothing_when_unsupported(monkeypatch):
    """On SQLite there is nothing to run; the hook must not spawn on every request."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///solar.db")
    cdc_listener.start(get_db=None, invalidate=None, read_flag=lambda *a, **k: "1")
    assert cdc_listener._state["supported"] is False
    cdc_listener._last_spawn_attempt = 0.0
    cdc_listener.ensure_running()
    assert cdc_listener._thread is None
