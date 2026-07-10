"""Boot resilience: the process must outlive the database.

Regression tests for the 2026-07-09 outage, where init_db() raised at import,
gunicorn never bound $PORT, and Render restart-looped the service forever.

The tests cover BOTH ways a database can fail a boot:
  * it raises quickly (suspended host, DNS failure)
  * it hangs (blackholed TCP connect, stalled server)

and assert that a request to /api/ping is never blocked behind a retry, because
Render restarts an instance after 60s of failing health checks.
"""

import threading
import time

import pytest
from flask import Flask

import boot_state


@pytest.fixture(autouse=True)
def _reset_boot_state():
    """Give each test a pristine module state.

    Tests that park a worker thread inside init_db() must release it themselves
    and join, via the `hang` fixture below. This fixture never force-clears
    bookkeeping out from under a live thread -- that thread would later
    decrement `inflight` belonging to the *next* test, or mark it ready.
    """
    original = (
        boot_state.BOOT_TIMEOUT_SECONDS,
        boot_state.RETRY_INTERVAL_SECONDS,
        boot_state.STUCK_ATTEMPT_SECONDS,
    )
    boot_state._state.update({
        "ready": False, "attempts": 0, "last_attempt": 0.0,
        "last_error": None, "ready_since": None,
        "inflight": 0, "inflight_since": 0.0,
    })
    boot_state._ready_fast = False
    yield
    (boot_state.BOOT_TIMEOUT_SECONDS,
     boot_state.RETRY_INTERVAL_SECONDS,
     boot_state.STUCK_ATTEMPT_SECONDS) = original
    assert boot_state.snapshot()["inflight"] == 0, (
        "a test left an init thread in flight; it will corrupt the next test"
    )


class _Hang:
    """An init_db() that blocks until released, tracking its threads."""

    def __init__(self):
        self.release = threading.Event()
        self.entered = threading.Semaphore(0)
        self.concurrent = 0
        self._lock = threading.Lock()
        self.max_concurrent = 0

    def __call__(self):
        with self._lock:
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        self.entered.release()
        try:
            assert self.release.wait(30), "hang fixture never released"
        finally:
            with self._lock:
                self.concurrent -= 1

    def wait_until_entered(self, timeout=5):
        assert self.entered.acquire(timeout=timeout), "init_db() never started"

    def finish(self):
        self.release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if boot_state.snapshot()["inflight"] == 0:
                return
            time.sleep(0.01)
        raise AssertionError("init threads did not unwind")


@pytest.fixture
def hang():
    h = _Hang()
    yield h
    h.finish()


def _app():
    app = Flask(__name__)

    @app.route("/api/ping")
    def ping():
        return {"pong": True}

    return app


def test_healthy_boot_is_ready_at_import():
    """A working database must behave exactly as before the change."""
    calls = []
    app = boot_state.attach(_app(), lambda: calls.append(1))

    assert boot_state.is_ready() is True
    assert calls == [1]
    assert app.test_client().get("/api/health/boot").status_code == 200


def test_raising_init_does_not_kill_the_process():
    """The original outage: init_db() raises. Import must survive."""
    def boom():
        raise RuntimeError("could not translate host name")

    app = boot_state.attach(_app(), boom)          # must not raise

    assert boot_state.is_ready() is False
    assert app.test_client().get("/api/ping").status_code == 200

    body = app.test_client().get("/api/health/boot").get_json()
    assert body["status"] == "degraded"
    assert "could not translate host name" in body["last_error"]


def test_hanging_init_does_not_stall_the_bind(hang):
    """A database that HANGS must not hold the port hostage.

    An exception is fast; a blackholed connect is not. attach() must give up
    waiting after BOOT_TIMEOUT_SECONDS and let gunicorn bind.
    """
    boot_state.BOOT_TIMEOUT_SECONDS = 0.3

    started = time.monotonic()
    boot_state.attach(_app(), hang)
    elapsed = time.monotonic() - started

    assert elapsed < 3.0, "attach() blocked for %.1fs; gunicorn would not bind" % elapsed
    assert boot_state.is_ready() is False
    assert boot_state.snapshot()["initializing"] is True


