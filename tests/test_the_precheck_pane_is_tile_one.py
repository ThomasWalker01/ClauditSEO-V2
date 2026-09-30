"""`?tab=precheck` renders the Precheck pane - its own file - beside the
sidebar in its precheck state, and the rail's tile 1 says when it counted
and how many pages.

Brief v4 Item 3b (`_plans/site-screen-brief-v4-2026-09-03.md`). The pane
was a wrapper inside `anatomy.tsx`; it is `pane_precheck.tsx` now, like
the other panes (CQ-02), and Item 2's table lands there. Tile 1 read
"counted" alone; it reads `counted HH:MM · N pages`. "+N since last
check" waits on Item 2, which stores the prior check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

_JS = """() => ({
  pane: (document.querySelector('.pane-name')?.textContent || '').trim(),
  panel: document.querySelectorAll('.pane-body .pre-panel').length,
  tile: (() => {
    const li = [...document.querySelectorAll('.seq-step')].find(
      (el) => (el.querySelector('.seq-name')?.textContent || '').trim() === 'Audit');
    // Precheck's line inside Audit's panel since brief v24 step BN.
    return (li?.querySelector('.seq-state')?.textContent || '').trim()
      .split(' · Audit: ')[0].replace(/^Precheck: /, '');
  })(),
})"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_the_pane_is_its_own_file():
    assert "export function PrecheckPane(" in (SRC / "pane_precheck.tsx").read_text(encoding="utf-8")
    assert "function PrecheckPane(" not in (SRC / "anatomy.tsx").read_text(encoding="utf-8")


def test_the_address_renders_the_pane_beside_the_sidebar_and_the_tile_says_what_it_counted(browser, served):
    import httpx

    base, ids = served
    pre = httpx.get(f"{base}/api/sites/{ids['site']}/precheck", timeout=30).json()
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=precheck", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".pane-body .pre-panel", timeout=30_000)
        pg.wait_for_selector(".seq-step .seq-state", state="attached", timeout=30_000)
        pg.wait_for_timeout(300)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    # `?tab=precheck` is Audit since brief v24 step BN, which holds the panel.
    assert got["pane"] == "Audit" and got["panel"] == 1, got
    # The head says what is shown (brief v5 step R): the fixture has an
    # audit, so its counts are from it.
    # No sidebar and no stage words since brief v24 step BO (ruling item 6).
    if pre:
        want = f"counted {pre['checked_at'][11:16]}"
        assert got["tile"].startswith(want), (got["tile"], want)
        if pre["sitemap_urls"] is not None:
            assert re.search(rf"· {pre['sitemap_urls']} pages$", got["tile"]), got["tile"]
    else:
        # The sweep's fixture runs no precheck: the tile says so.
        assert got["tile"] == "not run", got["tile"]
