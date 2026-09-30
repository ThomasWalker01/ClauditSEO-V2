"""A page count reaches the reader with the rung that produced it.

CQ-205, first raised in report 092 and carried High through 098. `99de440`
added `pages_fetched_basis` -- one key beside `pages_fetched` saying which of
three ways the number was arrived at -- and measured at HEAD before this file
was written, it is read by nothing: zero hits in `clauditseo/reporting/` and
zero in `dashboard/src`. The value is written by `_pages_fetched` in
`clauditseo/persistence/runs.py`, spread into the run's scope by `_scope`,
carried into the comparison's frame by `_run_pages_fetched`, and dropped at
every surface that renders the count.

**Why this is a provenance breach rather than a tidiness one.** PROFILE's
invariant is that a number's frame travels with the value: "two figures with
the same source and the same confidence are not comparable across different
frames". The three rungs are three frames.

  `recorded`   the crawler counted eligible pages at crawl time, with the
               pages in hand. Engine 0.9.0 and later.
  `derived`    no recorded count, so the stored page list was counted through
               `stored_page_is_eligible`. Trustworthy, and reconstructed.
  `attempted`  neither was available, so the number is URLs *attempted* -- a
               DNS failure leaves a page with `status=0` and it is counted
               here. This rung can only overstate.

Measured read-only against `data/clauditseo.db` on 24 August 2026, over all
fifteen stored runs: **5 `recorded`, 6 `derived`, 1 `attempted`**, 3 with no
evidence at all. Two runs both report 235 readable pages and they are not the
same claim -- one was counted by the crawler and one was reconstructed. The
client-facing coverage ratio on `www.acme.com.au`, `measured across 235 of
272 discovered pages (86.4%)`, is computed from the reconstructed one.

**The rule this file guards: a page count whose rung is not `recorded` says so
where the count is rendered, and one that is `recorded` does not.** The second
half is not decoration -- a qualifier on every line is a qualifier nobody
reads, and the ordinary case has to stay quiet for the unusual one to carry
weight. Same shape `_breadth_phrase` already uses: silent where there is
nothing to say.

Sibling of `tests/test_a_comparison_states_one_count_of_what_it_read.py`,
which guards *which* count is stated and owns the source-level rung
assertions. This file guards whether the rung survives the trip to a reader,
and asserts nothing about the derivation itself.

DISCIPLINE rule 3 -- the render sites were enumerated by grep over
`pages_fetched` before this was written, not from report 098's remediation
row, which names none of them:

  `_run_phrase`   `clauditseo/reporting/render.py`, the shared owner behind
                  both of `_diff_scope_lines`' sentences (current, baseline)
  `_scope_lines`  the run report's own crawl-scope line
  `scopeCount`    `dashboard/src/views.tsx`, the compare screen, likewise
                  behind two call sites

The wording is owned once in `render.py` and asserted to be the wording the
screen uses, because a Python string and a TypeScript string cannot import
each other and the only thing that can hold them together is a test that
reads both.
"""

import re
from pathlib import Path

import pytest

from clauditseo.reporting.render import (
    PAGES_FETCHED_BASIS_NOTE, render_comparison_report, render_run_report)


#: `run_b`'s scope as `get_run` assembles it. Four readable pages of ten
#: declared, so `_breadth_phrase` states a ratio beside the composite.
RUN_SCOPE = {"pages_fetched": 4, "pages_fetched_basis": "derived",
             "discovered": 10, "robots_blocked": 0, "truncated_by": None}

#: `diff["scope"]` as `compare_runs` assembles it for the same run. The path
#: count differs from the page count, so the sentence carries both clauses and
#: the basis note has to survive beside a second quantity rather than alone.
DIFF_SCOPE = {"pages_crawled": 3, "pages_fetched": 4,
              "pages_fetched_basis": "derived", "dimensions": ["ONP", "TEC"]}


