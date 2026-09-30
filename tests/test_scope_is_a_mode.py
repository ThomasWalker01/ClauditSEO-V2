"""Brief v23 step BK: scope is a mode, not a filter.

The page scope was React state behind a "Narrow to" field, and the screen
printed a paragraph conceding that "counts are for this page only, so they no
longer sum to the site total". Now the scope is in the address, the two modes
are told apart by blue site chrome and amber page chrome on the mode's own
furniture only, each mode states its own arithmetic, and a part with nothing
to draw in page mode draws nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.parts import open_page_filter
from tests.needs_build import needs_build

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


def _page(served, fn):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1080})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
            pg.wait_for_selector(".mode-bar", timeout=30_000)
            return fn(pg, base, ids)
        finally:
            browser.close()


def _choose_first_page(pg) -> str:
    pages = pg.evaluate("() => [...document.querySelectorAll('#anat-pages option')]"
                        ".map((o) => o.value)")
    assert pages, "the fixture crawled no page to scope to"
    open_page_filter(pg)
    pg.fill(".page-find", pages[0])
    pg.wait_for_function("() => location.hash.includes('page=')", timeout=15_000)
    pg.wait_for_selector(".cur-filter-note", timeout=15_000)
    return pages[0]


def _mode(pg) -> str:
    return pg.evaluate("() => document.querySelector('.mode-label').textContent")


@needs_build
def test_page_scope_survives_a_reload(served):
    def go(pg, base, ids):
        _choose_first_page(pg)
        hash_before = pg.evaluate("() => location.hash")
        pg.reload(wait_until="load")
        pg.wait_for_selector(".cur-filter-note", timeout=30_000)
        assert pg.evaluate("() => location.hash") == hash_before
        assert _mode(pg) == "Page mode"
    _page(served, go)


@needs_build
def test_back_returns_to_site_scope(served):
    def go(pg, base, ids):
        assert _mode(pg) == "Site mode"
        _choose_first_page(pg)
        assert _mode(pg) == "Page mode"
        pg.go_back()
        pg.wait_for_function("() => !location.hash.includes('page=')", timeout=15_000)
        pg.wait_for_function(
            "() => document.querySelector('.mode-label')?.textContent === 'Site mode'",
            timeout=15_000)
        # Item 179 (02-2): until the site's payload lands, the lanes stay whole
        # for the page they were read for, and say so; then the note goes.
        pg.wait_for_selector(".cur-filter-note", state="detached", timeout=15_000)
    _page(served, go)


@needs_build
def test_a_pane_link_keeps_the_page_scope_it_was_opened_under(served):
    """Before BK the chosen page followed the operator across every pane. In
    the address, a pane link that predates it (`?tab=all`) would have silently
    dropped them into site mode; `goto` carries the scope instead."""
    def go(pg, base, ids):
        _choose_first_page(pg)
        pg.click('a.seq-name:text-is("Record")')
        pg.wait_for_function("() => location.hash.includes('tab=')", timeout=15_000)
        assert "page=" in pg.evaluate("() => location.hash")
    _page(served, go)


_FURNITURE = [".run-scope[data-mode]", ".anat-narrow", ".mode-label",
              ".mode-seg.mode-on"]

_LEAKS_JS = """(furniture) => {
  const probe = document.createElement('span');
  probe.style.color = 'var(--mode-page)';
  document.querySelector('.run-scope').appendChild(probe);
  const hue = getComputedStyle(probe).color;
  probe.remove();
  const props = ['color', 'backgroundColor', 'borderTopColor', 'borderRightColor',
                 'borderBottomColor', 'borderLeftColor'];
  const leaks = [];
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    for (const p of props) {
      if (cs[p] !== hue) continue;
      if (p.startsWith('border') && cs[p.replace('Color', 'Width')] === '0px') continue;
      if (furniture.some((f) => el.matches(f))) continue;
      leaks.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} ${p}`);
    }
  }
  return { hue, leaks };
}"""


@needs_build
def test_the_mode_colour_appears_only_on_mode_furniture(served):
    """The rule that keeps BK and item 140 both true. Guards the mockups' three
    leaks: an amber primary action, an amber count chip, and any severity-shaped
    element taking the mode hue."""
    def go(pg, base, ids):
        _choose_first_page(pg)
        got = pg.evaluate(_LEAKS_JS, _FURNITURE)
        assert got["hue"] not in ("", "rgba(0, 0, 0, 0)")
        assert not got["leaks"], f"the page-mode hue left its furniture: {got['leaks']}"
        # Filled, per the design ruling of 2026-09-13: an edge alone was not
        # enough to tell the modes apart, and BK lets this one segment carry
        # the mode colour.
        seg = pg.evaluate("() => getComputedStyle(document.querySelector("
                          "'.mode-seg.mode-on')).backgroundColor")
        assert seg == got["hue"], "the active segment must carry the mode hue"
    _page(served, go)


@needs_build
def test_the_primary_action_is_blue_in_both_modes(served):
    read = ("() => { const p = document.createElement('span');"
            " p.style.color = 'var(--accent-solid)'; document.body.appendChild(p);"
            " const blue = getComputedStyle(p).color; p.remove();"
            " return { blue, fills: [...document.querySelectorAll('.tone-action-primary')]"
            ".map((e) => getComputedStyle(e).backgroundColor) }; }")

    def go(pg, base, ids):
        site = pg.evaluate(read)
        _choose_first_page(pg)
        page = pg.evaluate(read)
        for mode, got in (("site", site), ("page", page)):
            assert all(f == got["blue"] for f in got["fills"]), (
                f"a primary action is not blue in {mode} mode: {got}")
    _page(served, go)


@needs_build
def test_page_mode_reports_its_own_part_arithmetic_rather_than_asserting_a_rule(served):
    """True on Birch's home page (parts 26, standing 24) and false on
    Twenty22's (17 and 17): the line states the numbers in hand."""
    import httpx

    def go(pg, base, ids):
        _choose_first_page(pg)
        url = pg.evaluate(
            "() => new URLSearchParams(location.hash.split('?')[1]).get('page')")
        payload = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy",
                            params={"page": url}, timeout=30).json()
        parts = sum(c["total"]["value"] for c in payload["categories"])
        standing = payload["total"]
        want = ("sum to its standing" if parts == standing
                else f"sum to {parts}, not {standing}")
        pg.wait_for_function(
            "(w) => document.querySelector('.mode-arith.cur-filter-note')"
            "?.textContent.includes(w)", arg=want, timeout=15_000)
        line = pg.inner_text(".mode-arith")
        assert "no longer sum" not in line
        if parts != standing:
            assert "counted in each" in line, line
    _page(served, go)


def test_a_part_with_no_page_scope_block_draws_nothing():
    """Mobile's and International's `now` blocks are site pictures; drawn under
    a chosen page they were site mode with nothing hidden, which BK forbids."""
    src = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "{page && render.noPageBlock\n        ? null" in src
    for key in ("intl", "mobile"):
        assert f"  {key}: {{ noPageBlock: true, now: " in src, key
    # And no part that has a page block of its own is withheld.
    for key in ("headings", "images", "schema", "links", "security", "content"):
        start = src.index(f"  {key}: {{")
        assert "noPageBlock" not in src[start:src.index("},", start)], key


def test_the_apology_paragraph_is_gone():
    src = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    # The rendered sentence, not the phrase: the comment that replaced it
    # quotes the old wording to say why it went.
    assert "Counts are for this page only" not in src
