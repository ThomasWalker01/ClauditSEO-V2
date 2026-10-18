"""The landing's strip and band say each population's state once.

Screen audits round 3, landing:
- IP-03: "Find done" over an Analyses pill marked NEXT; the chapter word read
  its first member only.
- IP-04: eleven pills read "N seen once" over rows the lane below counts as
  "To confirm" - item 250's two states said as one.
- IP-05: "Record AUTOMATIC DONE" beside "held for assessment · 84".
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"
ANAT = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
LANES = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")


def test_the_find_chapter_reads_both_its_members():
    assert "const findSteps = CHAPTERS[0].members.map((i) => steps[i])" in ANAT
    assert 'findSteps.every((s) => s.status === "done") ? "done"' in ANAT
    assert "const find = steps[0];" not in ANAT


def test_a_pill_says_to_confirm_apart_from_seen_once():
    assert '<span className="parts-seen-word"> to confirm</span>' in LANES
    assert "${c.to_confirm!.value} to confirm" in LANES
    assert ".parts-to-confirm {" in (SRC / "styles.css").read_text(encoding="utf-8")


def test_the_record_step_is_not_done_while_the_report_is_held():
    assert 'status: recordDone && !held ? "done" : recordDone ? "partial" : "idle",' in ANAT
    assert "Critical or High still open · the client report waits on them" in ANAT


def test_page_mode_does_not_call_its_figures_site_wide():
    # IP-06: "as of … · site-wide" over "Regressed on this page 11".
    assert '{word && !page ? ` · ${word}` : ""}' in ANAT
    assert "this page's share" in ANAT


def test_the_held_count_names_where_the_findings_are():
    # US-02: nothing under "Critical or High open 84" named a part or a check.
    assert "+ severeWhere(categories)," in LANES
    body = LANES[LANES.index("export function severeWhere("):]
    body = body[:body.index("\n}\n")]
    assert '"critical" || f.severity === "high"' in body and ".slice(0, 3)" in body
    assert "` Most are in ${list}.`" in body
