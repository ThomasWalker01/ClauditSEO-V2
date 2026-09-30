"""Brief v23 step BL: the integrity line is a threshold, not a gradient.

No Critical or High finding may be unassessed when a client report is
generated. On Twenty22 run T1 the report went out describing 425 findings
nobody had looked at, and the six-step bar drew that as two green ticks. Not
100%, which will never hold; Critical and High only, which is the condition
under which sending is defensible.

Item 239 step 7 (the operator's ruling: "the report hold is the open Critical
and High in that copy"): the count is the site's running record - the Latest
View a client report is a copy of - and not one run's rows. A High only an
older audit raised, and nothing has cleared, still holds a report asked for
from a newer one.
"""

from __future__ import annotations

import pytest

from clauditseo.persistence import runs
from clauditseo.reporting import generate as gen
from tests.test_reporting_g7 import db_with_runs  # noqa: F401  (fixture)

pytestmark = pytest.mark.integrity_threshold


def _plant_high(conn, run_id):
    """One open High in the run. The g7 fixture's own High was `TEC/not-https`
    until item 143 step BD moved Security to SEC, which that fixture does not
    audit, so the clause plants its subject rather than inheriting one."""
    from clauditseo.engine.types import Finding, Severity
    site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?", (run_id,)).fetchone()[0]
    f = Finding(dimension="TEC", check_id="robots-missing", severity=Severity.HIGH,
                summary="planted High", subject="planted-high",
                affected_urls=["https://report.fixture/"])
    conn.execute("INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                 " confidence, summary, affected_urls, evidence, recommendation, fingerprint,"
                 " created_at) VALUES (lower(hex(randomblob(16))), ?, 'TEC', 'robots-missing',"
                 " 'high', 'deterministic', 'high', 'planted High', '[]', '{}', '', ?,"
                 " '2026-09-13T00:00:00')", (run_id, f.fingerprint))
    conn.execute("INSERT OR IGNORE INTO finding_states (site_id, fingerprint, state, updated_at)"
                 " VALUES (?, ?, 'open', '2026-09-13T00:00:00')", (site_id, f.fingerprint))
    conn.commit()


def _site(conn, run_id):
    return conn.execute("SELECT site_id FROM audit_runs WHERE id=?", (run_id,)).fetchone()[0]


def _severe(conn, run_id):
    """The site's open Critical and High in the ledger, whichever run raised
    them - what the hold counts."""
    return conn.execute(
        "SELECT DISTINCT fs.fingerprint, fs.site_id FROM finding_states fs"
        " JOIN findings f ON f.fingerprint = fs.fingerprint"
        " WHERE fs.site_id=? AND fs.state IN ('open','regressed')"
        " AND lower(f.severity) IN ('critical','high')", (_site(conn, run_id),)).fetchall()


def test_the_report_cannot_be_generated_with_an_unassessed_critical_or_high(db_with_runs):
    conn, run_ids = db_with_runs
    run_id = run_ids[0]
    _plant_high(conn, run_id)
    assert _severe(conn, run_id), "the fixture seeds no Critical or High to refuse on"
    with pytest.raises(ValueError, match="still open"):
        gen.generate(conn, "run", "client", [run_id])
    assert not conn.execute("SELECT 1 FROM reports").fetchone(), (
        "a refused report must leave no row behind")


def test_once_every_critical_and_high_is_assessed_the_report_generates(db_with_runs):
    """`accepted-risk` and `withdrawn` count as assessed, by BJ's rule: deciding
    to carry a risk is having worked a finding."""
    conn, run_ids = db_with_runs
    run_id = run_ids[0]
    for i, row in enumerate(_severe(conn, run_id)):
        runs.set_state(conn, row["site_id"], row["fingerprint"],
                       "accepted-risk" if i % 2 else "withdrawn")
    assert runs.open_severe(conn, _site(conn, run_id))["count"] == 0
    report = gen.generate(conn, "run", "client", [run_id])
    assert report["id"]


def test_the_internal_document_is_never_refused_for_it(db_with_runs):
    """The internal document is the operator's reading copy, and is how the
    assessing gets done - refusing it would block the work the rule asks for."""
    conn, run_ids = db_with_runs
    _plant_high(conn, run_ids[0])
    assert runs.open_severe(conn, _site(conn, run_ids[0]))["count"] > 0
    assert gen.generate(conn, "run", "internal", [run_ids[0]])["id"]


