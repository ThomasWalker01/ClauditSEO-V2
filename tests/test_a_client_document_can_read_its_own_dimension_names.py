"""UX-85: a dimension code enumerated in prose for a client carries its name.

The finding named one surface — the comparison document's scope sentence,
`clauditseo/reporting/render.py:1265`. `.claude/DISCIPLINE.md` rule 3 asks for
the consumers from a grep rather than from the report's list, and the grep
found **three**:

1. the comparison scope sentence, current run and baseline (`_run_phrase`);
2. the run report's header line — *"(T1, dimensions A11Y, AIS, CNT, LOC, OFP,
   ONP, PRF, TEC)"* — which is the document a client is handed most often, and
   which the finding's anchor did not reach;
3. the score-movement difference clause — *"AIS was audited only in the current
   run"* — inside the same comparison document, one heading below the sentence
   the finding did name.

Two of the three were outside the report's account. So the last guard in this
file is a source check rather than a fourth case: it enumerates the joins in
`render.py` and fails on one that bypasses the helper, which is what would have
found consumers 2 and 3 without a person doing the grep.

**What the fix does not touch, stated so it is a decision rather than an
oversight.** A client document tags every finding "(source: A11Y module,
confidence: high)" and every new one "A11Y was not audited by the baseline" —
825 findings on the comparison this was measured against. Those are a single
code used as a repeated source tag, not a set enumerated in prose, and keying
each of them would be noise. Keying them once, in the frame sentence that
already sits above the first count, is what makes them readable — so the frame
is deliberately made the document's key and the per-finding tags are left
alone.
"""

import re
from pathlib import Path

from clauditseo.reporting.render import (render_comparison_report,
                                         render_run_report)

BUCKETS = ("new", "resolved", "persisting", "not_rechecked")

#: The three the registry holds, and the words it holds for them. Not a table
#: this file keeps on its own: `test_the_words_come_from_the_registry` below
#: re-derives them from `registry.all_modules()`, so a module that renames
#: itself fails here rather than drifting away from the document.
KEYED = (("A11Y", "Accessibility"), ("OFP", "Off-Page"), ("PRF", "Performance"))


def _run(**over) -> dict:
    run = {"id": "a" * 32, "tier": "T2", "dimensions": ["A11Y", "OFP", "PRF"],
           "engine_version": "0.7.0", "composite_score": 90.0,
           "finished_at": "2026-08-14T00:00:00+00:00", "scope": None,
           "subscores": {}, "findings": []}
    run.update(over)
    return run


def _comparison(audience: str, **scope_over) -> str:
    scope = {"pages_fetched": 224, "pages_crawled": 220,
             "dimensions": ["A11Y", "OFP", "PRF"]}
    scope.update(scope_over)
    diff = {bucket: [] for bucket in BUCKETS}
    diff["scope"] = scope
    markdown, _ = render_comparison_report(
        {"domain": "example.test"}, _run(), _run(id="b" * 32), diff, audience)
    return markdown


def _line(markdown: str, prefix: str) -> str:
    hits = [ln for ln in markdown.splitlines() if ln.startswith(prefix)]
    assert len(hits) == 1, f"expected one {prefix!r} line, got {hits}"
    return hits[0]


# --- consumer 1: the comparison scope sentence, both runs -------------------

def test_the_comparison_scope_sentence_keys_its_codes_for_a_client():
    line = _line(_comparison("client"), "Comparison scope:")
    for code, word in KEYED:
        assert f"{word} ({code})" in line, (
            f"the client's scope sentence names {code} with no key: {line}")


def test_the_baseline_sentence_is_keyed_too_and_not_only_the_current_run():
    """`_run_phrase` is shared by both sentences, so fixing one fixes both —
    which is worth a test rather than an inspection, because the two call
    sites read different keys out of the same scope dict and a fix threaded
    into one of them would look complete."""
    line = _line(_comparison("client",
                             pages_fetched_baseline=99,
                             pages_crawled_baseline=99,
                             dimensions_baseline=["A11Y", "OFP"]),
                 "Baseline scope:")
    for code, word in (("A11Y", "Accessibility"), ("OFP", "Off-Page")):
        assert f"{word} ({code})" in line, (
            f"the client's baseline sentence names {code} with no key: {line}")


def test_the_operators_copy_still_reads_in_codes():
    """The audience distinction is what is *explained*, never which facts are
    stated. Spelling out "Accessibility" at the operator explains a word they
    already own, and the rest of their document is written in codes."""
    line = _line(_comparison("internal"), "Comparison scope:")
    assert "audited A11Y, OFP, PRF." in line, line
    assert "Accessibility" not in line, line


