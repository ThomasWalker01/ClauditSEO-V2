"""The comparison deliverable states the frame its counts were computed under.

WF-02, first named in report 023 and carried by every report since — 67 of
them — as *"the frame the comparison was computed under is stored and not
used by the document that needs it"*.

`compare_runs` has returned a `scope` key since the round-023 delta added it
(`clauditseo/persistence/runs.py`, `{"pages_crawled": …, "dimensions": […]}`),
and the comment above it says why: *"the diff carries the scope it was
computed under, so no surface has to restate it and none can restate it
differently."* Two surfaces read that diff. The screen takes the scope and
prints it (`dashboard/src/CompareView`). The client document did not — it
printed four counts, "New issues", "Resolved issues", "Persisting issues" and
"Not re-checked", with nothing anywhere on the page saying how many pages the
current run fetched or which dimensions it audited. A reader given "Resolved
issues — 12" cannot tell a fixed site from a narrower crawl, which is the same
class of error the "Not re-checked" section itself was added to remove.

Written over the shapes `compare_runs` can actually produce rather than the
one the happy path produces: `pages_crawled` is `None` whenever the current
run stored no crawl record, and a document that prints that as a number would
be inventing the fact this guard exists to state.

DISCIPLINE rule 3 — the consumers of `diff["scope"]` were enumerated by grep
before this was written, and there are two. The renderer is the one this file
fixes; the screen already reads it, and the last test here is a tripwire on
that second consumer so a later change cannot quietly leave one surface
stating the frame and the other silent.
"""

from pathlib import Path

from clauditseo.reporting import checks
from clauditseo.reporting.render import (DIFF_SCOPE_KEY,
                                         render_comparison_report)

#: Every bucket the renderer counts. Driving the fixture from this rather
#: than describing it: a bucket added to the renderer and not here would be
#: a count with no frame, which is the finding.
BUCKETS = ("new", "resolved", "persisting", "not_rechecked")


#: CQ-203. Both runs carried `"scope": None` here for ten reports, and that
#: is not a neutral fixture: `_breadth_phrase` is silent on a null scope
#: (`_breadth_absence`'s first cause, "stored no crawl record"), so every
#: document this file rendered came out with no coverage ratio beside either
#: composite. The whole of `## Score movement`'s breadth clause — the thing
#: WF-02's own commit shipped and CQ-70 later rewrote — was outside every
#: assertion below, and the guard could not have seen a defect in it.
#:
#: A real scope on both runs, with different ratios, so the clause renders
#: twice and the two are distinguishable. The numbers are deliberately not
#: 15: `pages_crawled: 15` is the DIFF's frame and these are the RUNS' own,
#: two different facts that the substring assertions below used to conflate.
_RUN_SCOPE_A = {"pages_fetched": 40, "discovered": 200,
                "discovered_basis": "sitemap"}
_RUN_SCOPE_B = {"pages_fetched": 60, "discovered": 200,
                "discovered_basis": "sitemap"}


def _runs() -> tuple[dict, dict]:
    a = {"id": "run-a", "finished_at": "2026-08-01T00:00:00+10:00",
         "composite_score": 70.0, "scope": dict(_RUN_SCOPE_A)}
    b = {"id": "run-b", "finished_at": "2026-08-20T00:00:00+10:00",
         "composite_score": 74.0, "scope": dict(_RUN_SCOPE_B)}
    return a, b


def _frame(markdown: str) -> list[str]:
    """The scope sentence, and only it.

    CQ-203's second half. Three assertions in this file were whole-document
    substring matches — `"15" in markdown`, `dimension in markdown` — which
    any occurrence anywhere satisfies, including one in a section that has
    nothing to do with the frame. `test_an_unrecorded_page_count_is_said_
    rather_than_printed` below already scoped itself this way and said why;
    the rest now do the same, from one helper rather than four spellings.
    """
    return [line for line in markdown.splitlines()
            if line.startswith("Comparison scope:")]


def _composites(markdown: str) -> list[str]:
    """The two composite lines, which are where the RUNS' own breadth clause
    renders — the half of `## Score movement` the null-scope fixture made
    unreachable."""
    return [line for line in markdown.splitlines()
            if line.startswith("- Baseline composite:")
            or line.startswith("- Current composite:")]


