"""The v5 step U and the part page's own settled shapes, guarded (brief
v12 step AN): the re-audit column opens on its button with the prose in
one closed `details`; the estimate says `~` once; the part's checks with
nothing open are one line naming them, not a row each; the legend strip
and the catalogue's own control count the same briefs; the internal link
suggestions stand under Links on the page and nowhere else; and the pages
line names both directions when both moved.

Marked as regression guards: each of these was accepted once and was
found undone when the operator read the running product on 2026-09-05.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import re

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
  const pane = document.querySelector('.anat-pane');
  return {
    primary: (document.querySelector('.reaudit .sec-refresh-open')?.textContent || '').trim(),
    details: [...document.querySelectorAll('.reaudit details')].map((d) => d.open),
    firstIsButton: document.querySelector('.reaudit .reaudit-field, .reaudit p, .reaudit details')
      ? !!document.querySelector('.reaudit .sec-refresh-open') : false,
    zeroRows: [...(pane?.querySelectorAll('table.causes tr.cause-row') || [])]
      .filter((tr) => (tr.querySelector('td.state-col')?.textContent || '').startsWith('0 ')).length,
    // One per section since brief v17 step AV3; joined, because the
    // regression this guards is a check missing from *any* of them.
    cleanLine: [...(pane?.querySelectorAll('.cause-clean-line') || [])]
      .map((p) => p.textContent.trim()).join(' '),
    legend: (document.querySelector('.legend-strip .legend-catalogue')?.textContent || '').trim(),
    fab: (document.querySelector('.catalogue-fab')?.textContent || '').trim(),
    links: document.querySelectorAll('.link-suggestions').length,
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


#: Images, not Headings: that part renders as three blocks since brief v14
#: step AP, where the actions row replaces the re-audit column. Images keeps
#: the page these clauses were written against, under the same dimension, so
#: the estimate they read is the same crawl's.
#: Indexability & canonicals since brief v16 step AT: Structured data took the three-block layout, and this clause drives the old part page's own controls.
PART = "Indexability & canonicals"


def _part(pg, base, site_id, label):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, label)
    pg.wait_for_selector(".anat-pane", timeout=15_000)
    pg.wait_for_timeout(400)
    return pg.evaluate(_JS)


def test_the_reaudit_column_opens_on_its_button_and_says_the_estimate_once(browser, served):
    """Brief v5 step U, and the `~~` the estimate grew when `human()` took
    its own tilde: `~2s`, never `~~2s`."""
    base, ids = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    on_the_layout_of_last_resort(pg)
    try:
        got = _part(pg, base, ids["site"], PART)
    finally:
        pg.close()
    assert got["firstIsButton"], got
    assert got["details"] == [False], got["details"]
    assert got["primary"].startswith("Re-check Indexability"), got["primary"]
    assert "~~" not in got["primary"], got["primary"]
    # The estimate appears only where the part knows its page count; where
    # it does, it carries exactly one tilde.
    for tilde in re.findall(r"~+\d+[smh]", got["primary"]):
        assert tilde.startswith("~") and not tilde.startswith("~~"), got["primary"]
    assert "free" in got["primary"], got["primary"]


def test_the_checks_with_nothing_open_are_one_line_naming_them(browser, served):
    """Ten `Info · 0 findings` rows said less than one sentence does.

    Read on Headings, whose thirteen checks made the row-per-check page
    unreadable and which states them on one line on either page - the old
    one until brief v14 step AP and the checks block since.
    """
    base, ids = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    on_the_layout_of_last_resort(pg)
    try:
        got = _part(pg, base, ids["site"], "Headings")
    finally:
        pg.close()
    assert got["zeroRows"] == 0, f"{got['zeroRows']} rows still read `0 findings`"
    assert re.match(r"^\d+ checks? (pass|clean) ", got["cleanLine"]), got["cleanLine"]
    # Named a SWEEP check. This clause first named h1-triple-restated, which
    # is brief-only: with no Headings brief run for this fixture it was never
    # measured, and item 157's rung 3 now moves it to the not-assessed line.
    # Reading it as clean was the vacuous pass that rung exists to stop.
    assert "h1-missing" in got["cleanLine"], got["cleanLine"]
    assert "h1-triple-restated" not in got["cleanLine"], got["cleanLine"]


def test_the_legend_and_the_catalogue_count_the_same_briefs(browser, served):
    base, ids = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    on_the_layout_of_last_resort(pg)
    try:
        got = _part(pg, base, ids["site"], PART)
    finally:
        pg.close()
    legend = re.search(r"(\d+) not run", got["legend"])
    fab = re.search(r"(\d+) not run", got["fab"])
    assert legend and fab, got
    assert legend.group(1) == fab.group(1), (got["legend"], got["fab"])


def test_the_link_suggestions_table_is_gone_from_every_part(browser, served):
    """The regression this clause was written for cannot recur, because
    the thing that regressed no longer exists.

    It stood under every part until brief v12 step AN filed it under
    Links on the page; brief v17 step AW closes it outright. A free table
    of under-linked pages with no check behind it, no record row and no
    place in a report was a second account of a question the part page
    now answers with findings. What is guarded now is that it is gone
    from *both* — the part it used to stand under, and the parts it used
    to leak onto.
    """
    base, ids = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    on_the_layout_of_last_resort(pg)
    try:
        elsewhere = _part(pg, base, ids["site"], PART)
        here = _part(pg, base, ids["site"], "Links on the page")
    finally:
        pg.close()
    assert elsewhere["links"] == 0, "the link table stands under a part it is not about"
    assert here["links"] == 0, (
        "the Internal link suggestions table is still rendered; brief v17 "
        "step AW moves the question onto the part page")


def test_the_pages_line_names_both_directions_when_both_moved(browser, served):
    """`±0 · 2 gone` said nothing arrived when two had."""
    base, ids = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    on_the_layout_of_last_resort(pg)
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=precheck", wait_until="load", timeout=30_000)
        # On Audit's precheck block since brief v24 step BO, and only where a
        # precheck has run: with none there is no line to misstate.
        pg.wait_for_selector(".pre-panel", timeout=30_000)
        line = pg.evaluate("() => (document.querySelector('.pre-published')?.textContent || '').trim()")
    finally:
        pg.close()
    # Whatever the fixture's diff, the line never claims nothing moved while
    # naming a number that moved.
    both = re.search(r"\+(\d+) · −(\d+) since last check", line)
    if both:
        assert int(both.group(1)) and int(both.group(2)), line
    else:
        assert not re.search(r"±0 since last check · \d+ gone", line), line
