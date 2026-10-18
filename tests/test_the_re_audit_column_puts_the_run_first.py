"""The re-audit column opens on its primary button - the whole choice in
its label - then the depth pills, all inside the first viewport; its
prose is one closed details; the amber "two sources" box is gone from the
part's body; the old opener at the column's foot is gone.

Brief v5 step U (`_plans/site-screen-brief-v5-2026-09-03.md`, Option B of
`analyse-reaudit-controls-options-2026-09-03.html`). The column opened
with three paragraphs and the depth pills stood about 1,100px down.

**Said against the brief.** The depth pills read `Quick · free`,
`Standard · free`, `Deep · free`, all green: the sweep asks for no analyst
at any depth, so a paid amber pill would have promised a spend that never
happens. "Engine decides" is gone as a pill; the Quick pill's title says
it is the engine's own starting depth.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_the_part_page_is_three_blocks import three_block_parts

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  const d = document.querySelector('.reaudit');
  const first = d?.firstElementChild;
  const box = (el) => el ? Math.round(el.getBoundingClientRect().bottom + window.scrollY) : null;
  return {
    firstIsButton: !!first && first.tagName === 'BUTTON' && first.classList.contains('reaudit-primary'),
    label: (first?.textContent || '').trim(),
    buttonBottom: box(first),
    depthBottoms: [...(d?.querySelectorAll('.reaudit-depth .tone') || [])].map(box),
    openDetails: d ? d.querySelectorAll('details[open]').length : -1,
    details: d ? d.querySelectorAll('details.reaudit-why').length : -1,
    amberInBody: document.querySelectorAll('.anat-pane .anat-contested').length,
    contestedInDetails: d ? d.querySelectorAll('.reaudit-why .reaudit-contested').length : -1,
    tagNotes: [...document.querySelectorAll('.anat-pane .causes .tone-source-sweep[title], .anat-pane .causes .tone-source-brief[title]')].filter((t) => /Two sources|Raised both/.test(t.title)).length,
    bothOnOneRow: [...document.querySelectorAll('.anat-pane .causes tr.cause-row')].filter((tr) => tr.querySelector('.tone-source-sweep') && tr.querySelector('.tone-source-brief')).length,
    footOpeners: [...(d?.querySelectorAll('p.sec-refresh') || [])].length,
    openers: d ? d.querySelectorAll('.sec-refresh-open').length : -1,
    confirms: d ? d.querySelectorAll('.sec-refresh-confirm').length : -1,
    sweepChips: [...(d?.querySelectorAll('.reaudit-sweep .tone') || [])].map((c) => c.textContent.trim()),
  };
}"""


# Which dimension refreshes Indexability & canonicals, read off the rule rather
# than written out. It was ONP by a tie broken on the code while ONP and TEC
# covered five sections each; item 143 step BD moved `security` out of TEC, so
# TEC covers four and is now the smallest run that refreshes the section.
from clauditseo import anatomy as _an_refresh  # noqa: E402
from tests.parts import ANATOMY_READY, open_part

INDEX_DIM = _an_refresh.refresh_for("indexability")["dimension"]
INDEX_ALSO = len(_an_refresh.refresh_for("indexability")["also"])


@pytest.fixture(scope="module")


def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_the_button_and_the_depths_are_in_the_first_viewport_and_the_prose_is_closed(browser, served):
    base, ids = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    on_the_layout_of_last_resort(pg)
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        # Images, not Headings: the column this measures is gone from the
        # parts that render as three blocks (brief v14 step AP), and Images
        # keeps it under the same dimension.
        # Indexability & canonicals since brief v16 step AT: Structured data took the three-block layout, and this clause drives the old part page's own controls.
        open_part(pg, 'Indexability & canonicals')
        pg.wait_for_selector(".reaudit", timeout=15_000)
        got = pg.evaluate(_JS)
        pg.click(".reaudit .reaudit-depth .tone:has-text('Deep')")
        pg.wait_for_timeout(200)
        deep = pg.evaluate(_JS)
        pg.click(".reaudit .sec-refresh-open")
        pg.wait_for_selector(".reaudit .sec-refresh-confirm", timeout=15_000)
        asked = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["firstIsButton"], got
    # Item 183: the part's name, and one word for the free re-check.
    assert got["label"].startswith("Re-check Indexability") and "Quick" in got["label"] and got["label"].endswith("free"), got["label"]
    assert got["buttonBottom"] <= 1080 and got["depthBottoms"] and all(b <= 1080 for b in got["depthBottoms"]), got
    assert got["details"] == 1 and got["openDetails"] == 0, got
    assert got["amberInBody"] == 0, "the amber box still stands in the part's body"
    assert got["footOpeners"] == 0 and got["openers"] == 1, got
    # ONP moves five parts on the fixture: three chips and "+ N more".
    assert len(got["sweepChips"]) <= 4 and (len(got["sweepChips"]) < 4 or got["sweepChips"][-1].startswith("+ ")), got["sweepChips"]
    assert "Deep" in deep["label"] and "Quick" not in deep["label"], deep["label"]
    assert asked["confirms"] == 1 and asked["openers"] == 1, asked


def test_a_contested_part_says_two_sources_on_the_tag_not_in_a_panel(browser, served):
    """Brief v10 step AF: the "Two sources, two questions" panel is gone;
    its sentence is the tooltip on the source tag of a check both raised,
    and the cause row counts both on one line."""
    import httpx

    base, ids = served
    anatomy = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()
    # Not a part that renders as three blocks (brief v13 AO, v14 AP, v15
    # AR): the column this reads is gone from those, and the same claim is
    # each part page's own test.
    three_blocks = three_block_parts()
    part = next((c for c in anatomy["categories"]
                 if c.get("contested") and c.get("refresh")
                 and c["key"] not in three_blocks), None)
    if not part:
        pytest.skip("the fixture holds no part with a check raised by both a sweep and a brief")
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    on_the_layout_of_last_resort(pg)
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, part["label"])
        pg.wait_for_selector(".reaudit", timeout=15_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["amberInBody"] == 0 and got["contestedInDetails"] == 0 and got["openDetails"] == 0, got
    assert got["tagNotes"] >= 1 and got["bothOnOneRow"] >= 1, got