def test_ping_is_not_blocked_while_init_hangs(hang):
    """The health check must stay fast while a retry is stuck.

    If /api/ping waited on the init attempt, Render would restart the instance
    after 60s of failures -- the exact loop this module prevents.
    """
    boot_state.BOOT_TIMEOUT_SECONDS = 0.2

    app = boot_state.attach(_app(), hang)
    hang.wait_until_entered()

    started = time.monotonic()
    response = app.test_client().get("/api/ping")
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert elapsed < 1.0, "/api/ping blocked %.2fs behind a hung init" % elapsed


def test_retry_is_single_flight_while_an_attempt_is_healthy(hang):
    """Concurrent requests must not pile up parallel init_db() calls."""
    boot_state.BOOT_TIMEOUT_SECONDS = 0.1
    boot_state.RETRY_INTERVAL_SECONDS = 0.0
    boot_state.STUCK_ATTEMPT_SECONDS = 60.0   # nothing is stuck yet

    app = boot_state.attach(_app(), hang)
    hang.wait_until_entered()

    client = app.test_client()
    for _ in range(10):
        client.get("/api/ping")

    assert hang.max_concurrent == 1, \
        "expected one in-flight init, saw %d" % hang.max_concurrent


def test_a_stuck_attempt_does_not_block_recovery_forever(hang):
    """Single-flight must not become single-forever.

    If an attempt hangs and holds the only in-flight slot, no later retry can
    run: the app binds its port, logs "will retry", and then never does --
    unable to heal even after the database returns. A stale attempt must be
    superseded after STUCK_ATTEMPT_SECONDS.
    """
    boot_state.BOOT_TIMEOUT_SECONDS = 0.1
    boot_state.RETRY_INTERVAL_SECONDS = 0.0
    boot_state.STUCK_ATTEMPT_SECONDS = 0.2    # the first attempt goes stale fast

    app = boot_state.attach(_app(), hang)
    hang.wait_until_entered()
    assert boot_state.snapshot()["attempts"] == 1

    time.sleep(0.3)                            # let the first attempt go stale
    app.test_client().get("/api/ping")         # ordinary traffic drives recovery

    hang.wait_until_entered()                  # a SECOND attempt actually ran
    snap = boot_state.snapshot()
    assert snap["attempts"] == 2, "stuck attempt suppressed the retry"
    assert snap["inflight"] == 2


def test_stuck_supersession_does_not_leak_a_thread_per_request(hang):
    """Superseding a stuck attempt must not spawn a thread on every request."""
    boot_state.BOOT_TIMEOUT_SECONDS = 0.1
    boot_state.RETRY_INTERVAL_SECONDS = 0.0
    boot_state.STUCK_ATTEMPT_SECONDS = 0.2

    app = boot_state.attach(_app(), hang)
    hang.wait_until_entered()

    time.sleep(0.3)
    client = app.test_client()
    started = time.monotonic()
    for _ in range(20):                        # a burst of traffic while stuck
        client.get("/api/ping")
    elapsed = time.monotonic() - started

    # One supersession, not twenty: the stuck window restarts on the new attempt.
    # The bound is derived from the wall clock rather than hard-coded to 2, so a
    # slow CI runner that genuinely crosses another stuck window does not flake.
    ceiling = 2 + int(elapsed / boot_state.STUCK_ATTEMPT_SECONDS) + 1
    attempts = boot_state.snapshot()["attempts"]
    assert attempts <= ceiling, \
        "spawned %d attempts in %.2fs; expected <= %d" % (attempts, elapsed, ceiling)
    assert attempts < 20, "spawned a thread per request (%d)" % attempts


def test_app_self_heals_when_the_database_returns():
    """Degraded -> ready without a redeploy, driven by ordinary traffic."""
    boot_state.RETRY_INTERVAL_SECONDS = 0.0
    state = {"up": False}

    def flaky():
        if not state["up"]:
            raise RuntimeError("database is suspended")

    app = boot_state.attach(_app(), flaky)
    assert boot_state.is_ready() is False

    state["up"] = True                     # the owner upgrades the plan
    client = app.test_client()
    for _ in range(50):                    # keep-warm ping drives recovery
        client.get("/api/ping")
        if boot_state.is_ready():
            break
        time.sleep(0.02)

    assert boot_state.is_ready() is True
    assert client.get("/api/health/boot").status_code == 200


