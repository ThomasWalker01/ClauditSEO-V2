"""CQ-229: one vocabulary, three sites, and nothing that let them drift.

`clauditseo/persistence/runs.py` decides a verification outcome and writes one
of four words onto every row it returns. Two things read those words and
neither can tell a word it does not know from a word that did not occur:

- `clauditseo/api/app.py` counts them through a `collections.Counter`, which
  answers **0** for a key that is not there, so a renamed word reports a
  truthful-looking zero;
- `dashboard/src/fixloop.tsx` maps them through `WORD` and assigns only when
  the lookup succeeds (`const word = WORD[o.outcome]; if (word) ...`), so a
  renamed word paints **no chip at all**.

Both absorptions are deliberate and both are right in isolation: neither
consumer should crash on an unknown word. What was missing is anything that
notices the rename. Renaming `not_checked` in the producer today turns the fix
loop's "undecided" count into a permanent zero and its chip into a blank, with
a green suite - the silent-zero shape this codebase names as a failure class
in `clauditseo/api/app.py`'s own comment beside the `Counter`.

**Derived from all three files rather than asserted against a list.**
DISCIPLINE rule 3: the producer's words are read out of its syntax tree, the
screen's out of its `WORD` map, and the server's out of the handler that calls
`verify_outcomes` - so a fifth word added tomorrow is inside this file's reach
on the day it is written, and the check cannot pass by agreeing with itself.

**Proven under mutation, not by argument.** With `not_checked` renamed to
`not_decided` in `runs.py` alone, the first clause fails naming both sides of
the difference and the third fails naming `app.py`; with the producer left
alone and `WORD`'s `unchanged` key renamed, the first clause fails the other
way round. Measured 30 August 2026, round 114.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RUNS = ROOT / "clauditseo/persistence/runs.py"
APP = ROOT / "clauditseo/api/app.py"
FIXLOOP = ROOT / "dashboard/src/fixloop.tsx"

#: The vocabulary as it stands, written down.
#:
#: The three cross-derivations below are equalities between what the tree says
#: at three places, and an equality has one blind spot: a rename applied to
#: all three at once satisfies every one of them. That is not a hypothetical
#: shape - a find-and-replace across the repo is exactly how a word would move
#: - and it is the case where the screen keeps painting and the server keeps
#: counting while every stored `outcome` written before the rename becomes a
#: word nothing knows.
#:
#: So this is the registry of the expected *result*, the same shape
#: `tests/test_a_scope_statement_is_never_a_regression.py` uses for the
#: scope-statement flags. It is not the hard-coded list DISCIPLINE rule 3
#: forbids: the population is still walked out of three files, and this is
#: only what that walk is held against. Changing a word here is a deliberate
#: act with a diff, which is the whole difference between a rename and a
#: rename nobody noticed.
VOCABULARY = frozenset({"still_present", "cleared", "not_checked", "unchanged"})

#: The function in `runs.py` that decides the word, and the local it decides
#: into. Named rather than searched for, because "every string assigned to a
#: variable called `outcome` anywhere in the file" is a wider net than the
#: claim and would quietly grow a fifth word from an unrelated function.
PRODUCER = "verify_outcomes"
PRODUCER_LOCAL = "outcome"

#: The handler in `app.py` that turns those words into the response the screen
#: reads, found by the call it makes rather than by its route decorator.
CONSUMER_CALL = "verify_outcomes"


def _producer_words() -> set[str]:
    """Every string constant assigned to `outcome` inside `verify_outcomes`."""
    tree = ast.parse(RUNS.read_text(encoding="utf-8"), str(RUNS))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == PRODUCER), None)
    assert fn is not None, (
        f"{PRODUCER} is no longer defined in {RUNS.name}; this guard's "
        "premise has moved and the file needs re-reading, not re-pointing")
    out = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if (isinstance(target, ast.Name) and target.id == PRODUCER_LOCAL
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)):
            out.add(value.value)
    return out


def _handler_source() -> str:
    """The body of the `app.py` handler that calls `verify_outcomes`."""
    text = APP.read_text(encoding="utf-8")
    tree = ast.parse(text, str(APP))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(isinstance(c, ast.Call)
               and isinstance(c.func, ast.Attribute)
               and c.func.attr == CONSUMER_CALL
               for c in ast.walk(node)):
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(
        f"no function in {APP.name} calls {CONSUMER_CALL}; the server half of "
        "this binding has moved")


def _screen_words() -> set[str]:
    """The keys of `fixloop.tsx`'s `WORD` map, read out of the source."""
    text = FIXLOOP.read_text(encoding="utf-8")
    m = re.search(r"const WORD[^=]*=\s*\{(.*?)\n\};", text, flags=re.S)
    assert m, (
        "fixloop.tsx no longer declares `const WORD = { ... };`, which is the "
        "screen half of this binding")
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:",
                          m.group(1), flags=re.M))


