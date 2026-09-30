"""Item 174, "match the landing reference", and item 175, "the headline measure
was wrong by half".

Three rounds of rule lists (168, 172, 173) were each built as written and the
landing still did not read like concept 05, so 174's target is a file,
`_relay/attachments/mockups/05-landing-reference.html`: match its values and
the relationships between them. This file holds the relationships the item
named as the ones that kept being lost, on geometry and computed style - not
source order, which is what let 171 through.

- **The bar is one row** and the nav is its right-hand anchor. Channel ruling
  20260917-1430 replaced 174's overflow sentence: navigation never hides,
  provenance never hides, a control for a mode you are not in is not drawn, and
  text shortens before any control is removed. So Pages and Notes sit beside the
  nav, the page filter is drawn only in page mode (held in
  `test_the_client_landing_is_three_lanes.py`), and the current audit is one
  line of text (item 239 step 5 retired the picker). With nothing
  hidden, one row needs 1,120 px; below that the bar is two rows. 174 asked for
  900, which is not reachable without hiding a control - measured and reported
  in 174's RESULT, not assumed.
- **The headline sets in two lines** (175): 68ch, never past ~72ch, and no
  `text-wrap: balance` - a long first line carrying the facts, a shorter second.
- **The cards are lighter than the page**, in both themes.
- **The chip sits in a fixed 46 px gutter**, a grid column, so the figures form
  a column.
- **The strip's pills are content width**, not stretched.
- **Nothing sits between the actions and the lanes** but the legend, a
  right-aligned control on the lane row, on the reference's 4 px scale.
"""

from __future__ import annotations

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (module fixture)

pytestmark = [
    pytest.mark.skipif(
        __import__("importlib.util", fromlist=["util"]).find_spec("playwright") is None,
        reason="playwright is not installed"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]


def _landing(served, fn, *, width=1440, scheme="dark"):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": width, "height": 1000}, color_scheme=scheme)
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}", wait_until="load", timeout=30_000)
            pg.wait_for_selector(".cl-landing .cl-lane", timeout=30_000)
            pg.wait_for_selector("#topbar-context .audit-now[data-audit]", state="attached",
                                 timeout=30_000)
            pg.wait_for_selector("#topbar-refs nav.refs", timeout=30_000)
            pg.wait_for_timeout(400)
            return fn(pg)
        finally:
            browser.close()


_BAR = """() => {
  const bar = document.querySelector('.topbar');
  const b = bar.getBoundingClientRect();
  const box = (sel) => { const e = document.querySelector(sel); if (!e) return null;
    const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; };
  const mid = (r) => (r.top + r.bottom) / 2;
  const parts = ['.topbar .brand', '.globalsearch', '#topbar-context .audit-now-text',
                 '#topbar-context .mode-switch', '#topbar-refs', '.topnav'].map((s) => [s, box(s)]);
  return { height: b.height, right: b.right, parts,
           mids: parts.map(([s, r]) => r ? Math.round(mid(r)) : null),
           scroll: bar.scrollWidth - bar.clientWidth,
           refsNext: document.querySelector('#topbar-refs')?.nextElementSibling?.className || '' };
}"""


@pytest.mark.parametrize("width", [1440, 1280, 1120])
def test_the_bar_is_one_row_with_the_nav_at_its_right(served, width):
    got = _landing(served, lambda pg: pg.evaluate(_BAR), width=width)
    assert all(r for _, r in got["parts"]), got
    assert max(got["mids"]) - min(got["mids"]) <= 4, f"{width}: the bar is not one row: {got}"
    assert got["height"] <= 60 and got["scroll"] <= 0, f"{width}: the bar overflows its row: {got}"
    nav = dict(got["parts"])[".topnav"]
    assert abs(nav["right"] - got["right"]) <= 1, f"{width}: the nav is not the right-hand anchor: {got}"
    refs = dict(got["parts"])["#topbar-refs"]
    assert refs["right"] <= nav["left"] and "topnav" in got["refsNext"], (
        f"{width}: Pages and Notes are not beside the nav: {got}")


