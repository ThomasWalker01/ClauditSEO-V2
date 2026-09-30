"""Five small labels (brief v5 step R): the sidebar's head says what is
shown; more audited than published says why; the precheck's figure
reaches Crawl & sitemaps as a grey badge; model ids are short everywhere;
a zero delta on Home is a dash.

`_plans/site-screen-brief-v5-2026-09-03.md` step R (UX-17, UX-18, UX-19,
UI-15, UI-14). The precheck and the lanes are answered through the page's
route table where the fixture cannot show the case: ten pages published
against the fixture's larger crawl, two nav pages not in the sitemap, and
a dated model id.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_the_precheck_pane_compares_and_suggests import _precheck

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

# The sidebar is retired (brief v24 step BO; channel ruling 2026-09-15): the
# pages line stands on Audit's precheck block, and a part's count on its shop
# header. The head's stage words were dropped with it; the destinations' state
# words say what they said.
_JS = """() => ({
  pagesLine: (document.querySelector('.pre-pages-line')?.textContent || '').replace(/\\s+/g, ' ').trim(),
})"""

_SHOP_JS = """() => { const row = [...document.querySelectorAll('.catalogue-shop .crow-part')]
    .find((r) => (r.querySelector('.crow-part-link')?.textContent || '').trim() === 'Crawl & sitemaps');
    const n = row?.querySelector('.crow-part-open'); return n ? n.textContent.trim() : null; }"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_the_head_the_pages_line_and_the_crawl_badge(browser, served):
    import httpx

    base, ids = served
    site = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    anatomy = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()
    # `["value"]` since item 156. What the badge DRAWS is still the figure -
    # a findings count is not a subset of a page set, so it renders plain.
    crawl_total = next(c["total"]["value"] for c in anatomy["categories"]
                       if c["key"] == "crawl")
    pre = _precheck(site["domain"].rstrip("/"))
    pre["sitemap_urls"] = 10
    pre["not_in_sitemap"] = [site["domain"].rstrip("/") + "/p1", site["domain"].rstrip("/") + "/p2"]
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.route(f"**/api/sites/{ids['site']}/precheck",
                 lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(pre)))
        pg.route(f"**/api/sites/{ids['site']}/precheck/compare",
                 lambda r: r.fulfill(status=200, content_type="application/json", body="null"))
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=precheck", wait_until="load", timeout=30_000)
        pg.wait_for_function("() => /audited/.test(document.querySelector('.pre-pages-line')?.textContent || '')",
                             timeout=30_000)
        got = pg.evaluate(_JS)
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".catalogue-shop .crow-part-open", timeout=30_000)
        crawl = pg.evaluate(_SHOP_JS)
    finally:
        pg.close()
    assert re.search(r"\d+ audited \(2 nav pages not in sitemap\)", got["pagesLine"]), got["pagesLine"]
    assert crawl, "no Crawl & sitemaps header in the shop"
    # The header counts what is open; the precheck's own figure is on Audit.
    assert re.match(rf"· {crawl_total}\b", crawl), crawl


def test_a_dated_model_id_reads_as_its_short_name_in_the_drawer(browser, served):
    import httpx

    base, ids = served
    lanes = httpx.get(f"{base}/api/runs/{ids['run']}/analyses", timeout=30).json()
    for r in lanes["ready"] + lanes["available"]:
        r["model"] = "claude-haiku-4-5-20251001"
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.route("**/api/runs/*/analyses",
                 lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(lanes)))
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        # With no part open the shop is Analyses' own body (brief v24 step BO).
        pg.wait_for_selector(".catalogue-shop .catalogue-table", timeout=30_000)
        pg.wait_for_selector(".catalogue-table tbody tr.crow", timeout=30_000)
        models = pg.evaluate("() => [...document.querySelectorAll('.catalogue-table tbody tr.crow')]"
                             ".map((tr) => tr.cells[3].textContent.trim().split(' ')[0])")
    finally:
        pg.close()
    assert models and all(m == "haiku-4-5" for m in models), models


def test_a_zero_delta_on_home_is_a_dash(browser, served):
    import httpx

    base, ids = served
    overview = httpx.get(f"{base}/api/overview", timeout=30).json()
    rows = overview.get("sites") or overview.get("rows") or []
    if not rows:
        pytest.skip("the overview holds no site row to set a delta on")
    for r in rows:
        r["delta"] = 0
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.route("**/api/overview", lambda r: r.fulfill(status=200, content_type="application/json",
                                                        body=json.dumps(overview)))
        pg.goto(f"{base}/#/", wait_until="load", timeout=30_000)
        # Item 176: the sites are cards, and the movement is a clause in the
        # card's sentence ("Audited 5 days ago, up 0.66").
        pg.wait_for_selector(".home-card", timeout=30_000)
        text = pg.evaluate("() => [...document.querySelectorAll('.home-card')].map((c) => c.textContent).join(' | ')")
    finally:
        pg.close()
    assert "▼ 0" not in text and "▲ 0" not in text, "a zero delta is drawn as a fall"
    assert "up 0," not in text and "down 0," not in text and "up 0." not in text \
        and "down 0." not in text, f"a zero delta is drawn as a movement: {text}"
