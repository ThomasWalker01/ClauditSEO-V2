"""The frame the two composites under `## Score movement` were computed under.

UX-86 (High, raised in report 092, carried unmoved through 094) and the
operator decision that gates it, `QUESTIONS.md` **Q-13**.

**The finding.** `render_comparison_report` printed `## Score movement` as two
composites and nothing else. Measured on the pair the operator's database
holds and that two fix steps generated client deliverables for: baseline
`8fdeb042` is **T2 over seven dimensions, composite 91.06**; current
`f80bc200` is **T3 over eight, composite 70.52**, and A11Y was audited only by
the current run. `site_trend` would mark that pair `comparable: False` on tier
alone — its comment at `clauditseo/persistence/runs.py:2724-2726` names these
two numbers as the case tier was added to the key for — but the document never
asks it. The two scope sentences above the heading do not cover this: the
baseline one scopes itself explicitly to *New issues and Resolved issues*,
which directs the reader not to apply it here.

**The question and the answer.** Q-13 asked whether a section comparing two
runs that are not comparable should still print both composites, or decline to
print a movement and say why. The operator answered **print both, framed**
(2026-08-23): keep the two composites and add one sentence naming each run's
tier and the dimensions the other never audited. The document states the facts
and leaves the inference unmade — so nothing here asserts what a
91.06-to-70.52 movement *means*, and a guard demanding such a sentence would
be guarding the answer the operator did not give.

**The rule this file guards: the section states the frame both composites were
computed under, or says it could not establish it.** Silence is not an option,
for the reason `_diff_scope_lines` already gives one heading up — the figures
are printed regardless, so an absent frame is not a fact withheld but two
numbers with nothing holding them.

**Symmetry is part of the rule, not decoration.** The half of UX-86 that is
not silence is that the framing which *was* present pointed the wrong way:
`_breadth_phrase` attached *measured across 235 of 272 discovered pages
(86.4%)* to the current composite and nothing to the baseline — so the run
that read 99 paths and never audited A11Y was the one that read as
unqualified. A frame naming one run's tier and not the other's would reproduce
that defect in the sentence written to close it.

Both reports give the cause of that silence as *the baseline stored no sitemap
total*. Measured read-only over `data/clauditseo.db` while this file was being
written, it is not: `8fdeb042` has `has_evidence` **False** and `scope`
**None**, so it stored no crawl record at all. The correction matters because
it decides how many sentences the document needs — four causes make
`_breadth_phrase` silent and they are not the same fact, one of them being
that the run reached everything its site declared, which *is* completeness.

DISCIPLINE rule 3 — the consumers of a run's `tier` and `dimensions` in a
rendered document, enumerated by grep rather than taken from the report's
list: `render_run_report` (`clauditseo/reporting/render.py`, which prints the
tier in its own header), `render_trend_report` (via `site_trend`'s rows), and
`render_comparison_report`, which is the one that had neither. `site_trend`
itself is WF-58 and is deliberately **not** touched here: its comparability
key still cannot see the dimension set, and giving `render_comparison_report`
a predicate to call is the next step rather than this one.
"""

import pytest

from clauditseo.reporting.checks import unsourced_number_lines
from clauditseo.reporting.render import render_comparison_report

#: The eight dimensions the current run of the measured pair audited, and the
#: seven the baseline did. The real values, not a reduced fixture: the
#: difference this section has to state is one dimension out of eight, which
#: is the hardest size to notice and the size the defect actually shipped at.
DIMS_CURRENT = ["A11Y", "AIS", "CNT", "LOC", "OFP", "ONP", "PRF", "TEC"]
DIMS_BASELINE = [d for d in DIMS_CURRENT if d != "A11Y"]

#: `diff["scope"]` as `compare_runs` assembles it. Present so the document
#: renders its other frame sentences and this file's assertions have to find
#: their own line among them rather than matching the first frame on the page.
DIFF_SCOPE = {"pages_crawled": 224, "pages_fetched": 235,
              "pages_fetched_basis": "recorded", "dimensions": DIMS_CURRENT,
              "pages_crawled_baseline": 99, "pages_fetched_baseline": 99,
              "pages_fetched_basis_baseline": "derived",
              "dimensions_baseline": DIMS_BASELINE}

