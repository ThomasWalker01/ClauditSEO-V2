"""The legend stands under the rail's head, and a re-run is one press from
the rail.

Brief step 4 (`_plans/site-screen-reorg-brief-2026-09-03.md`, UX-03 and
part of WF-02). The three-state legend - analysed, running, nothing - stood
in the column opposite the dots it explains and vanished once a section was
open, exactly when the other sections' dots still needed reading. And a
re-run was reachable only by opening a section and finding the control
inside it. Each rail row now carries a small re-run control that opens the
section on its refresh confirmation; the control spends nothing and carries
no mark, and the button that commits is still the one inside (F-10).

**Why a browser.** The claims are about where the legend is in the document
relative to the rail and what one press paints. The fixture is
`test_section_refresh.py`'s server: one site, one audit, sections with
sweeps behind them.

**What this does not drive.** The commit inside the confirmation, which
starts a crawl. The press asserted here is the opener's.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import pytest

from tests.test_a11y_rendered import DIST
from tests.test_section_refresh import served  # noqa: F401  (reused fixture)
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  // The legend is the strip above the content since brief v4 Item 3d, under
  // the pane's head; the parts list is the screen's sidebar.
  const tree = document.querySelector('.legend-strip');
  const head = document.querySelector('.pane-head');
  const legend = tree?.querySelector('.dot-legend');
  const after = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
  return {
    // The STRIP is what stands and stays; the dot-legend inside it is one
    // of its entries and comes and goes with the list it keys (item 197).
    // Reported apart because they were one field, and a change to the
    // entries then read as the strip having left the screen.
    strips: document.querySelectorAll('.legend-strip').length,
    stripUnderHead: after(head, tree),
    legendsInTree: tree ? tree.querySelectorAll('.dot-legend').length : 0,
    legendsElsewhere: document.querySelectorAll('.dot-legend').length - (tree ? tree.querySelectorAll('.dot-legend').length : 0),
    legendUnderHead: after(head, legend),
    legendStates: legend ? legend.querySelectorAll('.cat-dot').length : 0,
    // The glyph's home is the shop's part header since brief v24 step BO
    // (channel ruling 2026-09-15): the shop is the one list of every part.
    reruns: [...document.querySelectorAll('.catalogue-shop .crow-part')].map((row) => ({
      part: (row.querySelector('.crow-part-link')?.textContent || '').trim(),
      rerun: !!row.querySelector('.anat-rerun'),
      marked: !!row.querySelector('.anat-rerun .spend-mark'),
      label: row.querySelector('.anat-rerun')?.getAttribute('aria-label') || null,
    })),
    open: (document.querySelector('.anat-pane h2.part-h2')?.textContent || '').trim(),
    confirms: document.querySelectorAll('.sec-refresh-confirm').length,
    openers: document.querySelectorAll('.sec-refresh-open').length,
    confirmMarks: document.querySelectorAll('.sec-refresh-confirm .spend-mark').length,
    confirmText: (document.querySelector('.sec-refresh-confirm')?.textContent || '').trim(),
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


def _open(browser, base, site_id):
    pg = browser.new_page()
    on_the_layout_of_last_resort(pg)
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    # The shop's part headers, where the glyph lives (brief v24 step BO).
    pg.wait_for_selector(".catalogue-shop .crow-part", timeout=30_000)
    return pg


def test_the_legend_stands_under_the_rails_head_and_stays_when_a_section_is_open(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        before = pg.evaluate(_JS)
        # Content, not Headings: three blocks there since brief v14 AP.
        # Crawl & sitemaps since brief v17 step AX: Content gained a
        # renderer of its own and with it lost the cause table and
        # the re-audit control these clauses drive. The fixture's
        # twelve-page row moved to this part with them.
        open_part(pg, 'Crawl & sitemaps')
        pg.wait_for_selector(".reaudit-primary", timeout=15_000)
        after = pg.evaluate(_JS)
    finally:
        pg.close()
    # What this clause is about, and it is unchanged: one strip, under the
    # pane's head, still there once a section is open.
    for got in (before, after):
        assert got["strips"] == 1, got
        assert got["stripUnderHead"], f"the strip is not under the rail's head: {got}"

    # The dot-legend is an ENTRY on that strip, and item 197 made it come and
    # go with the thing it keys. `before` is the shop - `CatalogueList`
    # standing on the page, every dot on screen - so the key is there and
    # reads three states. `after` has a part open and the drawer shut, which
    # is where the operator found the defect: "these status dots don't seem
    # to have a purpose here any more."
    #
    # This asserted 3 in both states, so it encoded the defect. Amended
    # rather than loosened: it now says which state shows the key, which is
    # a stronger claim than the one it replaces.
    assert before["legendsInTree"] == 1 and before["legendsElsewhere"] == 0, before
    assert before["legendUnderHead"], f"the key is not under the rail's head: {before}"
    assert before["legendStates"] == 3, before
    assert after["legendsInTree"] == 0 and after["legendsElsewhere"] == 0, (
        "a part is open with the catalogue shut, so the list this keys is "
        f"not on the screen and neither should the key be: {after}")


def test_every_part_with_a_sweep_behind_it_offers_a_re_run_in_the_shop(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["reruns"], got
    with_control = [r for r in got["reruns"] if r["rerun"]]
    assert with_control, f"no shop part header offers a re-run: {got['reruns']}"
    for r in with_control:
        assert not r["marked"], f"the opener carries a spend mark: {r}"
        # Item 183: the free re-check's registered word.
        assert r["label"] == f"Re-check {r['part']}", r


def test_one_press_in_the_shop_opens_the_section_on_its_confirmation(browser, served):
    """Without opening the section's detail first: the press is the first
    thing done on the screen, and what it paints is the confirmation that
    names the dimension - never the run itself."""
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        assert pg.evaluate(_JS)["open"] == "", "a section is open before anything was pressed"
        pg.click(".catalogue-shop .crow-part:has(.crow-part-link:text-is('Crawl & sitemaps')) .anat-rerun")
        pg.wait_for_selector(".sec-refresh-confirm", timeout=15_000)
        got = pg.evaluate(_JS)
        # Selecting the section by its name afterwards lands on the opener,
        # not on a confirmation it was not asked for.
        # Accessibility since brief v16 step AT, for the reason every
        # other move in this chain records: the part this drove took the
        # three-block layout and no longer renders the control.
        import httpx

        from tests.test_the_part_page_is_three_blocks import old_page_part
        part = old_page_part(httpx.get(
            f"{base}/api/sites/{ids['site']}/anatomy", timeout=60).json())
        open_part(pg, part)
        # The part is the address's since brief v24 step BM, so the section
        # changes on the hashchange, a tick after the press: the previous
        # section's `.reaudit-primary` still matched for that tick.
        pg.wait_for_function(f"({_JS})().open === {part!r}", timeout=15_000)
        pg.wait_for_selector(".reaudit-primary", timeout=15_000)
        other = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["open"] == "Crawl & sitemaps", got
    # The drawer's primary stays above the confirmation (brief v5 step U).
    assert got["confirms"] == 1 and got["openers"] == 1, got
    assert "Re-run ONP?" in got["confirmText"] or "Re-run " in got["confirmText"], got["confirmText"]
    # Neither step is marked as spending: the sweep asks for no analyst, so
    # it spends no tokens - `test_section_refresh.py` holds both steps to
    # that, and the rail's opener changes nothing about it.
    assert got["confirmMarks"] == 0, got
    assert other["open"] == part and other["confirms"] == 0, other