def _diff(scope) -> dict:
    d = {bucket: [] for bucket in BUCKETS}
    if scope is not _ABSENT:
        d["scope"] = scope
    return d


#: Distinct from `None`: `compare_runs` always writes the key, but a diff
#: built by an older renderer's caller, or by a test, may not carry it at
#: all. The two are different facts and the document says both.
_ABSENT = object()


def _render(scope, audience: str = "client") -> str:
    markdown, _ = render_comparison_report(
        {"domain": "example.test"}, *_runs(), _diff(scope), audience)
    return markdown


def test_the_document_states_the_pages_and_the_dimensions_it_compared():
    markdown = _render({"pages_crawled": 15, "dimensions": ["OFP", "PRF", "TEC"]})
    frame = _frame(markdown)

    # CQ-203: scoped to the frame sentence rather than to the document. A
    # whole-document `"15" in markdown` is satisfied by a 15 in any section,
    # including one this test has no claim about, and with the runs carrying
    # their own populations there are now three other counts in the file.
    assert frame, "the comparison document has no scope sentence at all"
    assert any("15" in line for line in frame), (
        "the comparison document does not state how many pages the current "
        f"run fetched, so its four counts have no frame: {frame}")
    for dimension in ("OFP", "PRF", "TEC"):
        assert any(dimension in line for line in frame), (
            f"the scope sentence does not name {dimension}, one of the "
            f"dimensions the current run audited: {frame}")


def test_the_frame_is_stated_before_the_first_count_it_frames():
    """A frame printed under the counts is a footnote, not a frame."""
    markdown = _render({"pages_crawled": 15, "dimensions": ["PRF"]})
    lines = markdown.splitlines()

    frame = next(i for i, line in enumerate(lines) if "15" in line
                 and "composite" not in line.lower())
    first_count = next(i for i, line in enumerate(lines)
                       if line.startswith("## New issues"))
    assert frame < first_count, (
        "the scope sentence appears after the first count it frames")


def test_the_frame_carries_its_provenance_like_every_other_figure():
    """The product's rule for a number in prose, applied to this one.

    `checks.unsourced_number_lines` is the gate `assert_report_honest` runs
    on every generation, so a scope sentence without a tag would not merely
    be inconsistent — it would refuse to generate.
    """
    markdown = _render({"pages_crawled": 15, "dimensions": ["PRF"]})

    assert checks.unsourced_number_lines(markdown) == [], (
        "the comparison document carries a number with no source tag")


def test_an_unrecorded_page_count_is_said_rather_than_printed():
    """`pages_crawled` is None whenever the current run stored no crawl
    record. Printing that is how `None (source: engine, confidence: high)`
    reached a client once already.

    Scoped to the scope sentence rather than to the whole document: `- None.`
    is the placeholder an empty bucket has always printed, it predates this
    change and it is a different fact. A document-wide `"None" not in` would
    fail on it and say nothing about the page count.
    """
    markdown = _render({"pages_crawled": None, "dimensions": ["PRF"]})

    frame = [line for line in markdown.splitlines()
             if line.startswith("Comparison scope:")]
    assert all("None" not in line for line in frame), (
        f"the scope sentence prints a null page count as a figure: {frame}")
    assert all("page" not in line for line in frame), (
        f"the scope sentence claims a page count it does not have: {frame}")
    assert "Not assessed: the pages this comparison was computed over" in markdown, (
        "the document neither states the page count nor says it could not")
    assert "PRF" in markdown, (
        "the half of the frame that is known was dropped with the half that "
        "is not")


def test_a_diff_carrying_no_scope_at_all_says_so(): 
    """Silence is the failure this finding is about. A document that omits
    the frame reads exactly like one whose crawl was complete."""
    markdown = _render(_ABSENT)

    assert "Not assessed" in markdown, (
        "a comparison with no recorded scope produces a document that says "
        "nothing about its own frame")


