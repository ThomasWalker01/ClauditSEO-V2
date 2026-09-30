"""`scripts/prove_fail.py` must refuse every test whose subject is the built
bundle — CQ-164.

The script answers DISCIPLINE rule 1: does this assertion fail against the
parent commit's source? It answers by reverting SOURCE and re-running, which
says nothing about a test that loads `dashboard/dist`, because reverting
`dashboard/src` does not rebuild the bundle. The script knows this and refuses
those tests with exit 2 — but the set it refuses was a hand-kept tuple of one
while twenty-two test files bind to the bundle, so it answered wrongly for
twenty-one of them, and twenty-two commits worked around it by hand and said
so in their own bodies.

**The population here is derived from a different property than the script
uses**, deliberately, because a check drawing its evidence from the thing it
checks can only ever pass (DISCIPLINE rule 5). The script asks an
*import-graph* question over the AST: does this module, or a `tests.` module
it imports from, build a path ending in `dist`? This file asks a *decorator*
question over the text: does this module carry a `skipif` gate naming `DIST`,
so pytest itself declines to run it without the bundle? Twenty files answer
yes here and twenty-two answer yes there; the two the script adds are
`test_bundle_identity` (which degrades inside a function rather than skipping)
and `test_real_data_scale` (whose import sits below its gate). The subset
direction is the safe one, and a file appearing here and not there is the
failure this guard exists to catch.

**A textual scan was tried first and is wrong — recorded here so it is not
re-tried.** Searching each file's source for the string `dashboard/dist`
answers yes for `tests/test_a_brief_has_one_typical_cost.py` and
`tests/test_a_brief_price_says_what_it_covers.py`, whose docstrings both read
"Pure Python, deliberately. Nothing here loads `dashboard/dist`" — the two
files whose prose exists precisely to say the script CAN answer for them. A
scan that cannot tell code from the sentence describing it would refuse them.
Hence the AST.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.prove_fail import needs_build  # noqa: E402

#: A `skipif` whose condition names DIST — pytest's own refusal to run the file
#: without the bundle. `.*?DIST` across newlines rather than `[^)]*`, because
#: every multi-line gate in this tree calls `axe.available()` inside the
#: condition and a bracket-excluding class stops at that call's own paren.
_BUNDLE_GATE = re.compile(r"skipif\(.*?DIST", re.S)


def _bundle_gated() -> list[Path]:
    out = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        if _BUNDLE_GATE.search(path.read_text(encoding="utf-8", errors="replace")):
            out.append(path.relative_to(ROOT))
    return out


def test_the_population_is_not_empty():
    """Guards the guard: an over-tight gate regex would make every assertion
    below vacuous, and a vacuous population is how a hand-kept list of one
    survived four rounds of being named."""
    found = _bundle_gated()
    assert len(found) >= 20, (
        f"only {len(found)} test files were found to carry a bundle skip gate; "
        "the gate pattern has stopped matching and the assertions below are "
        "no longer testing anything"
    )


def test_every_bundle_gated_test_file_is_refused():
    """The direction CQ-164 names. A file pytest itself will not run without
    the bundle is a file whose result says nothing about the parent's source."""
    answered = [str(p) for p in _bundle_gated() if not needs_build(p)]
    assert not answered, (
        "prove_fail.py would answer for these test files, but each carries a "
        "skipif gate naming DIST, so it runs against whatever bundle is on "
        "disk and its answer is about neither commit:\n  "
        + "\n  ".join(answered)
    )


def test_a_file_that_only_imports_the_bundle_path_is_refused():
    """The transitive direction. `test_spend_mark.py` never names `dist`
    itself; it takes `DIST` from `test_a11y_rendered`. A rule reading one file
    at a time answers wrongly for it, which is most of the twenty-one."""
    assert needs_build(Path("tests/test_spend_mark.py"))


def test_a_pure_python_test_file_is_still_answered():
    """The must-not-change direction, and the one over-refusal would break.
    Exit 2 is cheap but it is not free: every file pushed into it is a hand
    proof, which is the friction the script exists to remove."""
    for path in ("tests/test_a_brief_has_one_typical_cost.py",
                 "tests/test_a_brief_price_says_what_it_covers.py",
                 "tests/test_prove_fail_refuses_bundle_tests.py"):
        assert not needs_build(Path(path)), (
            f"{path} does not load the bundle, so refusing it costs a hand "
            "proof for nothing"
        )


def test_the_refusal_reaches_the_command_line():
    """The unit answers about the predicate; this answers about the contract
    an operator meets. Exit 2 and a message naming the reason, run before the
    dirty-tree check so it costs no git work."""
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prove_fail.py"),
         "tests/test_spend_mark.py::test_x"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert run.returncode == 2, run.stdout + run.stderr
    assert "dashboard/dist" in run.stdout, run.stdout
