"""From inside one part, the way to the others is on the screen and in view.

Item 185, from an operator report verified on twenty22: opening a problem area
took the way out of every other one with it. The parts strip (`PartsStrip`,
item 169, concepts 05 and 10) was mounted in exactly one place - the foot of
the Client landing, 80% of the way down a document it ended - and the pane a
pill navigated to carried no part link at all. Measured before this test
existed: 18 `part=` links on the landing, 0 on an open part. Every part switch
cost Back, a scroll to the foot of the landing, and a click.

What is held here is the item's four conditions, and the fourth is the one a
weaker clause would drop: the control has to be in view from where the reader
IS, not merely first on a part page that measured 4,010 px. So the strip is
read at the foot of the document as well as at its head.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.parts import ANATOMY_READY, open_part
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

#: The registered word for the unread state (item 166). Read, never spelled:
#: a clause that writes the product's vocabulary down is a second definition.
NOT_READ_WORD = {e["id"]: e for e in json.loads(
    (Path(__file__).resolve().parents[1] / "clauditseo" / "glossary.json")
    .read_text(encoding="utf-8"))["entries"]}["not-read"]["word"]

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: What the switcher is, from the screen's own DOM. `keyOf` reads the target
#: out of the href rather than trusting the label, because the claim under
#: test is "this control navigates to a DIFFERENT part" and a label is not a
#: destination.
_READ = """() => {
  const keyOf = (a) => new URLSearchParams((a.getAttribute('href') || '').split('?')[1] || '')
                         .get('part');
  const pills = [...document.querySelectorAll('.part-switch .parts-link')];
  const sw = document.querySelector('.part-switch');
  const r = sw ? sw.getBoundingClientRect() : null;
  return {
    present: Boolean(sw),
    label: sw ? sw.getAttribute('aria-label') : null,
    keys: pills.map(keyOf),
    current: pills.filter((a) => a.getAttribute('aria-current') === 'page').map(keyOf),
    // A pill's own height: the 24px floor applies to a control, and cutting
    // the padding to fit the band is how a control loses it.
    shortest: pills.length ? Math.min(...pills.map((a) => Math.round(a.getBoundingClientRect().height))) : null,
    // Sticky, read where the reader stands rather than where the markup sits.
    inView: r ? (r.bottom > 0 && r.top < window.innerHeight) : null,
    top: r ? Math.round(r.top) : null,
    h: r ? Math.round(r.height) : null,
    scrollY: Math.round(window.scrollY),
    heading: document.querySelector('.part-h2')?.textContent?.trim() || null,
    pane: document.querySelectorAll('.anat-pane').length,
    // Item 186: every pill carries its count, unread or not. This clause
    // used to assert the opposite - that an unread pill showed no figure -
    // which was item 185 reading ruling 20260917-0140 as though it were about
    // any figure rather than about a ZERO standing as a clearance. A part's
    // count is the automatic checks' findings and does not become untrue
    // because no analysis has read them; and since `.parts-n` is the pill's
    // only coloured token, withholding it made eighteen identical outlines of
    // what item 172 built as a distribution.
    withoutFigure: pills.filter((a) => !a.querySelector('.parts-n'))
                        .map((a) => a.getAttribute('aria-label')),
    // What the switcher does still drop: the trailing staleness phrase.
    withStaleWord: pills.filter((a) => a.querySelector('.parts-unread-mark')).length,
    // The zero that the ruling is actually about, and where its qualification
    // lives on a pill too small for the phrase: the tone, the title, and the
    // label.
    unreadZeros: pills.filter((a) => a.dataset.unread === '1' && a.dataset.n === '0')
      .map((a) => ({ dim: a.className.includes('parts-zero'),
                     title: (a.getAttribute('title') || '').includes('not a clearance'),
                     label: a.getAttribute('aria-label') || '' })),
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


def _switcher(pg, base, ids, page: str = ""):
    """Open a part and read the switcher, at the head and at the foot."""
    q = f"?tab=findings{f'&page={page}' if page else ''}"
    pg.goto(f"{base}/#/sites/{ids['site']}{q}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".anat-pane", timeout=30_000)
    key = open_part(pg, "Crawl & sitemaps", timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    pg.wait_for_selector(".part-switch .parts-link", timeout=30_000)
    pg.wait_for_timeout(400)
    head = pg.evaluate(_READ)
    pg.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    pg.wait_for_timeout(300)
    foot = pg.evaluate(_READ)
    return key, head, foot


@pytest.mark.parametrize("mode", ["site", "page"])
def test_an_open_part_carries_every_other_part_and_keeps_it_in_view(browser, served, mode):
    """The item's conditions one, two and four, in both scope modes.

    Page mode is not a variation here, it is half the report: `PartsStrip`
    split on `page` only for its label, so it was landing-only in both, and a
    fix that reached one mode would have been half a fix.
    """
    import httpx

    base, ids = served
    pages = httpx.get(f"{base}/api/runs/{ids['run']}/pages", timeout=30).json()
    page = (pages.get("pages") or [{}])[0].get("url", "") if mode == "page" else ""
    if mode == "page" and not page:
        pytest.skip("the fixture crawl fetched nothing to scope to")
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        key, head, foot = _switcher(pg, base, ids, page)
    finally:
        pg.close()

    assert head["present"], f"no part switcher on an open part ({mode} mode)"
    others = [k for k in head["keys"] if k and k != key]
    assert len(others) >= 2, (
        f"a switcher that offers no other part is not a switcher: {head['keys']}")
    assert head["current"] == [key], (
        "exactly the open part is marked, and it is marked: "
        f"{head['current']} against {key}")
    assert head["shortest"] is None or head["shortest"] >= 24, (
        f"a pill fell under the 24px floor to fit the band: {head['shortest']}")
    assert head["withoutFigure"] == [], (
        "a pill drew no count, so it drew no tone either and the breakdown "
        f"reads as a tab bar (item 186): {head['withoutFigure']}")
    assert head["withStaleWord"] == 0, (
        "the switcher is carrying the landing's staleness phrase, which is the "
        "row it exists without")
    for z in head["unreadZeros"]:
        assert z["dim"] and z["title"] and NOT_READ_WORD in z["label"], (
            "a 0 on a part nothing has read is the clearance ruling's own "
            f"case, and this pill qualifies it nowhere: {z}")

    # Condition four. At the foot of the document the markup's position says
    # nothing; only the box does.
    assert foot["present"] and foot["inView"], (
        "the switcher left the viewport once the reader scrolled: "
        f"top {foot['top']} at scrollY {foot['scrollY']}")
    # `head["top"]` is read at scrollY 0, so it is where the strip sits in the
    # document; once the reader is past that, a kept-in-view control is pinned
    # rather than merely still visible. In page mode the fixture's part is
    # short enough that the document never scrolls that far, and "still
    # visible" is then the whole of the claim - which is why the stronger
    # clause is conditional rather than dropped.
    if foot["scrollY"] > head["top"]:
        assert foot["top"] <= 1, (
            "scrolled past where it sits, a kept-in-view control is at the top "
            f"of the viewport, not at {foot['top']}")


def test_pressing_another_part_opens_it_without_leaving_the_screen(browser, served):
    """The item's condition three, and the wart the first pass left.

    A hash change is not a scroll: the first build of this switcher changed
    the heading and left the viewport 1,145 px down, which is the middle of a
    part the reader had not read a word of. So this asserts where the press
    lands as well as what it opens.
    """
    base, ids = served
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        key, head, _ = _switcher(pg, base, ids)
        target = next(k for k in head["keys"] if k and k != key)
        pg.evaluate("() => window.scrollTo(0, 1200)")
        pg.wait_for_timeout(250)
        deep = pg.evaluate(_READ)
        pg.click(f".part-switch a[href*='part={target}']")
        pg.wait_for_function("(k) => new URLSearchParams(location.hash.split('?')[1] || '')"
                             ".get('part') === k", arg=target, timeout=15_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        pg.wait_for_timeout(600)
        after = pg.evaluate(_READ)
    finally:
        pg.close()

    assert deep["scrollY"] >= 900, (
        f"the part was too short to read from inside it: {deep['scrollY']}")
    assert after["pane"] == 1, "the press left the Analyses pane"
    assert after["heading"] and after["heading"] != head["heading"], (
        f"the heading did not change: {head['heading']} -> {after['heading']}")
    assert after["current"] == [target], (
        f"the mark did not follow the press: {after['current']} against {target}")
    assert after["present"], "the switcher did not come with the part it opened"
    # Landed on the part, not inside it: the heading is on the screen and not
    # underneath the strip that did the switching.
    assert after["scrollY"] < deep["scrollY"], (
        f"the press kept the previous part's scroll: {after['scrollY']}")
