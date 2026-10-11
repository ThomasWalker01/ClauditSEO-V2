"""The section holding the most severe fix is read first (item 266, row 3).

Fixes is read in two sections, free checks then Analysis. On URLs every
free card was `low` and the one `medium` sat under Analysis, below all of
them, so the worst thing on the page was the last thing read. The section
holding the most severe fix now comes first and its heading says why; on a
tie the usual order stands (held by `test_the_free_only_filter.py`).
"""

from __future__ import annotations

import httpx
import pytest

from tests.parts import ANATOMY_READY, open_part
from tests.test_a11y_rendered import DIST
from tests.test_the_free_only_filter import _JS, NEEDS_BROWSER, _plant
from tests.test_triage_ranks_the_section_rail import _serve


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("worstfirst")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Worst Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "costs.fixture"}, timeout=30).json()
        _plant(db, site["id"], {"meta-desc-length": "low", "meta-desc-missing": "low",
                                "title-entity-alignment": "high"})
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_analysis_section_leads_when_it_holds_the_worst_fix(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            open_part(pg, "Title & description")
            pg.wait_for_selector(".part-page .fix-card", timeout=15_000)
            got = pg.evaluate(_JS)
        finally:
            b.close()
    heads = [" ".join(h.split()) for h in got["fixHeads"]]
    assert [h.split("·")[0].strip() for h in heads] == ["Analysis", "Free checks"], heads
    assert heads[0].endswith("· holds the most severe fix"), heads
    assert "most severe" not in heads[1], heads
    assert got["cards"][0]["check"] == "ONP/title-entity-alignment", got["cards"]
