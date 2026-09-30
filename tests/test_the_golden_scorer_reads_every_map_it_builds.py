"""A scoring function that builds a lookup and never reads it.

**CQ-224, carried from report 099 to report 110 — ten reports, which is the
threshold `.claude/skills/audit-fix/SKILL.md` step 4 makes a disposition
mandatory at.** `clauditseo/golden.py`'s `score()` declared two structures
side by side, `raised` and `raised_rows`, filled both inside one loop, and
read only the second. A reader looking for what decides a catch found two
candidate structures and only one was live.

**Derived from the syntax tree, not from a list of names.** The population is
every local `score()` binds; the assertion is that none of them is filled and
then never consulted. A literal list would pass the day someone adds a third
dead map, which is the guard-population failure this repository has shipped
five times (`.claude/loop/PROFILE.md`, "a guard's population").

**A fill is not a read, and the first draft of this guard got that wrong.**
Written as a plain `Store`/`Load` split it passed against the unfixed tree:
`raised.setdefault(tool, set()).add(...)` puts `raised` in a `Load` context,
so the dead map looked used by the only evidence the split had. That draft was
run before the fix, per `.claude/DISCIPLINE.md` rule 1, and it is the reason
this file distinguishes the two. A load that is the receiver of a method call
standing alone as a statement is a **fill**; every other load is a **consult**.
`raised_rows` survives the same test on its own merits — `rows =
raised_rows.get(tool, [])` is an assignment, not a bare statement.

Scoped to `score()` on purpose. Whether the same rule should run over every
function in the package is a bigger claim than this finding makes, and a guard
that fails on unrelated code is a guard that gets deleted.
"""

from __future__ import annotations

import ast
from pathlib import Path

MODULE = Path("clauditseo/golden.py")
FUNCTION = "score"

#: Bindings a dead-store check must not read as dead. `_`-prefixed names are
#: the language's own "deliberately unused" convention, and the loop targets
#: of a `for` are consumed by the iteration itself.
IGNORED_PREFIX = "_"


def _function() -> ast.FunctionDef:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == FUNCTION:
            return node
    raise AssertionError(
        f"{MODULE} defines no function named {FUNCTION!r}; this guard's "
        "population is empty and every clause below would pass by finding "
        "nothing")


def _stored_and_consulted() -> tuple[set[str], set[str]]:
    """Every name `score()` binds, and every name it actually consults.

    A load is *not* a consult when it is the receiver of a method call that
    stands alone as a statement — `raised.setdefault(...)` and
    `xs.append(...)` fill a structure without asking it anything. Every other
    load counts, including a subscript target (`out[k] = v` reads `out`),
    which is deliberately generous: this clause is meant to catch a structure
    nothing consults, not to police every shape of mutation.
    """
    fn = _function()
    stored: set[str] = set()
    consulted: set[str] = set()
    fills: set[int] = set()
    for node in ast.walk(fn):
        # A bare `a.b(...)`/`a.b(...).c(...)` statement: peel the call chain
        # down to its root name and mark that one load as a fill.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            inner = node.value
            while (isinstance(inner, ast.Call)
                   and isinstance(inner.func, ast.Attribute)):
                inner = inner.func.value
            if isinstance(inner, ast.Name):
                fills.add(id(inner))
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                stored.add(node.id)
            elif id(node) not in fills:
                consulted.add(node.id)
    return stored, consulted


def test_the_function_binds_anything_at_all():
    """Population, from the tree. `score()` must actually bind locals or the
    dead-store clause below is vacuously true."""
    stored, _ = _stored_and_consulted()
    real = {n for n in stored if not n.startswith(IGNORED_PREFIX)}
    assert real, (
        f"{MODULE}::{FUNCTION} binds no locals this guard can see; its "
        "population is empty")


def test_no_local_is_built_and_never_consulted():
    """CQ-224. Every name `score()` binds is read somewhere in `score()`.

    A name whose only appearance is `x.setdefault(...)` as a bare statement is
    filled and never consulted, which is exactly the shape `raised` had: two
    maps declared together, both filled in one loop, one of them never asked
    anything afterwards.
    """
    stored, consulted = _stored_and_consulted()
    dead = sorted(n for n in stored
                  if n not in consulted and not n.startswith(IGNORED_PREFIX))
    assert not dead, (
        f"{MODULE}::{FUNCTION} binds {dead} and never reads them. A lookup "
        "built beside one that is read is a reader's trap: both look like "
        "what decides the result and only one is.")
