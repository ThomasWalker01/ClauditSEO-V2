"""Brief v25 step BP: the narrowable site-scope slot, and four parts off the
old layout.

A narrow is in the address, like scope: `?depth=N`, `?check=<id>`,
`?template=<pattern>`. The three-block layout applies it once, above the checks
table and the fixes; a depth or template narrow narrows the crawl population
every count reads, a check narrow does not; the part's coverage line never
narrows; the narrow is stated in the population's words; choosing a page drops
it.

Measured against the old code (DISCIPLINE rule 1): before this step Crawl had
no three-block page at all, so the first clause below could not find
`.part-page .cd-chart` and failed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.parts import open_page_filter
from tests.needs_build import needs_build

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

_READ = """() => ({
  hash: location.hash,
  line: document.querySelector('.narrow-line')?.textContent || '',
  coverage: document.querySelector('.part-coverage')?.textContent || '',
  fixes: [...document.querySelectorAll('.part-page [data-fix-check]')].map((e) => e.dataset.fixCheck),
  crawlOf: [...document.querySelectorAll('.part-page .count.pop-crawl')].map((e) => e.dataset.of),
  pressed: [...document.querySelectorAll('.part-page .cd-bar[aria-pressed="true"]')].length,
  slotAbove: (() => {
    const line = document.querySelector('.narrow-line');
    const table = document.querySelector('.part-page .part-checks');
    const fix = document.querySelector('.part-page .fix-card');
    const top = (e) => e ? e.getBoundingClientRect().top : null;
    return { line: top(line), table: top(table), fix: top(fix) };
  })(),
})"""


def _crawl(pg, base, site, tail=""):
    pg.goto(f"{base}/#/sites/{site}?tab=findings&part=crawl{tail}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".part-page .cd-chart .cd-bar", timeout=30_000)
    pg.wait_for_timeout(300)


def _with_page(served, fn):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1080})
        try:
            return fn(pg, base, ids["site"])
        finally:
            browser.close()


def _press_a_depth(pg):
    """Press the first depth bar that holds pages, and wait for the narrow."""
    bars = pg.query_selector_all(".part-page .cd-chart .cd-bar")
    for bar in bars:
        n = (bar.query_selector(".cd-n").text_content() or "").strip()
        if n.isdigit() and int(n) > 0:
            bar.click()
            pg.wait_for_selector(".narrow-line", timeout=10_000)
            pg.wait_for_timeout(200)
            return
    raise AssertionError("no depth bar holds pages on this fixture")


@needs_build
def test_a_narrow_lives_in_the_address_and_survives_reload(served):
    def go(pg, base, site):
        _crawl(pg, base, site)
        _press_a_depth(pg)
        pressed = pg.evaluate(_READ)
        pg.reload(wait_until="load")
        pg.wait_for_selector(".narrow-line", timeout=30_000)
        reloaded = pg.evaluate(_READ)
        pg.go_back()
        pg.wait_for_function("() => !location.hash.includes('depth=')", timeout=10_000)
        pg.wait_for_timeout(300)
        back = pg.evaluate(_READ)
        return pressed, reloaded, back
    pressed, reloaded, back = _with_page(served, go)
    assert re.search(r"depth=\d+", pressed["hash"]), pressed
    assert reloaded["hash"] == pressed["hash"] and reloaded["line"] == pressed["line"], (pressed, reloaded)
    assert back["line"] == "" and back["pressed"] == 0, back


@needs_build
def test_a_narrow_is_applied_once_above_the_checks_table_and_the_fixes(served):
    def go(pg, base, site):
        _crawl(pg, base, site)
        _press_a_depth(pg)
        return pg.evaluate(_READ)
    got = _with_page(served, go)
    tops = got["slotAbove"]
    assert tops["line"] is not None and tops["table"] is not None, got
    assert tops["line"] < tops["table"], tops
    if tops["fix"] is not None:
        assert tops["line"] < tops["fix"], tops
    src = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert src.count("siteScopedNarrow(part,") == 1, "the narrow is applied in more than one place"


@needs_build
def test_a_depth_narrow_narrows_the_population_and_every_count_reads_it(served):
    """155's rule on the new layout, driven on URLs & parameters' template
    narrow, which carries per-page rows on this fixture (Crawl's rows there
    are site-level and draw no crawl count to read): every crawl-population
    count reads the narrowed page set as its `of`. A depth narrow goes through
    the same `onPages` population; the depth line's words are asserted below."""
    def go(pg, base, site):
        pg.goto(f"{base}/#/sites/{site}?tab=findings&part=urls", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".part-page .un-template", timeout=30_000)
        pg.wait_for_timeout(300)
        before = pg.evaluate(_READ)
        for i in range(len(pg.query_selector_all(".part-page .un-template"))):
            pg.query_selector_all(".part-page .un-template")[i].click()
            pg.wait_for_selector(".narrow-line", timeout=10_000)
            pg.wait_for_timeout(250)
            got = pg.evaluate(_READ)
            if got["crawlOf"]:
                return before, got
            pg.click(".narrow-clear")
            pg.wait_for_function("() => !document.querySelector('.narrow-line')", timeout=10_000)
        raise AssertionError("no template narrow on this fixture keeps a counted row")
    before, after = _with_page(served, go)
    n = re.match(r"Showing pages under (\S+): (\d+) of (\d+) crawled pages\.", after["line"])
    assert n, after["line"]
    narrowed, whole = n.group(2), n.group(3)
    assert int(narrowed) < int(whole), after["line"]
    assert all(o == narrowed for o in after["crawlOf"] if o), (narrowed, after["crawlOf"])
    assert before["crawlOf"] and all(o == whole for o in before["crawlOf"] if o), (whole, before["crawlOf"])


