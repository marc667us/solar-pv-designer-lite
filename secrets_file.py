"""Encrypted secrets at rest -- the `.env` file, but unreadable without the master key.

WHY THIS EXISTS
---------------
`.env` holds the Flask SECRET_KEY, the Paystack secret, both admin passwords and the SMTP
password IN PLAINTEXT. It is correctly gitignored, so it never reaches GitHub -- but "not in
git" is not the same as "secure". Anything that can read the disk can read every secret the
app has: a stray backup, a synced folder, a shared machine, a support ZIP, a misconfigured
container mount. This repo already leaked five live secrets into PUBLIC CI logs for 35 days on
2026-07-10, so the threat is not hypothetical here.

`.env.enc` is the same content, encrypted with a key that lives ONLY in the environment. Steal
the file and you have ciphertext.

WHAT THIS DOES NOT SOLVE, stated plainly
----------------------------------------
This is encryption AT REST, not a secret manager. The master key must itself live somewhere,
and that somewhere is an environment variable (`SOLARPRO_SECRETS_KEY`), set in the Render
dashboard and never written to disk. So:

  * It DOES protect against a stolen/copied/backed-up file, a shared machine, and a secret
    accidentally committed later.
  * It does NOT protect against an attacker who can already read this process's environment
    or memory. If they can, they have the master key and everything it opens.

That is the standard bootstrap problem and the honest boundary of this approach. Vault (which
`secrets_broker` already speaks to) is the real answer; this is the layer that makes the
interim safe rather than pretending the interim is fine.

PRECEDENCE, and why this order cannot break production
------------------------------------------------------
`os.environ` WINS over this file. On Render every secret arrives as a dashboard environment
variable and there is no `.env` at all, so production behaviour is byte-for-byte unchanged by
this module -- it can only supply a value the environment did not already have. A security
change that can take the site down is not a security improvement.
"""

from __future__ import annotations

import base64
import logging
import os
import threading

logger = logging.getLogger("secrets_file")

# The encrypted store, and the env var holding the key that opens it.
ENC_FILE_ENV = "SOLARPRO_SECRETS_FILE"     # optional override of the path
MASTER_KEY_ENV = "SOLARPRO_SECRETS_KEY"    # base64 Fernet key -- NEVER written to disk
DEFAULT_ENC_FILE = ".env.enc"

_cache: dict[str, str] | None = None
_lock = threading.Lock()


class SecretsFileError(Exception):
    """The encrypted store exists but could not be opened."""


def _fernet():
    """The cipher, or None when no master key is configured.

    Fernet is AES-128-CBC with an HMAC-SHA256 authentication tag. The authentication is the
    part that matters as much as the secrecy: a truncated or tampered `.env.enc` fails loudly
    on decrypt instead of yielding a half-parsed set of secrets.
    """
    key = os.environ.get(MASTER_KEY_ENV, "").strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:                                     # pragma: no cover
        logger.warning("secrets_file: cryptography is not installed; encrypted store ignored")
        return None
    try:
        return Fernet(key.encode())
    except Exception:
        # The key itself is malformed. Say so WITHOUT echoing it -- an error message is a
        # place secrets go to be logged.
        raise SecretsFileError(
            f"{MASTER_KEY_ENV} is not a valid Fernet key (expected 32 url-safe base64 bytes)")


def enc_path() -> str:
    return os.environ.get(ENC_FILE_ENV, "").strip() or DEFAULT_ENC_FILE


def generate_key() -> str:
    """A fresh master key, for the operator to place in the environment."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def _parse_env_text(text: str) -> dict[str, str]:
    """KEY=VALUE lines to a dict. Blank lines and `#` comments ignored.

    Deliberately the same shape as a `.env` so encrypting one is lossless, and so an operator
    can reason about the plaintext they are about to encrypt.
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def load(force: bool = False) -> dict[str, str]:
    """Decrypt the store into memory. Returns {} when there is nothing to load.

    Input:  force -- re-read even if already cached.
    Output: the decrypted KEY -> VALUE mapping.

    NEVER RAISES ON A MISSING STORE. No key configured, or no file, is the ordinary state of a
    machine that has not adopted this yet -- and the app must still start. A store that EXISTS
    but cannot be opened is different: that is a misconfiguration an operator has to see, so
    it raises.
    """
    global _cache
    if _cache is not None and not force:
        return _cache

    with _lock:
        if _cache is not None and not force:
            return _cache

        path = enc_path()
        have_store = os.path.exists(path)
        cipher = _fernet()

        # NO STORE AT ALL is the ordinary state of a machine that has not adopted this yet.
        # Silence is correct: the app must still start.
        if not have_store:
            _cache = {}
            return _cache

        # A STORE THAT EXISTS WITH NO KEY TO OPEN IT IS A CONFIGURATION FAILURE, and it must
        # be loud. Codex (Q6, REFUTED, 2026-07-18) caught that returning {} here builds
        # exactly the 2am trap this module claims to prevent: an operator encrypts .env,
        # deletes the plaintext, later loses SOLARPRO_SECRETS_KEY -- and the app starts
        # cheerfully with no secrets, behaving as though none were ever configured. Every
        # downstream failure then points somewhere else.
        if cipher is None:
            raise SecretsFileError(
                f"{path} exists but {MASTER_KEY_ENV} is not set -- the encrypted secrets "
                f"cannot be opened. Set the master key, or remove {path} if the store is "
                f"genuinely no longer in use.")

        try:
            with open(path, "rb") as fh:
                blob = fh.read()
            text = cipher.decrypt(blob).decode("utf-8")
        except SecretsFileError:
            raise
        except Exception as exc:
            # The exception text is NOT included. A decrypt failure from `cryptography` is
            # generic anyway, and this message is destined for logs.
            raise SecretsFileError(
                f"{path} could not be decrypted -- wrong {MASTER_KEY_ENV}, or the file is "
                f"corrupt or truncated ({type(exc).__name__})") from None

        _cache = _parse_env_text(text)
        # The COUNT, never the names and never the values. A key name is a map of what the
        # app holds and where to aim.
        logger.info("secrets_file: loaded %d secrets from the encrypted store", len(_cache))
        return _cache