def test_a_stale_attempt_cannot_resurrect_an_old_error():
    """Attempt 1 hangs, attempt 2 succeeds, then attempt 1 fails.

    The late failure must not overwrite last_error, or /api/health/boot would
    report database_ready:true beside a stale error.
    """
    boot_state.BOOT_TIMEOUT_SECONDS = 0.1
    boot_state.RETRY_INTERVAL_SECONDS = 0.0
    boot_state.STUCK_ATTEMPT_SECONDS = 0.2

    release_first = threading.Event()
    calls = {"n": 0}
    lock = threading.Lock()

    def flaky():
        with lock:
            calls["n"] += 1
            mine = calls["n"]
        if mine == 1:
            release_first.wait(10)            # hangs, then fails
            raise RuntimeError("stale connection reset")
        return                                # attempt 2 succeeds

    app = boot_state.attach(_app(), flaky)
    time.sleep(0.3)                            # first attempt goes stale
    app.test_client().get("/api/ping")         # attempt 2 runs and succeeds

    deadline = time.monotonic() + 5
    while not boot_state.is_ready() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert boot_state.is_ready() is True

    release_first.set()                        # now the stale attempt fails
    deadline = time.monotonic() + 5
    while boot_state.snapshot()["inflight"] and time.monotonic() < deadline:
        time.sleep(0.01)

    body = app.test_client().get("/api/health/boot").get_json()
    assert body["database_ready"] is True
    assert body["last_error"] is None, "a superseded attempt resurrected its error"
    assert body["ready_since"] is not None


def test_thread_start_failure_does_not_break_the_health_check(monkeypatch):
    """`RuntimeError: can't start new thread` must never escape start_attempt().

    start_attempt() runs from before_request on every request and from attach()
    at import. If it raised, /api/ping would 500, Render would restart the
    instance after 60s, and we would be back in the crash-loop this module
    exists to prevent.
    """
    def cannot_start(*args, **kwargs):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(boot_state.threading, "Thread", cannot_start)

    app = boot_state.attach(_app(), lambda: None)      # import must survive
    assert boot_state.is_ready() is False

    response = app.test_client().get("/api/ping")      # request must survive
    assert response.status_code == 200

    snap = boot_state.snapshot()
    assert snap["inflight"] == 0, "the reserved in-flight slot was leaked"
    assert "can't start new thread" in snap["last_error"]


def test_degraded_serves_503_not_a_schema_error(hang):
    """While degraded, DB-backed routes must say 'not ready', not crash.

    /api/ping and /api/health/boot stay available so Render keeps the instance
    alive and an operator can see why.
    """
    boot_state.BOOT_TIMEOUT_SECONDS = 0.1

    app = _app()

    @app.route("/dashboard")
    def dashboard():
        raise AssertionError("must not reach a DB-backed view while degraded")

    boot_state.attach(app, hang)
    client = app.test_client()

    response = client.get("/dashboard")
    assert response.status_code == 503
    assert response.headers.get("Retry-After")
    assert response.get_json()["error"] == "SERVICE_UNAVAILABLE"

    assert client.get("/api/ping").status_code == 200          # Render's check
    assert client.get("/api/health/boot").status_code == 503    # honest, and reachable


def test_gate_runs_before_other_before_request_hooks(hang):
    """Our gate must precede hooks that touch the database.

    web_app registers `_bump_last_seen`, which queries on every request. If our
    hook ran after it, each request during an outage would first burn the whole
    psycopg2 connect_timeout inside that hook.
    """
    boot_state.BOOT_TIMEOUT_SECONDS = 0.1
    app = _app()
    reached = []

    @app.before_request
    def _touches_the_database():          # registered BEFORE attach(), as web_app's are
        reached.append("db-hook")
        return None

    @app.route("/dashboard")
    def dashboard():
        return {"ok": True}

    boot_state.attach(app, hang)

    assert app.test_client().get("/dashboard").status_code == 503
    assert reached == [], "a DB-touching hook ran before the degraded gate"

    assert app.before_request_funcs[None][0].__name__ == "_ensure_db_ready"


