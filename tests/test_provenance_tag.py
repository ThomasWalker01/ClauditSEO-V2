"""One spelling of a figure's provenance, in one function, for the whole product.

`render.m()` has said in its own docstring since it was written that it is
"the only way numbers enter prose". That was never true. The tag it produces —
`source: <who>, confidence: <how sure>` — was additionally spelled out by hand
in nineteen other places across three modules: table cells in
`render._score_table` and `render.render_trend_report`, the analyst rows in
`generate.py`, the field-metric lines in `analysts/expert.py`, and a dozen
prose tails in `render.py` itself. Each was a separate copy of the same
vocabulary, so a change to what a provenance tag says would have landed in the
one that was edited and in none of the others — a client document and the
internal document beside it disagreeing about how the product names its own
evidence.

Carried in `audits/DISPOSITIONS.md` for sixteen rounds as "provenance tag has
three independent implementations". Three was an undercount, which is itself
the argument for a guard rather than a sweep: a sweep fixes the copies someone
found, and the count of copies is exactly what nobody could keep.

**What this asserts, and what it deliberately does not.** It asserts that no
Python string literal outside `provenance_tag` puts `source:` and
`confidence:` together. It does not assert anything about the *wording* — that
is `provenance_tag`'s to choose and `tests/test_reporting_g7.py` and
`clauditseo/reporting/checks.py` to hold — and it does not reach TypeScript.
`dashboard/src/components.tsx:558` renders a fourth shape, ` (<confidence>
confidence)`, dropping the source entirely; it cannot call a Python function,
and bringing it into this vocabulary changes rendered text an operator reads,
which is a product decision rather than a deduplication. That deferral is
named in the round-061 `DISPOSITIONS.md` row rather than left for the next
reader to rediscover.

Comments are not searched, because comments are not output. This walks the AST
and looks at string constants and f-strings only, which is why the several
comments in `render.py` quoting an example tag do not trip it — they are
documentation of the rule, and a guard that punished them would teach people
to stop writing them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "clauditseo"

#: The function that is allowed to spell it, and the file it lives in.
HOME = "clauditseo/reporting/render.py"
HOME_FUNCTION = "provenance_tag"

#: Both halves in one string literal. Either alone is ordinary English — a
#: `source:` in a log line, a `confidence:` in a docstring about a model — and
#: flagging those would make the guard noise. Together they are the tag.
TAG = re.compile(r"source:.*confidence:", re.S)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Docstrings are documentation, held to the same rule as comments."""
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            out.add(id(body[0].value))
    return out


def _spellings(path: Path) -> list[tuple[int, str]]:
    """Every string literal in one file that spells a provenance tag.

    Reports the outermost node only. An f-string is a `JoinedStr` whose parts
    are `Constant`s, and reporting both would name the same defect twice and
    make the count in a failure message wrong.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstring_nodes(tree)
    inner = {id(part) for node in ast.walk(tree)
             if isinstance(node, ast.JoinedStr) for part in node.values}
    found = []
    for node in ast.walk(tree):
        if id(node) in docs or id(node) in inner:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        elif isinstance(node, ast.JoinedStr):
            text = ast.unparse(node)
        else:
            continue
        if TAG.search(text):
            found.append((node.lineno, text[:90]))
    return sorted(found)


def _home_function_lines() -> range:
    """Where `provenance_tag` starts and ends, so its own return is excused.

    By AST rather than by line number, so moving the function does not need
    this file edited — the failure mode of every hand-kept range in this
    repository's history.
    """
    tree = ast.parse((ROOT / HOME).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == HOME_FUNCTION:
            return range(node.lineno, (node.end_lineno or node.lineno) + 1)
    raise AssertionError(
        f"{HOME_FUNCTION} is not defined in {HOME}. If it moved, move this "
        f"guard's HOME with it — do not delete the guard.")


def test_the_provenance_tag_is_spelled_in_exactly_one_place():
    offenders = []
    home_lines = _home_function_lines()
    for path in sorted(PACKAGE.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        for lineno, text in _spellings(path):
            if rel == HOME and lineno in home_lines:
                continue
            offenders.append(f"{rel}:{lineno}: {text}")

    assert not offenders, (
        f"{len(offenders)} string literal(s) spell a provenance tag by hand "
        f"instead of calling `render.{HOME_FUNCTION}()`. A tag written out "
        f"here does not change when the tag changes:\n  "
        + "\n  ".join(offenders))


def test_the_one_place_still_spells_it():
    """The other half. A guard whose subject vanished passes for the wrong
    reason, and this one would: delete `provenance_tag`'s body and the sweep
    above finds nothing to complain about."""
    home_lines = _home_function_lines()
    spelled = [ln for ln, _ in _spellings(ROOT / HOME) if ln in home_lines]
    assert spelled, (
        f"`{HOME_FUNCTION}` no longer contains the tag it exists to own, so "
        f"the sweep above is asserting over an empty subject.")
