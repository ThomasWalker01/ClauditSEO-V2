"""Item 226 (Accessibility, change 1): the fix-order waterfall is drawn at
site scope.

`A11yNow` already drew `FixOrderWaterfall` when no page was in hand, but the
part registered no `siteNow`, so the site branch never called it: on twenty22
T3 the part opened on the checks table with no picture, and "instances open
now" appeared nowhere. Registered the way International and Mobile were.
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_the_accessibility_fix_order_and_overlay import _finding, _inst, _sampled
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://a11ysite.fixture"
PAGES = ["/", "/a/", "/b/", "/c/", "/d/"]


def _plant(db, site_id):
    conn = connect(db)
    run = runs.create_run(conn, site_id, ["A11Y"], "T2")
    runs.store_evidence(conn, run, {"pages": [{"url": BASE + p, "status": 200} for p in PAGES]})
    runs.mark_complete(conn, run, now_iso())
    _sampled(conn, run, 1, len(PAGES))
    _finding(conn, run, "fp-a11y", "link-name-missing", [BASE + "/"],
             [_inst(f"main > a:nth-of-type({i})") for i in range(3)])
    # Item 279 (row 3): four more pages, so the check's group holds more
    # cards than it shows before "show all".
    for i, p in enumerate(PAGES[1:]):
        _finding(conn, run, f"fp-a11y-{i}", "link-name-missing", [BASE + p],
                 [_inst(f"main > p > a.more-{i}")])
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("a11ysite")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "A11y Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "a11ysite.fixture"}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@needs_build
def test_the_site_view_opens_on_the_waterfall(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=a11y",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-page .part-checks", timeout=15_000)
            got = pg.evaluate("""() => ({
              head: document.querySelector('.part-page .now-card h4')?.textContent || '',
              open: document.querySelector('.part-page .fixorder-open')?.textContent || '',
              before: !!document.querySelector('.part-page .now-card')
                && (document.querySelector('.part-page .now-card')
                    .compareDocumentPosition(document.querySelector('.part-checks'))
                    & Node.DOCUMENT_POSITION_FOLLOWING) > 0,
            })""")
        finally:
            b.close()
    assert got["head"] == "What the site has now", got
    assert "instances open now" in " ".join(got["open"].split()), got
    assert got["before"], "the picture stands above the checks table"


@needs_build
def test_a_bar_opens_its_checks_fixes_group(served):
    """Item 279 (row 3): the bars were buttons that did nothing. A press now
    opens that check's group under Fixes, every card shown, and the bar says
    it is the one pressed. The smallest bar holds its count, and each bar
    says its kind under its label."""
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=a11y",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-page .fixorder-bar", timeout=15_000)
            cards = "document.querySelectorAll('[data-fix-check=\"link-name-missing\"]').length"
            before = pg.evaluate(f"() => {cards}")
            bars = pg.evaluate("""() => [...document.querySelectorAll('.fixorder-bar')].map((b) => ({
              h: b.getBoundingClientRect().height, n: b.textContent.trim(),
              kind: b.closest('li').querySelector('.fixorder-kind')?.textContent || '',
            }))""")
            pg.click(".fixorder-bar")
            pg.wait_for_function(f"() => {cards} === 5", timeout=10_000)
            pressed = pg.get_attribute(".fixorder-bar", "aria-pressed")
            group = pg.evaluate("() => (document.querySelector('.fix-group')?.textContent || '')"
                                ".replace(/\\s+/g, ' ').trim()")
        finally:
            b.close()
    assert before == 3, before
    assert pressed == "true"
    # Item 279 (row 4): the group says what the waterfall says of its step,
    # not a path prefix.
    assert "this check assessed" in group and "template /" not in group, group
    assert all(bar["h"] >= 16 and bar["n"] for bar in bars), bars
    assert all(bar["kind"] in ("site chrome", "one template", "page by page") for bar in bars), bars


@needs_build
def test_a_card_says_where_and_what_to_do(served):
    """Item 279 (row 5): each card was one sentence while the row carried the
    elements and the module's advice. The card names the elements (here, the
    selectors axe recorded), says what to do, and copies the first selector."""
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=a11y",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-fixes .fix-card .fix-where", timeout=15_000)
            got = pg.evaluate("""() => {
              const card = [...document.querySelectorAll('.part-fixes .fix-card')]
                .find((c) => (c.querySelector('.fix-page')?.textContent || '').trim() === '/');
              return card && {
                where: [...card.querySelectorAll('.fix-where code')].map((c) => c.textContent),
                todo: (card.querySelector('.fix-new')?.textContent || '').trim(),
                copy: (card.querySelector('.fix-copy')?.textContent || '').trim(),
              };
            }""")
        finally:
            b.close()
    assert got, "no card for /"
    assert got["where"] == [f"main > a:nth-of-type({i})" for i in range(3)], got
    assert got["todo"] == "Do this: fix", got
    assert got["copy"] == "copy selector", got


@needs_build
def test_a_card_can_be_marked_fixed_and_offers_its_re_check(served):
    """Item 279 (row 6): no control on the part marked a fix done. Each card
    of an automatic row that names a page now carries the fix loop's tick;
    once ticked, it offers a re-check of that page, through the route the
    Record uses."""
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=a11y",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-fixes .fix-card .fix-done .fix-chk", timeout=15_000)
            box = pg.locator(".part-fixes .fix-card .fix-done .fix-chk").first
            before = pg.locator(".part-fixes .fix-card").first.locator(".fix-done button").count()
            box.check()
            pg.wait_for_function(
                "() => [...document.querySelectorAll('.part-fixes .fix-done button')]"
                ".some((b) => b.textContent.includes('re-check this page'))", timeout=10_000)
            label = box.get_attribute("aria-label")
        finally:
            b.close()
    assert before == 0
    assert label and label.startswith("mark fixed: "), label