def test_the_internal_audience_is_told_the_frame_too():
    """The audience distinction is what is explained, never which facts are
    stated — the operator reading the internal copy needs the frame most."""
    markdown = _render({"pages_crawled": 15, "dimensions": ["PRF"]}, "internal")
    frame = _frame(markdown)

    assert frame, "the internal copy has no scope sentence"
    assert any("15" in line and "PRF" in line for line in frame), (
        f"the internal copy's scope sentence is missing half the frame: {frame}")


def test_each_composite_carries_the_breadth_its_own_run_was_measured_over():
    """CQ-203's first half, as a claim rather than as a fixture note.

    Both runs in `_runs()` carried a null scope for ten reports, and
    `_breadth_phrase` is silent on one — so `## Score movement` printed two
    bare composites in every document this file rendered, and no assertion
    here could tell that from a renderer that had stopped emitting the clause
    altogether. The two runs are given DIFFERENT ratios so a phrase computed
    from the wrong run cannot satisfy this.
    """
    markdown = _render({"pages_crawled": 15, "dimensions": ["PRF"]})
    baseline, current = _composites(markdown)

    assert "20.0%" in baseline, (
        f"the baseline composite carries no coverage ratio: {baseline!r}")
    assert "30.0%" in current, (
        f"the current composite carries no coverage ratio: {current!r}")


def test_the_screen_still_reads_the_same_scope_key():
    """Tripwire on the other consumer of the diff's scope, not evidence it
    renders — DISCIPLINE rule 4. What it can say is that the screen has not
    stopped reading the key while the document started, which is the split
    that let the two surfaces disagree for 67 reports.

    The spelling is derived from `DIFF_SCOPE_KEY` rather than written out.
    Until round 108 this hardcoded `data.scope`, so renaming the Python
    constant moved the document and left this green — CQ-204. The assertion
    it makes is unchanged; only where the key comes from is.
    """
    view = Path("dashboard/src/views.tsx").read_text(encoding="utf-8")

    assert f"data.{DIFF_SCOPE_KEY}" in view, (
        "the screen no longer reads the diff's scope; the two consumers of "
        "compare_runs' scope have diverged again")
    assert "pages_crawled" in view, (
        "the screen no longer names pages_crawled")


# --- UX-85, taken at round 103 -----------------------------------------------
#
# The strict xfail round 102 recorded here is retired, by the mechanism it was
# recorded for: the fix made this XPASS, which reddened the suite, which is
# what forced the marker off rather than leaving a passing test wearing an
# `xfail`. Round 102's reason for not taking it then — the fix changes what a
# client deliverable says, so it owns a `RENDERER_VERSION` bump and a
# `CHANGELOG.md` entry and cannot ride in a commit about `views.tsx` — is
# discharged by this round having exactly that as its whole lever
# (`RENDERER_VERSION` 1.33.0).
#
# This test stays where round 102 put it and asserts what it always asserted.
# The other two surfaces the same rule reaches — the run report's header and
# the score-movement difference clause, neither named by the finding — are in
# `tests/test_a_client_document_can_read_its_own_dimension_names.py`, together
# with the source guard that would have found them.

def test_the_client_copy_does_not_name_dimensions_in_internal_acronyms():
    """The audience test, applied to the frame the audience was given.

    `render.py`'s own rule is that the audience distinction is what is
    EXPLAINED, never which facts are stated — which is why the internal copy
    is not asserted on here. A client handed 'audited A11Y, AIS, CNT' has the
    fact and not the meaning, and the frame exists to be read.

    The registry already holds the words: every module carries a `name`
    ('Accessibility' for A11Y), so this is a lookup rather than a new
    vocabulary to invent and keep in step.
    """
    markdown = _render({"pages_crawled": 15,
                        "dimensions": ["A11Y", "OFP", "PRF"]}, "client")
    frame = _frame(markdown)

    assert frame, "the client copy has no scope sentence"
    sentence = " ".join(frame)
    # The words the registry already holds for these three. A key beside the
    # acronym satisfies this as well as a replacement does — the requirement
    # is that the client can read the frame, not which of the two shapes it
    # takes.
    for code, word in (("A11Y", "Accessibility"), ("OFP", "Off-page"),
                       ("PRF", "Performance")):
        assert word.lower() in sentence.lower(), (
            f"the client copy names {code} with no key a client can read: "
            f"{frame}")
