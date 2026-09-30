"""Item 232 (International, change 1): an analysis the locale gate settled
as not applicable is held, with its reason, and nothing says one "has run".

On twenty22 the part's card said "Not applicable: this site presents one
locale", while the actions row offered "Run analysis · this audit" and the
line beneath it read "no analysis has run on this part" - the product's
usual wording for an analysis that is owed. Now the button is held with the
gate's reason and the line says the analysis does not apply.

Not done here: the filing asked for a link to the expert form's Target
locales input. No screen offers that input at site scope (only the per-page
expert panel does), so the reason names what would change the answer
instead of linking to a form that is not there.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.db.connection import connect
from clauditseo.engine.types import Tier
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://onelocale.fixture"
HTML = ("<html lang='en-AU'><head><title>One</title></head><body><main><h1>One</h1>"
        "<p>One locale, one market, one language on every page of the site.</p>"
        "</main></body></html>")


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP", "TEC"], "T2")
    pages = [Page(url=BASE + p, requested_url=BASE + p, status=200,
                  content_type="text/html", content=HTML) for p in ("/", "/a/")]
    runs.store_evidence(conn, run_id, snapshot(CrawlResult(start_url=BASE + "/", tier=Tier.T2,
                                                           pages=pages)))
    runs.mark_complete(conn, run_id, now_iso())
    conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?",
                 (json.dumps(["/", "/a/"]), run_id))
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("onelocale")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "One Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "onelocale.fixture"}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_gate_is_settled_on_this_fixture(served):
    base, site_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    part = next(c for c in view["categories"] if c["key"] == "intl")
    assert (part.get("gate") or {}).get("state") == "na", part.get("gate")


@needs_build
def test_the_run_control_is_held_and_nothing_says_one_has_run(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=intl",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-actions .act-brief", timeout=15_000)
            got = pg.evaluate("""() => ({
              held: document.querySelector('.part-actions .act-brief')?.getAttribute('aria-disabled'),
              why: document.querySelector('.part-actions .spend-why')?.textContent || '',
              prov: document.querySelector('.part-actions .part-prov')?.textContent || '',
            })""")
        finally:
            b.close()
    assert got["held"] == "true", got
    assert got["why"].startswith("not applicable on this site: it presents one locale"), got
    assert "has run" not in got["prov"] and "not applicable" in got["prov"], got