def get(name: str, default: str = "") -> str:
    """One secret from the encrypted store, or `default`.

    `os.environ` is NOT consulted here -- callers decide precedence, and `secrets_broker`
    deliberately prefers the real environment so production is unaffected by this module.
    """
    try:
        return load().get(name, default)
    except SecretsFileError as exc:
        # A broken store must not take down every caller: the broker's tier rules already
        # decide what a missing secret means for each path.
        logger.error("secrets_file: %s", exc)
        return default


def populate_environ() -> int:
    """Put the decrypted secrets into os.environ, without overriding what is already there.

    Input:  none.
    Output: how many variables were set (0 when there is no store).

    WHY THIS IS NECESSARY, and it is not optional:

    `secrets_broker` is NOT the app's only reader of secrets. `web_app.py` reads SECRET_KEY
    straight from `os.environ` and falls back to `secrets.token_hex(32)` when it is missing --
    a RANDOM key on every restart, which silently invalidates every session and logs out every
    user. Several other modules read os.environ directly too. So an encrypted store that only
    the broker can see would let an operator delete their `.env`, watch the app start
    "successfully", and then field complaints about being logged out constantly.

    `setdefault` semantics, deliberately: the real environment still wins, exactly as in
    `secrets_broker._env_warm` and in web_app's own `.env` loader. This function fills gaps.

    NEVER LOGS A NAME OR A VALUE -- a count only. Callers run this at boot, where logs are
    verbose and widely read.
    """
    try:
        data = load()
    except SecretsFileError as exc:
        # LOUD, BUT NEVER FATAL. This is the boot path, and `wsgi.py` says in its own
        # docstring why that matters: "an exception raised here means the process never
        # listens and Render restarts it forever. That is precisely how the 2026-07-09
        # Postgres expiry became a total outage."
        #
        # I shipped this as a `raise` on 2026-07-18 and it immediately took out the test
        # suite, because any process without the master key now died at import. On Render it
        # would have been worse: a missing env var could refuse the whole site rather than
        # degrade one feature.
        #
        # `load()` still raises for callers who explicitly ASK for the store -- the CLI, and
        # anything that cannot work without it. That is where the Q6 protection belongs. This
        # function's job is only to FILL GAPS, and a gap-filler that cannot run is not a
        # reason to refuse to start: the environment may well already hold everything, which
        # is exactly the case on Render.
        logger.error("secrets_file: %s", exc)
        logger.error("secrets_file: continuing WITHOUT the encrypted store -- any secret it "
                     "was meant to supply will be missing")
        return 0

    applied = 0
    for name, value in data.items():
        if not os.environ.get(name):
            os.environ[name] = value
            applied += 1
    if applied:
        logger.info("secrets_file: populated %d environment variables from the "
                    "encrypted store", applied)
    return applied