def _comparison(basis: str | None = "derived", audience: str = "client") -> str:
    """One rendered comparison, at whichever rung the caller asks for.

    `None` means the key is absent entirely, which is every diff stored before
    `99de440` -- the case the fix must stay silent on rather than guess at.
    """
    scope = dict(DIFF_SCOPE)
    run_scope = dict(RUN_SCOPE)
    if basis is None:
        del scope["pages_fetched_basis"]
        del run_scope["pages_fetched_basis"]
    else:
        scope["pages_fetched_basis"] = basis
        run_scope["pages_fetched_basis"] = basis
    a = {"id": "run-a", "finished_at": "2026-08-01T00:00:00+10:00",
         "composite_score": 70.0, "scope": None}
    b = {"id": "run-b", "finished_at": "2026-08-20T00:00:00+10:00",
         "composite_score": 74.0, "scope": run_scope}
    diff = {"new": [], "resolved": [], "persisting": [], "not_rechecked": [],
            "scope": scope}
    markdown, _ = render_comparison_report({"domain": "x.test"}, a, b, diff,
                                           audience)
    return markdown


def _scope_sentence(markdown: str) -> str:
    line = [ln for ln in markdown.splitlines()
            if ln.startswith("Comparison scope:")]
    assert line, "the document states no comparison scope at all"
    return line[0]


# --- the rung reaches the client deliverable -------------------------------

@pytest.mark.parametrize("basis", ["derived", "attempted"])
def test_a_count_that_was_not_recorded_says_so_where_it_is_rendered(basis):
    """The finding, stated as an assertion.

    Matched on the owned note rather than on prose, so the wording stays free
    to change and the fact does not.
    """
    sentence = _scope_sentence(_comparison(basis))

    assert PAGES_FETCHED_BASIS_NOTE[basis] in sentence, (
        f"a page count arrived at by {basis!r} is rendered indistinguishably "
        f"from one the crawler recorded: {sentence!r}")


def test_a_recorded_count_carries_no_qualifier():
    """The ordinary rung stays quiet, or the unusual one carries no weight.

    Asserted against the other two notes rather than against the absence of a
    parenthesis: the sentence already carries one where the path count
    differs, so "no bracket" would be the wrong observable.
    """
    sentence = _scope_sentence(_comparison("recorded"))

    for rung in ("derived", "attempted"):
        assert PAGES_FETCHED_BASIS_NOTE[rung] not in sentence, (
            "a count the crawler recorded is qualified as though it had been "
            f"reconstructed: {sentence!r}")


def test_a_diff_stored_before_the_rung_existed_says_nothing_about_it():
    """Absent is not `attempted`.

    A diff written before `99de440` did not record how its count was arrived
    at, and standing the worst rung in for silence would put a caveat on a
    client document on no evidence -- the same class of invention the rung
    exists to prevent.
    """
    sentence = _scope_sentence(_comparison(None))

    for note in PAGES_FETCHED_BASIS_NOTE.values():
        assert note not in sentence, (
            "a comparison that recorded no basis states one anyway: "
            f"{sentence!r}")


def test_the_baseline_sentence_carries_the_rung_too():
    """`_run_phrase` is shared by both sentences, and WF-28's whole case is
    that the baseline's frame was left off a document that framed the current
    run. A rung reaching one sentence and not the other repeats it."""
    scope = {**DIFF_SCOPE, "pages_fetched_baseline": 9,
             "pages_fetched_basis_baseline": "attempted",
             "pages_crawled_baseline": 9,
             "dimensions_baseline": ["ONP"]}
    a = {"id": "run-a", "finished_at": "2026-08-01T00:00:00+10:00",
         "composite_score": 70.0, "scope": None}
    b = {"id": "run-b", "finished_at": "2026-08-20T00:00:00+10:00",
         "composite_score": 74.0, "scope": RUN_SCOPE}
    markdown, _ = render_comparison_report(
        {"domain": "x.test"}, a, b,
        {"new": [], "resolved": [], "persisting": [], "not_rechecked": [],
         "scope": scope}, "client")

    # `Baseline scope:`, not `Baseline run` — the document already opens
    # with a `Baseline run \`run-a\` versus current run \`run-b\`` line that
    # names the pair rather than framing either, and the first draft of this
    # test matched that one and passed the wrong sentence to the assertion.
    # The dead end is left named because the two prefixes differ by one word
    # and the wrong one is the more obvious guess.
    baseline = [ln for ln in markdown.splitlines()
                if ln.startswith("Baseline scope:")]
    assert baseline, "the document states no baseline scope at all"
    assert PAGES_FETCHED_BASIS_NOTE["attempted"] in baseline[0], (
        "the baseline's page count is an attempt count and the sentence "
        f"framing it does not say so: {baseline[0]!r}")