def test_a_medium_or_low_left_open_does_not_hold_the_report(db_with_runs):
    conn, run_ids = db_with_runs
    run_id = run_ids[0]
    for row in _severe(conn, run_id):
        runs.set_state(conn, row["site_id"], row["fingerprint"], "fixed")
    open_lower = conn.execute(
        "SELECT count(*) FROM findings WHERE run_id=? AND lower(severity) NOT IN"
        " ('critical','high')", (run_id,)).fetchone()[0]
    assert open_lower, "the fixture has no lower finding to leave open"
    assert gen.generate(conn, "run", "client", [run_id])["id"]


# --- item 170: what a report was built over, recorded when it was built ------

def test_a_client_report_records_what_it_went_out_over(db_with_runs):
    """Channel ruling 20260917-0250. `finding_states` keeps one current row per
    fingerprint and no history, so "was anything unassessed when this went out"
    cannot be read back afterwards; it is written on the row at generation,
    by the rule the refusal enforces - unassessed is state `open`."""
    conn, run_ids = db_with_runs
    run_id = run_ids[0]
    for row in _severe(conn, run_id):
        runs.set_state(conn, row["site_id"], row["fingerprint"], "fixed")
    before = runs.run_assessed(conn, run_id, conn.execute(
        "SELECT site_id FROM audit_runs WHERE id=?", (run_id,)).fetchone()[0])
    report = gen.generate(conn, "run", "client", [run_id])
    row = conn.execute("SELECT unassessed_severe, unassessed_total, assessed_pct"
                       " FROM reports WHERE id=?", (report["id"],)).fetchone()
    assert row["unassessed_severe"] == 0, "a client report past the guard has none"
    assert row["unassessed_total"] == before["total"] - before["assessed"], row
    assert row["assessed_pct"] == before["pct"], row


def test_the_deliver_state_tells_its_three_cases_apart(db_with_runs):
    """A report that predates the guard is a legacy row, not a live failure;
    one that passed it and went out over open Mediums and Lows is the case the
    threshold leaves to the operator; one generated after the guard but before
    the counts were recorded says so rather than reading as clean."""
    conn, run_ids = db_with_runs
    site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                           (run_ids[0],)).fetchone()[0]

    def put(created_at, severe=None, total=None, pct=None):
        conn.execute("DELETE FROM reports")
        conn.execute(
            "INSERT INTO reports (id, site_id, run_ids, template, audience, path, created_at,"
            " unassessed_severe, unassessed_total, assessed_pct)"
            " VALUES (lower(hex(randomblob(16))), ?, ?, 'run', 'client', 'x.md', ?, ?, ?, ?)",
            (site_id, f'["{run_ids[0]}"]', created_at, severe, total, pct))
        conn.commit()
        return runs.report_state(conn, site_id)

    assert runs.report_state(conn, site_id) is None, "no client report, no state"

    legacy = put("2026-09-08T23:29:27+00:00")
    assert legacy["predates_guard"] and not legacy["recorded"], legacy
    assert legacy["unassessed_below"] is None, "not recorded is never zero"

    unrecorded = put("2026-09-14T00:00:00+00:00")
    assert not unrecorded["predates_guard"] and not unrecorded["recorded"], unrecorded

    below = put("2026-09-17T00:00:00+00:00", severe=0, total=412, pct=18)
    assert below["recorded"] and not below["predates_guard"], below
    assert below["unassessed_below"] == 412 and below["assessed_pct"] == 18, below

    # One minute either side of 1efbe9a, so the boundary is the guard's commit.
    assert put("2026-09-13T06:22:42+00:00")["predates_guard"] is True
    assert put("2026-09-13T06:24:42+00:00")["predates_guard"] is False


def test_a_high_an_older_audit_raised_holds_a_report_asked_of_a_newer_one(db_with_runs):
    """The hold is the running record's, not the picked audit's: the planted
    High is the OLDER run's, the report is asked of the newer, and it is held.
    Under the one-run count it would have gone out."""
    conn, run_ids = db_with_runs
    older, newer = run_ids[0], run_ids[-1]
    for row in _severe(conn, older):
        runs.set_state(conn, row["site_id"], row["fingerprint"], "accepted-risk")
    _plant_high(conn, older)
    assert not [r for r in conn.execute(
        "SELECT 1 FROM findings WHERE run_id=? AND check_id='robots-missing'"
        " AND summary='planted High'", (newer,))], "precondition: only the older run raised it"
    with pytest.raises(ValueError, match="1 Critical or High finding still open"):
        gen.generate(conn, "run", "client", [newer])