#: Run B's stored scope: 235 readable pages of the 272 the sitemap declares,
#: so `_breadth_phrase` states a ratio beside the current composite.
SCOPE_CURRENT = {"pages_fetched": 235, "pages_fetched_basis": "recorded",
                 "discovered": 272, "robots_blocked": 0, "truncated_by": None}

#: Run A's: crawl evidence, but no declared total, so `_breadth_phrase` is
#: silent beside the baseline composite.
#:
#: **Not the live baseline's shape, and the difference is the point.** Reports
#: 092 and 094 both state the cause of the asymmetry as *the baseline stored
#: no sitemap total*. Measured read-only over `data/clauditseo.db` while this
#: was being written, `8fdeb042` has `has_evidence` **False** and `scope`
#: **None** — it stored no crawl record at all, which is a different cause one
#: rung further back. Both are real and both are here: this constant is the
#: report's cause, `SCOPE_NONE` below is the operator's. A single sentence over
#: the two would have been false for the run the finding was raised on.
SCOPE_BASELINE = {"pages_fetched": 99, "pages_fetched_basis": "derived",
                  "discovered": None, "robots_blocked": 0,
                  "truncated_by": None}

#: What `get_run` returns for run `8fdeb042` today: nothing.
SCOPE_NONE = None


def _render(a_extra: dict | None = None, b_extra: dict | None = None,
            audience: str = "client") -> str:
    a = {"id": "8fdeb0421539437da618bd2c18c596e2",
         "finished_at": "2026-08-17T00:00:00+10:00", "composite_score": 91.06,
         "tier": "T2", "dimensions": DIMS_BASELINE, "scope": SCOPE_BASELINE,
         **(a_extra or {})}
    b = {"id": "f80bc20010ac4439afbb6f638edb89d2",
         "finished_at": "2026-08-17T00:00:00+10:00", "composite_score": 70.52,
         "tier": "T3", "dimensions": DIMS_CURRENT, "scope": SCOPE_CURRENT,
         **(b_extra or {})}
    diff = {"new": [], "resolved": [], "persisting": [], "not_rechecked": [],
            "scope": DIFF_SCOPE}
    markdown, _ = render_comparison_report({"domain": "x.test"}, a, b, diff,
                                           audience)
    return markdown


def _movement_section(markdown: str) -> str:
    """Everything between `## Score movement` and the next heading.

    Scoped rather than searched whole, for CQ-203's reason: the two scope
    sentences above this heading already name both runs' dimensions, so an
    assertion against the whole document would be satisfied by a frame that
    is nowhere near the figures it frames.
    """
    lines = markdown.splitlines()
    start = [i for i, ln in enumerate(lines) if ln == "## Score movement"]
    assert start, "the document has no `## Score movement` section at all"
    rest = lines[start[0] + 1:]
    end = [i for i, ln in enumerate(rest) if ln.startswith("## ")]
    return "\n".join(rest[:end[0]] if end else rest)


def _frame_sentence(markdown: str) -> str:
    section = _movement_section(markdown)
    line = [ln for ln in section.splitlines() if ln.startswith("Score frame:")]
    assert line, (
        "the section states no frame for its two composites, so a 91.06 "
        "computed at T2 over seven dimensions and a 70.52 computed at T3 "
        "over eight are printed four lines apart as a movement — UX-86, "
        "reproduced in a client deliverable already on disk. Section was:\n"
        f"{section}")
    return line[0]


@pytest.mark.parametrize("audience", ["client", "internal"])
def test_the_section_names_both_tiers_and_the_dimension_only_one_run_audited(
        audience):
    """The finding, stated as an assertion, on the measured pair's own shape."""
    sentence = _frame_sentence(_render(audience=audience))

    assert "T2" in sentence and "T3" in sentence, (
        "the frame names neither tier or only one of them, and the tier is "
        f"the term `site_trend` would refuse this pair on: {sentence!r}")
    assert "A11Y" in sentence, (
        "the one dimension the baseline never audited is not named, so the "
        "reader is not told which part of the score is new rather than "
        f"worse: {sentence!r}")
    assert "current run" in sentence, (
        "the frame does not say which run A11Y was audited by, which is the "
        f"whole of what makes the difference readable: {sentence!r}")
    assert "source:" in sentence, (
        "a stated frame carries provenance like every other claim in the "
        f"document: {sentence!r}")


