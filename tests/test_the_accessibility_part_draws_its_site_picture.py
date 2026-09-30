"""Item 226 (Accessibility, change 1): the fix-order waterfall is drawn at
site scope.

`A11yNow` already drew `FixOrderWaterfall` when no page was in hand, but the
part registered no `siteNow`, so the site branch never called it: on twenty22
T3 the part opened on the checks table with no picture, and "instances open
now" appeared nowhere. Registered the way International and Mobile were.
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_the_accessibility_fix_order_and_overlay import _finding, _inst, _sampled
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://a11ysite.fixture"


def _plant(db, site_id):
    conn = connect(db)
    run = runs.create_run(conn, site_id, ["A11Y"], "T2")
    runs.store_evidence(conn, run, {"pages": [{"url": BASE + "/", "status": 200}]})
    runs.mark_complete(conn, run, now_iso())
    _sampled(conn, run, 1, 1)
    _finding(conn, run, "fp-a11y", "link-name-missing", [BASE + "/"],
             [_inst(f"main > a:nth-of-type({i})") for i in range(3)])
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("a11ysite")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "A11y Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "a11ysite.fixture"}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@needs_build
def test_the_site_view_opens_on_the_waterfall(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=a11y",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-page .part-checks", timeout=15_000)
            got = pg.evaluate("""() => ({
              head: document.querySelector('.part-page .now-card h4')?.textContent || '',
              open: document.querySelector('.part-page .fixorder-open')?.textContent || '',
              before: !!document.querySelector('.part-page .now-card')
                && (document.querySelector('.part-page .now-card')
                    .compareDocumentPosition(document.querySelector('.part-checks'))
                    & Node.DOCUMENT_POSITION_FOLLOWING) > 0,
            })""")
        finally:
            b.close()
    assert got["head"] == "What the site has now", got
    assert "instances open now" in " ".join(got["open"].split()), got
    assert got["before"], "the picture stands above the checks table"