# --- consumer 2: the run report header, outside the finding's anchor --------

def test_the_run_reports_header_keys_its_codes_for_a_client():
    markdown, _ = render_run_report({"domain": "x.test"}, _run(), "client")
    line = _line(markdown, "Prepared ")
    for code, word in KEYED:
        assert f"{word} ({code})" in line, (
            f"the client run report's header names {code} with no key: {line}")


def test_the_run_reports_header_is_unchanged_for_the_operator():
    markdown, _ = render_run_report({"domain": "x.test"}, _run(), "internal")
    assert "dimensions A11Y, OFP, PRF)" in _line(markdown, "Prepared ")


# --- consumer 3: the score-movement difference clause -----------------------

def _movement(audience: str) -> str:
    diff = {bucket: [] for bucket in BUCKETS}
    markdown, _ = render_comparison_report(
        {"domain": "example.test"}, _run(dimensions=["A11Y", "OFP"]),
        _run(id="b" * 32, dimensions=["A11Y", "OFP", "PRF"]), diff, audience)
    return _line(markdown, "Score frame:")


def test_the_difference_clause_keys_the_dimension_only_one_run_audited():
    line = _movement("client")
    assert "Performance (PRF) was audited only in the current run" in line, line


def test_the_difference_clause_is_unchanged_for_the_operator():
    line = _movement("internal")
    assert "PRF was audited only in the current run" in line, line


# --- the two properties the helper itself owns -----------------------------

def test_the_words_come_from_the_registry_rather_than_a_table_here():
    """A second vocabulary is a second thing to keep in step. If a module
    renames itself this fails and `KEYED` is corrected — rather than the
    document quietly disagreeing with `/api/meta`, which serves the same
    `name` to the dashboard."""
    import clauditseo.modules  # noqa: F401  (register dimensions)
    from clauditseo.engine import registry

    known = registry.all_modules()
    for code, word in KEYED:
        assert known[code].name == word


def test_a_code_the_registry_does_not_hold_renders_as_itself():
    """A run stored under a dimension since removed still renders. Inventing a
    name for one would be worse than printing the code the run recorded — and
    a `KeyError` here would take out a whole document for one stale row."""
    markdown, _ = render_run_report(
        {"domain": "x.test"}, _run(dimensions=["A11Y", "GONE"]), "client")
    line = _line(markdown, "Prepared ")
    assert "Accessibility (A11Y), GONE)" in line, line


# --- the guard that finds the next consumer --------------------------------

_JOIN = re.compile(r"\.join\(([^)]*)\)")

#: The spelling this rule was fixed from, kept verbatim so the matcher below
#: is checked against a real instance rather than only against its absence.
_PRE_FIX = '    audited = f"audited {\', \'.join(dimensions)}" if dimensions else None'


def _unkeyed_joins(source: str) -> list[str]:
    """Every `.join()` over a dimension list that does not go through the
    helper. `_dimension_count` is allowed by name rather than by shape: "8
    dimensions" names none of them, so it has nothing to key."""
    offenders = []
    for line_no, line in enumerate(source.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue          # prose about the rule, not an instance of it
        for match in _JOIN.finditer(line):
            operand = match.group(1).lower()
            if "dimension" not in operand and "dims" not in operand:
                continue
            if "_dimension_words" in operand or "_dimension_count" in operand:
                continue
            offenders.append(f"{line_no}: {line.strip()}")
    return offenders


def test_no_join_in_the_renderer_puts_dimension_codes_into_prose_unkeyed():
    """The enumeration rule 3 asks for, mechanised.

    Two of this rule's three consumers were outside the finding's anchor and
    were found by grepping for the shape. This is that grep, kept: a fourth
    surface added later fails here rather than shipping to a client.

    Scoped to `render.py` because that is the module that writes documents.
    """
    source = Path("clauditseo/reporting/render.py").read_text(encoding="utf-8")
    offenders = _unkeyed_joins(source)
    assert not offenders, (
        "a dimension list is joined into prose without going through "
        "_dimension_words, so one audience gets bare acronyms (UX-85):\n  "
        + "\n  ".join(f"render.py:{o}" for o in offenders))


def test_that_guard_is_capable_of_failing():
    """DISCIPLINE rule 1: a guard never seen to fail is not a guard.

    The pre-fix line, run through the same function. If this stops failing,
    the matcher has stopped recognising the shape it was written for and the
    test above is passing vacuously.
    """
    assert _unkeyed_joins(_PRE_FIX) == ["1: " + _PRE_FIX.strip()]
