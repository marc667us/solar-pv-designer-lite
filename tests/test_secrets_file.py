"""Encrypted secrets at rest.

`.env` held the Flask SECRET_KEY, the Paystack secret, both admin passwords and the SMTP
password in PLAINTEXT. Gitignored is not the same as secure: anything that can read the disk
-- a backup, a synced folder, a shared machine, a support ZIP -- could read every secret the
app has. This repo leaked five live secrets into PUBLIC CI logs for 35 days on 2026-07-10, so
the threat model is not theoretical.

The single most important test here is `test_production_behaviour_is_unchanged`: a security
change that can take the live site down is not a security improvement.
"""

import os

import pytest

import secrets_file


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    """Every test gets its own key and store, and none of them touch the real files."""
    monkeypatch.setenv(secrets_file.MASTER_KEY_ENV, secrets_file.generate_key())
    monkeypatch.setenv(secrets_file.ENC_FILE_ENV, str(tmp_path / ".env.enc"))
    secrets_file.load(force=True)
    yield
    secrets_file._cache = None


def _write_env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text, encoding="utf-8")
    return str(p)


class TestTheFileIsActuallyOpaque:
    """The whole point. If a secret is readable in the ciphertext, nothing else matters."""

    def test_no_secret_appears_in_the_encrypted_file(self, tmp_path):
        secrets = {
            "SECRET_KEY": "2c8240aabbccddeeff00112233445566778899aa02da",
            "PAYSTACK_SECRET_KEY": "sk_test_deadbeefcafebabe0123456789",
            "SOLARPRO_ADMIN_PASSWORD": "fern-rustle-quiet-hardware",
            "SMTP_PASS": "npqPwMxxYYzz1234Wmwf",
        }
        src = _write_env(tmp_path, "\n".join(f"{k}={v}" for k, v in secrets.items()))
        out = secrets_file.encrypt_file(src)

        raw = open(out, "rb").read()
        for name, value in secrets.items():
            assert value.encode() not in raw, f"{name} is READABLE in the ciphertext"
        # Nor should the VALUES leak in any obvious encoding.
        import base64
        for value in secrets.values():
            assert base64.b64encode(value.encode()) not in raw

    def test_the_round_trip_is_lossless(self, tmp_path):
        src = _write_env(tmp_path, "A=one\nB=two\nC=three")
        secrets_file.encrypt_file(src)
        assert secrets_file.load(force=True) == {"A": "one", "B": "two", "C": "three"}

    def test_comments_and_blank_lines_are_not_parsed_as_secrets(self, tmp_path):
        """Renamed after Codex (Q8) pointed out the old name claimed something it never
        checked: it proved comments are IGNORED by the parser, not that they SURVIVE the
        round trip. Both matter, so both are asserted -- survival against the decrypted
        bytes, which is the only place it is observable.
        """
        text = "# a comment\n\nA=one\n\n# another\nB=two\n"
        src = _write_env(tmp_path, text)
        out = secrets_file.encrypt_file(src)

        assert secrets_file.load(force=True) == {"A": "one", "B": "two"}

        restored = secrets_file._fernet().decrypt(open(out, "rb").read()).decode("utf-8")
        assert restored == text, "the store must preserve the file byte for byte"
        assert "# a comment" in restored

    def test_quoted_values_are_unquoted(self, tmp_path):
        src = _write_env(tmp_path, 'A="quoted"\nB=\'single\'\nC=bare')
        secrets_file.encrypt_file(src)
        assert secrets_file.load(force=True) == {"A": "quoted", "B": "single", "C": "bare"}

    def test_a_value_containing_equals_is_not_truncated(self, tmp_path):
        """Base64 keys end in `=` padding. Splitting on every `=` would silently corrupt them
        -- and a corrupted secret fails at the provider, far from here.
        """
        src = _write_env(tmp_path, "KEY=abc==\nURL=postgres://u:p@host/db?x=1")
        secrets_file.encrypt_file(src)
        got = secrets_file.load(force=True)
        assert got["KEY"] == "abc=="
        assert got["URL"] == "postgres://u:p@host/db?x=1"


