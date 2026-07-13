"""`INSERT OR REPLACE` must never be reachable on Postgres.

WHY THIS TEST EXISTS
--------------------
`INSERT OR REPLACE` is SQLite-only. On Postgres it is a hard syntax error
(`syntax error at or near "OR"`), and db_adapter._translate_sqlite_to_postgres
translates `INSERT OR IGNORE` but NOT `INSERT OR REPLACE` (db_adapter.py:105-119),
so the statement reaches the server verbatim.

Since the Postgres cutover this shipped TWICE:

  * boms_save_rates      -- the owner clicked "Save labour %" on the Cost Estimate and
                            got a database syntax error flashed onto the page.
  * _boq_record_override -- the same statement, but inside `except Exception: pass`,
                            so it failed SILENTLY on every call and the BOQ rate library
                            simply never learned anything on live. No error, no symptom.

The second one is the reason this is a TEST and not just a fix. A defect that raises
gets reported; a defect that is swallowed does not, and grep is not run before every
deploy. So the rule is enforced mechanically instead:

    An `INSERT OR REPLACE` may appear ONLY on the non-Postgres side of a branch that
    tests DATABASE_URL.

That is the house pattern already used at web_app.py:22777 (boq_cost_plan_months),
:28687 (product_brands) and :29045 (admin_settings) -- this test simply makes the
pattern mandatory rather than customary.

It is an AST test, not a grep: it resolves whether each occurrence is genuinely inside
the `else:` of a DATABASE_URL check, which a regex cannot decide.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

# The modules that actually execute against the live database. new_*.py source files that
# are spliced into web_app.py are checked too where they are imported at runtime; the ones
# that are pure splice-sources are not, because they never run.
TARGETS = ["web_app.py"]


def _polarity(node: ast.AST, flags: dict[str, int]) -> int | None:
    """Is this expression TRUE on Postgres (+1), true on SQLite (-1), or unrelated (None)?

    Input:  an expression node, plus the known Postgres-flag variables and their polarity.
    Output: +1, -1, or None.

    POLARITY IS THE WHOLE POINT, and getting it wrong is how this guard would quietly stop
    guarding. Codex caught the first version treating the `else:` limb of ANY DATABASE_URL
    branch as the safe one. That holds for `if is_pg:` -- but it is exactly backwards for

        is_sqlite = not bool(os.environ.get("DATABASE_URL"))
        if is_sqlite: ...
        else:  c.execute("INSERT OR REPLACE ...")   # runs ON POSTGRES. The bug. Passing.

    So the limb that is safe is not "the else limb", it is "the limb that runs on SQLite" --
    and which limb that is depends on the sign of the test.
    """
    # not X  -> flip
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = _polarity(node.operand, flags)
        return -inner if inner else None

    # bool(X) -> transparent
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "bool" and node.args):
        return _polarity(node.args[0], flags)

    # `... is None` / `== None` on a DATABASE_URL read means "SQLite".
    if isinstance(node, ast.Compare):
        left = _polarity(node.left, flags)
        if left and len(node.ops) == 1:
            op = node.ops[0]
            comparators = node.comparators
            is_none = (len(comparators) == 1
                       and isinstance(comparators[0], ast.Constant)
                       and comparators[0].value is None)
            if is_none and isinstance(op, (ast.Is, ast.Eq)):
                return -left
            if is_none and isinstance(op, (ast.IsNot, ast.NotEq)):
                return left
        return left

    if isinstance(node, ast.Name) and node.id in flags:
        return flags[node.id]

    if any(isinstance(n, ast.Constant) and n.value == "DATABASE_URL" for n in ast.walk(node)):
        return 1

    return None


def _pg_flags(tree: ast.AST) -> dict[str, int]:
    """Variables that HOLD the 'am I on Postgres?' answer, with their polarity.

    `is_pg = bool(os.environ.get("DATABASE_URL"))`      -> {"is_pg": +1}
    `is_sqlite = not os.environ.get("DATABASE_URL")`    -> {"is_sqlite": -1}

    Needed because the correctly-guarded sites (product_brands:28687, admin_settings:29045)
    branch on a local flag rather than repeating the os.environ call inline. A guard that
    cries wolf on correct code gets deleted, so it reads the variable instead of
    pattern-matching one spelling of the check.
    """
    flags: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            value = getattr(node, "value", None)
            if value is None:
                continue
            p = _polarity(value, flags)
            if p is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    flags[t.id] = p
    return flags


def _literal_str(node: ast.AST) -> str | None:
    """The string a node evaluates to, folding `"INSERT OR " + "REPLACE"` back together.

    Codex's second point: a fragmented literal would slip past a check that only looks at
    whole ast.Constant strings. Fold constant string concatenation so it cannot.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_str(node.left)
        right = _literal_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _offenders(source: bytes) -> list[tuple[int, str]]:
    """Every INSERT OR REPLACE literal that is NOT on the SQLite side of a PG branch.

    Input:  the module source as bytes (ast.parse honours the coding declaration, which
            matters because web_app.py is CRLF + mojibake and will not decode as clean UTF-8).
    Output: list of (lineno, snippet) for each offending literal.
    """
    tree = ast.parse(source)
    flags = _pg_flags(tree)

    # ast has no parent links, so build them once. For a given literal we need the chain of
    # enclosing `if` statements AND which limb it sits in.
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def guarded(node: ast.AST) -> bool:
        """True if `node` can only run on SQLite.

        For each enclosing `if` that decides the backend, work out which limb we are in and
        whether THAT limb is the SQLite one -- taking the sign of the test into account:

            if is_pg:      ... else: <SQLITE>      polarity +1 -> orelse is SQLite
            if is_sqlite:  <SQLITE> else: ...      polarity -1 -> body   is SQLite
        """
        child = node
        cur = parents.get(node)
        while cur is not None:
            if isinstance(cur, ast.If):
                p = _polarity(cur.test, flags)
                if p:
                    in_body = any(child is s or child in ast.walk(s) for s in cur.body)
                    in_else = any(child is s or child in ast.walk(s) for s in cur.orelse)
                    # SQLite limb is `orelse` when the test is true on Postgres, and `body`
                    # when the test is true on SQLite.
                    if (p == 1 and in_else) or (p == -1 and in_body):
                        return True
            child = cur
            cur = parents.get(cur)
        return False

    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        text = _literal_str(node)
        if text and "insert or replace" in text.lower() and not guarded(node):
            out.append((node.lineno, text.strip()[:70]))
    return out