def test_below_one_rows_width_the_bar_wraps_and_the_page_does_not_scroll(served):
    got = _landing(served, lambda pg: pg.evaluate("""() => ({
      doc: document.documentElement.scrollWidth, vw: window.innerWidth,
      bar: document.querySelector('.topbar').getBoundingClientRect().height })"""), width=900)
    assert got["doc"] <= got["vw"], f"the page scrolls sideways at 900 px: {got}"
    assert got["bar"] > 60, f"the bar did not take a second row where one does not fit: {got}"


_HEADLINE = """() => {
  const s = document.querySelector('.run-head-landing .bl-sentence');
  const cs = getComputedStyle(s);
  const probe = document.createElement('span');
  probe.textContent = '0'; probe.style.font = cs.font; probe.style.letterSpacing = cs.letterSpacing;
  probe.style.position = 'absolute'; probe.style.visibility = 'hidden';
  s.parentElement.appendChild(probe);
  const ch = probe.getBoundingClientRect().width; probe.remove();
  const range = document.createRange(); range.selectNodeContents(s);
  const lines = {};
  for (const r of range.getClientRects()) {
    if (r.width < 1) continue;
    const k = Math.round(r.top / 4);
    const e = lines[k] || (lines[k] = { left: r.left, right: r.right });
    e.left = Math.min(e.left, r.left); e.right = Math.max(e.right, r.right);
  }
  return { fontSize: parseFloat(cs.fontSize), maxWidth: parseFloat(cs.maxWidth), ch,
           wrap: cs.textWrap || cs.textWrapStyle || '', balance: (cs.textWrapStyle || cs.textWrap || '').includes('balance'),
           lines: Object.keys(lines).sort((a, b) => a - b).map((k) => lines[k].right - lines[k].left),
           text: s.textContent.replace(/\\s+/g, ' ').trim() };
}"""


def test_the_headline_sets_in_two_lines_at_68ch_without_balancing(served):
    got = _landing(served, lambda pg: pg.evaluate(_HEADLINE))
    assert got["fontSize"] >= 30, f"the headline is not the reference's 2rem: {got}"
    measure = got["maxWidth"] / got["ch"]
    assert 64 <= measure <= 72, f"the measure is {measure:.1f}ch, not 68 (never past ~72): {got}"
    assert not got["balance"], f"text-wrap: balance fights the long-then-short shape: {got}"
    assert len(got["lines"]) == 2, f"the headline is {len(got['lines'])} lines at 1440, not two: {got}"
    assert got["lines"][0] > got["lines"][1], f"the second line is not the shorter: {got}"


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_the_cards_are_lighter_than_the_page(served, scheme):
    got = _landing(served, lambda pg: pg.evaluate("""() => {
      const lum = (c) => { const m = c.match(/[\\d.]+/g).slice(0, 3).map(Number).map((v) => {
        v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
        return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]; };
      return { ground: lum(getComputedStyle(document.body).backgroundColor),
               lanes: [...document.querySelectorAll('.cl-landing .cl-lane')]
                 .map((l) => lum(getComputedStyle(l).backgroundColor)) };
    }"""), scheme=scheme)
    assert got["lanes"] and all(l > got["ground"] for l in got["lanes"]), (
        f"{scheme}: a lane is not lighter than the page ground: {got}")


def test_the_chips_sit_in_a_46px_grid_gutter(served):
    got = _landing(served, lambda pg: pg.evaluate("""() =>
      [...document.querySelectorAll('.cl-landing .cl-lane')].map((l) => ({
        lane: l.getAttribute('aria-label'),
        entries: [...l.querySelectorAll('.cl-entry')].map((e) => {
          const cs = getComputedStyle(e), fig = e.querySelector('dd.fig'), dt = e.querySelector('dt');
          return { display: cs.display, cols: cs.gridTemplateColumns,
                   figLeft: Math.round(fig.getBoundingClientRect().left),
                   dtLeft: Math.round(dt.getBoundingClientRect().left),
                   entryLeft: Math.round(e.getBoundingClientRect().left) }; }) }))"""))
    for lane in got:
        for e in lane["entries"]:
            assert e["display"] == "grid" and e["cols"].split()[0] == "46px", (lane["lane"], e)
            assert e["dtLeft"] - e["entryLeft"] == 46 + 12, (lane["lane"], e)
        assert len({e["figLeft"] for e in lane["entries"]}) <= 1, f"the chips are not a column: {lane}"


