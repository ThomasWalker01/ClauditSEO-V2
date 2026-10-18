"""The page dossier says which crawls it looked in, and which run each crawl
row was (item 257, rows 2 and 3 of the pages-notes audit).

The dossier read "seen in 6 crawl(s)" on a site with eleven crawls: only the
newest `DOSSIER_RUNS` are opened, so six was the window, not the count. And
its crawl history was a date, a status, words and depth, with nothing to say
whether a row was a full audit or a one-part re-check of the same day.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

URL = "https://dossier.test/a"


def _crawl(conn, site, day, *, with_page=True, kind="audit", tier="T2"):
    run_id = runs.create_run(conn, site, ["TEC"], tier, kind=kind,
                             scan_scope="site" if kind == "audit" else "page")
    pages = [{"url": "https://dossier.test/", "status": 200, "word_count": 100}]
    if with_page:
        pages.append({"url": URL, "status": 200, "word_count": 300, "title": "A"})
    runs.store_evidence(conn, run_id, {"start_url": "https://dossier.test/", "pages": pages})
    conn.execute("UPDATE audit_runs SET status='complete', started_at=? WHERE id=?",
                 (f"2026-09-{day:02d}T00:00:00+00:00", run_id))
    conn.commit()
    return run_id


def _site(tmp_path):
    conn = connect(tmp_path / "dossier.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    return conn, repo.create_site(conn, repo.create_client(conn, op, "Dossier Co"), "dossier.test")


def test_the_count_is_of_the_crawls_looked_in_and_says_how_many_there_are(tmp_path):
    conn, site = _site(tmp_path)
    for day in range(1, runs.DOSSIER_RUNS + 4):            # nine crawls
        _crawl(conn, site, day, with_page=day % 3 != 0)
    got = runs.page_dossier(conn, site, URL)
    assert got["crawls"] == {"looked_in": runs.DOSSIER_RUNS, "total": runs.DOSSIER_RUNS + 3}
    assert len(got["history"]) == 4, "the page is in four of the newest six crawls"


def test_each_crawl_row_names_its_run(tmp_path):
    conn, site = _site(tmp_path)
    _crawl(conn, site, 1, tier="T3")
    _crawl(conn, site, 2, kind="refresh")
    rows = runs.page_dossier(conn, site, URL)["history"]
    assert [(r["kind"], r["tier"], r["scope"]) for r in rows] == [
        ("refresh", "T2", "page"), ("audit", "T3", "site")], rows


@needs_build
def test_the_dossier_says_what_it_counted_and_which_run_each_row_was(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    conn = connect(Path(ids["db"]))
    try:
        site = conn.execute("SELECT domain FROM sites WHERE id=?", (ids["site"],)).fetchone()[0]
        evidence = json.loads(conn.execute(
            "SELECT crawl_evidence FROM audit_runs WHERE id=?", (ids["run"],)).fetchone()[0])
        url = next(p["url"] for p in evidence["pages"] if p.get("status") == 200)
        want = runs.page_dossier(conn, ids["site"], url)
    finally:
        conn.close()
    assert want["history"], f"the fixture's page {url} on {site} has no crawl history"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}/dossier/{quote(url, safe='')}", wait_until="load")
            pg.wait_for_selector(".dossier-run", timeout=30_000)
            got = pg.evaluate("""() => ({
              line: document.querySelector('.dossier-url + p').textContent.replace(/\\s+/g, ' '),
              runs: [...document.querySelectorAll('.dossier-run')].map((e) => e.textContent.trim()) })""")
        finally:
            browser.close()
    c = want["crawls"]
    n = len(want["history"])
    plural = lambda k: f"{k} crawl{'' if k == 1 else 's'}"  # noqa: E731
    said = (f"seen in {n} of the last {plural(c['looked_in'])} ({c['total']} in all)"
            if c["total"] > c["looked_in"] else f"seen in {n} of the site's {plural(c['total'])}")
    assert said in got["line"], got["line"]
    assert "crawl(s)" not in got["line"]
    assert len(got["runs"]) == n and all(got["runs"]), got["runs"]
    for row, label in zip(want["history"], got["runs"]):
        if row["kind"] == "audit":
            assert label.startswith(row["tier"]), (row, label)