def encrypt_file(src: str, dst: str | None = None) -> str:
    """Encrypt a plaintext `.env` into `.env.enc`. Returns the path written.

    Input:  src -- the plaintext env file. dst -- output, defaults to `enc_path()`.
    Output: the path written.

    THIS DOES NOT DELETE THE PLAINTEXT. Deleting the operator's only copy of their secrets as
    a side effect of encrypting them is how someone loses production access at 2am. The CLI
    tells them to remove it once they have verified the round trip themselves.
    """
    cipher = _fernet()
    if cipher is None:
        raise SecretsFileError(
            f"set {MASTER_KEY_ENV} before encrypting (generate one with: "
            f"python -m secrets_file keygen)")

    with open(src, "r", encoding="utf-8") as fh:
        text = fh.read()

    parsed = _parse_env_text(text)
    if not parsed:
        raise SecretsFileError(f"{src} contains no KEY=VALUE lines -- refusing to write an "
                               f"empty store")

    dst = dst or enc_path()
    blob = cipher.encrypt(text.encode("utf-8"))

    # ATOMIC WRITE. Codex (Q5, 2026-07-18): writing O_TRUNC straight to the destination means
    # a crash mid-write leaves a truncated store that looks finished. Write a temporary file
    # beside it, fsync, then rename -- os.replace is atomic on both POSIX and Windows, so the
    # destination is either the old file or the complete new one, never a half of either.
    #
    # 0600 is POSIX hygiene and is honest about its limits: on WINDOWS the mode is largely
    # ignored and readability is governed by the directory's ACL inheritance. If Windows-local
    # at-rest protection matters, the file needs an explicit DACL or DPAPI -- this module does
    # not pretend otherwise.
    tmp = f"{dst}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, blob)
        os.fsync(fd)
    finally:
        os.close(fd)

    # ROUND-TRIP VERIFY BEFORE the file becomes the real store. An encrypted file that cannot
    # be decrypted is worse than none: the operator deletes the plaintext believing they have
    # a copy.
    #
    # COMPARED AS RAW BYTES, not as parsed dicts. Codex (Q7): a parsed comparison proves the
    # KEY=VALUE pairs survived but says nothing about comments, ordering, blank lines or any
    # dotenv syntax this parser ignores -- so a file could pass while quietly losing content
    # the operator can still see in their plaintext.
    try:
        written_back = cipher.decrypt(open(tmp, "rb").read()).decode("utf-8")
        if written_back != text:
            raise SecretsFileError(
                "round-trip verification FAILED -- what was written back does not match the "
                "source, so the store was NOT created")
        if _parse_env_text(written_back) != parsed:      # belt and braces
            raise SecretsFileError("round-trip verification FAILED on the parsed contents")
    except SecretsFileError:
        os.unlink(tmp)
        raise
    except Exception as exc:
        os.unlink(tmp)
        raise SecretsFileError(
            f"round-trip verification could not complete ({type(exc).__name__}) -- the store "
            f"was NOT created") from None

    os.replace(tmp, dst)
    return dst


def _main(argv: list[str]) -> int:                          # pragma: no cover - CLI
    """`python -m secrets_file {keygen|encrypt|verify}`."""
    cmd = argv[1] if len(argv) > 1 else ""

    if cmd == "keygen":
        print(generate_key())
        print("", file=__import__("sys").stderr)
        print(f"Set this as {MASTER_KEY_ENV} in your environment and in the Render "
              f"dashboard.", file=__import__("sys").stderr)
        print("Do NOT commit it and do NOT write it to a file.",
              file=__import__("sys").stderr)
        return 0

    if cmd == "encrypt":
        src = argv[2] if len(argv) > 2 else ".env"
        try:
            out = encrypt_file(src)
        except SecretsFileError as exc:
            print(f"error: {exc}"); return 1
        n = len(load(force=True))
        print(f"wrote {out} ({n} secrets, verified by round trip)")
        print(f"the plaintext {src} was NOT deleted -- verify with "
              f"`python -m secrets_file verify`, then remove it yourself")
        return 0

    if cmd == "verify":
        try:
            data = load(force=True)
        except SecretsFileError as exc:
            print(f"error: {exc}"); return 1
        if not data:
            print("no encrypted store loaded "
                  f"(is {MASTER_KEY_ENV} set, and does {enc_path()} exist?)")
            return 1
        # NAMES ONLY, never values. Printing names is acceptable HERE and only here: this is
        # an operator running a command about their own secrets, not a service writing a log.
        # Codex (Q3) flagged it; it stays, deliberately, because a verify command that will
        # not tell you what it verified is useless.
        print(f"{len(data)} secrets readable from {enc_path()}:")
        shadowed = []
        for name in sorted(data):
            if os.environ.get(name, ""):
                shadowed.append(name)
                print(f"  {name}  (SHADOWED by the environment -- the app uses the env value)")
            else:
                print(f"  {name}")
        if shadowed:
            # Codex (Q4): env precedence is right for production but it is a footgun -- a
            # stale env var silently shadows a rotated secret in the store, forever, with no
            # symptom. Naming them is what turns that from silent into merely surprising.
            print("")
            print(f"WARNING: {len(shadowed)} secret(s) in the store are being IGNORED because")
            print("the environment already sets them. If you rotated a value in the store and")
            print("the app is still using the old one, this is why.")
        return 0

    print(__doc__)
    print("usage: python -m secrets_file {keygen|encrypt [file]|verify}")
    return 1


if __name__ == "__main__":                                  # pragma: no cover
    import sys
    raise SystemExit(_main(sys.argv))
