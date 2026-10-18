"""The chooser's times are this site's own stored runs', not a constant (item
255, the audit pane's AC-02, AC-03 and US-02).

The time column was `pages x {quick 1.8, standard 4.5, deep 11}` seconds under
a foot saying "Times are estimates and get more honest as runs are stored".
No code read a stored run. On twenty22 the Nav · Quick cell promised "~27s"
for the scan that had just taken eight minutes; its Quick site audits measure
about 12 s a page.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)
from tests.test_the_precheck_pane_compares_and_suggests import COMPARE, _precheck

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _run(conn, site, *, pages, secs, kind="audit", depth="quick", status="complete",
         analyst=False, day=1):
    run_id = runs.create_run(conn, site, ["TEC"], "T2", kind=kind, analyst_enabled=analyst,
                             scan_scope="site" if pages > 1 else "page", scan_depth=depth)
    start = f"2026-09-{day:02d}T00:00:00+00:00"
    m, s = divmod(secs, 60)
    conn.execute("UPDATE audit_runs SET status=?, started_at=?, finished_at=?, crawled_paths=?"
                 " WHERE id=?",
                 (status, start, f"2026-09-{day:02d}T00:{m:02d}:{s:02d}+00:00",
                  json.dumps([f"/p{i}" for i in range(pages)]), run_id))
    conn.commit()
    return run_id


def _site(tmp_path):
    conn = connect(tmp_path / "pace.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    return conn, repo.create_site(conn, repo.create_client(conn, op, "Pace Co"), "pace.test")


def test_the_pace_is_the_median_of_the_sites_stored_runs(tmp_path):
    conn, site = _site(tmp_path)
    for day, secs in enumerate((100, 300, 200), start=1):          # 10, 30, 20 s a page
        _run(conn, site, pages=10, secs=secs, day=day)
    pace = runs.scan_pace(conn, site)
    assert pace["audit"]["quick"]["per_page"] == {"secs": 20.0, "runs": 3}
    assert pace["audit"]["standard"]["per_page"] == {"secs": None, "runs": 0}, (
        "a depth with no stored run was given a figure")


def test_a_one_page_run_is_a_duration_and_never_a_rate(tmp_path):
    """One page carries the whole fixed cost: divided into a per-page rate it
    would say a 45-page audit takes half an hour."""
    conn, site = _site(tmp_path)
    _run(conn, site, pages=10, secs=100, day=1)
    _run(conn, site, pages=1, secs=40, day=2)
    pace = runs.scan_pace(conn, site)
    assert pace["audit"]["quick"]["per_page"] == {"secs": 10.0, "runs": 1}
    assert pace["audit"]["quick"]["one_page"] == {"secs": 40.0, "runs": 1}


def test_a_recheck_is_timed_apart_from_an_audit_and_other_runs_are_left_out(tmp_path):
    conn, site = _site(tmp_path)
    _run(conn, site, pages=10, secs=100, day=1)
    _run(conn, site, pages=1, secs=12, kind="refresh", day=2)
    _run(conn, site, pages=8, secs=8, kind="verify", day=3)         # neither kind
    _run(conn, site, pages=10, secs=900, status="failed", day=4)    # did not finish a reading
    _run(conn, site, pages=10, secs=600, depth="deep", analyst=True, day=5)
    pace = runs.scan_pace(conn, site)
    assert pace["recheck"]["quick"]["one_page"] == {"secs": 12.0, "runs": 1}
    assert pace["audit"]["quick"]["per_page"] == {"secs": 10.0, "runs": 1}, (
        "a verification, a failed run or another depth moved Quick's pace")
    assert pace["audit"]["deep"]["per_page"] == {"secs": 60.0, "runs": 1}
    # A run from before the depth column is what its analyst flag says.
    old = _run(conn, site, pages=10, secs=200, day=6)
    conn.execute("UPDATE audit_runs SET scan_depth=NULL WHERE id=?", (old,))
    conn.commit()
    assert runs.scan_pace(conn, site)["audit"]["quick"]["per_page"] == {"secs": 15.0, "runs": 2}


def test_no_screen_multiplies_pages_by_the_constant_itself():
    """The constant is the fallback inside `estimate` and nowhere else."""
    for name in ("scanmatrix.tsx", "reaudit.tsx", "part_page.tsx"):
        src = (UI / name).read_text(encoding="utf-8")
        uses = [m.start() for m in re.finditer(r"SECS_PER_PAGE\[|SECS_PER_PAGE\.", src)]
        if name != "scanmatrix.tsx":
            assert not uses, f"{name} still times a scan from the constant"
            continue
        body = src[src.index("export function estimate"):]
        body = body[:body.index("\n}\n")]
        assert len(uses) == 1 and "SECS_PER_PAGE[depth]" in body, (
            "the constant is read outside `estimate`'s fallback")


def _human(secs: float) -> str:
    if secs < 90:
        return f"~{round(secs)}s"
    if secs < 3600:
        return f"~{_js_round(secs / 60)}m"
    h = secs / 3600
    return f"~{h:.1f}h" if h < 2 else f"~{_js_round(h)}h"


def _js_round(x: float) -> int:
    import math
    return math.floor(x + 0.5)


@needs_build
def test_the_grid_quotes_the_sites_measured_time_and_says_where_it_came_from(served):
    """The item's signal, on the fixture: give the site three stored Quick
    audits at a known pace and the Site · Quick cell reads pages x that pace,
    with the foot naming the run count."""
    import sqlite3
    from playwright.sync_api import sync_playwright
    base, ids = served
    conn = sqlite3.connect(ids["db"])
    conn.row_factory = sqlite3.Row
    before = [dict(r) for r in conn.execute(
        "SELECT id, started_at, finished_at, crawled_paths, scan_depth FROM audit_runs"
        " WHERE site_id=?", (ids["site"],))]
    try:
        # Every stored audit of the fixture site: 20 pages in 400 s, Quick.
        with conn:
            conn.execute("UPDATE audit_runs SET started_at=substr(started_at,1,11)||'00:00:00+00:00',"
                         " finished_at=substr(started_at,1,11)||'00:06:40+00:00', scan_depth='quick',"
                         " crawled_paths=? WHERE site_id=? AND status='complete' AND kind='audit'",
                         (json.dumps([f"/p{i}" for i in range(20)]), ids["site"]))
        pace = runs.scan_pace(conn, ids["site"])
        got_runs = pace["audit"]["quick"]["per_page"]
        assert got_runs["secs"] == 20.0 and got_runs["runs"] >= 1, pace
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pg = browser.new_page(viewport={"width": 1568, "height": 1200})
            try:
                # The fixture runs no precheck, and without one no row has a
                # page count to time. The neighbouring test's wire: 15 nav
                # pages, 55 published.
                pre = _precheck("https://fixture.test")
                pg.route(f"**/api/sites/{ids['site']}/precheck",
                         lambda r: r.fulfill(status=200, content_type="application/json",
                                             body=json.dumps(pre)))
                pg.route(f"**/api/sites/{ids['site']}/precheck/compare",
                         lambda r: r.fulfill(status=200, content_type="application/json",
                                             body=json.dumps(COMPARE)))
                pg.goto(f"{base}/#/sites/{ids['site']}?tab=history", wait_until="load")
                pg.wait_for_selector(".scan-grid .scan-cell .scan-time", timeout=30_000)
                pg.wait_for_function(
                    "() => /this site's own|a default/.test(document.querySelector('.scan-foot').textContent)",
                    timeout=20_000)
                got = pg.evaluate("""() => {
                  const heads = [...document.querySelectorAll('.scan-grid .scan-rowhead')];
                  const cells = [...document.querySelectorAll('.scan-grid .scan-cell')];
                  return { rows: heads.map((h, i) => ({
                             label: h.querySelector('strong').textContent.trim(),
                             pages: h.querySelector('.scan-pages').textContent.trim(),
                             times: cells.slice(i * 3, i * 3 + 3).map((c) => c.querySelector('.scan-time').textContent.trim()),
                             names: cells.slice(i * 3, i * 3 + 3).map((c) => c.getAttribute('aria-label')) })),
                           foot: document.querySelector('.scan-foot').textContent }; }""")
            finally:
                browser.close()
    finally:
        with conn:
            for r in before:
                conn.execute("UPDATE audit_runs SET started_at=?, finished_at=?, crawled_paths=?,"
                             " scan_depth=? WHERE id=?",
                             (r["started_at"], r["finished_at"], r["crawled_paths"], r["scan_depth"], r["id"]))
        conn.close()
    assert f"Quick about 20 s a page from {got_runs['runs']} stored run" in got["foot"], got["foot"]
    assert "get more honest" not in got["foot"]
    many = [r for r in got["rows"] if re.match(r"\d+ pages", r["pages"]) and int(r["pages"].split()[0]) > 1]
    assert many, f"the fixture's precheck gave no row more than one page: {got['rows']}"
    for r in many:
        n = int(r["pages"].split()[0])
        assert r["times"][0] == _human(n * 20.0), (
            f"{r['label']} · Quick over {n} pages reads {r['times'][0]}, and the site's "
            f"stored runs say {_human(n * 20.0)}")
        # No Standard or Deep run is stored: Quick's time, as a floor.
        assert r["times"][1].startswith("≥") and r["times"][2].startswith("≥"), r
        assert "at least" in r["names"][1] and "at least" not in r["names"][0], r["names"]
    assert "as a bound" in got["foot"], got["foot"]
