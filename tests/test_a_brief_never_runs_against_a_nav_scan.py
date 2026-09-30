"""A brief never runs against a nav or page scan: the server refuses with
409 and one sentence. Since item 239 step 5 nothing picks an audit, so the
site screen never holds a nav scan: its controls read the site-wide run and
are enabled, with no refusal said.

Brief v6 step V3 (`_plans/site-screen-brief-v6-2026-09-03.md`). Four paid
briefs on Birch are bound to a nav scan and would be offered to run again
once the picker moved to a site-wide audit.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import json
import time

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST
from tests.test_coverage import DIMS, _Hub, _run
from tests.test_triage_ranks_the_section_rail import _serve

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]


@pytest.fixture(scope="module")
def served():
    """A site-wide audit, then a twelve-page nav scan as the newest run."""
    server, thread, db, base = _serve("navrefuse")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Refuse Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "navrefuse.fixture"}, timeout=30).json()
        conn = connect(db)
        result = _run(_Hub())
        wide = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, wide, result)
        time.sleep(1.1)
        nav = runs.create_run(conn, site["id"], DIMS, "T2", scan_scope="nav")
        runs.complete_run(conn, nav, result)
        conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?",
                     (json.dumps([f"/p{n}" for n in range(12)]), nav))
        conn.commit()
        conn.close()
        yield base, site["id"], wide, nav
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_server_refuses_a_nav_scan_with_one_sentence(served):
    base, site_id, wide, nav = served
    refused = httpx.post(f"{base}/api/runs/{nav}/expert/images", json={}, timeout=30)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == (
        "This audit is a nav scan — an analysis run against it reads 12 pages. "
        "Pick a site-wide audit, or run one on step 2.")
    # Nothing was claimed: the same request against the site-wide run is
    # not "already running".
    again = httpx.post(f"{base}/api/runs/{nav}/expert/images", json={}, timeout=30)
    assert again.status_code == 409 and "already running" not in again.json()["detail"]


_JS = """() => {
  const q = (s) => document.querySelector(s);
  return {
    runAll: q('.run-all') ? { disabled: q('.run-all').disabled, title: q('.run-all').title } : null,
    rows: [...document.querySelectorAll('.catalogue-table .crow-act button.spend-btn')].map((b) => b.disabled || b.getAttribute('aria-disabled') === 'true'),
    note: (document.querySelector('.catalogue-drawer .narrow-pick-note')?.textContent || '').trim(),
  };
}"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_a_newer_nav_scan_does_not_disable_the_controls(browser, served):
    """The fixture's nav scan is newer than its site-wide run. Nothing picks
    it (item 239 step 5): the drawer reads the site-wide run, its run-all is
    enabled, and no refusal is said. The refusal itself is the server's,
    asserted above."""
    base, site_id, wide, nav = served
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    on_the_layout_of_last_resort(pg)
    try:
        # A part open: the drawer is mounted over a part only (brief v24 step BO).
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=title-desc", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".catalogue-fab", timeout=30_000)
        pg.click(".catalogue-fab")
        pg.wait_for_selector(".run-all", timeout=30_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["runAll"] and not got["runAll"]["disabled"], got
    assert got["note"] == "" and not any(got["rows"]), got
