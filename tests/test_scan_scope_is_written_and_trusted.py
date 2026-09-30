"""`scan_scope` is written on every launch, backfilled where it was NULL, and
trusted over the tier wherever "site-wide" is decided.

Brief v3 step I (`_plans/site-screen-brief-v3-2026-09-03.md`, WF-08 and
WF-05b). Every run on the operator's database predated the column, so
`scan_scope` was NULL on all of them and the dashboard fell back to the
tier: a T2 run that fetched the navigation set - twenty pages - stood as
the latest site-wide crawl, and the record marked 207 of 227 pages "not in
latest crawl" on every group; a T1 run that fetched one page wore
"site-wide" in the scope bar and its 94.2 stood as the site's score on Home.

Three halves. The launch route writes a scope on every insert - the
chooser's, or `full` for the by-hand launcher (`nav` when it asked for the
navigation set). Migration `0034` backfills from the crawl's own page
count. And the readers - `runs.scope_of` on the server, `scopeOf` in the
dashboard - decide by the stored scope, else by the page count, and never
by the tier.
"""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from clauditseo.db import migrate as migrate_mod
from clauditseo.db.connection import connect
from clauditseo.db.migrate import MIGRATIONS_DIR, applied, migrate
from clauditseo.persistence import repo, runs
from tests.test_a11y_rendered import DIST
from tests.test_coverage import DIMS

BACKFILL = "0034_backfill_scan_scope.py"

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


# ---- the migration ----------------------------------------------------------------

def _through_0033(db: Path) -> sqlite3.Connection:
    conn = connect(db)
    applied(conn)
    for path in migrate_mod._files():
        if path.name == BACKFILL:
            continue
        with conn:
            if path.suffix == ".py":
                migrate_mod._apply_python(path, conn)
            else:
                conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
    return conn


def _paths(n: int) -> str:
    return json.dumps([f"/p{i}" for i in range(n)])


def test_the_backfill_reads_the_crawls_own_page_count_and_never_the_tier(tmp_path):
    assert (MIGRATIONS_DIR / BACKFILL).is_file()
    conn = _through_0033(tmp_path / "old.db")
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Scope Co"), "scope.fixture")
    rows = {
        "one_page_t1": ("T1", _paths(1)),
        "nav_t2": ("T2", _paths(20)),
        "site_t3": ("T3", _paths(224)),
        "small_t3": ("T3", _paths(20)),     # a T3 that fetched few: left NULL
        "middling_t2": ("T2", _paths(99)),  # over the nav bound: left NULL
        "no_paths": ("T2", None),
    }
    ids = {}
    for name, (tier, paths) in rows.items():
        run_id = runs.create_run(conn, site, DIMS, tier)
        conn.execute("UPDATE audit_runs SET crawled_paths=?, scan_scope=NULL WHERE id=?",
                     (paths, run_id))
        ids[name] = run_id
    verify = runs.create_run(conn, site, DIMS, "T2", kind="verify")
    conn.execute("UPDATE audit_runs SET crawled_paths=?, scan_scope=NULL WHERE id=?",
                 (_paths(1), verify))
    conn.commit()

    ran = migrate(conn)
    assert ran == [BACKFILL], ran
    got = {name: conn.execute("SELECT scan_scope FROM audit_runs WHERE id=?",
                              (run_id,)).fetchone()[0] for name, run_id in ids.items()}
    assert got == {"one_page_t1": "page", "nav_t2": "nav", "site_t3": None,
                   "small_t3": None, "middling_t2": None, "no_paths": None}, got
    assert conn.execute("SELECT scan_scope FROM audit_runs WHERE id=?",
                        (verify,)).fetchone()[0] is None, "a verification is narrow by kind"
    assert migrate(conn) == [], "the backfill ran twice"
    # And the readers' rule fills what the backfill left: by count, never tier.
    read = {name: runs.scope_of(conn.execute("SELECT * FROM audit_runs WHERE id=?",
                                             (run_id,)).fetchone())
            for name, run_id in ids.items()}
    assert read["site_t3"] == "site" and read["middling_t2"] == "site"
    assert read["small_t3"] == "nav" and read["no_paths"] is None
    conn.close()


def test_the_launch_route_writes_a_scope_on_every_insert(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    # Never crawl: the row is what this reads, and it is written before the
    # crawl thread starts.
    import clauditseo.api.app as app_mod
    monkeypatch.setattr(app_mod, "_execute_run", lambda *a, **k: None)
    db = tmp_path / "launch.db"
    client = TestClient(create_app(db_path=db))
    c = client.post("/api/clients", json={"name": "Launch Co"}).json()
    site = client.post(f"/api/clients/{c['id']}/sites", json={"domain": "launch.fixture"}).json()
    cases = [
        ({"scope": "site", "depth": "quick"}, "site"),
        ({"dims": ["TEC"], "tier": "T2"}, "full"),
        ({"dims": ["TEC"], "tier": "T2", "nav_only": True}, "nav"),
    ]
    conn = connect(db)
    for body, want in cases:
        resp = client.post(f"/api/sites/{site['id']}/audits", json=body)
        assert resp.status_code == 202, resp.text
        run_id = resp.json()["run_id"]
        got = conn.execute("SELECT scan_scope FROM audit_runs WHERE id=?", (run_id,)).fetchone()[0]
        assert got == want, (body, got)
        # Each launch has to finish before the next is allowed.
        conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run_id,))
        conn.commit()
    conn.close()


