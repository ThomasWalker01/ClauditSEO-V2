"""Two runs in the same second still have a newest one.

`started_at` is written by `now_iso()` at second resolution, and every query
asking "the latest run" ordered by it alone. Ordering by a non-unique column
is not an ordering: SQLite may return either row, so "the site's current
position" was whichever of two runs the query planner happened to reach
first.

This is not a rare tie. The adaptive planner completes a T1 pulse and then a
deeper run in the same pass, and `test_blocked_runs` produces two audits over
a two-page fixture — both land in the same second routinely. The observed
symptom was `current_state` reporting the *earlier* run's transitions as the
latest audit's work, so a run that cleared two findings was credited with
none and the run that cleared nothing was credited with the earlier run's
opens.
"""

from __future__ import annotations

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite
from tests.test_history_g4 import BROKEN_PROMO, GOOD_PROMO, _routes

FAST = TierBudget(max_pages=10, request_timeout_s=5, wall_clock_s=30, delay_s=0)
DIMS = ["TEC", "ONP", "CNT"]
SAME_SECOND = "2026-08-15T00:00:00+00:00"


def _site(tmp_path, name):
    conn = connect(tmp_path / name)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Tie Co")
    return conn, repo.create_site(conn, client, "tie.fixture")


def _audit(conn, site_id, promo):
    server = FixtureSite(_routes(promo)).start()
    try:
        crawled = crawl(server.base_url + "/", Tier.T2, budget=FAST)
    finally:
        server.stop()
    result = run_audit(Site(domain="tie.fixture"), crawled, DIMS, Tier.T2)
    run_id = runs.create_run(conn, site_id, DIMS, "T2")
    runs.complete_run(conn, run_id, result)
    return run_id


def _tie_the_timestamps(conn, site_id):
    """Force the collision the clock produces on its own. Written explicitly
    so the test states the condition rather than racing for it."""
    with conn:
        conn.execute("UPDATE audit_runs SET started_at=? WHERE site_id=?",
                     (SAME_SECOND, site_id))


def test_the_newer_of_two_runs_in_one_second_is_the_latest(tmp_path):
    """The reported symptom, at the surface an operator reads. Run one leaves
    findings open; run two revisits the same pages and finds them fixed. Only
    run two can have cleared anything, so `moved.fixed` is non-zero exactly
    when `current_state` resolved the tie to the newer run."""
    conn, site_id = _site(tmp_path, "latest.db")
    _audit(conn, site_id, BROKEN_PROMO)
    second = _audit(conn, site_id, GOOD_PROMO)
    _tie_the_timestamps(conn, site_id)

    fixed_by_second = conn.execute(
        "SELECT COUNT(*) FROM finding_states WHERE changed_by_run=? AND state='fixed'",
        (second,)).fetchone()[0]
    assert fixed_by_second, "the fixture must have the second run clear something"

    moved = runs.current_state(conn, site_id)["moved"]
    assert moved["fixed"] == fixed_by_second, (
        f"current_state credited the wrong run: expected {fixed_by_second} "
        f"fixed from the newer run, got {moved}")
    conn.close()


def test_the_deliverables_list_puts_the_newer_run_first(tmp_path):
    """`current_state` was the reported symptom; the same ordering decides
    which run heads the Deliverables screen, which run the scheduler measures
    its interval from, and which two runs Home subtracts to produce a score
    delta. One tie-break, several screens."""
    conn, site_id = _site(tmp_path, "list.db")
    first = _audit(conn, site_id, BROKEN_PROMO)
    second = _audit(conn, site_id, GOOD_PROMO)
    _tie_the_timestamps(conn, site_id)

    listed = [r["id"] for r in runs.site_reports(conn, site_id)["runs"]]
    assert listed[:2] == [second, first], (
        f"newest-first list returned {[i[:8] for i in listed[:2]]}, expected "
        f"{[second[:8], first[:8]]}")
    conn.close()


def test_every_started_at_ordering_carries_a_tie_break():
    """The rule, enumerated from source rather than from a list someone kept
    up to date by hand. Nine query sites already order by `started_at` with a
    `rowid` tie-break; the ones that did not were the defect. A new query that
    forgets it fails here rather than in whichever screen reads it."""
    import pathlib
    import re

    offenders = []
    for path in sorted(pathlib.Path("clauditseo").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"ORDER BY\s+(?:\w+\.)?started_at[^\"']*", text):
            clause = match.group(0)
            if "rowid" not in clause:
                line = text[:match.start()].count("\n") + 1
                offenders.append(f"{path.as_posix()}:{line}  {clause.strip()}")
    assert not offenders, (
        "ordering by a second-resolution timestamp with no tie-break:\n  "
        + "\n  ".join(offenders))