def test_ready_app_does_not_gate_any_route():
    """The 503 gate must vanish entirely once the database is ready."""
    app = _app()

    @app.route("/dashboard")
    def dashboard():
        return {"ok": True}

    boot_state.attach(app, lambda: None)
    assert boot_state.is_ready() is True
    assert app.test_client().get("/dashboard").status_code == 200


def test_bad_env_value_does_not_crash_import():
    """This module protects boot; it must not be the thing that breaks it."""
    assert boot_state._env_float("NOPE_MISSING", 7.5) == 7.5

    import os
    bad = ["not-a-number", "-5", "nan", "inf", "-inf", ""]
    try:
        for value in bad:
            os.environ["BOOT_STATE_TEST_BAD"] = value
            assert boot_state._env_float("BOOT_STATE_TEST_BAD", 3.0) == 3.0, value
        # Zero is a parseable float with a pathological meaning: it would defeat
        # the retry throttle and the stuck window. A minimum rejects it.
        os.environ["BOOT_STATE_TEST_BAD"] = "0"
        assert boot_state._env_float("BOOT_STATE_TEST_BAD", 3.0, minimum=0.1) == 3.0
        assert boot_state._env_float("BOOT_STATE_TEST_BAD", 3.0) == 0.0  # allowed when no floor
    finally:
        os.environ.pop("BOOT_STATE_TEST_BAD", None)


def test_unrelated_paths_are_not_exempted_by_the_health_prefix(hang):
    """/api/healthcheck must NOT slip through the /api/health/ exemption."""
    boot_state.BOOT_TIMEOUT_SECONDS = 0.1
    app = _app()

    @app.route("/api/healthcheck")
    def healthcheck():
        return {"ok": True}

    boot_state.attach(app, hang)
    client = app.test_client()

    assert client.get("/api/healthcheck").status_code == 503   # gated
    assert client.get("/api/health/boot").status_code == 503    # exempt, reports degraded
    assert client.get("/api/ping").status_code == 200           # exempt, alive


def test_open_postgres_passes_the_connect_timeout(monkeypatch):
    """Lock in the production contract: normalised URL, sslmode, connect_timeout."""
    import db_adapter

    captured = {}

    class _FakePsycopg2:
        @staticmethod
        def connect(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return object()

    monkeypatch.setitem(__import__("sys").modules, "psycopg2", _FakePsycopg2)
    monkeypatch.setattr(db_adapter, "_PgConnAdapter", lambda raw: raw)
    monkeypatch.setenv("PG_CONNECT_TIMEOUT", "5")
    monkeypatch.setenv("PGSSLMODE", "require")

    db_adapter.open_postgres("postgres://u:p@host:5432/db")

    assert captured["url"] == "postgresql://u:p@host:5432/db", "legacy scheme not normalised"
    assert captured["sslmode"] == "require"
    assert captured["connect_timeout"] == 5, "an unreachable database must fail fast"


def test_connect_timeout_is_parsed_defensively():
    """db_adapter must never raise while parsing PG_CONNECT_TIMEOUT, and never
    yield 0 -- libpq reads 0 as 'wait forever', the hang we are bounding."""
    import os
    import db_adapter

    cases = {None: 10, "": 10, "abc": 10, "0": 10, "1": 10,
             "inf": 10, "nan": 10, "-3": 10, "2": 2, "30": 30, "7.9": 7}
    for value, expected in cases.items():
        if value is None:
            os.environ.pop("PG_CONNECT_TIMEOUT", None)
        else:
            os.environ["PG_CONNECT_TIMEOUT"] = value
        assert db_adapter._connect_timeout() == expected, "%r -> %r" % (value, expected)
    os.environ.pop("PG_CONNECT_TIMEOUT", None)