class TestFailureModes:

    def test_a_wrong_key_fails_loudly_rather_than_returning_garbage(self, tmp_path,
                                                                   monkeypatch):
        src = _write_env(tmp_path, "A=one")
        secrets_file.encrypt_file(src)
        monkeypatch.setenv(secrets_file.MASTER_KEY_ENV, secrets_file.generate_key())
        with pytest.raises(secrets_file.SecretsFileError):
            secrets_file.load(force=True)

    def test_a_tampered_file_is_rejected(self, tmp_path):
        """Fernet authenticates as well as encrypts. A truncated or edited store must not
        yield a half-parsed set of secrets -- partial secrets are worse than none.
        """
        src = _write_env(tmp_path, "A=one\nB=two")
        out = secrets_file.encrypt_file(src)
        blob = bytearray(open(out, "rb").read())
        blob[len(blob) // 2] ^= 0xFF          # flip one bit in the middle
        open(out, "wb").write(bytes(blob))
        with pytest.raises(secrets_file.SecretsFileError):
            secrets_file.load(force=True)

    def test_a_truncated_file_is_rejected(self, tmp_path):
        src = _write_env(tmp_path, "A=one\nB=two")
        out = secrets_file.encrypt_file(src)
        blob = open(out, "rb").read()
        open(out, "wb").write(blob[: len(blob) // 2])
        with pytest.raises(secrets_file.SecretsFileError):
            secrets_file.load(force=True)

    def test_no_key_and_no_store_is_not_an_error(self, monkeypatch):
        """A machine that has not adopted this yet must still start."""
        monkeypatch.delenv(secrets_file.MASTER_KEY_ENV, raising=False)
        assert secrets_file.load(force=True) == {}
        assert secrets_file.get("ANYTHING") == ""

    def test_a_store_with_no_key_to_open_it_fails_LOUDLY(self, tmp_path, monkeypatch):
        """THE TRAP I BUILT AND CODEX CAUGHT (Q6, REFUTED, 2026-07-18).

        Returning {} here is silence at the worst possible moment. The sequence is ordinary:
        an operator encrypts .env, deletes the plaintext as instructed, and later loses
        SOLARPRO_SECRETS_KEY -- a new machine, a wiped shell, a Render env edit. With silence,
        the app starts happily with NO secrets and behaves as though none were ever
        configured; every downstream failure then points somewhere else entirely, and the one
        fact that would explain them is the one fact nobody is told.

        An existing store that cannot be opened is a configuration failure, and configuration
        failures must be loud.
        """
        src = _write_env(tmp_path, "A=one")
        secrets_file.encrypt_file(src)
        monkeypatch.delenv(secrets_file.MASTER_KEY_ENV, raising=False)
        secrets_file._cache = None

        with pytest.raises(secrets_file.SecretsFileError) as excinfo:
            secrets_file.load(force=True)
        assert secrets_file.MASTER_KEY_ENV in str(excinfo.value), (
            "the error must name the variable the operator has to set")

    def test_a_malformed_master_key_is_reported_without_echoing_it(self, monkeypatch):
        monkeypatch.setenv(secrets_file.MASTER_KEY_ENV, "not-a-valid-fernet-key-at-all")
        with pytest.raises(secrets_file.SecretsFileError) as excinfo:
            secrets_file.load(force=True)
        assert "not-a-valid-fernet-key-at-all" not in str(excinfo.value), (
            "the error message echoed the key -- error messages get logged")

    def test_refuses_to_write_an_empty_store(self, tmp_path):
        """Encrypting an empty file would silently replace real secrets with nothing."""
        src = _write_env(tmp_path, "# only comments\n\n")
        with pytest.raises(secrets_file.SecretsFileError):
            secrets_file.encrypt_file(src)

    def test_a_store_that_does_not_round_trip_is_never_left_on_disk(self, tmp_path,
                                                                    monkeypatch):
        """THE 2AM TEST.

        If encryption silently produced a file that cannot be read back, the operator would
        delete their plaintext believing they had a copy -- and discover otherwise the next
        time the app restarted. So `encrypt_file` decrypts what it just wrote and compares,
        and deletes the file rather than leave a broken one that looks finished.

        Simulated by corrupting the cipher's output, which is the observable behaviour of any
        cause -- a bad cipher, a short write, a full disk.
        """
        real_fernet = secrets_file._fernet

        class _BadCipher:
            def __init__(self, inner):
                self._inner = inner

            def encrypt(self, data):
                # Encrypts something OTHER than what it was handed.
                return self._inner.encrypt(b"SOMETHING=else")

            def decrypt(self, blob):
                return self._inner.decrypt(blob)

        monkeypatch.setattr(secrets_file, "_fernet",
                            lambda: _BadCipher(real_fernet()))

        src = _write_env(tmp_path, "A=one" + chr(10) + "B=two")
        with pytest.raises(secrets_file.SecretsFileError, match="round-trip"):
            secrets_file.encrypt_file(src)

        assert not os.path.exists(secrets_file.enc_path()), (
            "a store that failed verification was left on disk looking finished")
        assert os.path.exists(src), "the plaintext must survive a failed encrypt"

    def test_verification_compares_BYTES_not_merely_the_parsed_pairs(self, tmp_path,
                                                                     monkeypatch):
        """Codex (Q7): a parsed comparison proves the KEY=VALUE pairs survived and says
        nothing about anything else in the file.

        Found by mutation testing: disabling the raw-byte check changed no test, because the
        parsed check caught the only corruption being simulated. This simulates the case only
        the byte check can see -- a store whose secrets are all intact but which has silently
        lost the operator's comments. They would have no way to know until they needed them.
        """
        real_fernet = secrets_file._fernet

        class _CommentEatingCipher:
            def __init__(self, inner):
                self._inner = inner

            def encrypt(self, data):
                kept = [ln for ln in data.decode().splitlines()
                        if ln.strip() and not ln.strip().startswith("#")]
                return self._inner.encrypt(chr(10).join(kept).encode())

            def decrypt(self, blob):
                return self._inner.decrypt(blob)

        monkeypatch.setattr(secrets_file, "_fernet",
                            lambda: _CommentEatingCipher(real_fernet()))

        src = _write_env(tmp_path, "# keep me" + chr(10) + "A=one" + chr(10) + "B=two")
        with pytest.raises(secrets_file.SecretsFileError, match="round-trip"):
            secrets_file.encrypt_file(src)
        assert not os.path.exists(secrets_file.enc_path())

    def test_encrypting_does_not_delete_the_plaintext(self, tmp_path):
        """Deleting the operator's only copy of their secrets as a side effect is how someone
        loses production access at 2am.
        """
        src = _write_env(tmp_path, "A=one")
        secrets_file.encrypt_file(src)
        assert os.path.exists(src)


class TestTheBrokerIntegration:
    """secrets_broker is the app's only secret path. This must not change how it behaves."""

    def test_production_behaviour_is_unchanged(self, tmp_path, monkeypatch):
        """THE TEST THAT MATTERS MOST.

        On Render every secret arrives as a dashboard environment variable and there is no
        `.env` at all. The environment must therefore WIN: the encrypted store may only fill a
        gap, never override. If this inverts, a stale encrypted file silently shadows the
        live configuration -- and the app would keep using a rotated-away secret.
        """
        import secrets_broker
        src = _write_env(tmp_path, "OPENROUTER_API_KEY=from-the-encrypted-file")
        secrets_file.encrypt_file(src)
        secrets_file.load(force=True)

        monkeypatch.setenv("OPENROUTER_API_KEY", "from-the-real-environment")
        got = secrets_broker._env_warm("ai/openrouter")
        assert got == {"api_key": "from-the-real-environment"}

    def test_the_encrypted_store_fills_a_gap_the_environment_does_not_have(self, tmp_path,
                                                                          monkeypatch):
        import secrets_broker
        src = _write_env(tmp_path, "OPENROUTER_API_KEY=from-the-encrypted-file")
        secrets_file.encrypt_file(src)
        secrets_file.load(force=True)

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        got = secrets_broker._env_warm("ai/openrouter")
        assert got == {"api_key": "from-the-encrypted-file"}

    def test_an_unopenable_store_does_not_take_the_app_down(self, tmp_path, monkeypatch):
        """The broker's tier rules already decide what a missing secret means per path. A
        broken store must degrade to "absent", not raise through every caller.
        """
        import secrets_broker
        src = _write_env(tmp_path, "OPENROUTER_API_KEY=x")
        secrets_file.encrypt_file(src)
        monkeypatch.setenv(secrets_file.MASTER_KEY_ENV, secrets_file.generate_key())
        secrets_file._cache = None

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert secrets_broker._env_warm("ai/openrouter") is None   # absent, not an exception


class TestPopulateEnviron:
    """The store must reach code that reads os.environ DIRECTLY, not only the broker.

    THE BUG THIS PREVENTS, caught before it shipped on 2026-07-18: `web_app.py` reads
    SECRET_KEY straight from `os.environ` and falls back to `secrets.token_hex(32)` when it is
    missing -- a RANDOM key on every restart, which silently invalidates every session and
    logs out every user. An encrypted store only the broker could see would have let the
    plaintext `.env` be deleted, the app start "successfully", and the real symptom appear
    later as constant logouts with no obvious cause.
    """

    def test_it_fills_variables_the_environment_does_not_have(self, tmp_path, monkeypatch):
        src = _write_env(tmp_path, "SECRET_KEY=stable-across-restarts")
        secrets_file.encrypt_file(src)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        secrets_file._cache = None

        assert secrets_file.populate_environ() == 1
        assert os.environ["SECRET_KEY"] == "stable-across-restarts"

    def test_it_never_overrides_the_real_environment(self, tmp_path, monkeypatch):
        """Same rule as the broker and as web_app's own loader: the environment wins. A store
        that overrode it would let a stale file shadow a rotated production secret.
        """
        src = _write_env(tmp_path, "SECRET_KEY=from-the-store")
        secrets_file.encrypt_file(src)
        monkeypatch.setenv("SECRET_KEY", "from-the-environment")
        secrets_file._cache = None

        assert secrets_file.populate_environ() == 0
        assert os.environ["SECRET_KEY"] == "from-the-environment"

    def test_an_empty_value_in_the_environment_counts_as_absent(self, tmp_path, monkeypatch):
        """`SECRET_KEY=` set to empty is not a configured secret -- and Flask would take the
        empty string and produce an unusable session key rather than fall back.
        """
        src = _write_env(tmp_path, "SECRET_KEY=real-value")
        secrets_file.encrypt_file(src)
        monkeypatch.setenv("SECRET_KEY", "")
        secrets_file._cache = None

        assert secrets_file.populate_environ() == 1
        assert os.environ["SECRET_KEY"] == "real-value"

    def test_no_store_is_a_silent_no_op(self, monkeypatch):
        """Render has no .env.enc. Boot must be completely unaffected there."""
        monkeypatch.delenv(secrets_file.MASTER_KEY_ENV, raising=False)
        secrets_file._cache = None
        assert secrets_file.populate_environ() == 0

    def test_an_unopenable_store_is_LOUD_but_never_stops_the_process(self, tmp_path,
                                                                     monkeypatch, caplog):
        """THE REGRESSION I SHIPPED AND HAD TO PULL BACK, 2026-07-18.

        I first made this RAISE. It immediately took out the test suite -- every process
        without the master key died at import -- and on Render it would have been worse: a
        missing environment variable could have refused the whole site rather than degrade
        one feature. `wsgi.py`'s own docstring warns about precisely this: "an exception
        raised here means the process never listens and Render restarts it forever. That is
        precisely how the 2026-07-09 Postgres expiry became a total outage."

        The Q6 protection did not go away -- it moved to where it belongs. `load()` still
        raises for callers who explicitly ASK for the store. `populate_environ` only fills
        gaps, and a gap-filler that cannot run is not a reason to refuse to start.
        """
        import logging
        src = _write_env(tmp_path, "SECRET_KEY=x")
        secrets_file.encrypt_file(src)
        monkeypatch.delenv(secrets_file.MASTER_KEY_ENV, raising=False)
        secrets_file._cache = None

        with caplog.at_level(logging.ERROR):
            assert secrets_file.populate_environ() == 0      # no exception
        assert secrets_file.MASTER_KEY_ENV in caplog.text, "the failure must still be LOUD"
        assert "continuing WITHOUT" in caplog.text

    def test_load_still_raises_for_a_caller_that_explicitly_asks(self, tmp_path, monkeypatch):
        """Where the Q6 protection lives now. The CLI, and anything that cannot work without
        the store, must still be told plainly rather than handed an empty dict.
        """
        src = _write_env(tmp_path, "SECRET_KEY=x")
        secrets_file.encrypt_file(src)
        monkeypatch.delenv(secrets_file.MASTER_KEY_ENV, raising=False)
        secrets_file._cache = None

        with pytest.raises(secrets_file.SecretsFileError):
            secrets_file.load(force=True)

    def test_it_logs_a_count_not_the_names(self, tmp_path, monkeypatch, caplog):
        import logging
        src = _write_env(tmp_path, "PAYSTACK_SECRET_KEY=sk_test_anothersecret")
        secrets_file.encrypt_file(src)
        monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
        secrets_file._cache = None

        with caplog.at_level(logging.INFO):
            secrets_file.populate_environ()
        assert "sk_test_anothersecret" not in caplog.text
        assert "PAYSTACK_SECRET_KEY" not in caplog.text


class TestItDoesNotLeakThroughLogs:

    def test_loading_logs_a_count_not_the_names_or_values(self, tmp_path, caplog):
        """A key NAME is a map of what the app holds and where to aim."""
        import logging
        src = _write_env(tmp_path, "PAYSTACK_SECRET_KEY=sk_test_supersecretvalue")
        secrets_file.encrypt_file(src)
        with caplog.at_level(logging.INFO):
            secrets_file.load(force=True)
        text = caplog.text
        assert "sk_test_supersecretvalue" not in text
        assert "PAYSTACK_SECRET_KEY" not in text
        # Codex (Q8): `assert "1" in text` was loose enough to pass on almost any log line.
        # Assert the actual sentence the module emits.
        assert "loaded 1 secrets from the encrypted store" in text