@needs_build
def test_a_check_narrow_does_not_change_the_population(served):
    def go(pg, base, site):
        pg.goto(f"{base}/#/sites/{site}?tab=findings&part=indexability", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".part-page .cc-root", timeout=30_000)
        pg.wait_for_timeout(300)
        before = pg.evaluate(_READ)
        button = pg.query_selector(".part-page .cc-card button.cc-check")
        if button is None:
            pytest.fail("no chain on this fixture carries a check to press")
        button.click()
        pg.wait_for_selector(".narrow-line", timeout=10_000)
        pg.wait_for_timeout(200)
        return before, pg.evaluate(_READ)
    before, after = _with_page(served, go)
    assert "check=" in after["hash"], after
    # The population, not the number of rows that draw it: item 180's ruling
    # 20260918-0402 gave the checks table a row for every check the engine filed
    # under the part, so the whole-part view draws more counts than the narrowed
    # one. What must not change is the denominator each of them names.
    assert before["crawlOf"] and after["crawlOf"], (before["crawlOf"], after["crawlOf"])
    assert set(after["crawlOf"]) == set(before["crawlOf"]), (before["crawlOf"], after["crawlOf"])
    assert "fix cards" in after["line"], after["line"]


@needs_build
def test_the_coverage_line_does_not_narrow(served):
    def go(pg, base, site):
        _crawl(pg, base, site)
        before = pg.evaluate(_READ)
        _press_a_depth(pg)
        return before, pg.evaluate(_READ)
    before, after = _with_page(served, go)
    assert before["coverage"] and after["coverage"] == before["coverage"], (before, after)


@needs_build
def test_the_narrow_is_stated_in_the_populations_words(served):
    def go(pg, base, site):
        _crawl(pg, base, site)
        _press_a_depth(pg)
        pressed = pg.evaluate(_READ)
        # A pasted link states the same line.
        pg.goto("about:blank")
        pg.goto(f"{base}/{pressed['hash']}", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".narrow-line", timeout=30_000)
        return pressed, pg.evaluate(_READ)
    pressed, pasted = _with_page(served, go)
    assert re.fullmatch(r"Showing depth \d+: \d+ of \d+ crawled pages\. Clear", pressed["line"]), pressed["line"]
    assert pasted["line"] == pressed["line"], (pressed, pasted)


@needs_build
def test_a_narrow_is_dropped_when_a_page_is_chosen(served):
    def go(pg, base, site):
        _crawl(pg, base, site)
        _press_a_depth(pg)
        pages = pg.evaluate("() => [...document.querySelectorAll('#anat-pages option')].map((o) => o.value)")
        open_page_filter(pg)
        pg.fill(".page-find", pages[-1])
        pg.wait_for_function("() => location.hash.includes('page=')", timeout=15_000)
        pg.wait_for_timeout(300)
        return pg.evaluate(_READ)
    got = _with_page(served, go)
    assert "depth=" not in got["hash"] and got["line"] == "", got


def test_the_four_parts_declare_site_now_and_not_site_scope():
    src = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    table = src[src.index("export const PART_RENDERERS"):]
    for key, slot in (("crawl", "CrawlSiteNow"), ("indexability", "IndexabilitySiteNow"),
                      ("urls", "UrlsSiteNow"), ("speed", "SpeedSiteNow")):
        m = re.search(rf"^\s*{key}: \{{(.*?)\}},\s*$", table, re.M | re.S)
        assert m, f"{key} has no renderer"
        entry = m.group(1)
        assert f"siteNow: {slot}" in entry, (key, entry)
        assert "siteScope" not in entry, f"{key} declares siteScope, which skips the checks table"


def test_pages_are_keyed_the_way_155_keys_them():
    """`/x` and `/x/` are one page for every narrow: the depth predicate and
    the narrow's page set both go through `pathKey`, which must agree with
    `runs._host_path`."""
    narrow = (SRC / "narrow.ts").read_text(encoding="utf-8")
    depth = (SRC / "crawl_depth.tsx").read_text(encoding="utf-8")
    assert "keys.add(pathKey(u))" in narrow
    assert "keys.has(pathKey(url))" in depth
    from clauditseo.persistence import runs
    assert runs._host_path("https://x.test/a/", "x.test") == runs._host_path("https://x.test/a", "x.test")