def test_the_frame_is_stated_above_the_composites_it_frames():
    """WF-02's rule, applied to the section it was never applied to: a frame
    printed under the figures it frames is a footnote."""
    section = _movement_section(_render())

    assert section.index("Score frame:") < section.index("- Baseline composite:"), (
        "the frame is printed below the two figures it frames, which is the "
        "shape WF-02's fix rejected for the comparison's other counts")


def test_a_dimension_only_the_baseline_audited_is_named_too():
    """Symmetry, which is the half of UX-86 that was not silence.

    A current run that dropped a dimension the baseline audited breaks the
    comparison in exactly the same way and in the direction that flatters the
    current score. A frame that only ever names what the baseline missed
    would state one of those two cases and be silent on the other.
    """
    sentence = _frame_sentence(_render(
        a_extra={"dimensions": DIMS_CURRENT},
        b_extra={"dimensions": [d for d in DIMS_CURRENT if d != "LOC"]}))

    assert "LOC" in sentence and "baseline run" in sentence, (
        "a dimension audited only by the baseline is not named, so a current "
        "run that dropped a weak dimension reports an improvement with "
        f"nothing on the page saying where it came from: {sentence!r}")


def test_two_like_for_like_runs_are_told_they_are():
    """The frame is a frame, not a warning.

    Where the two runs agree on tier and on dimension set, the section says
    so. Printing the sentence only on a mismatch would make its absence carry
    the meaning "comparable", which is a fact asserted by silence — the thing
    this document is not allowed to do.
    """
    sentence = _frame_sentence(_render(
        a_extra={"tier": "T3", "dimensions": DIMS_CURRENT}))

    assert "T3" in sentence, f"the shared tier is not stated: {sentence!r}"
    assert "the same 8 dimensions" in sentence, (
        "two runs over the same dimension set are not told they are, so the "
        "reader cannot tell a like-for-like pair from an unframed one: "
        f"{sentence!r}")


def test_a_shared_dimension_set_at_two_tiers_still_says_the_sets_agree():
    """The mixed case, which is the one a plain "they match" sentence gets
    wrong: the tiers differ, so the pair is not like-for-like, but the
    dimension set is not what makes it so. Saying nothing about the
    dimensions here would leave the reader to assume the worse of the two."""
    sentence = _frame_sentence(_render(a_extra={"dimensions": DIMS_CURRENT}))

    assert "T2" in sentence and "T3" in sentence, (
        f"the two differing tiers are not both named: {sentence!r}")
    assert "Both runs audited the same dimensions." in sentence, (
        "the dimension set agrees and the document does not say so, so a "
        f"tier difference reads as covering both terms: {sentence!r}")


@pytest.mark.parametrize("missing", [{"tier": None}, {"dimensions": []}])
def test_a_run_whose_frame_was_not_recorded_gets_the_not_assessed_shape(
        missing):
    """No fabrication and no silence, which is the product's standing rule
    for a fact it cannot establish."""
    section = _movement_section(_render(a_extra=missing))

    assert "[TO CONFIRM:" in section, (
        "a run with no recorded tier or no recorded dimension set produced "
        "either a fabricated frame or none at all; the product's shape for "
        f"a fact it could not establish is `[TO CONFIRM: …]`. Section:\n"
        f"{section}")
    assert "Score frame:" not in section, (
        "the frame sentence was printed for a pair one side of which has no "
        "frame on record, which asserts what it could not read")


def test_a_coverage_ratio_on_only_one_composite_says_why_the_other_has_none():
    """The asymmetry UX-86 names, in the direction it actually pointed.

    On the measured pair the ratio sits on the *more* complete run: the
    baseline declared no sitemap total, so `_breadth_phrase` is silent beside
    it and the run that read 99 paths reads as the unqualified one. The
    absence has to state its own cause, because the three causes
    `_breadth_phrase` is silent for are not the same fact — a run that
    reached everything its site declared is silent for a reason that *is*
    completeness, and a document may not print one sentence over both.
    """
    section = _movement_section(_render())

    assert "coverage ratio" in section, (
        "only the current composite carries `measured across 235 of 272 "
        "discovered pages (86.4%)` and nothing on the page says why the "
        f"baseline carries none. Section:\n{section}")
    assert "declared no page total" in section, (
        "the absent ratio is stated without its cause, so a reader cannot "
        "tell the baseline from a run that was measured in full")


