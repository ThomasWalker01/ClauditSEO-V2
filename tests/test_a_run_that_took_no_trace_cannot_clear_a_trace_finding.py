"""A run that did not trace a page may not clear a finding only a trace raises
(relay item 159).

`_apply_states` already refuses to clear on two axes, each added after it bit:
which page (a nav crawl clearing pages it never fetched) and which scope (a
narrow run clearing site-scoped findings). This is the third: which
instrument. A page refresh fetched the page and took no trace, so the trace
checks were silent on it and every one of them was marked `fixed` - due back
as a regression on the next traced audit.

Measured before the fix on a throwaway database, through the real refresh
route: a traced PRF audit raised eleven trace findings on `/`, and one Speed
refresh of `/` moved all eleven `open -> fixed` (`cleared: 11`). The first
clause below is that measurement, and it was red against the pre-change tree.

The suite sets `CLAUDITSEO_TRACE_PERF=0`, so `perf.trace_for_run` is
monkeypatched wherever a route would take the trace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo import perf
from clauditseo.api.app import create_app
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.modules import prf, sec, tec
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite
from tests.test_the_speed_trace_checks import CLEAN, DEFECT
from tests.test_verify import FAST, _routes

#: DEFECT plus enough transfer to cross the page-weight budget, so all twelve
#: page-naming PRF trace checks fire - `page-weight` included, which the
#: pre-fix measurement did not cover.
HEAVY = {**DEFECT, "resources": DEFECT["resources"] + [
    {"url": "https://x.test/big.js", "type": "script", "bytes": 4_000_000,
     "transfer": 3_000_000, "blocking": False, "compression": "br",
     "cache_control": "max-age=60", "whitespace_ratio": 0.02,
     "coverage": "unavailable"}]}


def _db(tmp: Path, domain: str):
    db = tmp / "t159.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    return db, conn, repo.create_site(conn, client, domain)


def _states(conn, site_id: str) -> dict[str, tuple[str, str, str | None]]:
    """check_id -> (state, changed_by_run, path list) for every finding."""
    out = {}
    for r in conn.execute(
            "SELECT f.check_id, f.affected_urls, fs.state, fs.changed_by_run"
            " FROM finding_states fs JOIN findings f"
            " ON f.fingerprint = fs.fingerprint AND f.rowid = ("
            "   SELECT MAX(rowid) FROM findings WHERE fingerprint = fs.fingerprint)"
            " WHERE fs.site_id=?", (site_id,)):
        out.setdefault(r["check_id"], []).append(
            (r["state"], r["changed_by_run"], r["affected_urls"]))
    return out


def _trace_ids(states) -> set[str]:
    return {c for c in states if runs.trace_instrumented("PRF", c)}


# --- through the route: the measured defect, and its control ----------------

@pytest.fixture
def traced_site(tmp_path, monkeypatch):
    """A fixture site with one completed PRF audit whose every page carried
    HEAVY, and a client onto the database.

    The provider hub is emptied: a PRF refresh at T2 asks the configured CWV
    providers, and on a machine holding keys that is a live Google call about
    a 127.0.0.1 URL - twenty seconds a clause, answering nothing here."""
    from clauditseo.providers.base import ProviderHub
    monkeypatch.setattr(ProviderHub, "from_settings",
                        classmethod(lambda cls, cfg: cls(backlink_providers=[],
                                                         cwv_providers=[])))
    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id = _db(tmp_path, site.base_url + "/")
        crawled = crawl(site.base_url + "/", Tier.T2, budget=FAST)
        traces = {p.url: HEAVY for p in crawled.pages if p.status == 200}
        result = run_audit(Site(domain=site.base_url + "/"), crawled, ["PRF"],
                           Tier.T2, context={"perf_traces": traces})
        runs.complete_run(conn, runs.create_run(conn, site_id, ["PRF"], "T2"),
                          result)
        yield site, TestClient(create_app(db_path=db)), conn, site_id
    finally:
        site.stop()


def test_a_refresh_that_took_no_trace_clears_no_trace_finding(
        traced_site, monkeypatch):
    """The item's defect, end to end: the trace pass answers nothing, as it
    does on a machine with no renderer, and the refresh must leave every trace
    finding on the page exactly where it was."""
    site, client, conn, site_id = traced_site
    monkeypatch.setattr(perf, "trace_for_run",
                        lambda crawl, run_id: ({}, "not taken - test"))
    before = _states(conn, site_id)
    assert {"ttfb-slow", "page-weight", "lcp-slow"} <= _trace_ids(before), (
        "the planted audit raised no trace findings to protect")

    body = client.post(f"/api/sites/{site_id}/refresh",
                       json={"url": site.base_url + "/", "section": "speed"}).json()
    assert body["dimension"] == "PRF" and body["pages"] == 1, body
    assert body["cleared"] == 0, (
        f"a refresh that took no trace cleared {body['cleared']} finding(s)")
    after = _states(conn, site_id)
    for check in _trace_ids(before):
        assert after[check] == before[check], (
            f"{check} moved on a run that never traced its page: "
            f"{before[check]} -> {after[check]}")


def test_a_refresh_takes_the_trace_and_a_clean_one_clears(
        traced_site, monkeypatch):
    """The control, and the other half of the fix: the refresh now asks for
    the trace, and a trace that finds the page clean is evidence of absence.
    Without this clause the one above passes against a rule that never
    clears a trace finding at all."""
    site, client, conn, site_id = traced_site
    asked = []

    def fake(crawl, run_id):
        asked.append([p.url for p in crawl.pages])
        return {p.url: CLEAN for p in crawl.pages if p.status == 200}, "test"

    monkeypatch.setattr(perf, "trace_for_run", fake)
    before = _states(conn, site_id)
    body = client.post(f"/api/sites/{site_id}/refresh",
                       json={"url": site.base_url + "/", "section": "speed"}).json()
    assert asked == [[site.base_url + "/"]], (
        f"the refresh did not trace the one page it read: {asked}")
    after = _states(conn, site_id)
    on_home = {c for c in _trace_ids(before)
               if any(json.loads(u) == [site.base_url + "/"] for _s, _r, u in before[c])}
    assert on_home, "no trace finding named the refreshed page"
    for check in on_home:
        assert all(s == "fixed" and r == body["run_id"] for s, r, _u in after[check]), (
            f"{check} was traced clean and did not clear: {after[check]}")
    stored = json.loads(conn.execute(
        "SELECT crawl_evidence FROM audit_runs WHERE id=?",
        (body["run_id"],)).fetchone()["crawl_evidence"])
    assert any(isinstance(p.get("perf"), dict) for p in stored["pages"]), (
        "the refresh took a trace and stored none of it as evidence")


def test_a_refresh_whose_dimension_reads_no_trace_takes_none(
        tmp_path, monkeypatch):
    """The throttled pass is the dearest thing a run can buy, so only the
    dimensions that read it pay for it."""
    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id = _db(tmp_path, site.base_url + "/")
        crawled = crawl(site.base_url + "/", Tier.T2, budget=FAST)
        runs.complete_run(conn, runs.create_run(conn, site_id, ["ONP"], "T2"),
                          run_audit(Site(domain=site.base_url + "/"), crawled,
                                    ["ONP"], Tier.T2))
        called = []
        monkeypatch.setattr(perf, "trace_for_run",
                            lambda c, r: called.append(r) or ({}, "x"))
        resp = TestClient(create_app(db_path=db)).post(
            f"/api/sites/{site_id}/refresh",
            json={"url": site.base_url + "/", "section": "headings"})
        assert resp.status_code == 200, resp.text
        assert called == [], "an ONP refresh took a performance trace"
    finally:
        site.stop()


# --- the state machine itself, with no network ------------------------------

def _crawl(*paths: str, html: str = "<html></html>") -> CrawlResult:
    pages = [Page(url=f"https://x.test{p}", requested_url=f"https://x.test{p}",
                  status=200, content_type="text/html", content=html)
             for p in paths]
    return CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=pages)


def _complete(conn, site_id, crawl_result, dims, traces, kind="audit"):
    result = run_audit(Site(domain="https://x.test/"), crawl_result, dims,
                       Tier.T2, context={"perf_traces": traces})
    run_id = runs.create_run(conn, site_id, dims, "T2", kind=kind)
    runs.complete_run(conn, run_id, result)
    return run_id, result


def test_an_audit_does_not_clear_on_the_pages_its_sample_skipped(tmp_path):
    """Not only a refresh. The trace samples one page per template and a
    machine with no renderer takes none, so an AUDIT that fetched `/a` without
    tracing it has not looked for `/a`'s trace findings either. The page it
    did trace, clean, clears - in the same run, so the contrast cannot be the
    pass having switched itself off."""
    _db_path, conn, site_id = _db(tmp_path, "https://x.test/")
    _complete(conn, site_id, _crawl("/", "/a"), ["PRF"],
              {"https://x.test/": HEAVY, "https://x.test/a": HEAVY})
    run_id, _ = _complete(conn, site_id, _crawl("/", "/a"), ["PRF"],
                          {"https://x.test/": CLEAN,
                           "https://x.test/a": {"traced": False}})
    for check, rows in _states(conn, site_id).items():
        if not runs.trace_instrumented("PRF", check):
            continue
        for state, by, urls in rows:
            if json.loads(urls) == ["https://x.test/a"]:
                assert state == "open", f"{check} on untraced /a became {state}"
            else:
                assert (state, by) == ("fixed", run_id), (
                    f"{check} on traced-clean / did not clear: {state}")


def test_the_instrument_rule_leaves_every_other_check_alone(tmp_path):
    """The rule is about trace-derived checks and nothing else. A title
    finding on the same page, re-read by the same untraced run and gone,
    clears as it always did."""
    _db_path, conn, site_id = _db(tmp_path, "https://x.test/")
    _complete(conn, site_id, _crawl("/"), ["PRF", "ONP"],
              {"https://x.test/": HEAVY})
    good = ("<html lang=en><head><title>A perfectly reasonable page title</title>"
            "<meta name=description content='A description long enough to pass "
            "the length check on this page'></head><body><main><h1>h</h1>"
            "<p>x</p></main></body></html>")
    run_id, _ = _complete(conn, site_id, _crawl("/", html=good), ["PRF", "ONP"], {})
    states = _states(conn, site_id)
    onp_cleared = [c for c, rows in states.items()
                   if not runs.trace_instrumented("PRF", c)
                   and any(s == "fixed" and r == run_id for s, r, _u in rows)]
    assert onp_cleared, "no non-trace finding cleared on the untraced re-read"
    assert all(s == "open" for c in _trace_ids(states) for s, _r, _u in states[c])


def test_verify_reports_an_untraced_page_as_not_checked(tmp_path):
    """The reporting half says what the clearing half did. A page read
    without a trace was not looked at for `ttfb-slow`, so the operator is told
    `not_checked` - not `unchanged`, which claims the page was examined."""
    _db_path, conn, site_id = _db(tmp_path, "https://x.test/")
    _complete(conn, site_id, _crawl("/"), ["PRF"], {"https://x.test/": HEAVY})
    fps = [r["fingerprint"] for r in conn.execute(
        "SELECT fingerprint FROM findings WHERE check_id='ttfb-slow'")]
    run_id, result = _complete(conn, site_id, _crawl("/"), ["PRF"], {},
                               kind="verify")
    out = runs.verify_outcomes(conn, site_id, fps, run_id,
                               crawled=result.crawled_paths,
                               seen=runs.emitted_fingerprints(result),
                               traced=result.traced_paths)
    assert [o["outcome"] for o in out] == ["not_checked"], out
    assert out[0]["decided"] is False


def test_traced_paths_are_the_pages_the_trace_answered_on():
    """`{"traced": False}` is the pass having run and failed on that page:
    the same test `prf._trace_checks` applies before it reads a trace."""
    result = run_audit(Site(domain="https://x.test/"), _crawl("/", "/a", "/b"),
                       ["PRF"], Tier.T2,
                       context={"perf_traces": {"https://x.test/": CLEAN,
                                                "https://x.test/a": {"traced": False}}})
    assert result.crawled_paths == {"/", "/a", "/b"}
    assert result.traced_paths == {"/"}


def test_the_instrument_set_is_every_trace_derived_id_and_page_weight():
    """Read off the modules' own sets, so a check added to any of them is
    protected the day it is added.

    `page-weight` was a local addition here while PRF's set left it out; item
    168 moved it into the set, and this reads it from there. The claim under
    it is unchanged and still checked below: since migration 0054 nothing but
    the trace raises it.
    """
    for dim, ids in (("PRF", prf.TRACE_DERIVED_CHECKS),
                     ("TEC", tec.TRACE_DERIVED_CHECKS),
                     ("SEC", sec.TRACE_DERIVED_CHECKS)):
        for check in ids:
            assert runs.trace_instrumented(dim, check), f"{dim}/{check}"
    assert runs.trace_instrumented("PRF", "page-weight")
    assert not runs.trace_instrumented("PRF", "cwv-not-assessed")
    assert not runs.trace_instrumented("TEC", "page-weight"), (
        "the set is keyed by dimension; an id is not trace-derived everywhere")

    huge = "<html><body>" + "x" * 5_000_000 + "</body></html>"
    untraced = run_audit(Site(domain="https://x.test/"), _crawl("/", html=huge),
                         ["PRF"], Tier.T2)
    assert "page-weight" not in {f.check_id for f in untraced.findings}, (
        "something other than the trace raises page-weight again, so an "
        "untraced run can measure it and this rule would withhold a real "
        "clearance")
