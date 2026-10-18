"""Item 222 (Speed, change 1's remainder): a per-template row names its
template as the card's subject.

Speed analysis rows are per template (`page: null`, `template` set). Item 217
stopped them landing on "/" - they are filed on the template's traced page -
but the card still named that one page as its subject, so a template-wide
TTFB read as one page's. The card now reads "template /seo/<slug>/ · traced
on /seo/a/".
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://templaterow.fixture"
HOME, TRACED = BASE + "/", BASE + "/seo/a/"


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["PRF"], "T3")
    runs.store_evidence(conn, run_id, {"pages": [
        {"url": HOME, "status": 200, "title": "Home", "canonical": HOME},
        {"url": TRACED, "status": 200, "title": "A", "canonical": TRACED}]})
    runs.mark_complete(conn, run_id, now_iso())
    rows = [{"check": "PRF/ttfb-slow", "dimension": "PRF", "check_id": "ttfb-slow",
             "page": TRACED, "status": "FAIL", "severity": "medium",
             "evidence": "TTFB 1.8 s on the template's traced page",
             "replacement": "Cache-Control: public, max-age=600", "note": "",
             "extra": {"template": "/seo/<slug>/"}}]
    runs.store_expert_report(conn, run_id, "speed", {
        "model": "m-1", "cost": 0.2, "report": "## Speed", "findings": [],
        "contract": {"status": "read", "part": "speed", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "speed", "m-1", rows)
    runs.recompute_contract_states(conn, site_id, "speed")
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("templaterow")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Tpl Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "templaterow.fixture"}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_state_carries_the_template(served):
    base, site_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()
    states = view.get("states") or []
    row = next((s for s in states if s.get("check_id") == "ttfb-slow"), None)
    assert row and row.get("template") == "/seo/<slug>/", row


@needs_build
def test_the_card_names_the_template_and_where_it_was_traced(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=speed",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-fixes .fix-card", timeout=15_000)
            subject = pg.evaluate(r"""() => {
              const card = [...document.querySelectorAll('.part-fixes .fix-card')]
                .find((c) => (c.querySelector('.fix-check')?.textContent || '').includes('ttfb-slow'));
              return (card?.querySelector('.fix-page')?.textContent || '').replace(/\s+/g, ' ').trim();
            }""")
        finally:
            b.close()
    assert subject == "template /seo/<slug>/ · traced on /seo/a/", subject