def test_the_absent_ratio_states_the_cause_the_live_baseline_actually_has():
    """The same section on the shape the operator's database holds.

    Reports 092 and 094 both give the cause as *the baseline stored no sitemap
    total*. It is not: measured read-only over `data/clauditseo.db`,
    `8fdeb042` has `has_evidence` False and `scope` None, so the run stored no
    crawl record at all and the missing total is one rung further forward than
    the finding says. A document printing the report's wording for this run
    would state a cause the run does not have — which is why the four causes
    `_breadth_absence` distinguishes are four and not one.
    """
    section = _movement_section(_render(a_extra={"scope": SCOPE_NONE}))

    assert "stored no crawl record" in section, (
        "the live baseline's absent coverage ratio is explained by a cause "
        f"that is not its own. Section:\n{section}")
    assert "declared no page total" not in section, (
        "the report's wording was printed for a run whose evidence row does "
        "not exist, which asserts a fact about a record there is none of")


def test_a_pair_that_both_reached_everything_declared_is_not_told_otherwise():
    """The counter-assertion, and rule 5's shape: the sentence above must be
    able to be absent. Two runs neither of which carries a ratio have no
    asymmetry to explain, and inventing one would be the defect reversed."""
    complete = {"pages_fetched": 10, "pages_fetched_basis": "recorded",
                "discovered": 10, "robots_blocked": 0, "truncated_by": None}
    section = _movement_section(_render(a_extra={"scope": complete},
                                        b_extra={"scope": complete}))

    assert "coverage ratio" not in section, (
        "a sentence explaining an absent coverage ratio was printed for a "
        f"pair where neither composite carries one. Section:\n{section}")


@pytest.mark.parametrize("audience", ["client", "internal"])
def test_the_new_sentences_carry_their_own_provenance(audience):
    """Gate G7 over the whole document, not only the lines added.

    The frame states dimension counts, and a count with no source tag is
    exactly what `unsourced_number_lines` refuses — the check that has
    blocked a real client document twice.
    """
    flagged = unsourced_number_lines(_render(audience=audience))

    assert flagged == [], (
        f"the document no longer passes the honesty gate: {flagged}")


def test_the_run_that_read_everything_is_not_told_it_read_too_little():
    """UX-89. The fourth cause, in the one pairing that prints it.

    `_breadth_absence` names four causes and the caller's sentence is shaped
    for three of them: a colon, then the reason a composite *lacks* a coverage
    ratio. The fourth is not a lack. A run that reached every page its site
    declared is silent for a reason that is completeness, and printed through
    the deficiency sentence it reads as a shortfall — on the measured pair,
    the run that read 100% of what it declared reads as the qualified one
    beside a run that read 86.4%.

    The module's own docstring at `clauditseo/reporting/render.py:1177-1181`
    already says this ("one of the four causes `_breadth_absence`
    distinguishes is a run that reached everything its site declared, for
    which the absence *is* completeness"), so the finding is the code not
    doing what the comment beside it states.

    **The population is asserted, not assumed.** The pairing has to be one
    where exactly one side is silent and the silent one is the complete one;
    if the section carried no asymmetry sentence at all this test would pass
    on a document that says nothing, which is the vacuity the profile's
    guard-population invariant names.
    """
    complete = {"pages_fetched": 10, "pages_fetched_basis": "recorded",
                "discovered": 10, "robots_blocked": 0, "truncated_by": None}
    section = _movement_section(_render(a_extra={"scope": complete}))

    assert "coverage ratio" in section, (
        "the population is empty: this pairing must print the asymmetry "
        f"sentence for the assertion below to mean anything. Section:\n"
        f"{section}")
    assert "reached every page its site declared" in section, (
        "the completeness cause is not the one being stated, so this test is "
        f"not exercising the case it was written for. Section:\n{section}")

    assert "ratio: the baseline run reached every page" not in section, (
        "the baseline reached every page its site declared and the current "
        "run reached 86.4% of its own, and the document offers the "
        "baseline's completeness as the reason it carries no ratio — the "
        "more complete run reads as the less qualified one, in the sentence "
        f"written to stop exactly that misreading. Section:\n{section}")
