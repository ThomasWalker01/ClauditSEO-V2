"""CQ-236: a report does not date a finding from an ID label alone.

The finding, first raised at report 107 and carried to report 119 — ten
Evidence-column citations, which is what brought it under `SKILL.md` step 4's
carried-cohort rule this round. Reports 098 through 106 each opened roughly
two hundred finding rows with a `**Claim as first raised in report NNN**:`
annotation, and the report number in it was found by matching the row's ID
*label* against the oldest report using that label. The auditor renumbered IDs
every round until report 088, so a label is not a finding: report 001's
`CQ-05` was an ownership check on `/api/client-reports/{report_id}`, fixed at
round 015 by `05389cb`, while the `CQ-05` row carrying that back-attribution
across nine reports was `cli.py`'s fixed-tier branch storing no crawl
evidence. One row, two unrelated defects, one of them fixed eighty-three
rounds before the header claiming it was first raised.

**What this guard enforces is the cheaper of the two remedies report 119
offered** (Phase 2, row 6): stop back-attributing by ID label at all, and let
"first raised" be derived from anchor continuity instead — which is what
`scripts/check_anchors.py`'s `anchor_ages` already does for paths, and what
`SKILL.md` step 4's cohort walk does when it counts citations per ID across
`audits/` under round 107's restriction to labels stable since report 088.
The expensive remedy — matching each claim's text against the named report's
same-ID row — needs fuzzy comparison of two prose cells and was not taken.

**The practice had already stopped, and that is why the guard is shaped this
way rather than as a repair.** Measured over the whole corpus at round 119:
1,644 annotations, every one of them in reports 098-106, none in report 107
or later. Report 107 is where CQ-236 was raised and where the auditor stopped
writing them, unguarded, by hand. Nothing prevented their return, which is
CQ-236's own closing sentence: *"the mechanism that produced this is untouched
and will do it again at the next ID collision."* This is that mechanism.

**Committed reports are not edited to satisfy this.** `audits/**` is absent
from `test_loop_instructions.py`'s `REGISTER_FILES` for that reason, and
`audit-fix/SKILL.md` step 2 says a round may not touch a report it did not
write. So the historical window is not asserted away with a frozen count
either — a hand-copied constant taken once off a report is CQ-160's exact
shape, still open. The confinement is derived: every annotation must live in
a report at or before 106, and that is checked against the tree.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.private_register import needs_register

AUDITS = Path(__file__).resolve().parents[1] / "audits"

#: A report file: three digits, a date, `.md`. `DISPOSITIONS.md` is not one
#: and is excluded by the pattern rather than by name, so a second register
#: added beside it needs no change here.
REPORT = re.compile(r"^(\d{3})-\d{4}-\d{2}-\d{2}\.md$")

#: A findings-table row: the ID cell, then the rest of the line.
ROW = re.compile(r"^\|\s*((?:CQ|WF|UX|UI)-\d+)\s*\|(.*)$")

#: The annotation, and only where it *leads* the row's own second cell. The
#: distinction is load-bearing and was measured rather than assumed: a loose
#: search for the phrase returns 1,677 hits and a violation, but that
#: violation is report 107's CQ-236 row *quoting* the phrase inside double
#: quotes while describing the defect. Reading a quotation as a claim is the
#: same mistake CQ-236 is about, one level up, so the extractor matches the
#: annotation in the position the annotation actually occupies. This is the
#: treatment `check_anchors.py` already gives its own quoted-as-defect case.
LEADING = re.compile(r"^\s*\*{0,2}Claim as first raised in report (\d{3})\*{0,2}\s*:")

#: The last report that carries the practice. Derived from the corpus by the
#: population test below rather than trusted from here: if a claim ever
#: appears in a later report this constant is not what fails, the assertion
#: naming the offending file is.
LAST_WINDOW_REPORT = 106

#: Where a label stopped being renumbered, so where a label and a finding
#: become the same thing. Round 107's cohort restriction, and the reason a
#: claim below it cannot be sound.
STABLE_FROM = 88

#: Reports read for their labels but not held to the rule, each with the
#: reason. A committed report may not be edited to make a guard pass any more
#: than to make one fail, and the loop forbids the round that meets a red
#: report from editing it - so a report that breaks the rule after the fact
#: is named here, once, with why, rather than rewritten (`QUESTIONS.md` Q-46,
#: the operator's option 4, 2026-09-03). The prohibition itself moved into
#: `.claude/agents/auditor.md` in the same change, so this set should never
#: grow: a second entry means the prompt failed, not the guard.
QUARANTINED: dict[str, str] = {
    "139": "deep audit of 2026-09-02 (`f3b12ed`): 170 `Claim as first raised in "
           "report NNN` annotations, a practice abolished at report 107 (CQ-236), "
           "written by an auditor prompt that did not yet forbid it. Kept intact: "
           "it found KI-59, the applied draft migration, and a re-run might not.",
}


def _reports() -> dict[str, Path]:
    """Every report, keyed by its three-digit number. The population."""
    out = {}
    for p in sorted(AUDITS.glob("*.md")):
        m = REPORT.match(p.name)
        if m:
            out[m.group(1)] = p
    return out


def _claims(text: str) -> list[tuple[int, str, str]]:
    """`(line number, finding id, claimed report)` for each annotation."""
    found = []
    for i, line in enumerate(text.splitlines(), 1):
        m = ROW.match(line)
        if not m:
            continue
        lead = LEADING.match(m.group(2).split("|")[0])
        if lead:
            found.append((i, m.group(1), lead.group(1)))
    return found


def _corpus() -> tuple[dict[str, Path], list[tuple[str, int, str, str]]]:
    reports = _reports()
    claims = []
    for num, path in sorted(reports.items()):
        if num in QUARANTINED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line, fid, target in _claims(text):
            claims.append((path.name, line, fid, target))
    return reports, claims


@needs_register
def test_the_extractor_finds_the_annotations_it_is_about():
    """The population, derived from the tree and asserted non-empty.

    Every clause below is an is-empty assertion, so this is the one that
    stops them being vacuous. `PROFILE.md`'s guard-population invariant asks
    for exactly this, and asks that the population come from the tree rather
    than from a literal — so the count is compared against zero and against
    the number of reports, never against a copied figure.
    """
    reports, claims = _corpus()

    assert len(reports) > 100, sorted(reports)
    assert claims, (
        "no back-attribution annotation was found anywhere in audits/, so "
        "every clause in this file is vacuous. Either the corpus lost "
        "reports 098-106 or LEADING no longer matches how they are written")
    # More than one report, so the extractor is not keying on a single file,
    # and enough claims that the clauses below have something to be about.
    # Compared against the corpus rather than against a copied figure: the
    # first draft of this line asserted `>= 9` from a loose earlier count and
    # was wrong by one, because report 101 does not exist and report 107
    # carries only quotations. That is CQ-160's shape in miniature and it is
    # recorded rather than quietly corrected.
    carriers = {name for name, _, _, _ in claims}
    assert len(carriers) > 1, sorted(carriers)
    assert len(claims) > len(carriers), (
        "each carrier holds one claim, which is not how reports 098-106 are "
        f"written: {len(claims)} claims across {len(carriers)} reports")


def test_every_back_attribution_names_a_report_that_carries_that_id():
    """A claim resolves, or it is a citation to nothing.

    The weaker half of CQ-236 and the one the corpus already satisfies: the
    named report must exist and must actually mention the ID being dated.
    Kept because it is what makes the historical window *readable* — a
    reader auditing one of the 1,644 claims by hand can at least reach the
    row it points at — and because it is the clause that would catch a
    typo'd report number, which the confinement clause below cannot see.
    """
    reports, claims = _corpus()

    broken = []
    for name, line, fid, target in claims:
        if target not in reports:
            broken.append(f"{name}:{line} {fid} names report {target}, "
                          f"which does not exist")
            continue
        text = reports[target].read_text(encoding="utf-8", errors="replace")
        if not re.search(r"\b" + re.escape(fid) + r"\b", text):
            broken.append(f"{name}:{line} {fid} claims first raised in "
                          f"report {target}, which never mentions it")
    assert broken == [], broken


def test_no_report_after_the_window_dates_a_finding_by_its_label():
    """The fix. The practice stopped at report 107; this is what keeps it so.

    An ID label is only a finding from report 088 onward, so a claim reaching
    below that is a guess dressed as a citation — and 1,420 of the 1,644 in
    the corpus do reach below it. Rather than permit the sound subset and
    leave an escape hatch nobody uses, the annotation is refused outright in
    any report after the historical window: a report needing to date a
    finding derives it from anchor continuity, which is what the cohort walk
    and `check_anchors.anchor_ages` already do.

    The confinement is derived from the corpus, not asserted against a
    copied count — CQ-160 is open against precisely that shape.
    """
    _, claims = _corpus()

    late = [f"{name}:{line} {fid} -> report {target}"
            for name, line, fid, target in claims
            if int(name[:3]) > LAST_WINDOW_REPORT]
    assert late == [], (
        "a report after the historical window dates a finding by its ID "
        "label; IDs were renumbered every round before report "
        f"{STABLE_FROM:03d}, so this is a citation to whatever report used "
        f"the label first. Derive it from anchor continuity instead: {late}")


@pytest.mark.parametrize("fixture_report,expect", [
    ("107-2026-08-29.md", 0),
    ("098-2026-08-24.md", None),
])
def test_a_quotation_of_the_annotation_is_not_read_as_one(fixture_report,
                                                          expect):
    """Report 107 quotes the header while describing the defect.

    The discriminating case for `LEADING`, and the reason the extractor is
    anchored to the start of the row's second cell instead of searching the
    line. Report 107's CQ-236 row contains the exact phrase twice, both
    times inside double quotes; report 098 carries the real thing. A matcher
    that could not tell them apart would report the finding's own
    description as an instance of the finding.
    """
    path = AUDITS / fixture_report
    if not path.is_file():
        pytest.skip(f"{fixture_report} is not in this corpus")
    text = path.read_text(encoding="utf-8", errors="replace")

    assert "Claim as first raised in report" in text, (
        "the phrase is absent, so this case proves nothing about telling a "
        "quotation from a claim")
    found = _claims(text)
    if expect == 0:
        assert found == [], found
    else:
        assert found, "report 098 carries real annotations and none was found"


def test_the_clauses_fail_on_a_corpus_that_breaks_them(tmp_path):
    """DISCIPLINE rule 1, on fixtures, because the real corpus is clean.

    A committed report may not be edited to make a guard fail, so the two
    is-empty clauses are exercised against a corpus built here. Without this
    the clauses above are three assertions nobody has ever seen disagree
    with anything.
    """
    audits = tmp_path / "audits"
    audits.mkdir()
    (audits / "100-2026-01-01.md").write_text(
        "| CQ-01 | a finding |\n", encoding="utf-8")
    # After the window, and naming a report that does not carry the label.
    (audits / "120-2026-01-02.md").write_text(
        "| CQ-99 | **Claim as first raised in report 100**: text |\n",
        encoding="utf-8")

    import tests.test_a_finding_is_not_dated_by_a_reused_label as mod
    saved = mod.AUDITS
    mod.AUDITS = audits
    try:
        # The real clauses, called against the broken corpus, not a
        # re-derivation of their conditions beside them. A rule 1 step that
        # reimplements the assertion proves the reimplementation.
        with pytest.raises(AssertionError,
                           match="dates a finding by its ID label"):
            mod.test_no_report_after_the_window_dates_a_finding_by_its_label()
        with pytest.raises(AssertionError, match="never mentions it"):
            mod.test_every_back_attribution_names_a_report_that_carries_that_id()
    finally:
        mod.AUDITS = saved

    # And the same two clauses pass again the moment AUDITS is the real
    # corpus, so the failures above are the fixture and not this file.
    test_no_report_after_the_window_dates_a_finding_by_its_label()
    test_every_back_attribution_names_a_report_that_carries_that_id()
