"""A run's address lands on the record it belongs to (item 251, step 2).

`#/runs/<id>` rendered a finished run's own record with no banner, so a
stored link showed a past audit as though it were the site; it redirects to
the history view, which names the audit and offers the way back. A run that
is in flight, failed or cancelled keeps the run page, which the history view
has no place for. `#/runs/<id>/page/<url>` lands on the page's dossier, and
the page-level analyses that lived there moved with it.

The compare screen keeps its header and the fingerprint diff; a list is
drawn 25 rows at a time.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import now_iso
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")
BUILT = pytest.mark.skipif(not (DIST / "index.html").is_file(),
                           reason="dashboard not built (npm run build in dashboard/)")

HOME = "https://d.fixture/"


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "dossier.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "D Co"), "d.fixture")
    yield conn, site_id
    conn.close()


def _run(conn, site_id, at, pages, kind="audit"):
    run = runs.create_run(conn, site_id, ["ONP"], "T2", kind=kind,
                          scan_scope="site" if kind == "audit" else None)
    runs.store_evidence(conn, run, {"start_url": HOME, "pages": [
        {"url": u, "status": 200, "title": "t"} for u in pages]})
    conn.execute("UPDATE audit_runs SET status='complete', started_at=?, finished_at=?,"
                 " created_at=?, crawled_paths=? WHERE id=?",
                 (at, at, at, json.dumps(["/" + u.split("/", 3)[3] for u in pages]), run))
    conn.commit()
    return run


def test_a_page_level_analysis_runs_against_the_run_that_last_measured_the_page(db):
    """Not the site's newest run (channel answer 20261002-1150): a page the
    newest crawl did not fetch was last measured by an older one."""
    conn, site_id = db
    about = HOME + "about/"
    older = _run(conn, site_id, "2026-09-18T00:00:00+00:00", [HOME, about])
    newer = _run(conn, site_id, "2026-09-28T00:00:00+00:00", [HOME])
    assert runs.page_dossier(conn, site_id, HOME)["measured_run_id"] == newer
    assert runs.page_dossier(conn, site_id, about)["measured_run_id"] == older


def test_the_dossier_lists_the_newest_report_of_each_tool_for_the_page(db):
    """Whichever run produced it: a page re-crawled since its last analysis
    still has that analysis."""
    conn, site_id = db
    older = _run(conn, site_id, "2026-09-18T00:00:00+00:00", [HOME])
    newer = _run(conn, site_id, "2026-09-28T00:00:00+00:00", [HOME])

    def store(run, tool, page, text):
        runs.store_expert_report(conn, run, tool, {"model": "m", "report": text, "findings": []},
                                 page_url=page)

    store(older, "content-brief", HOME, "the older judgement")
    assert [(r["tool"], r["run_id"]) for r in runs.page_report_index(conn, site_id, HOME)] == [
        ("content-brief", older)]
    # Another page's report, and a site-scoped one, are not this page's.
    store(older, "content-brief", HOME + "about/", "another page")
    store(newer, "speed", None, "site-scoped")
    assert [r["tool"] for r in runs.page_report_index(conn, site_id, HOME)] == ["content-brief"]
    # A newer report of the same tool for the same page replaces the older.
    conn.execute("UPDATE expert_reports SET created_at='2026-09-18T01:00:00+00:00'")
    store(newer, "content-brief", HOME, "the newer judgement")
    got = runs.page_report_index(conn, site_id, HOME)
    assert [(r["tool"], r["run_id"]) for r in got] == [("content-brief", newer)]
    # And the text is read from the run it is stored under, for that page.
    assert runs.expert_report(conn, older, "content-brief", page_url=HOME)["report"] == "the older judgement"


# ---- the screen --------------------------------------------------------------------

@NEEDS_BROWSER
@BUILT
def test_a_finished_runs_address_lands_on_the_history_view_with_its_banner(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1440, "height": 1000})
            pg.goto(f"{base}/#/runs/{ids['run']}", wait_until="load", timeout=30_000)
            pg.wait_for_selector(".history-banner", timeout=30_000)
            got = pg.evaluate("""() => ({
              hash: location.hash,
              banner: document.querySelector('.history-banner').textContent.trim(),
              back: document.querySelector('.history-banner a')?.getAttribute('href'),
              heading: (document.querySelector('h2')?.textContent || '').trim(),
            })""")
        finally:
            b.close()
    assert got["hash"] == f"#/sites/{ids['site']}?tab=all&view=audits&run={ids['run']}", got["hash"]
    assert got["banner"].startswith("Viewing as of audit"), got["banner"]
    assert got["back"] == f"#/sites/{ids['site']}?tab=all&view=audits", got["back"]


@NEEDS_BROWSER
@BUILT
def test_a_run_in_flight_keeps_the_run_page(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    conn = connect(__import__("pathlib").Path(ids["db"]))
    run_id = runs.create_run(conn, ids["site"], ["TEC"], "T2")
    conn.close()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                pg = b.new_page(viewport={"width": 1440, "height": 1000})
                pg.goto(f"{base}/#/runs/{run_id}", wait_until="load", timeout=30_000)
                pg.wait_for_selector("h2", timeout=30_000)
                pg.wait_for_timeout(1500)
                got = pg.evaluate("() => ({hash: location.hash, banner: !!document.querySelector('.history-banner'), h2: document.querySelector('h2').textContent})")
            finally:
                b.close()
    finally:
        conn = connect(__import__("pathlib").Path(ids["db"]))
        conn.execute("DELETE FROM audit_runs WHERE id=?", (run_id,))
        conn.commit()
        conn.close()
    assert got["hash"] == f"#/runs/{run_id}", got
    assert not got["banner"] and "running" in got["h2"], got


@NEEDS_BROWSER
@BUILT
def test_the_compare_lists_are_drawn_a_page_at_a_time(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1440, "height": 1000})
            pg.goto(f"{base}/#/compare/{ids['run']}/{ids['run2']}", wait_until="load", timeout=30_000)
            pg.wait_for_selector("h2:has-text('Audit comparison')", timeout=30_000)
            pg.wait_for_timeout(1000)
            got = pg.evaluate("""() => [...document.querySelectorAll('.card')].filter((c) => c.querySelector('h3')).map((c) => ({
              title: c.querySelector('h3').textContent.trim(),
              rows: c.querySelectorAll('ul > li').length,
              more: (c.querySelector('.compare-more')?.textContent || '').trim(),
            }))""")
        finally:
            b.close()
    assert got, "the compare screen drew no list"
    for card in got:
        total = int(card["title"].rsplit("(", 1)[1].rstrip(")"))
        assert card["rows"] == min(total, 25), card
        assert bool(card["more"]) == (total > 25), card
        if total > 25:
            assert card["more"].startswith(f"Showing 25 of {total}."), card


# ---- reports (item 251 step 5) --------------------------------------------------

def test_a_report_row_states_what_its_document_was_built_over():
    """From the frozen copy stored with the report, which nothing read."""
    copy = {"taken_at": "2026-09-29T00:00:00+00:00",
            "composite": {"run_id": "r1", "score": 70.29, "tier": "T2",
                          "at": "2026-09-28T20:17:00+00:00"},
            "findings": [{"fingerprint": "a"}, {"fingerprint": "b"}],
            "hold": {"count": 1},
            "measured_from": "2026-09-18T07:50:00+00:00",
            "measured_to": "2026-09-28T20:17:00+00:00",
            "analyses": {"speed": {"at": "2026-09-23T02:49:00+00:00"},
                         "urls": {"at": "2026-09-23T11:28:00+00:00"}}}
    got = runs._built_over(json.dumps(copy))
    assert got == {
        "taken_at": "2026-09-29T00:00:00+00:00", "run_id": "r1", "score": 70.29, "tier": "T2",
        "audit_at": "2026-09-28T20:17:00+00:00", "open_findings": 2, "held_on": 1,
        "measured_from": "2026-09-18T07:50:00+00:00",
        "measured_to": "2026-09-28T20:17:00+00:00",
        "analyses": 2, "oldest_analysis": "2026-09-23T02:49:00+00:00"}
    assert runs._built_over(None) is None and runs._built_over("not json") is None


@NEEDS_BROWSER
@BUILT
def test_the_per_run_report_address_lands_on_the_sites_reports_tab(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1440, "height": 1000})
            pg.goto(f"{base}/#/reports/{ids['run']}", wait_until="load", timeout=30_000)
            pg.wait_for_function("() => location.hash.endsWith('/reports')", timeout=30_000)
            landed = pg.evaluate("location.hash")
        finally:
            b.close()
    assert landed == f"#/sites/{ids['site']}/reports", landed