# --- and the run report, which is the other Python surface -----------------

def test_the_run_report_crawl_scope_line_carries_the_rung():
    """`_scope_lines` renders the same count from the same stored dict.

    A different sentence in a different document, and the rung is the same
    fact -- so a fix reaching only the comparison is CQ-04's own shape: one
    quantity, two surfaces, one of them corrected.
    """
    # `tier` and `engine_version` are not optional to this renderer — the
    # header line reads them directly and a run dict without them raises
    # `KeyError` before a single scope line is built. Read off the real
    # signature after that failure rather than guessed at a second time.
    run = {"id": "run-b", "finished_at": "2026-08-20T00:00:00+10:00",
           "composite_score": 74.0, "tier": "T2", "engine_version": "0.9.0",
           "scope": {**RUN_SCOPE, "pages_fetched_basis": "attempted"},
           "subscores": {}, "dimensions": ["ONP"]}
    # `(site, run, audience, shared_cause=None, ...)` — findings ride on the
    # run dict, they are not a positional. Passing a list where `audience`
    # goes put "client" into `shared_cause` and raised inside
    # `_shared_cause_lines`, which is a long way from the mistake.
    markdown, _ = render_run_report({"domain": "x.test"}, run, "client")

    line = [ln for ln in markdown.splitlines()
            if ln.startswith("Crawl scope:")]
    assert line, "the run report states no crawl scope at all"
    assert PAGES_FETCHED_BASIS_NOTE["attempted"] in line[0], (
        f"the run report renders an attempt count as a page count: {line[0]!r}")


# --- and the screen, which cannot import the wording -----------------------

def test_the_compare_screen_reads_the_rung_and_uses_the_same_words():
    """DISCIPLINE rule 4 -- evidence the key is read and the wording agrees,
    not evidence of what is painted; the rendered sweep is what paints it.

    Scoped to `scopeCount` and to `CompareResult`'s own scope declaration
    rather than to the file, for CQ-85's reason: `pages_fetched` appears
    elsewhere in this module on a different payload, so a document-wide
    membership test passes on a string with nothing to do with the
    comparison.
    """
    view = Path("dashboard/src/views.tsx").read_text(encoding="utf-8")

    declared = re.search(r"scope\?: \{(.*?)\}", view, re.S)
    assert declared, "CompareResult no longer declares a scope at all"
    assert "pages_fetched_basis" in declared.group(1), (
        "the compare screen's payload type does not carry "
        "`pages_fetched_basis`, so the rung stops at the wire")

    # From the note table rather than from `function scopeCount`: the words
    # live in a `const` above the function, so a slice starting at the
    # function is scoped past the thing it was written to read. Found by the
    # assertion, not by inspection, and named here because the obvious anchor
    # is the wrong one.
    start = view.index("const BASIS_NOTE")
    body = view[start:view.index("export function CompareView", start)]
    assert "scopeCount" in body, (
        "the slice no longer reaches the function that uses the notes, so "
        "this test would pass on a table nothing reads")
    for rung in ("derived", "attempted"):
        assert PAGES_FETCHED_BASIS_NOTE[rung] in body, (
            f"the screen states the {rung!r} rung in different words from the "
            "document, so an operator reading both is told two things")