def test_home_shows_the_last_site_wide_score_not_a_one_page_scan(tmp_path):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    from tests.test_coverage import _Hub, _run

    db = tmp_path / "home.db"
    client = TestClient(create_app(db_path=db))
    c = client.post("/api/clients", json={"name": "Home Co"}).json()
    site = client.post(f"/api/clients/{c['id']}/sites", json={"domain": "home.fixture"}).json()
    conn = connect(db)
    result = _run(_Hub())
    wide = runs.create_run(conn, site["id"], DIMS, "T3")
    runs.complete_run(conn, wide, result)
    conn.execute("UPDATE audit_runs SET crawled_paths=?, scan_scope=NULL, composite_score=70.5"
                 " WHERE id=?", (_paths(224), wide))
    time.sleep(1.1)
    one = runs.create_run(conn, site["id"], DIMS, "T1")
    runs.complete_run(conn, one, result)
    conn.execute("UPDATE audit_runs SET crawled_paths=?, scan_scope=NULL, composite_score=94.2"
                 " WHERE id=?", (_paths(1), one))
    conn.commit()
    conn.close()
    overview = client.get("/api/overview").json()
    row = next(s for s in overview["sites"] if s["site_id"] == site["id"]) \
        if isinstance(overview, dict) else next(s for s in overview if s["site_id"] == site["id"])
    assert row["score"] == 70.5, row
    # The client's own listing carries `latest_score`; `/api/sites` does not.
    listed = next(s for s in client.get(f"/api/clients/{c['id']}").json()["sites"]
                  if s["id"] == site["id"])
    assert listed["latest_score"] == 70.5, listed
    assert listed["run_count"] == 2, listed


# ---- the dashboard -----------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A site-wide T3 audit of 224 paths, then a T2 audit that fetched 20 -
    the operator's own shape - with `scan_scope` NULL on both."""
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from tests.test_coverage import _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="scanscope"))
    db = tmp / "clauditseo.db"
    app = create_app(db_path=db)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")
    base = f"http://127.0.0.1:{port}"
    try:
        c = httpx.post(f"{base}/api/clients", json={"name": "Scope Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{c['id']}/sites",
                          json={"domain": "scope.fixture"}, timeout=30).json()
        conn = connect(db)
        result = _run(_Hub())
        wide = runs.create_run(conn, site["id"], DIMS, "T3")
        runs.complete_run(conn, wide, result)
        # The site-wide crawl fetched the findings' pages and more.
        pages = {u for f in result.findings for u in f.affected_urls if u.startswith("http")}
        from urllib.parse import urlsplit
        wide_paths = sorted({urlsplit(u).path or "/" for u in pages} | {f"/p{i}" for i in range(224)})
        conn.execute("UPDATE audit_runs SET crawled_paths=?, scan_scope=NULL WHERE id=?",
                     (json.dumps(wide_paths), wide))
        time.sleep(1.1)
        # The navigation scan opens one finding of its own, on a page the
        # site-wide crawl fetched, so it is the run that last moved the
        # counts and the stamp names it.
        from clauditseo.engine.types import Finding, Severity
        result.findings.append(Finding(
            dimension="TEC", check_id="security-headers", severity=Severity.LOW,
            summary="A header is missing on /p1.", subject="/p1",
            affected_urls=["https://x.test/p1"]))
        nav = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, nav, result)
        conn.execute("UPDATE audit_runs SET crawled_paths=?, scan_scope=NULL WHERE id=?",
                     (_paths(20), nav))
        conn.commit()
        conn.close()
        yield base, site["id"], wide, nav
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
@NEEDS_BROWSER
def test_the_record_and_the_bar_trust_the_page_count_not_the_tier(browser, served):
    base, site_id, wide, nav = served
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=all&group=none", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".state-filters", timeout=30_000)
        pg.click('[aria-label="state filter"] [data-state="all"]')
        pg.wait_for_selector("tbody tr:has(code)", timeout=30_000)
        marked = pg.evaluate("() => document.querySelectorAll('tbody tr .page-gone').length")
        # The stamp heads the landing's Waiting lane since brief v24 step BM.
        pg.goto(f"{base}/#/sites/{site_id}", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".cur-when", timeout=30_000)
        stamp = pg.inner_text(".cur-when")
        pg.click('a.seq-name:text-is("Record")')
        pg.click('.record-view a:text-is("Audits")')
        pg.wait_for_selector(".runs-table tbody tr", timeout=30_000)
        scores = pg.evaluate("() => [...document.querySelectorAll('.runs-table tbody tr')].map((tr) => tr.querySelectorAll('td')[4].textContent.trim())")
        caption = pg.inner_text(".runs-table caption")
    finally:
        pg.close()
    # The newest run fetched twenty pages: by tier a site reading, by count a
    # navigation scan. The marker rests on the 224-page crawl, which fetched
    # every finding's page, so nothing is marked gone.
    assert marked == 0, f"{marked} rows marked against a twenty-page crawl"
    assert "nav scan" in stamp and "site-wide" not in stamp, stamp
    assert scores[0] == "nav scan", scores
    assert "page scan / nav scan" in caption, caption
