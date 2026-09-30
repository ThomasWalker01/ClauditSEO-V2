"""The legend is a strip above the content, one per pane with only that
pane's symbols; the sidebar holds no legend; before anything has counted
the site the strip says it fills in as steps run.

Brief v4 Item 3d (`_plans/site-screen-brief-v4-2026-09-03.md`). The dot
legend and the selected/same-pages swatches stood in the Analyse rail,
and no other pane explained its symbols. On Analyse the strip also
carries the catalogue's control, "All briefs · N not run".
"""

from __future__ import annotations

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

_JS = """() => {
  const strip = document.querySelector('.legend-strip');
  const head = document.querySelector('.pane-head');
  const body = document.querySelector('.pane-body');
  const after = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
  return {
    strips: document.querySelectorAll('.legend-strip').length,
    text: (strip?.textContent || '').trim().replace(/\\s+/g, ' '),
    underHead: after(head, strip) && after(strip, body),
    inSidebar: document.querySelectorAll('.site-sidebar .legend-strip, .site-sidebar .dot-legend, .site-sidebar .anat-legend').length,
    dots: strip ? strip.querySelectorAll('.dot-legend .cat-dot').length : 0,
    catalogue: strip ? strip.querySelectorAll('.anat-catalogue-open').length : 0,
    catalogueElsewhere: document.querySelectorAll('.anat-catalogue-open').length - (strip ? strip.querySelectorAll('.anat-catalogue-open').length : 0),
  };
}"""

# Brief v24 step BN: Audit holds the precheck, so `precheck` is no pane of
# its own and has no strip of its own; Audit's strip is read at `history`.
READY = {"history": ".scan-matrix", "findings": ".anat-pane",
         "all": ".state-filters"}


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_each_pane_has_its_own_strip_and_the_sidebar_none(browser, served):
    base, ids = served
    seen = {}
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        for tab, ready in READY.items():
            # Analyses with a part open, where the strip carries the drawer control
            # (brief v24 step BO: with none, the shop is the body).
            pg.goto(f"{base}/#/sites/{ids['site']}?tab={tab}" + ("&part=crawl" if tab == "findings" else ""), wait_until="load", timeout=30_000)
            pg.wait_for_selector(ready, timeout=30_000)
            pg.wait_for_selector(".legend-strip", timeout=30_000)
            # The seeded site has been counted, so the strip leaves its
            # "fills in as steps run" state once the anatomy payload lands.
            # A fixed 200 ms read that state whenever the payload was slower,
            # and failed under a loaded full suite (2026-09-14).
            pg.wait_for_function("() => !document.querySelector('.legend-strip')"
                                 "?.textContent.includes('Legend fills in')", timeout=30_000)
            pg.wait_for_timeout(200)
            seen[tab] = pg.evaluate(_JS)
    finally:
        pg.close()
    for tab, got in seen.items():
        assert got["strips"] == 1 and got["underHead"], (tab, got)
        assert got["inSidebar"] == 0, (tab, got)
        assert got["text"], (tab, got)
    texts = [got["text"] for got in seen.values()]
    assert len(set(texts)) == len(texts), "two panes share one legend"
    # Item 197: NO pane keys a dot here, findings included. The three dots
    # key the analyses list - `LookDot`, `anat-rank` and `anat-rerun` are
    # drawn only inside `CatalogueList` - and this loop reads every pane in
    # its default state, which for findings inside a part means the drawer
    # shut. A key to a symbol that is not on the screen is the one thing the
    # header of `legend_strip.tsx` says this strip stopped being. The
    # operator, reading a part page: "these status dots don't seem to have a
    # purpose here any more."
    #
    # This clause asserted 3 until then, so it encoded the defect; it is
    # amended rather than loosened. The other half - the keys arriving with
    # the drawer, and staying on the shop, where the same list stands
    # unwrapped - is driven in
    # `test_the_legend_keys_what_is_on_the_screen.py`, which presses the
    # control. What this clause is about stays what it was: one strip per
    # pane, and the catalogue's own control on findings alone.
    assert seen["findings"]["catalogue"] == 1, seen["findings"]
    assert seen["findings"]["catalogueElsewhere"] == 0, seen["findings"]
    assert all(got["dots"] == 0 for got in seen.values()), seen
    assert all(got["catalogue"] == 0 for tab, got in seen.items() if tab != "findings"), seen
    assert seen["history"]["text"].startswith("Counts"), seen["history"]["text"]
    assert seen["all"]["text"].startswith("Filter"), seen["all"]["text"]


def test_before_anything_has_counted_the_site_the_strip_says_so(browser, served):
    import httpx

    base, ids = served
    client = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()["client_id"]
    fresh = httpx.post(f"{base}/api/clients/{client}/sites",
                       json={"domain": "https://nothing-legend.test/"}, timeout=30).json()
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{fresh['id']}?tab=precheck", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".legend-strip", timeout=30_000)
        pg.wait_for_timeout(400)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["text"] == "Legend fills in as steps run.", got
