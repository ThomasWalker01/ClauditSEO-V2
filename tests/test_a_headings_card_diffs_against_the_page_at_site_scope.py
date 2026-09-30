"""Item 224 (Headings, change 1): at site scope a Headings card diffs the
brief's outline against the page's own.

`HeadingsFixBody` built its baseline from `facts`, and `facts` is null when no
page is in hand, so on twenty22 T3 every line of every corrected outline was
tagged `[proposed]` under an empty "Now" - 38 lines on /website-seo/,
headings the page plainly already had among them. The site view now carries
the outline the crawl kept for each page an analysis row names
(`page_outlines`), and the card diffs against that.

Same fixture as `test_the_headings_part_page.py`: the home page's h4 "Our
clients" is relevelled to h3 and nothing else moves.
"""

from __future__ import annotations

import httpx
import pytest

from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_the_headings_part_page import BASE, HOME, POST, _plant
from tests.test_triage_ranks_the_section_rail import _serve


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("siteoutline")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Outline Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": BASE.split("//")[1]}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_site_view_carries_the_outline_of_each_page_a_row_names(served):
    base, site_id = served
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    part = next(c for c in view["categories"] if c["key"] == "headings")
    outlines = part.get("page_outlines") or {}
    assert set(outlines) == {HOME, POST}, sorted(outlines)
    assert [h[1] for h in outlines[HOME]["outline"]][-1] == "Our clients", outlines[HOME]


@needs_build
def test_the_card_marks_only_what_moves(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=headings",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-fixes .fix-card", timeout=15_000)
            got = pg.evaluate("""() => {
              const card = [...document.querySelectorAll('.part-fixes .fix-card')]
                .find((c) => c.querySelector('[data-fix-check="heading-skip"]')
                             && (c.querySelector('.fix-page')?.textContent || '').trim() === '/');
              if (!card) return null;
              return {
                was: card.querySelectorAll('.outline-was li').length,
                marks: [...card.querySelectorAll('.out-mark')].map((m) => m.textContent.trim()),
              };
            }""")
        finally:
            b.close()
    assert got, "no heading-skip card for / at site scope"
    assert got["marks"] == ["relevelled h4 → h3"], got
    assert got["was"] > 0, got
