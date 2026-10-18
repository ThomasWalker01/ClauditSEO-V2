"""`PRIOR_RUN` — the run before this one, and what it is not.

Item 136k. The contract gives one name to "the previous site-wide run" so
that `CNT/stale` and 136h's resolved canonical chains do not each invent a
private answer to the same question.

**The relation this file exists to keep apart from its neighbour.** The Score
trend also pairs a run with an earlier one, but on the NEAREST SAME BASIS
(`partner_run_id`) — a T1 run's partner is another T1 run. `PRIOR_RUN` is the
run before this one in TIME, whatever its tier. On the operator's own Birch
data the two resolve to different runs, and the fixture below reproduces that
shape rather than reading the live database: a test pinned to stored rows goes
red the day they are deleted, and passes vacuously on a machine that never
audited that site.
"""

from __future__ import annotations

import sqlite3

import pytest

from clauditseo.persistence import repo, runs


@pytest.fixture()
def db(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture()
def site(db):
    op = repo.ensure_default_operator(db)
    return repo.create_site(db, repo.create_client(db, op, "C"), "x.test")


def _run(conn, site_id, when: str, *, kind="audit", tier="T2",
         scope="full", score=50.0, status="complete") -> str:
    """One stored run. `started_at` is what `prior_run` orders on, so it is
    stated per row rather than left to insertion order — the ordering is the
    thing under test and letting it fall out of rowid would test nothing."""
    run_id = runs.create_run(conn, site_id, ["TEC"], tier, kind=kind,
                             scan_scope=scope)
    conn.execute(
        "UPDATE audit_runs SET started_at=?, created_at=?, status=?,"
        " composite_score=? WHERE id=?",
        (when, when, status, score, run_id))
    conn.commit()
    return run_id


def test_prior_run_skips_narrow_and_page_scans(db, site):
    """A page scan crawled some pages, so its evidence is not what the site
    looked like — reading it as the prior state would report every page it
    did not fetch as changed."""
    old = _run(db, site, "2026-01-01T00:00:00+00:00")
    _run(db, site, "2026-01-02T00:00:00+00:00", scope="page")
    _run(db, site, "2026-01-03T00:00:00+00:00", kind="verify", scope="page")
    now = _run(db, site, "2026-01-04T00:00:00+00:00")

    got = runs.prior_run(db, site, now)
    assert got and got["run_id"] == old, got


def test_a_refresh_is_a_prior_run_but_is_not_site_reading(db, site):
    """The operator's ruling of 2026-09-07, and the distinction it turns on.

    A refresh may be `PRIOR_RUN` — its evidence is what the site looked like
    last time. It is still not `SITE_READING_KINDS`, which answers the other
    question: whether the run's RESULT may be generalised to the site. Both
    hold at once, and asserting only the first would let someone "simplify"
    one constant into the other.
    """
    _run(db, site, "2026-01-01T00:00:00+00:00")
    fresh = _run(db, site, "2026-01-02T00:00:00+00:00", kind="refresh",
                 scope=None)
    now = _run(db, site, "2026-01-03T00:00:00+00:00")

    got = runs.prior_run(db, site, now)
    assert got and got["run_id"] == fresh, got
    assert "refresh" in runs.PRIOR_RUN_KINDS
    assert not runs.is_site_reading("refresh")


def test_an_unscored_run_is_not_a_prior_run(db, site):
    """A run nobody scored is a state the record never accepted."""
    old = _run(db, site, "2026-01-01T00:00:00+00:00")
    _run(db, site, "2026-01-02T00:00:00+00:00", score=None)
    now = _run(db, site, "2026-01-03T00:00:00+00:00")
    got = runs.prior_run(db, site, now)
    assert got and got["run_id"] == old, got


def test_first_site_wide_run_has_no_prior(db, site):
    first = _run(db, site, "2026-01-01T00:00:00+00:00")
    assert runs.prior_run(db, site, first) is None
    # And a site whose only earlier runs are narrow is the same answer, not
    # an empty map: the contract says a check must read this as "cannot
    # answer" rather than "unchanged".
    _run(db, site, "2025-12-31T00:00:00+00:00", scope="page")
    assert runs.prior_run(db, site, first) is None


def test_the_prior_run_is_older_than_the_run_that_asked(db, site):
    """Found by driving the resolver on real rows: excluding the reference by
    id alone and taking the newest of the rest returns a run that came AFTER,
    whenever the reference is not the newest — which is precisely the case a
    check reading history is in."""
    _run(db, site, "2026-01-01T00:00:00+00:00")
    middle = _run(db, site, "2026-01-02T00:00:00+00:00")
    newest = _run(db, site, "2026-01-03T00:00:00+00:00")

    got = runs.prior_run(db, site, middle)
    assert got and got["run_id"] != newest, (
        "the prior run is newer than the run that asked for it")
    assert got["captured_at"] < "2026-01-02T00:00:00+00:00", got


def test_prior_run_is_not_the_score_trend_partner(db, site):
    """Both relations, one fixture, different answers.

    The shape is the operator's Birch data (2026-09-07): a T1 run whose
    PRIOR_RUN is a T2 run minutes earlier, while the nearest run on its own
    basis is a T1 run from the day before. Reproduced rather than read, for
    the reason in this module's docstring.
    """
    older_t1 = _run(db, site, "2026-01-01T23:10:00+00:00", tier="T1")
    prior_t2 = _run(db, site, "2026-01-02T05:14:00+00:00", tier="T2")
    now = _run(db, site, "2026-01-02T05:15:00+00:00", tier="T1")

    got = runs.prior_run(db, site, now)
    assert got and got["run_id"] == prior_t2, got
    # The trend's relation is a different one and must not resolve here.
    assert got["run_id"] != older_t1
    assert got["tier"] == "T2", (
        "PRIOR_RUN took the same tier, which is the trend partner's rule")


def test_prior_run_reports_the_basis_it_was_taken_on(db, site):
    """The contract promises run id, captured-at, tier, engine and dimension
    set. A caller comparing evidence across an engine change needs to know one
    happened, so the fields are asserted rather than left to whatever the row
    happened to carry."""
    _run(db, site, "2026-01-01T00:00:00+00:00")
    now = _run(db, site, "2026-01-02T00:00:00+00:00")
    got = runs.prior_run(db, site, now)
    assert set(got) == {"run_id", "captured_at", "tier", "engine_version",
                        "dimensions"}, got
    assert got["dimensions"] == ["TEC"] and got["tier"] == "T2"


def test_no_site_at_all_is_none_not_an_error(db, site):
    assert runs.prior_run(db, "no-such-site") is None

# --- what `stale` compares against (item 136p) ---------------------------

def test_the_hashes_stale_reads_come_from_prior_run(db, site):
    """One notion of "the previous run", not two.

    `prior_content_hashes` answered both questions at once - which run is
    previous, and what did it record - under its own rule, `kind='audit'`.
    That excluded a refresh (the contract includes one) and included a page
    scan (the contract does not), so `stale` answered "changed since last
    time" against a different set of runs than the contract defines.

    Measured on the operator's data before the change: on Acme the run
    selected was a ONE-page scan, so `stale` could answer for none of the
    fourteen pages it was being asked about. The page scan below is that
    case.
    """
    _run(db, site, "2026-01-01T00:00:00+00:00")            # the real prior
    _run(db, site, "2026-01-02T00:00:00+00:00", scope="page")   # newer, narrow
    now = _run(db, site, "2026-01-03T00:00:00+00:00")

    prior = runs.prior_run(db, site, now)
    assert prior, "no prior run resolved at all"
    # The page scan is newer and is NOT what the hashes come from.
    scan = db.execute(
        "SELECT id FROM audit_runs WHERE site_id=? AND scan_scope='page'",
        (site,)).fetchone()["id"]
    assert prior["run_id"] != scan, (
        "the hashes would come from a page scan, which is what item 136p "
        "exists to stop")

    # And the function that reads them takes a run, not a site: the two
    # questions are separate now, which is the point of the split.
    import inspect
    src = inspect.signature(runs.content_hashes)
    assert list(src.parameters) == ["conn", "run_id"], src
    assert not hasattr(runs, "prior_content_hashes"), (
        "the old reader is still here, so there are two definitions of "
        "'the previous run' again")


def test_content_hashes_reads_one_run_and_says_nothing_where_there_is_none():
    """`None` is not an empty map. A run that stored no evidence, or stored
    it before the hash existed, cannot answer - and `stale` must treat that
    as "cannot answer" rather than "unchanged", which is the over-firing its
    second condition exists to stop."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    import tempfile
    from pathlib import Path as _P
    with tempfile.TemporaryDirectory() as d:
        conn = connect(_P(d) / "c.db")
        migrate(conn)
        assert runs.content_hashes(conn, None) is None
        assert runs.content_hashes(conn, "no-such-run") is None
        conn.close()