def test_the_strips_pills_are_content_width(served):
    got = _landing(served, lambda pg: pg.evaluate("""() => {
      const pills = [...document.querySelectorAll('.bl-actions .seq-step')];
      return pills.map((li) => {
        const w = li.getBoundingClientRect().width;
        const was = li.style.width; li.style.width = 'max-content';
        const content = li.getBoundingClientRect().width; li.style.width = was;
        return { w: Math.round(w), content: Math.round(content) };
      });
    }"""))
    assert len(got) == 4, got
    assert all(abs(p["w"] - p["content"]) <= 1 for p in got), f"a pill is stretched past its content: {got}"


def test_nothing_but_the_legend_stands_between_the_actions_and_the_lanes(served):
    got = _landing(served, lambda pg: pg.evaluate("""() => {
      const r = (sel) => document.querySelector(sel).getBoundingClientRect();
      const actions = r('.run-head .bl-actions'), lane = r('.cl-landing .cl-lane');
      const legend = document.querySelector('.cl-landing > details.legend');
      const summary = legend.querySelector('summary').getBoundingClientRect();
      const landing = r('.cl-landing');
      const parts = document.querySelector('.cl-landing > .cl-parts');
      const between = [...document.querySelectorAll('body *')].filter((e) => {
        const b = e.getBoundingClientRect();
        return b.height > 0 && b.top >= actions.bottom - 1 && b.bottom <= lane.top + 1
          && !legend.contains(e) && !e.contains(legend)
          && !(parts && (parts.contains(e) || e.contains(parts)))
          && !e.contains(document.querySelector('.cl-lane'))
          && !e.closest('.sr-only'); }).map((e) => e.className || e.tagName);
      const lanes = [...document.querySelectorAll('.cl-landing .cl-lane')].map((l) => l.getBoundingClientRect());
      const cs = getComputedStyle(document.querySelector('.cl-landing .cl-lane'));
      const pr = parts ? parts.getBoundingClientRect() : null;
      return { between, toLegend: summary.top - actions.bottom,
               hasParts: !!parts,
               legendToParts: pr ? Math.round(pr.top - summary.bottom) : null,
               partsToLane: pr ? Math.round(lane.top - pr.bottom) : null,
               toLane: lane.top - summary.bottom,
               legendRight: Math.round(landing.right - summary.right),
               laneGap: Math.round(lanes[1].left - lanes[0].right),
               pad: [cs.paddingTop, cs.paddingLeft, cs.paddingBottom], radius: cs.borderTopLeftRadius };
    }"""))
    assert got["between"] == [], (
        "something stands between the actions and the lanes that is neither "
        f"the legend nor the parts band: {got}")
    assert got["legendRight"] <= 1, f"the legend is not right-aligned on the lane row: {got}"
    assert 28 <= got["toLegend"] <= 36, f"off the 4 px scale: {got}"
    # The parts band, there on the operator's ruling (item 195A): "I want it
    # to sit between these two rows for this screen only. above the waiting on
    # you section." The reference does not have it; the instruction that put
    # it there is newer than the reference and from the same author, so the
    # relationship is amended rather than argued with.
    assert got["hasParts"], (
        "the parts band has left the space between the actions and the lanes, "
        f"where item 195A put it: {got}")
    assert got["legendToParts"] % 4 == 0 and 24 <= got["legendToParts"] <= 40, (
        f"the legend-to-band gap is off the 4 px scale: {got}")
    assert got["partsToLane"] % 4 == 0 and 8 <= got["partsToLane"] <= 20, (
        f"the band-to-lane gap is off the 4 px scale: {got}")
    assert got["laneGap"] == 16 and got["pad"] == ["16px", "16px", "8px"] and got["radius"] == "10px", got
