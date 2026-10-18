"""The scope bar holds the one page filter, on every pane; the precheck's
missing pages are links.

Brief v3 step J (`_plans/site-screen-brief-v3-2026-09-03.md`, UI-10 and
UX-14) moved the `NARROW TO` input to the Analyse pane's head. Brief v4
Item 1 (`site-screen-brief-v4-2026-09-03.md`) absorbs that step the other
way: the filter is the bar's left column, beneath the counts, so it is one
control on every pane and the bar is one row - which
`test_the_scope_bar_is_two_columns.py` measures. This file keeps the two
claims that survive: the filter is in the bar and nowhere else, and the
precheck's "N pages missing from the sitemap" names the pages, each a link
to its own page (UX-14).
"""

from __future__ import annotations

import pytest

from tests.parts import open_page_filter
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  // Item 173: the filter is still one control, the bar's and never a pane's;
  // the bar is the shell's since the head stopped being a card.
  const bar = document.querySelector('#topbar-context');
  const pane = document.querySelector('.pane-body');
  return {
    barFilter: bar ? bar.querySelectorAll('.page-find').length : -1,
    paneFilter: pane ? pane.querySelectorAll('.page-find').length : -1,
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


@pytest.mark.parametrize("tab,ready", [
    ("findings", ".catalogue-shop .crow-part"),
    ("all", ".state-filters"),
    ("history", ".scan-matrix"),   # the runs are the Record's since brief v24 step BN
])
def test_the_filter_is_the_bars_and_the_pane_holds_none(browser, served, tab, ready):
    base, ids = served
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab={tab}", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ready, timeout=30_000)
        pg.wait_for_selector(".run-scope .bl-sentence", timeout=30_000)
        # Item 174 (channel ruling 20260917-1430): the filter is page mode's
        # control, so site mode draws none; One page shows it, in the bar.
        site_mode = pg.evaluate(_JS)
        open_page_filter(pg)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert site_mode["barFilter"] == 0 and site_mode["paneFilter"] == 0, (
        f"{tab}: site mode draws a page filter: {site_mode}")
    assert got["barFilter"] == 1, f"{tab}: the bar does not hold the page filter: {got}"
    assert got["paneFilter"] == 0, (tab, got)
    # The head's own rows (BM's `scope-state`/`scope-side`) are item 173's
    # `test_the_head_is_the_sentence_and_its_actions_and_the_bar_holds_the_context`.


def test_the_prechecks_missing_pages_are_links_to_their_own_pages(browser, served):
    import httpx

    base, ids = served
    pre = httpx.get(f"{base}/api/sites/{ids['site']}/precheck", timeout=30).json()
    # `null` until a precheck has run; the sweep's fixture runs none.
    missing = (pre or {}).get("not_in_sitemap") or []
    if not missing:
        pytest.skip("the fixture's precheck finds no navigation page missing from the sitemap")
    pg = browser.new_page()
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=precheck", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".pane-body .pre-found a", timeout=30_000)
        hrefs = pg.evaluate("() => [...document.querySelectorAll('.pane-body .pre-found a')].map((a) => a.getAttribute('href'))")
    finally:
        pg.close()
    assert len(hrefs) == len(missing), (hrefs, missing)
    assert all(h.startswith(f"#/sites/{ids['site']}/dossier/") for h in hrefs), hrefs
