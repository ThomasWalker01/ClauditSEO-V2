"""A crawl that fetched nothing is a finished audit, not a finished failure.

A blanket `Disallow: /`, a 5xx on robots.txt or an unreachable host all end
with zero eligible pages. That run stored as `complete`, which is how a site
that was never retrieved acquired a scored client deliverable — and it is also
the single most valuable finding an SEO audit can return, so it must not be
filed as a failure either.

`blocked` is the third thing: terminal, successful, and honest about what it
saw. It keeps its findings, stays in the fix loop, writes no trend point, and
its modules raise nothing about pages that were never fetched.
"""

from __future__ import annotations

import pytest

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import CrawlResult, Page, TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite
from tests.test_history_g4 import BROKEN_PROMO, GOOD_PROMO, _routes

FAST = TierBudget(max_pages=10, request_timeout_s=5, wall_clock_s=30, delay_s=0)
DIMS = ["TEC", "ONP", "CNT", "LOC"]


def _page(url: str, *, status: int = 200, content_type: str = "text/html") -> Page:
    return Page(url=url, requested_url=url, status=status,
                content_type=content_type, content="<html><body>x</body></html>",
                elapsed_ms=5.0, headers={})


def _blocked_crawl() -> CrawlResult:
    """Nothing fetched: every URL refused before a request was made."""
    return CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[],
                       robots_blocked=["https://x.test/"])


def _db(tmp_path, name: str):
    conn = connect(tmp_path / name)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Blocked Co")
    return conn, repo.create_site(conn, client, "x.test")


def _store(conn, site_id, crawl_result, *, tier=Tier.T2):
    result = run_audit(Site(domain="x.test", business_type="local-service"),
                       crawl_result, DIMS, tier)
    run_id = runs.create_run(conn, site_id, DIMS, tier.value)
    runs.complete_run(conn, run_id, result)
    return run_id, result


# --- rule 1: the status ------------------------------------------------------

def test_a_crawl_that_fetched_nothing_completes_as_blocked(tmp_path):
    conn, site_id = _db(tmp_path, "status.db")
    run_id, _ = _store(conn, site_id, _blocked_crawl())
    assert runs.get_run(conn, run_id)["status"] == "blocked"
    conn.close()


def test_a_crawl_that_fetched_pages_still_completes(tmp_path):
    """The other side of the rule, and the one that must not move: an ordinary
    audit is unaffected."""
    conn, site_id = _db(tmp_path, "normal.db")
    server = FixtureSite(_routes(GOOD_PROMO)).start()
    try:
        fetched = crawl(server.base_url + "/", Tier.T2, budget=FAST)
    finally:
        server.stop()
    run_id, _ = _store(conn, site_id, fetched)
    assert runs.get_run(conn, run_id)["status"] == "complete"
    conn.close()


def test_pages_fetched_but_none_eligible_is_also_blocked(tmp_path):
    """`eligible`, not `fetched`. A crawl that retrieved three 404s and a PDF
    has pages in its result and no page any page-derived check can read, which
    is the same blindness by a different route."""
    conn, site_id = _db(tmp_path, "ineligible.db")
    junk = CrawlResult(
        start_url="https://x.test/", tier=Tier.T2,
        pages=[_page("https://x.test/a", status=404),
               _page("https://x.test/b", status=500),
               _page("https://x.test/c.pdf", content_type="application/pdf")])
    run_id, _ = _store(conn, site_id, junk)
    assert runs.get_run(conn, run_id)["status"] == "blocked"
    conn.close()


# --- rule 2: terminal SUCCESS, not failure -----------------------------------

def test_a_blocked_run_keeps_its_findings(tmp_path):
    """It measured robots.txt and the sitemap in their own right. Filing it as
    a failure would throw away the evidence that explains the block."""
    conn, site_id = _db(tmp_path, "findings.db")
    run_id, result = _store(conn, site_id, _blocked_crawl())
    stored = runs.run_findings(conn, run_id)
    assert stored, "a blocked run must keep the findings it did raise"
    assert len(stored) == len(result.findings)
    conn.close()