@pytest.mark.parametrize("filename", TARGETS)
def test_insert_or_replace_never_reaches_postgres(filename: str) -> None:
    path = REPO / filename
    offenders = _offenders(path.read_bytes())
    assert not offenders, (
        f"{filename}: `INSERT OR REPLACE` is SQLite-only and is a SYNTAX ERROR on "
        f"Postgres. Each of these is reachable on live. Put it on the `else:` side of "
        f"an `if bool(os.environ.get(\"DATABASE_URL\")):` branch and give Postgres a real "
        f"`ON CONFLICT (<key>) DO UPDATE SET ...` upsert:\n"
        + "\n".join(f"  line {ln}: {snip}" for ln, snip in offenders)
    )


def test_the_test_can_actually_fail() -> None:
    """A guard that cannot fail is not a guard.

    The whole value of this file is the AST distinction between the two limbs of the
    branch, so prove it: the same statement is an offence in the `body` (runs on Postgres)
    and is fine in the `orelse` (runs on SQLite). If this ever stops discriminating, the
    test above would silently pass forever.
    """
    bad = b'''
import os
if bool(os.environ.get("DATABASE_URL")):
    c.execute("INSERT OR REPLACE INTO t (a) VALUES (?)", (1,))
'''
    good = b'''
import os
if bool(os.environ.get("DATABASE_URL")):
    c.execute("INSERT INTO t (a) VALUES (?) ON CONFLICT (a) DO UPDATE SET a=EXCLUDED.a", (1,))
else:
    c.execute("INSERT OR REPLACE INTO t (a) VALUES (?)", (1,))
'''
    # The guard is very often written through a local flag (`is_pg = ...`) rather than by
    # repeating the os.environ call inline -- that is how product_brands and admin_settings
    # do it. Resolving the flag is what stops this test from crying wolf on correct code.
    via_flag = b'''
import os
is_pg = bool(os.environ.get("DATABASE_URL"))
if is_pg:
    c.execute("INSERT INTO t (a) VALUES (?) ON CONFLICT (a) DO UPDATE SET a=EXCLUDED.a", (1,))
else:
    c.execute("INSERT OR REPLACE INTO t (a) VALUES (?)", (1,))
'''
    # Both of these were found by Codex against the FIRST version of this detector, which
    # treated the `else:` limb of any DATABASE_URL branch as safe and only looked at whole
    # string constants. Each is a real way for the bug to ship while the guard says green,
    # so each is now a case the guard must catch.
    inverted_flag = b'''
import os
is_sqlite = not bool(os.environ.get("DATABASE_URL"))
if is_sqlite:
    c.execute("INSERT INTO t (a) VALUES (?)", (1,))
else:
    c.execute("INSERT OR REPLACE INTO t (a) VALUES (?)", (1,))   # runs ON POSTGRES
'''
    inverted_flag_ok = b'''
import os
is_sqlite = not bool(os.environ.get("DATABASE_URL"))
if is_sqlite:
    c.execute("INSERT OR REPLACE INTO t (a) VALUES (?)", (1,))   # SQLite limb -- fine
else:
    c.execute("INSERT INTO t (a) VALUES (?) ON CONFLICT (a) DO UPDATE SET a=EXCLUDED.a", (1,))
'''
    split_literal = b'''
import os
if bool(os.environ.get("DATABASE_URL")):
    c.execute("INSERT OR " + "REPLACE INTO t (a) VALUES (?)", (1,))
'''
    assert _offenders(bad), "the detector failed to flag an INSERT OR REPLACE that runs on Postgres"
    assert not _offenders(good), "the detector wrongly flagged the SQLite else-branch"
    assert not _offenders(via_flag), "the detector failed to resolve an `is_pg` flag variable"
    assert _offenders(inverted_flag), (
        "POLARITY: `if is_sqlite: ... else: <INSERT OR REPLACE>` runs on Postgres. Treating "
        "every else-limb as safe is exactly the false negative Codex found"
    )
    assert not _offenders(inverted_flag_ok), "the detector inverted the polarity the other way"
    assert _offenders(split_literal), (
        "a concatenated literal must still be folded and caught -- otherwise the invariant "
        "is one `+` away from being bypassed"
    )