def test_the_vocabulary_is_the_one_this_file_records():
    """The blind spot the three equalities below share, closed.

    Renaming a word at all three sites in one pass leaves every equality true
    and every stored `outcome` written before the pass unreadable — the rows
    the fix loop reads its standing position from. This is the clause that
    makes such a change land as a diff on a line someone has to edit on
    purpose.
    """
    produced = _producer_words()
    assert produced == set(VOCABULARY), (
        "the producer no longer emits the recorded vocabulary. If this is a "
        "deliberate rename, every `outcome` already stored under the old word "
        "is now a word nothing reads — migrate them, then change VOCABULARY "
        "in the same commit.\n"
        f"  emitted and unrecorded: {sorted(produced - set(VOCABULARY))}\n"
        f"  recorded and not emitted: {sorted(set(VOCABULARY) - produced)}")


def test_the_producer_and_the_screen_name_the_same_outcome_words():
    """The rename table maps exactly the words the producer can emit.

    Equality in both directions. A word the producer emits and the screen
    cannot spell paints no chip; a key the screen carries and the producer
    never emits is dead code that reads as coverage.
    """
    produced, screen = _producer_words(), _screen_words()
    assert produced, "no outcome word was found in the producer at all"
    assert produced == screen, (
        "the producer and the screen disagree about the verification "
        "vocabulary. `fixloop.tsx` assigns only when `WORD[o.outcome]` hits, "
        "so a word it cannot spell paints nothing.\n"
        f"  emitted by {RUNS.name} and unknown to the screen: "
        f"{sorted(produced - screen)}\n"
        f"  spelled by the screen and never emitted: "
        f"{sorted(screen - produced)}")


def test_the_server_counts_no_word_the_producer_cannot_emit():
    """A `Counter` subscript is a silent zero when its key never occurs.

    `app.py`'s own comment beside the tally says the subtraction it replaced
    "has no way to be wrong about one finding without being wrong about the
    total". A subscript on a word nothing emits has the opposite problem: it
    is wrong about one word and right about the total, forever, at zero.
    """
    produced = _producer_words()
    counted = set(re.findall(r"tally\[\"([a-z_]+)\"\]", _handler_source()))
    assert counted, (
        "the handler no longer counts outcomes through `tally[\"...\"]`; the "
        "server half of this binding has changed shape")
    unknown = sorted(counted - produced)
    assert not unknown, (
        "the verify response counts these words and the producer never emits "
        f"one of them, so each reports a permanent zero: {unknown}")


def test_every_outcome_word_is_named_by_the_handler_that_reports_it():
    """The other direction: a word the response never mentions is unreported.

    `cleared` is counted from `o["cleared"]` rather than from the word, so
    this is deliberately "named in the handler" and not "subscripted on the
    tally" - the narrower rule would fail on a shape the code is entitled to
    have. What it will not tolerate is a producer word the handler has never
    heard of, which is precisely what a rename leaves behind.
    """
    handler = _handler_source()
    missing = sorted(w for w in _producer_words() if f'"{w}"' not in handler)
    assert not missing, (
        "these outcome words are emitted by "
        f"{RUNS.relative_to(ROOT).as_posix()} and are named nowhere in the "
        "handler that reports the verification, so nothing on the wire "
        f"carries them: {missing}")
