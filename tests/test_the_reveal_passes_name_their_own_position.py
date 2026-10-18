"""CQ-219, carried from report 098 to report 108 — ten reports.

`REVEAL["client"]` is built in two halves: a list literal, and two `.append`
calls placed further down the file so each can carry the paragraph explaining
why it is a separate pass. Both paragraphs name their own position in words,
and both names were wrong.

Round 097 inserted the `.pill-schedule` pass BETWEEN the literal and the
`.pill-read` append. That made `.pill-schedule` the third pass and `.pill-read`
the fourth. Neither comment moved: the first still called itself "a fourth
pass ... for the reason the third one gives", deferring to a block that is now
below it, and the second still called itself "a third pass ... because the two
above are already in states this one would destroy", with three above it.

Nothing functional turns on the order — each pass gets its own page load — so
nothing could go red. What the two sentences are FOR is telling the next author
where a fifth pass goes and why, and both were telling them the wrong thing.

Correcting the words would have left the next insertion free to do it again,
which is why this file exists instead. The ordinal is derived from the parsed
source: the length of the list literal plus each append's position among the
appends. Insert a pass anywhere and whichever comments now name the wrong
ordinal go red here.

Read from source with `ast` rather than by importing the module: the ordering
being checked is a property of how the file is WRITTEN, and an import would
answer with the assembled list, which is the same answer whatever the comments
say. It also keeps this guard out of the browser gate — `test_a11y_rendered`
is skipped whole without Chromium and a built bundle, and a comment's accuracy
does not need either.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SWEEP = Path(__file__).resolve().parents[0] / "test_a11y_rendered.py"

#: Enough to name every pass this list is ever likely to hold. A position past
#: the end of this is itself a failure — an unnamed ordinal cannot be checked,
#: and silently passing one is how the defect above survived ten reports.
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth",
            "seventh", "eighth", "ninth", "tenth"]

ROUTE = "client"


def _source() -> str:
    return SWEEP.read_text(encoding="utf-8")


def _literal_passes(tree: ast.Module) -> int:
    """How many passes the `REVEAL` literal declares for this route."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "REVEAL"
                   for t in node.targets):
            continue
        assert isinstance(node.value, ast.Dict), "REVEAL is no longer a dict"
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value == ROUTE:
                assert isinstance(value, ast.List), (
                    f"REVEAL[{ROUTE!r}] is no longer a list literal")
                return len(value.elts)
        raise AssertionError(f"REVEAL declares no {ROUTE!r} route")
    raise AssertionError("test_a11y_rendered.py no longer assigns REVEAL")


def _appends(tree: ast.Module) -> list[ast.Expr]:
    """Every `REVEAL["client"].append(...)` at module level, in source order."""
    found = []
    for node in tree.body:
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == "append"):
            continue
        target = func.value
        if not (isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "REVEAL"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == ROUTE):
            continue
        found.append(node)
    return sorted(found, key=lambda n: n.lineno)


def _comment_above(lines: list[str], lineno: int) -> str:
    """The contiguous `#` block immediately above a statement, joined."""
    block = []
    index = lineno - 2          # `lineno` is 1-based; step to the line above
    while index >= 0 and lines[index].lstrip().startswith("#"):
        block.append(lines[index].lstrip().lstrip("#").strip())
        index -= 1
    return " ".join(reversed(block))


def test_the_route_is_still_assembled_in_two_halves():
    """The floor. Every assertion below is about appends that carry a comment;
    if the appends stop existing the whole file passes vacuously, which is the
    guard's-population defect this repo names elsewhere.
    """
    tree = ast.parse(_source())

    assert _literal_passes(tree) >= 1, (
        f"REVEAL[{ROUTE!r}]'s literal declares no passes")
    assert len(_appends(tree)) >= 2, (
        f"REVEAL[{ROUTE!r}] is no longer extended by appends; this guard has "
        f"nothing left to check and must be retired or rewritten rather than "
        f"left green")


def test_each_appended_pass_names_the_position_it_actually_occupies():
    """RED before this round, twice over — both appended passes named the
    other one's ordinal.
    """
    source = _source()
    lines = source.split("\n")
    tree = ast.parse(source)

    base = _literal_passes(tree)
    appends = _appends(tree)

    for offset, node in enumerate(appends):
        position = base + offset + 1
        assert position <= len(ORDINALS), (
            f"pass {position} has no ordinal in ORDINALS; extend the list "
            f"rather than letting an unnamed position pass unchecked")
        correct = ORDINALS[position - 1]
        comment = _comment_above(lines, node.lineno)

        assert comment, (
            f"the pass appended at line {node.lineno} carries no comment, so "
            f"the next author has nothing saying why it is a separate pass")

        # Case-insensitive because these are sentence openings: the real
        # comment reads "A fourth pass on `client`". Written case-sensitive
        # first and it reported the pass as naming NO ordinal rather than the
        # wrong one, which is a worse diagnosis of the same failure.
        pattern = r"\b(?:a|the) {word} pass\b"
        named = [word for word in ORDINALS
                 if re.search(pattern.format(word=word), comment, re.I)]
        assert named == [correct], (
            f"the pass appended at line {node.lineno} is pass {position} of "
            f"{base + len(appends)} and its comment names {named or 'none'}, "
            f"not {correct!r}. A pass was inserted above it and the sentence "
            f"telling the next author where a further pass goes was left "
            f"behind — CQ-219.")


def test_no_appended_pass_miscounts_the_passes_standing_above_it():
    """The second half of CQ-219, and a distinct claim from the ordinal.

    `.pill-read`'s paragraph explained itself by counting what precedes it —
    "the two above are already in states this one would destroy" — and after
    round 097 there were three. A comment can name the right ordinal and still
    miscount its predecessors, so this is asserted separately rather than
    folded into the test above.
    """
    source = _source()
    lines = source.split("\n")
    tree = ast.parse(source)

    base = _literal_passes(tree)
    counts = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
              "six": 6, "seven": 7, "eight": 8, "nine": 9}

    for offset, node in enumerate(_appends(tree)):
        above = base + offset
        comment = _comment_above(lines, node.lineno)
        for word, value in counts.items():
            if not re.search(r"\bthe {word} above\b".format(word=word),
                             comment):
                continue
            assert value == above, (
                f"the pass appended at line {node.lineno} says 'the {word} "
                f"above' and has {above} above it — CQ-219's second half")
