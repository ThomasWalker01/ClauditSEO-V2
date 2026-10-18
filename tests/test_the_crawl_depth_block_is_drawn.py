"""How deep the crawl had to go, drawn at the running product.

Brief v16b. The block is a histogram of pages by clicks from the home page on
the Crawl & sitemaps part, and the clauses below are the item's own Accept
list: the bars count what the crawl recorded, past three clicks is the only
warn tone, a bar narrows the finding list to its pages, the sitemap-only
pages are named on the home bar rather than hidden in a tooltip, and a run
that recorded no depth says so instead of drawing zero.

**Why a fixture of its own and not the shared crawl fixture.**
`test_a11y_rendered.py`'s pages carry no `click_depth` at all, so every
clause here would have been vacuous against it and would have passed against
a renderer that drew nothing - DISCIPLINE rule 5, which that file's own
UX-60 note records paying for once already. Enriching it instead was
rejected on measurement: forty-odd browser tests share it and several assert
finding counts, so pages gaining a depth would move numbers in guards that
have nothing to do with this one.

The depths below are planted rather than crawled, for the same reason brief
v16a's picture test plants its markup: `click_depth` is
`crawler.evidence.click_depth`'s output and `test_the_link_graph.py` already
asks whether that walk is right. This file asks whether the *drawing* agrees
with the field, which is a different question and the only one it can answer
from a browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part

SITE = "depthfixture.test"
HOME = f"https://{SITE}/"

#: The planted distribution, and every count below is derived from it rather
#: than written twice. Two pages carry no depth at all: `click_depth` seeds
#: at the home page and walks outward, so a page the sitemap put in the
#: frontier and no internal link points at comes back None. Those are the
#: block's "sitemap-only", and they are the reason this fixture has any.
DEPTHS: dict[str, int | None] = {
    HOME: 0,
    f"https://{SITE}/a": 1,
    f"https://{SITE}/b": 1,
    f"https://{SITE}/c": 2,
    f"https://{SITE}/d": 3,
    f"https://{SITE}/e": 4,
    f"https://{SITE}/f": 5,
    f"https://{SITE}/orphan-one": None,
    f"https://{SITE}/orphan-two": None,
}
#: What the bars must therefore read: the home bar carries the home page and
#: both orphans, and the axis runs to 5 with nothing past it.
EXPECTED = {0: 3, 1: 2, 2: 1, 3: 1, 4: 1, 5: 1}
SITEMAP_ONLY = 2

#: One finding at a depth past three and one at a depth inside it, so
#: narrowing to a bar has something to keep and something to drop. Both check
#: ids file under Crawl & sitemaps (`anatomy.CHECK_CATEGORY`).
FINDINGS = [
    ("cd-deep-status", "http-status-error", "A page five clicks in errors",
     f"https://{SITE}/f"),
    ("cd-near-redirect", "redirect-chain", "A page one click in redirects",
     f"https://{SITE}/a"),
]

NEEDS_BROWSER = pytest.mark.skipif(
    not __import__("clauditseo.axe", fromlist=["axe"]).available(),
    reason="needs clauditseo[render] and `playwright install chromium`")


def _page(url: str, depth: int | None) -> dict:
    return {"url": url, "status": 200, "content_type": "text/html",
            "title": "Fixture", "canonical": url, "click_depth": depth,
            "word_count": 400}


def _plant(db: Path, site_id: str, depths: dict[str, int | None],
           scan_scope: str | None = None) -> str:
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["TEC"], "T3", scan_scope=scan_scope)
    runs.store_evidence(conn, run_id, {
        "start_url": HOME,
        "pages": [_page(url, d) for url, d in depths.items()]})
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        for fp, check, summary, url in FINDINGS:
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id,"
                " severity, source, summary, affected_urls, affected_total,"
                " fingerprint, created_at) VALUES (?, ?, 'TEC', ?, 'medium',"
                " 'deterministic', ?, ?, 1, ?, ?)",
                (create_id(), run_id, check, summary, json.dumps([url]), fp,
                 now_iso()))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state,"
                " changed_by_run, updated_at) VALUES (?, ?, 'open', ?, ?)",
                (site_id, fp, run_id, now_iso()))
    conn.close()
    return run_id


def _site(base: str, domain: str) -> str:
    client = httpx.post(f"{base}/api/clients", json={"name": "Depth Co"},
                        timeout=30).json()
    return httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": domain}, timeout=30).json()["id"]


@pytest.fixture(scope="module")
def served():
    """Three sites: the planted distribution, a run that recorded no depth at
    all, and a crawl that never went past three clicks."""
    server, thread, db, base = _serve("crawldepth")
    try:
        full = _site(base, SITE)
        _plant(db, full, DEPTHS)
        blank = _site(base, f"nodepth.{SITE}")
        _plant(db, blank, {url: None for url in DEPTHS})
        shallow = _site(base, f"shallow.{SITE}")
        _plant(db, shallow, {url: d for url, d in DEPTHS.items()
                             if d is not None and d <= 3})
        yield base, {"full": full, "blank": blank, "shallow": shallow}
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _depth(base: str, site_id: str) -> dict:
    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    part = next(c for c in view["categories"] if c["key"] == "crawl")
    return part["depth"]


# --- the payload the drawing is made from --------------------------------

def test_the_crawl_part_carries_the_depths_the_run_recorded(served):
    base, sites = served
    d = _depth(base, sites["full"])
    assert d["recorded"] is True
    assert {b["depth"]: b["pages"] for b in d["bars"]} == EXPECTED
    # Contiguous from the home bar to the deepest, and stopping there: an
    # axis padded past what the crawl reached would say it looked further.
    assert [b["depth"] for b in d["bars"]] == sorted(EXPECTED)
    assert d["bars"][0]["sitemap_only"] == SITEMAP_ONLY
    # Every page the run stored is on a bar, which is the property the
    # sitemap-only rule exists to keep: a page with no click path is still a
    # page the crawl fetched.
    assert sum(b["pages"] for b in d["bars"]) == len(DEPTHS) == d["crawled"]


def test_only_the_crawl_part_is_given_a_depth_block(served):
    base, sites = served
    view = httpx.get(f"{base}/api/sites/{sites['full']}/anatomy",
                     timeout=30).json()
    drawn = [c["key"] for c in view["categories"] if c.get("depth")]
    assert drawn == ["crawl"], drawn


def test_a_run_that_recorded_no_depth_says_so_rather_than_saying_zero(served):
    """The distinction the absent-data contract is about. A payload of
    `recorded: False` and no bars is not the same object as a payload of bars
    that all read zero, and the block draws a sentence for one and a chart
    for the other."""
    base, sites = served
    d = _depth(base, sites["blank"])
    assert d["recorded"] is False
    assert d["bars"] == []
    assert d["crawled"] == len(DEPTHS)


def test_a_crawl_no_deeper_than_three_has_nothing_past_the_rule(served):
    base, sites = served
    d = _depth(base, sites["shallow"])
    assert max(b["depth"] for b in d["bars"]) == 3
    assert not [b for b in d["bars"] if b["depth"] >= d["deep_from"]]


# --- the drawing ----------------------------------------------------------

@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_JS = """() => {
  const bars = [...document.querySelectorAll('.cd-chart .cd-bar')];
  const cs = (el) => getComputedStyle(el);
  return {
    bars: bars.length,
    counts: bars.map((b) => b.querySelector('.cd-n').textContent),
    labels: bars.map((b) => b.querySelector('.cd-label').textContent),
    fills: bars.map((b) => cs(b.querySelector('.cd-fill')).backgroundColor),
    heights: bars.map((b) => b.querySelector('.cd-fill').getBoundingClientRect().height),
    pressed: bars.map((b) => b.getAttribute('aria-pressed')),
    rules: bars.map((b) => b.classList.contains('cd-rule')),
    ruleWord: (document.querySelector('.cd-ruleword') || {}).textContent || '',
    absent: document.querySelectorAll('.cd-absent').length,
    note: (document.querySelector('.cd-note') || {}).textContent || '',
    head: (document.querySelector('.cd-head') || {}).textContent || '',
    causes: [...document.querySelectorAll('table.causes tbody tr .cause-name, '
             + 'table.causes tbody tr code')].map((c) => c.textContent.trim()),
    causeRows: document.querySelectorAll('table.causes tbody tr').length,
    // The three-block layout (brief v25 step BP): the narrow applies to the
    // fix cards under the picture, and is stated in a line.
    fixes: [...document.querySelectorAll('.part-page [data-fix-check]')].map((e) => e.dataset.fixCheck),
    narrowLine: (document.querySelector('.narrow-line') || {}).textContent || '',
    hash: window.location.hash,
  };
}"""


def _open(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
            timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Crawl & sitemaps')
    pg.wait_for_selector(".cd-root", timeout=15_000)


BROWSER = [NEEDS_BROWSER,
           pytest.mark.skipif(not (DIST / "index.html").is_file(),
                              reason="dashboard not built")]


def _mark(fn):
    for m in BROWSER:
        fn = m(fn)
    return fn


@_mark
def test_depth_bars_count_what_the_crawl_recorded(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["bars"] == len(EXPECTED)
    assert got["counts"] == [str(EXPECTED[d]) for d in sorted(EXPECTED)]
    # The deepest bar is drawn and nothing past it is: a tail of empty bars
    # would say the crawl went further than it did.
    assert got["labels"][-1] == "5 clicks"
    # Heights are the counts, to a pixel of rounding. Read off the rendered
    # boxes rather than off the style attribute, because it is the drawn bar
    # an operator compares by eye.
    tallest = max(got["heights"])
    for i, d in enumerate(sorted(EXPECTED)):
        want = tallest * EXPECTED[d] / max(EXPECTED.values())
        assert abs(got["heights"][i] - want) < 1.5, (d, got["heights"])
    # The item's sentence, verbatim: it is the block's whole argument.
    assert ("Anything past three is hard for a crawler to keep fresh and hard "
            "for a person to find" in " ".join(got["note"].split()))


@_mark
def test_past_three_clicks_is_the_only_warn(browser, served):
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"])
        got = pg.evaluate(_JS)
        _open(pg, base, sites["shallow"])
        shallow = pg.evaluate(_JS)
    finally:
        pg.close()
    inside = {got["fills"][d] for d in (0, 1, 2, 3)}
    past = {got["fills"][d] for d in (4, 5)}
    assert len(inside) == 1 and len(past) == 1, (inside, past)
    assert not (inside & past), "a bar past three is drawn as one inside it"
    # One rule, on the first bar past three, and it says what it divides.
    assert got["rules"] == [False, False, False, False, True, False]
    assert got["ruleWord"] == "past three clicks"
    # And a crawl that never went past three has no rule and no warn bar at
    # all - the degradation, drawn rather than asserted about.
    assert not any(shallow["rules"])
    assert shallow["ruleWord"] == ""
    assert set(shallow["fills"]) == inside


@_mark
def test_a_depth_bar_narrows_to_its_pages(browser, served):
    """The bar is a control: pressing it narrows the part's finding list to
    the pages at that depth and the address carries the choice, so the
    narrowed screen is a link somebody else can open."""
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"])
        before = pg.evaluate(_JS)
        # Depth 5 holds one of the two findings; depth 1 holds the other.
        #
        # Waited on by the bar that must end up pressed, not by `.cd-picked`:
        # that line is already on screen after the first press, so a second
        # wait on it returns before React has flushed anything and reads the
        # previous selection's list. Brief v16a step AT-b's own test lost two
        # runs to exactly this and its remedy is the one used here - wait for
        # the state being asserted, not for the element around it.
        pg.click(".cd-chart .cd-bar:nth-child(6)")
        pg.wait_for_selector(".cd-bar:nth-child(6)[aria-pressed='true']",
                             timeout=10_000)
        deep = pg.evaluate(_JS)
        pg.click(".cd-chart .cd-bar:nth-child(2)")
        pg.wait_for_selector(".cd-bar:nth-child(2)[aria-pressed='true']",
                             timeout=10_000)
        near = pg.evaluate(_JS)
        pg.click(".cd-clear")
        pg.wait_for_selector(".cd-picked", state="detached", timeout=10_000)
        cleared = pg.evaluate(_JS)
    finally:
        pg.close()
    # On the three-block layout since brief v25 step BP: the pressed bar
    # narrows the fix cards, and the line says which population they are.
    assert len(before["fixes"]) >= 2, before["fixes"]
    assert "depth=5" in deep["hash"]
    assert deep["pressed"] == ["false"] * 5 + ["true"]
    assert deep["fixes"] and all("http-status-error" in c for c in deep["fixes"]), deep["fixes"]
    assert deep["narrowLine"].startswith("Showing depth 5:"), deep["narrowLine"]
    assert "depth=1" in near["hash"]
    assert near["fixes"] and all("redirect-chain" in c for c in near["fixes"]), near["fixes"]
    # And the way back out: the address loses the depth and the list is whole.
    assert "depth=" not in cleared["hash"]
    assert cleared["fixes"] == before["fixes"] and cleared["narrowLine"] == ""


@_mark
def test_sitemap_only_pages_are_named_on_the_home_bar(browser, served):
    """A page that reached the crawl with no click path from home is a real
    signal, so it is on the axis label where it is read rather than in a
    tooltip nobody hovers. It is counted in the home bar, not beside it."""
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["full"])
        got = pg.evaluate(_JS)
        _open(pg, base, sites["shallow"])
        shallow = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["labels"][0] == f"home + {SITEMAP_ONLY} sitemap-only"
    assert got["counts"][0] == str(EXPECTED[0]) == str(1 + SITEMAP_ONLY)
    # A crawl every page of which has a click path says "home" and no more:
    # the qualifier is a finding, and a finding of nothing is not drawn.
    assert shallow["labels"][0] == "home"


@_mark
def test_missing_depth_is_absent_not_zero(browser, served):
    """A run that recorded no depth draws a sentence naming what is missing,
    not a chart of zeroes - which would be this product asserting every page
    is at the home page, a measurement the run never made."""
    base, sites = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, sites["blank"])
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["absent"] == 1
    assert got["bars"] == 0
    # The heading and the sub-line still stand: the block says what it is
    # about before it says it cannot answer.
    assert "How deep the crawl had to go" in got["head"]


# --- the stylesheet -------------------------------------------------------

def test_every_selector_in_the_depth_sheet_is_namespaced():
    """`crawl_depth.css` is loaded globally, so a selector of its own that is
    not `.cd-` is a rule on every other screen in the app. The argument that
    this block's diff cannot reach another screen rests on this, which is why
    it is a property test rather than a regression guard.

    The same clause brief v16a step AT-b wrote for `schema_graph.css`, and
    the same reason: the sheet is imported by `main.tsx` beside `styles.css`
    and nothing scopes it.
    """
    import re
    sheet = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
             / "crawl_depth.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)
    stray = sorted({c for c in re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", css)
                    if not c.startswith("cd-")})
    assert not stray, f"not namespaced: {stray}"
