"""
Guard: a workflow must never put a secret on curl's command line.

THE BUG THIS PREVENTS
    `curl ... -d "$BODY"` places the request body in curl's ARGV, where any
    other process on the runner can read it from /proc/<pid>/cmdline or
    `ps aux`. When BODY holds a secret, that is a disclosure.

    The safe form pipes the body to curl on STDIN:

        jq -nc --arg v "$SECRET" '{value: $v}' \\
        | curl -fsS -X PUT ... -d @-

    ...together with `set -eo pipefail`, because once the body is piped the
    pipeline's exit status would otherwise be curl's alone -- so a jq failure
    producing an EMPTY body would sail through as success and overwrite a
    real secret with "".

HISTORY
    Codex flagged this in set-cdc-drain-token.yml on 2026-07-19 and it was
    fixed there. The sweep on 2026-07-20 found THREE more, two of them real:
      - set-enterprise-job-token.yml   (ENTERPRISE_JOB_TOKEN)
      - set-render-metrics-bearer.yml  (METRICS_BEARER)
      - render-rotate-leaked-secrets.yml (EVERY rotated secret -- the very
        workflow used to rotate credentials after the 2026-07-10 leak)
    Each carried a comment claiming the secret "never reaches the curl
    command line". The comment was true of the jq part and false of the curl
    part. Comments are not enforcement; this test is.
"""

from __future__ import annotations

import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW_DIR = os.path.join(REPO_ROOT, ".github", "workflows")

#: Workflows that use `-d "$BODY"` with a NON-secret body. Verified by
#: reading each BODY= assignment on 2026-07-20: a domain name, JVM options,
#: a connection-pool size, and literal constants ("local", "2"). Putting
#: those in argv discloses nothing.
#:
#: An entry here is a claim that the body carries no secret. If one of these
#: workflows starts sending a credential, move it to the piped form instead
#: of widening this list.
NON_SECRET_BODY = {
    "attach-kc-custom-domain.yml",   # {"name": "<domain>"}
    "fix-kc-memory-oom.yml",         # JAVA_OPTS / pool size / "2"
    "patch-kc-cache-local.yml",      # {"value": "local"}
    "patch-kc-jvm-failsafe.yml",     # JAVA_OPTS
}

_RE_ARGV_BODY = re.compile(r'-d\s+"\$\{?BODY\}?"')


def _workflow_files():
    if not os.path.isdir(WORKFLOW_DIR):
        pytest.skip("no .github/workflows directory")
    for name in sorted(os.listdir(WORKFLOW_DIR)):
        if name.endswith((".yml", ".yaml")):
            yield name


def _strip_comments(text: str) -> str:
    """Drop YAML/shell # comments so a comment DESCRIBING the bad pattern is
    not mistaken for the bad pattern itself -- several of these workflows
    now document it deliberately."""
    return "\n".join(re.sub(r"#.*$", "", line) for line in text.splitlines())


def test_no_secret_body_on_curl_argv():
    """No workflow may pass a secret body via -d "$BODY"."""
    offenders = []
    for name in _workflow_files():
        if name in NON_SECRET_BODY:
            continue
        path = os.path.join(WORKFLOW_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            body = _strip_comments(fh.read())
        for m in _RE_ARGV_BODY.finditer(body):
            line_no = body[: m.start()].count("\n") + 1
            offenders.append(f"{name}:{line_no}")

    assert not offenders, (
        'curl called with -d "$BODY" -- this puts the body in ARGV, readable '
        "via /proc/<pid>/cmdline or `ps aux`:\n\n"
        + "\n".join(f"    {o}" for o in offenders)
        + "\n\nPipe it instead:\n"
        "    jq -nc --arg v \"$SECRET\" '{value: $v}' \\\n"
        "    | curl -fsS -X PUT ... -d @-\n"
        "and add `set -eo pipefail` so an empty body cannot pass as success.\n"
        "If the body genuinely carries NO secret, add the filename to "
        "NON_SECRET_BODY with a note on what it sends."
    )


def test_piped_secret_workflows_set_pipefail():
    """Any workflow piping a body into curl must also set pipefail.

    Without it the pipeline reports only curl's status, so a jq failure
    yielding an empty body would look like success and could overwrite a
    live secret with an empty string.
    """
    missing = []
    for name in _workflow_files():
        path = os.path.join(WORKFLOW_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        body = _strip_comments(raw)
        if "-d @-" not in body:
            continue
        if not re.search(r"set\s+-[a-z]*e[a-z]*o[a-z]*\s+pipefail|set\s+-o\s+pipefail", body):
            missing.append(name)

    assert not missing, (
        "Workflow pipes a body into curl (-d @-) but never sets pipefail, so "
        "a jq failure would pass as success and could write an EMPTY secret:\n\n"
        + "\n".join(f"    {m}" for m in missing)
    )


@pytest.mark.parametrize("name", sorted(NON_SECRET_BODY))
def test_non_secret_exemptions_are_still_real(name):
    """Stop the exemption list going stale.

    If an exempted workflow no longer uses -d "$BODY" at all, its entry is
    dead and must be removed -- otherwise it silently pre-authorises a future
    secret-bearing call in the same file.
    """
    path = os.path.join(WORKFLOW_DIR, name)
    if not os.path.exists(path):
        pytest.fail(f"{name} no longer exists -- remove it from NON_SECRET_BODY")
    with open(path, "r", encoding="utf-8") as fh:
        body = _strip_comments(fh.read())
    assert _RE_ARGV_BODY.search(body), (
        f'{name} no longer uses -d "$BODY" -- remove it from NON_SECRET_BODY '
        "so the guard tightens."
    )
