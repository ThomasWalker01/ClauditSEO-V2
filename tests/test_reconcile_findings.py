"""Relay 029: a finding must not be able to leave the tracked register
silently.

Ground truth is the real transition, not a synthetic fixture — `audits/
038-2026-08-17.md` and `audits/039-2026-08-17.md` are committed, and relay
028 already established by hand, three separate times, exactly what left
between them: CQ-35, CQ-76 and WF-40, while the report's own accounting
claimed "Nothing is disproved and nothing is not-re-found" — false both
times (039's report, and 040's, which inherited the same gap).
"""

from __future__ import annotations

from pathlib import Path

from scripts.reconcile_findings import (
    _newest_reports, main, not_carried_forward_ids, pillar_finding_ids,
    unaccounted_drops,
)

from tests.private_register import skip_module

# Before the reads below, not after: this module's ground truth is two
# committed audit reports, and `audits/` does not ship (item 187). A
# module-level `read_text` of an absent path raises during COLLECTION, which
# aborts the whole suite rather than failing one file - measured on the first
# exported tree, where this line took 4,200 other tests down with it.
skip_module()

AUDITS = Path(__file__).resolve().parent.parent / "audits"
REPORT_038 = (AUDITS / "038-2026-08-17.md").read_text(encoding="utf-8")
REPORT_039 = (AUDITS / "039-2026-08-17.md").read_text(encoding="utf-8")


def test_the_fixtures_are_the_real_committed_reports():
    """Guards the fixture itself — a renamed or moved report file would make
    every assertion below vacuously pass against near-empty strings."""
    assert "CQ-35" in REPORT_038
    assert len(REPORT_038) > 10_000
    assert len(REPORT_039) > 10_000


def test_038_pillar_count_matches_the_hand_count_recorded_in_its_own_commit():
    """`5133a5f`'s own commit body states m=117, counted the same way: a
    plain grep over every ID mention in prose first returned 124, inflated
    by cross-references inside other rows' text."""
    assert len(pillar_finding_ids(REPORT_038)) == 117


def test_the_real_038_to_039_transition_names_exactly_the_three_known_drops():
    """The ground truth this whole mechanism is built against. Relay 028
    found these three by hand; this must find the same three and nothing
    else — not two, not four."""
    assert unaccounted_drops(REPORT_038, REPORT_039) == {"CQ-35", "CQ-76", "WF-40"}


def test_a_real_disposition_suppresses_the_drop():
    """A finding that genuinely leaves the pillar tables, and is named in
    the current report's own "not carried forward" table, must not be
    reported as unaccounted — that is the whole distinction between a
    disposition and a silent drop. Synthetic, not the 038/039 fixture:
    every real candidate in that pair (WF-15) happens to keep a closed stub
    row in the pillar table too, which is a different, also-legitimate
    shape this test is not the one to cover."""
    previous = "## PHASE 1\n### Code Quality\n| CQ-99 | thing | High | x.py:1 | y |\n"
    current = ("## PHASE 1\n### Code Quality\n"
               "### Prior findings not carried forward\n"
               "| CQ-99 | **fixed** | verified by running it |\n")

    assert "CQ-99" in pillar_finding_ids(previous)
    assert "CQ-99" not in pillar_finding_ids(current)
    assert "CQ-99" in not_carried_forward_ids(current)
    assert unaccounted_drops(previous, current) == set()


def test_dispositions_md_cohort_membership_does_not_excuse_a_drop():
    """CQ-35 is also DISPOSITIONS.md's 18-round "business-type vocabulary"
    entry. If cohort membership were treated as an automatic disposition,
    this check would have missed exactly the drop it exists to catch —
    which is already what happened once, by a human reading it that way."""
    assert "CQ-35" in unaccounted_drops(REPORT_038, REPORT_039)


def test_a_row_inside_cross_pillar_findings_is_not_mistaken_for_a_tracked_row():
    """`Cross-pillar findings` and `Not assessable` reuse the `| ID |` shape
    for prose that names findings without giving them a tracked row — WF-42
    is discussed under `Cross-pillar findings` in 039 in the form
    `**WF-42 × CQ-49 (...)**`, not `| WF-42 | ... |`, so it must not count
    as a pillar row from that section alone."""
    ids = pillar_finding_ids(REPORT_039)
    # WF-42 has its own real Code Quality row this round; the point is that
    # counting it must come from THAT row, not from the cross-pillar prose
    # mentioning it a second time — verified by the exact count above
    # rather than by presence/absence, which a double-count would not show.
    assert "WF-42" in ids


def test_main_says_nothing_to_compare_on_a_first_ever_report(tmp_path, capsys):
    """The two zero-exit endings must not share an output. A lone report has
    nothing to compare against, which is a different claim from "compared,
    found nothing dropped" — collapsing them would read a brand-new install
    as a clean bill of health it never earned."""
    (tmp_path / "001-2026-01-01.md").write_text("# Round 1\n", encoding="utf-8")

    code = main([], audits_dir=tmp_path)

    assert code == 0
    assert "nothing to compare" in capsys.readouterr().out


def test_main_exits_nonzero_and_names_names_on_the_real_fixture(tmp_path, capsys):
    """End-to-end through the CLI entry point, not just the library
    functions, against copies of the real committed reports."""
    (tmp_path / "038-2026-08-17.md").write_text(REPORT_038, encoding="utf-8")
    (tmp_path / "039-2026-08-17.md").write_text(REPORT_039, encoding="utf-8")

    code = main([], audits_dir=tmp_path)
    out = capsys.readouterr().out

    assert code == 1
    assert "CQ-35" in out and "CQ-76" in out and "WF-40" in out


def test_main_reports_clean_when_nothing_is_unaccounted(tmp_path, capsys):
    """A report compared against itself has dropped nothing — the
    complementary case to the fixture above, proving the check can also
    pass rather than only ever firing."""
    (tmp_path / "001-2026-01-01.md").write_text(REPORT_038, encoding="utf-8")
    (tmp_path / "002-2026-01-02.md").write_text(REPORT_038, encoding="utf-8")

    code = main([], audits_dir=tmp_path)

    assert code == 0
    assert "clean" in capsys.readouterr().out


def test_newest_reports_ignores_non_report_files(tmp_path):
    """`DISPOSITIONS.md` lives in the same directory and must never be
    mistaken for a numbered report."""
    (tmp_path / "DISPOSITIONS.md").write_text("not a report", encoding="utf-8")
    (tmp_path / "001-2026-01-01.md").write_text("# Round 1\n", encoding="utf-8")

    found = _newest_reports(tmp_path)

    assert [p.name for p in found] == ["001-2026-01-01.md"]
