"""CQ-204, carried from report 091 to report 108 — sixteen reports.

`DIFF_SCOPE_KEY` was introduced with a comment saying it is named once so the
two readers of it cannot drift apart on the spelling. Three things were wrong
with that at the same time, and the comment made all three invisible:

  * The **writer** is not a reader. `compare_runs` in
    `clauditseo/persistence/runs.py` spelled `"scope"` by hand, so renaming the
    constant would have left the document reading a key nothing writes.
  * The constant had exactly **one** reader — `_run_report` in the module that
    declares it — not two.
  * `dashboard/src/views.tsx` is TypeScript and cannot import a Python
    constant. It spells the key by hand and always will. What holds it in step
    is a test that reads both files, and the comment named no such test
    because none existed for this key; the tripwire that did exist
    (`test_the_screen_still_reads_the_same_scope_key`) hardcoded `data.scope`,
    so renaming the Python constant left it green.

The remedy is the one this repo already applies to the same problem one file
over: `PAGES_FETCHED_BASIS_NOTE`'s comment in `views.tsx` says plainly that
TypeScript cannot import a Python dict and names the test that holds the two
in step. A comment that asserts a protection is a liability; a comment that
names the mechanism is checkable, and this file is that mechanism.

Every assertion below derives the key from `DIFF_SCOPE_KEY` at runtime. None
of them spells `"scope"`, which is the whole point: renaming the constant must
move every surface or fail here.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from clauditseo.persistence import runs
from clauditseo.reporting.render import DIFF_SCOPE_KEY


def _compare_runs_source() -> str:
    return inspect.getsource(runs.compare_runs)


def test_the_writer_reads_the_constant_rather_than_spelling_the_key():
    """RED before this round: `compare_runs` built its return dict with a bare
    `"scope":` literal, so the one function that decides the key's spelling was
    the one function not reading the constant that owns it.
    """
    source = _compare_runs_source()

    assert "DIFF_SCOPE_KEY" in source, (
        "compare_runs does not read DIFF_SCOPE_KEY; the writer of the key is "
        "not bound to the constant that names it, so a rename moves the "
        "readers and leaves the writer behind")
    assert f'"{DIFF_SCOPE_KEY}":' not in source, (
        f"compare_runs still spells the scope key literally as "
        f"{DIFF_SCOPE_KEY!r}; the constant and the literal can drift apart "
        f"exactly as they did before it existed")


def test_the_comparison_still_carries_its_frame_under_that_key():
    """The floor, and it passes on both trees on purpose.

    A guard that only forbids a literal is satisfied by deleting the key. This
    asserts the payload itself, keyed by the constant, so the fix cannot reach
    green by removing the thing it was meant to name.
    """
    tree = ast.parse(_compare_runs_source())
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef), (
        "compare_runs' source no longer parses as a single function")

    # `compare_runs`' OWN return, not `ast.walk`'s. It defines fifteen nested
    # helpers between the docstring and the end, each with returns of its own,
    # and `ast.walk` yields breadth-first — so both `walk(...)[-1]` and
    # `walk(...)[0]` name a helper's return on some tree and this function's on
    # another. Written the first way here and it was red before the fix for a
    # reason that had nothing to do with the fix.
    returns = [n for n in function.body if isinstance(n, ast.Return)]
    assert len(returns) == 1, (
        f"expected exactly one top-level return in compare_runs, "
        f"found {len(returns)}")

    rendered = ast.dump(returns[0])
    assert "DIFF_SCOPE_KEY" in rendered, (
        "compare_runs' returned dict is no longer keyed by DIFF_SCOPE_KEY")
    for part in ("pages_crawled", "dimensions", "pages_crawled_baseline",
                 "dimensions_baseline"):
        assert part in rendered, (
            f"the scope frame no longer carries {part!r}; this guard was "
            f"written to bind a key's spelling, not to license dropping the "
            f"frame it names")


def test_the_document_reads_the_key_through_the_constant():
    """The floor for the other surface. `render.py` already did this before
    the round and must keep doing it — a fix that bound the writer by
    unbinding the reader would be a lateral move.
    """
    render = Path("clauditseo/reporting/render.py").read_text(encoding="utf-8")

    assert "diff.get(DIFF_SCOPE_KEY)" in render, (
        "the run report no longer reads the diff's scope through "
        "DIFF_SCOPE_KEY")


def test_the_screen_is_tied_to_the_constant_and_not_to_a_hardcoded_spelling():
    """RED before this round, and the assertion that actually catches a rename.

    Not evidence the screen renders — DISCIPLINE rule 4, and the tripwire this
    replaces says so in its own docstring. What it is evidence of: the only
    thing standing between the Python constant and the TypeScript literal is
    derived from the constant, so renaming `DIFF_SCOPE_KEY` reddens this
    rather than shipping a screen that reads a key nothing writes.

    RED before, because the tripwire that existed spelled `"data.scope"` out
    and this asserts that no guard for this key does.
    """
    view = Path("dashboard/src/views.tsx").read_text(encoding="utf-8")

    assert f"data.{DIFF_SCOPE_KEY}" in view, (
        f"the comparison screen no longer reads data.{DIFF_SCOPE_KEY}; the "
        f"two consumers of compare_runs' scope have diverged again")

    tripwire = Path(
        "tests/test_the_comparison_document_states_its_own_frame.py"
    ).read_text(encoding="utf-8")
    assert f'"data.{DIFF_SCOPE_KEY}"' not in tripwire, (
        f'the older tripwire still hardcodes "data.{DIFF_SCOPE_KEY}", so '
        f"renaming DIFF_SCOPE_KEY leaves it green — which is how a constant "
        f"introduced to prevent drift came to permit it")


def test_the_constants_comment_names_the_mechanism_rather_than_asserting_one():
    """RED before this round.

    The comment claimed two readers and a protection. Neither was true. This
    asserts the shape the repo already uses for the identical
    Python-cannot-reach-TypeScript problem at `PAGES_FETCHED_BASIS_NOTE`: say
    that the screen spells it by hand, and name the file that fails when the
    two diverge.
    """
    render = Path("clauditseo/reporting/render.py").read_text(encoding="utf-8")
    declaration = render.split("DIFF_SCOPE_KEY =")[0]
    comment = declaration.rsplit("\n\n", 1)[-1]

    assert Path(__file__).name in comment, (
        "DIFF_SCOPE_KEY's comment does not name the test that holds its three "
        "surfaces in step, so a reader has only its word that anything does")
    assert "two readers" not in comment, (
        "DIFF_SCOPE_KEY's comment still claims two readers; the writer in "
        "runs.py and the screen in views.tsx are not readers of it")