def test_a_blocked_run_is_the_site_s_latest_audit(tmp_path):
    """`current_state` and the fix loop both key on the newest completed audit.
    If a blocked run is invisible to them, the operator's standing position
    silently reverts to a crawl that may be weeks old."""
    conn, site_id = _db(tmp_path, "state.db")
    run_id, _ = _store(conn, site_id, _blocked_crawl())
    state = runs.current_state(conn, site_id)
    row = conn.execute("SELECT started_at FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    assert state["last_audit"] == row["started_at"], \
        "the blocked run is the latest audit and current_state must see it"
    conn.close()


def test_a_blocked_run_does_not_read_as_failed(tmp_path):
    conn, site_id = _db(tmp_path, "notfailed.db")
    run_id, _ = _store(conn, site_id, _blocked_crawl())
    run = runs.get_run(conn, run_id)
    assert run["status"] != "failed"
    assert run["error"] is None, "nothing went wrong; the site said no"
    assert run["finished_at"], "a terminal status has a finish time"
    conn.close()


# --- rule 3: no trend point --------------------------------------------------

def test_a_blocked_run_writes_no_metric_snapshots(tmp_path):
    """A trend line is the artefact used to prove a fix landed. A run that
    measured nothing must not put a point on it — gated where the rows are
    written, so no reader has to remember to exclude it."""
    conn, site_id = _db(tmp_path, "snapshots.db")
    _store(conn, site_id, _blocked_crawl())
    rows = conn.execute(
        "SELECT metric_key FROM metric_snapshots WHERE site_id=?",
        (site_id,)).fetchall()
    assert [r["metric_key"] for r in rows] == [], \
        "a blocked run recorded a trend point"
    conn.close()


def test_a_normal_run_still_writes_its_snapshots(tmp_path):
    """The control: the gate must be about blindness, not about snapshots."""
    conn, site_id = _db(tmp_path, "snapshots_ok.db")
    server = FixtureSite(_routes(GOOD_PROMO)).start()
    try:
        fetched = crawl(server.base_url + "/", Tier.T2, budget=FAST)
    finally:
        server.stop()
    _store(conn, site_id, fetched)
    keys = {r["metric_key"] for r in conn.execute(
        "SELECT metric_key FROM metric_snapshots WHERE site_id=?", (site_id,))}
    assert "composite_score" in keys
    conn.close()


# --- rule 4: no claim about a page that was never fetched --------------------

PAGE_DERIVED_LOC_CHECKS = {
    "nap-missing", "localbusiness-schema-missing", "opening-hours-missing",
    "nap-inconsistent",
}


def test_no_page_derived_finding_is_raised_without_a_page():
    """"No phone number found on any crawled page" — with no crawled page.
    The sentence is true only by vacuity, and a client reads it as a defect
    on their site."""
    from clauditseo.modules.loc import LocalModule

    findings = LocalModule().run(
        [], Tier.T2, {"crawl": _blocked_crawl(),
                      "site": Site(domain="x.test", business_type="local-service")})
    raised = {f.check_id for f in findings}
    assert not (raised & PAGE_DERIVED_LOC_CHECKS), (
        f"raised about pages that were never fetched: "
        f"{sorted(raised & PAGE_DERIVED_LOC_CHECKS)}")


def test_the_same_checks_still_fire_when_a_page_was_fetched():
    """The control. Suppressing the claims everywhere would make the report
    quieter rather than more honest."""
    from clauditseo.modules.loc import LocalModule

    fetched = CrawlResult(start_url="https://x.test/", tier=Tier.T2,
                          pages=[_page("https://x.test/")])
    findings = LocalModule().run(
        [], Tier.T2, {"crawl": fetched,
                      "site": Site(domain="x.test", business_type="local-service")})
    raised = {f.check_id for f in findings}
    assert "nap-missing" in raised
    assert "localbusiness-schema-missing" in raised


@pytest.mark.parametrize("dimension", ["ONP", "CNT", "AIS", "A11Y"])
def test_no_other_module_claims_anything_about_an_unfetched_page(dimension):
    """The rule is not LOC's alone: any check whose subject is a path is a
    claim about a page, and there was no page."""
    from clauditseo.engine import registry

    module = registry.get(dimension)
    findings = module.run([], Tier.T2,
                          {"crawl": _blocked_crawl(), "site": Site(domain="x.test")})
    page_scoped = [f.check_id for f in findings if f.subject.startswith("/")]
    assert page_scoped == [], f"{dimension} raised {page_scoped} with no page fetched"


# --- a blocked run is not a deliverable, and not a reason to re-audit --------

def test_a_blocked_run_cannot_become_a_client_deliverable(tmp_path):
    """The document would lead with a score for a site never retrieved. The
    scope line says so honestly, but a deliverable is the artefact that leaves
    the building — refusing is cheaper to explain than a caveat nobody reads."""
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    db = tmp_path / "deliverable.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client_id = repo.create_client(conn, op, "Blocked Co")
    site_id = repo.create_site(conn, client_id, "x.test")
    run_id, _ = _store(conn, site_id, _blocked_crawl())
    conn.close()

    api = TestClient(create_app(db_path=db))
    resp = api.post("/api/reports", json={"template": "run", "audience": "client",
                                          "run_ids": [run_id]})
    assert resp.status_code == 422, resp.text
    assert "fetched no pages" in resp.json()["detail"].lower() or \
           "blocked" in resp.json()["detail"].lower()


def test_the_reports_payload_says_which_runs_may_be_scored(tmp_path):
    """Both row shapes, because the screen prints a score from each of them.

    The rendered half of this is guarded in `test_a11y_rendered.py`, and it
    can only reach the bare-run table: painting the analyses table for a
    blocked run needs a stored brief, and the sweep's blocked site has none.
    So the shape is asserted here, where both rows can be built — otherwise
    the fix to the second render site would ship with nothing watching it.

    `status`, not a pre-computed boolean. The client already owns the
    predicate (`hasScore`), it is applied at six other render sites, and a
    server that shipped its own answer would be a second definition of when a
    composite may be printed.
    """
    conn, site_id = _db(tmp_path, "payload.db")
    run_id, _ = _store(conn, site_id, _blocked_crawl())
    runs.store_expert_report(conn, run_id, "crawl",
                             {"model": "test-model", "report": "text",
                              "findings": [], "tokens": 10})
    payload = runs.site_reports(conn, site_id)
    conn.close()

    assert payload["runs"], "the blocked run is not listed at all"
    assert [r["status"] for r in payload["runs"]] == ["blocked"], (
        "the bare-run rows carry no status, so the screen cannot tell a run "
        f"that fetched nothing from one that did: {payload['runs']}")
    assert payload["reports"], "the stored brief is not listed at all"
    assert [r["run_status"] for r in payload["reports"]] == ["blocked"], (
        "the analysis rows carry the run's composite and not the status that "
        f"qualifies it: {payload['reports']}")


def test_a_blocked_run_counts_as_an_audit_for_the_scheduler(tmp_path):
    """`due_sites` reads the newest completed run to decide whether the
    interval has elapsed. A site that blocks every crawl would show no
    completed run at all, so the scheduler would re-trigger on every tick —
    hammering a host that has already said no."""
    from datetime import datetime, timedelta

    from clauditseo import scheduler

    conn, site_id = _db(tmp_path, "sched.db")
    conn.execute("UPDATE sites SET schedule='weekly' WHERE id=?", (site_id,))
    conn.commit()
    run_id, _ = _store(conn, site_id, _blocked_crawl())

    # Just blocked: not due, and the scheduler must know a crawl happened.
    assert [s["id"] for s in scheduler.due_sites(conn, datetime.now())] == []

    # A fortnight later the weekly interval has elapsed and it is due again.
    later = datetime.now() + timedelta(days=14)
    assert [s["id"] for s in scheduler.due_sites(conn, later)] == [site_id]
    conn.close()


# --- a blocked crawl clears nothing, page-scoped or site-scoped -------------

def _states(conn):
    return {r["state"]: r["n"] for r in conn.execute(
        "SELECT state, COUNT(*) n FROM finding_states GROUP BY state")}


def test_a_blocked_crawl_clears_nothing_it_never_looked_at(tmp_path):
    """Round 006 stopped an empty crawl clearing PAGE-scoped findings, by
    requiring the finding's page to have been revisited. A site-scoped finding
    names no page, so that guard never applied to it — the dimension having
    run was the whole test. LOC kept raising its two site-scoped findings on
    an empty crawl, which hid the hole; once LOC correctly stopped describing
    pages it never fetched, their absence read as a fix.

    So a crawl that fetched nothing marked findings verified-fixed, attributed
    them to the blocked run, and reported them to the operator as that run's
    work — with each one due to return as a false regression on the next real
    audit."""
    conn, site_id = _db(tmp_path, "clears.db")

    server = FixtureSite(_routes(GOOD_PROMO)).start()
    try:
        fetched = crawl(server.base_url + "/", Tier.T2, budget=FAST)
    finally:
        server.stop()
    _store(conn, site_id, fetched)
    before = _states(conn)
    assert before.get("open"), "the fixture must leave something open to clear"
    open_before = {r["fingerprint"] for r in conn.execute(
        "SELECT fingerprint FROM finding_states WHERE state IN ('open','regressed')")}

    blocked_id, _ = _store(conn, site_id, _blocked_crawl())

    still_open = {r["fingerprint"] for r in conn.execute(
        "SELECT fingerprint FROM finding_states WHERE state IN ('open','regressed')")}
    assert open_before <= still_open, (
        f"a crawl that fetched nothing cleared {sorted(open_before - still_open)}")
    assert _states(conn).get("fixed", 0) == before.get("fixed", 0), \
        f"the fixed count moved: {before} -> {_states(conn)}"
    cleared = conn.execute(
        "SELECT COUNT(*) FROM finding_states WHERE changed_by_run=?"
        " AND state IN ('fixed','regressed')", (blocked_id,)).fetchone()[0]
    assert cleared == 0, \
        f"{cleared} finding(s) marked fixed or regressed by a run that saw nothing"

    # It may still OPEN what it genuinely measured. robots.txt was fetched and
    # is missing — that finding is the evidence explaining the block, and
    # suppressing it would lose the reason along with the false clearance.
    opened = conn.execute(
        "SELECT COUNT(*) FROM finding_states WHERE changed_by_run=? AND state='open'",
        (blocked_id,)).fetchone()[0]
    assert opened, "the findings that explain the block must enter the record"

    # The operator-visible surface, not just the table. `current_state` keys
    # `moved` on the site's newest audit, which a blocked run now is — so a
    # false clearance does not merely sit in the database, it is reported to
    # the operator as the blocked run's work. This is the number the site
    # screen puts in front of them.
    moved = runs.current_state(conn, site_id)["moved"]
    assert moved["fixed"] == 0, \
        f"the site screen credits a crawl that fetched nothing with {moved}"
    assert moved["regressed"] == 0, f"and with regressions it cannot have seen: {moved}"
    conn.close()


def test_a_crawl_that_fetched_pages_still_clears_what_it_verified(tmp_path):
    """The control, and the property this must not cost: a real crawl that
    revisits a page and finds the problem gone still records the fix."""
    conn, site_id = _db(tmp_path, "clears_ok.db")

    broken = FixtureSite(_routes(BROKEN_PROMO)).start()
    try:
        first = crawl(broken.base_url + "/", Tier.T2, budget=FAST)
    finally:
        broken.stop()
    _store(conn, site_id, first)
    assert _states(conn).get("open"), "nothing open to fix"

    good = FixtureSite(_routes(GOOD_PROMO)).start()
    try:
        second = crawl(good.base_url + "/", Tier.T2, budget=FAST)
    finally:
        good.stop()
    run_id, _ = _store(conn, site_id, second)

    assert _states(conn).get("fixed"), \
        "a crawl that looked again and found it gone must still clear it"
    assert conn.execute(
        "SELECT COUNT(*) FROM finding_states WHERE changed_by_run=? AND state='fixed'",
        (run_id,)).fetchone()[0] > 0
    conn.close()
