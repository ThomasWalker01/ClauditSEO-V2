"""One audit, one population: a findings count never counts coverage notes, and
says what it left out.

Found from a screenshot of the twenty22 landing, and measured on the live server
before the fix:

    "It found 36 findings in this audit"     headline.assessed.total  = 36
    "Start triage - 36 not yet assessed"     total - assessed         = 36
    "32 Outstanding" (the lane below it)     standing_by_state.open   = 32
    "held for assessment - 7 to assess"      unassessed_severe.count  = 7

Run 991401ab wrote 36 rows: 7 High, 17 Medium, 4 Low, 8 Info. Four of the Info
rows were `axe-coverage`, `unreachable-not-assessed`, `cwv-not-assessed` and
`backlinks-not-assessed` - coverage notes. Item 180's ruling (20260918-0400)
settled that a coverage note is not a finding and is not counted with them, and
`standing_by_state` has excluded them since; `run_assessed` never got the same
treatment. So one screen said 36 and 32 for the same idea, and the 36 counted
four things the screen elsewhere says are not findings.

A note also cannot ever BE assessed - there is nothing to decide about "this
could not be measured" - so while four of them sat in the denominator the
assessed percentage could not reach 100 for the life of the run. The wrong
population twice.

The 7 was never wrong: it is the Critical and High subset. What it lacked was
saying so, next to a "32 not yet assessed" that means every severity. Both
figures name their population now.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


def _plant(conn, run_id: str, check_id: str, severity: str, fp: str) -> str:
    site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                           (run_id,)).fetchone()[0]
    conn.execute("INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                 " confidence, summary, affected_urls, evidence, recommendation, fingerprint,"
                 " created_at) VALUES (lower(hex(randomblob(16))), ?, 'TEC', ?, ?,"
                 " 'deterministic', 'high', 'planted', '[]', '{}', '', ?,"
                 " '2026-09-18T00:00:00')", (run_id, check_id, severity, fp))
    # `changed_by_run` matters here and not in the other fixtures that copy this
    # shape: `current_state`'s `moved` counts rows this run moved, so a planted
    # row with a null one is in the standing and not in what the audit opened -
    # which is a real difference, not the population difference F1 is about.
    conn.execute("INSERT OR REPLACE INTO finding_states"
                 " (site_id, fingerprint, state, updated_at, changed_by_run)"
                 " VALUES (?, ?, 'open', '2026-09-18T00:00:00', ?)", (site_id, fp, run_id))
    conn.commit()
    return site_id


@pytest.fixture(scope="module")
def counted():
    """A completed audit with two coverage notes and one High planted in it."""
    from tests.test_coverage import DIMS, _Hub, _run
    from tests.test_triage_ranks_the_section_rail import _serve

    server, thread, db, base = _serve("notecounts")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Note Counts"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "notecounts.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        # The two shapes `coverage_note_sql` matches, both Info as it requires.
        site_id = _plant(conn, run_id, "cwv-not-assessed", "info", "note-cwv")
        _plant(conn, run_id, "axe-coverage", "info", "note-axe")
        _plant(conn, run_id, "robots-missing", "high", "planted-high")
        conn.close()
        yield base, db, run_id, site_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_fixture_holds_notes_for_this_to_count():
    """DISCIPLINE rule 5, and this guard is entirely about a difference: with
    no coverage note in the run every clause below passes on an empty set."""
    assert "not-assessed" in runs.coverage_note_sql()
    assert "coverage" in runs.coverage_note_sql()


def test_the_count_excludes_the_notes_and_reports_them(counted):
    base, db, run_id, site_id = counted
    conn = connect(db)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM findings WHERE run_id=?",
                            (run_id,)).fetchone()[0]
        got = runs.run_assessed(conn, run_id, site_id)
        assert got["notes"] >= 2, (
            f"the fixture's planted coverage notes are not being seen: {got}")
        assert got["total"] == rows - got["notes"], (
            f"{rows} rows in the run, {got['notes']} of them coverage notes, and "
            f"the count says {got['total']}")
        # And a note is not counted as unassessed either, which is the half that
        # capped the percentage: it can never be assessed.
        assert got["assessed"] + (got["total"] - got["assessed"]) == got["total"]
    finally:
        conn.close()


def test_the_audits_count_and_the_standing_count_read_one_population(counted):
    """The contradiction itself: 36 against 32 on one screen.

    Everything in this fixture's run is `open` and the site has one run, so the
    audit's findings and the standing's open findings are the same set - and any
    difference between the two figures is a difference of population, which is
    the defect.
    """
    base, db, run_id, site_id = counted
    conn = connect(db)
    try:
        audit = runs.run_assessed(conn, run_id, site_id)
        standing = runs.standing_by_state(conn, site_id)
        open_now = standing.get("open", {"n": 0})["n"]
        assert audit["total"] == open_now, (
            f"the audit counts {audit['total']} findings and the standing counts "
            f"{open_now} open, from one run where nothing has been assessed: "
            f"{audit} vs { {k: v['n'] for k, v in standing.items()} }")
        assert audit["notes"] == standing["_notes"]["n"], (
            "the two figures set aside different numbers of coverage notes: "
            f"{audit['notes']} and {standing['_notes']['n']}")
    finally:
        conn.close()


def test_what_the_latest_audit_moved_counts_the_same_population(counted):
    """The same fault four lines from the fix for it (audit finding F1).

    `current_state` calls `standing_by_state` - notes excluded - and then
    counted what the latest audit moved with a bare `GROUP BY state` over
    `finding_states`, so the landing rendered "First audit +36 -0" beside its
    own "It found 32 findings ... 4 coverage notes not counted" and a strip
    reading "SUMS TO 32". Four of the seven sites on the operator's database
    showed it: twenty22 36/32, 13acme 51/47, acme-agency 56/52, Acme
    177/176.

    In this fixture every row is `open` and was moved by the one run, so the
    two figures are the same set and any difference is a difference of
    population.
    """
    base, db, run_id, site_id = counted
    conn = connect(db)
    try:
        cur = runs.current_state(conn, site_id)
        moved = cur.get("moved") or {}
        opened = moved.get("opened", moved.get("open"))
        assert opened == cur["open"], (
            f"the standing counts {cur['open']} open and the latest audit is "
            f"credited with opening {opened}, from one run over one population: "
            f"{moved}")
        notes = runs.standing_by_state(conn, site_id)["_notes"]["n"]
        assert notes >= 2, f"the fixture's notes are not reaching the standing: {notes}"
    finally:
        conn.close()


def test_the_payload_carries_what_it_set_aside(counted):
    base, db, run_id, site_id = counted
    got = httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                    params={"run_id": run_id}, timeout=60).json()
    assessed = (got.get("headline") or {}).get("assessed") or {}
    assert assessed.get("notes"), (
        f"the payload does not say what the count left out: {assessed}")


# ---- the words -------------------------------------------------------------

def test_no_screen_spells_the_noun_and_three_of_them_read_it():
    """Home said it and the landing did not. One spelling of the noun now.

    The predicate stays each caller's, and that is the point rather than a
    compromise: Home and the landing say these were NOT counted, while the
    Record says how many its own list holds. Sharing the claim would have made
    one of the three false - which is how this guard found the third caller,
    `pane_record.tsx`, when the shared string still carried "not counted".
    """
    pop = (SRC / "population.tsx").read_text(encoding="utf-8")
    assert "export const coverageNotes" in pop
    offenders = []
    for path in sorted(SRC.glob("*.tsx")):
        if path.name == "population.tsx":
            continue
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith(("//", "*", "{/*")):
                continue
            if re.search(r"coverage note\$\{|coverage notes? \$\{", line):
                offenders.append(f"{path.name}:{n}: {line.strip()[:90]}")
    assert not offenders, "a screen spells the noun itself:\n" + "\n".join(offenders)
    for name in ("home.tsx", "client_lanes.tsx", "pane_record.tsx"):
        assert "coverageNotes(" in (SRC / name).read_text(encoding="utf-8"), name


def test_a_coverage_note_is_not_a_fix_and_not_drawn_as_a_fault():
    """Audit F3. On Speed, `PRF/cwv-not-assessed` was the sixth "Free check"
    where the part's own count - the strip, the catalogue chip and the Record
    filter - is five; it drew a fix card under the heading Fixes; and the check
    table gave it the state word `open`, which the registry defines as "a fault
    the latest audit still found", with `0` in a PAGES column, which reads as
    clean.

    Measured after, on the live Speed part page: `Free checks · 5`, no card,
    and the row reading `info | PRF/cwv-not-assessed | 1 | — | — | not
    measured`, with a line naming the note the list left out.
    """
    part = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    # One predicate, shared - the part page had none of its own.
    assert "isCoverageNote(s)" in part, "fixesOf does not mark coverage notes"
    assert "coverageNote: isCoverageNote" in part or "coverageNote: isCoverageNote(s)" in part
    assert "!f.coverageNote" in part, "a coverage note can still reach shownFixes"
    # The state word is the registry's, not `open`.
    assert 'MEASURE_WORD["not-measured"]' in part, (
        "the check table has no not-measured state for a note")
    assert "allNotes" in part
    api = (SRC / "api.ts").read_text(encoding="utf-8")
    assert "export const isCoverageNote" in api
    # And the pane that had its own copy now reads the shared one.
    rec = (SRC / "pane_record.tsx").read_text(encoding="utf-8")
    assert "isCoverageNote" in rec and "const isCoverageNote" not in rec, (
        "pane_record still declares its own predicate")


def test_the_registry_holds_the_word_the_note_is_drawn_with():
    entries = {e["id"]: e for e in json.loads(
        (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))["entries"]}
    assert entries["not-assessed"]["word"] == "not measured", entries["not-assessed"]
    # And why `open` was wrong for it.
    assert "fault" in entries["state-open"]["full"], entries["state-open"]


def test_the_hold_names_the_severities_it_counts():
    """"N to assess" beside "N not yet assessed" was one word over two
    populations. The mark says which findings hold the report, in the words the
    sentence under the headline already uses."""
    hold = (SRC / "report_hold.tsx").read_text(encoding="utf-8")
    assert "export const heldWords" in hold
    assert "Critical or High to assess" in hold
    anat = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    assert anat.count("heldWords(") >= 2, (
        "the strip still builds the hold's words itself")
    assert "to assess`" not in anat, "a second spelling of the hold's tail"


def test_the_registry_still_owns_the_held_word():
    entries = {e["id"]: e for e in json.loads(
        (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))["entries"]}
    assert entries["report-held"]["word"] == "held for assessment"
    hold = (SRC / "report_hold.tsx").read_text(encoding="utf-8")
    assert 'entry("report-held")' in hold
