"""Item 161: the strip panel reserves its tallest state, and a height too small
fails silently.

`.strip-panel` is a fixed height with `overflow: hidden` (item 146), so a
second facts line or a second description line that does not fit is simply not
drawn, and nothing on screen says so. The two guards beside it in
`test_the_snippet_and_strips.py` assert invariance - the height does not move -
and pass at any height, including one that clips. This renders the tallest
state against the built stylesheet and asserts both second lines sit inside the
panel's box, not merely in the DOM.

The markup mirrors `StripPanel`, `ResultCard` and `StripFacts` in
`title_snippet.tsx`; a clause below holds the class names to that source so a
renamed class cannot leave this measuring a panel the screen no longer draws.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("playwright")

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dashboard" / "dist" / "assets"
SRC = ROOT / "dashboard" / "src"

#: The tallest state 161 names: a two-line description (long enough to clamp),
#: a path long enough to ellipsise, and a facts row carrying the falls-off
#: clause so it wraps to its second line.
TALLEST = """
<div class="strip-panel pinned" id="panel">
  <div class="strip-panel-head">
    <span>pinned</span><span class="strip-panel-hint">click again to open page scope</span>
  </div>
  <div class="snip-card" style="max-width: 652px">
    <div class="snip-site">www.example-client-site.com.au</div>
    <div class="snip-title-wrap"><span class="snip-title">A title long enough that it runs past the result box edge and is cut there by Google</span></div>
    <div class="snip-desc" id="desc">A description written well past the limit so that it wraps onto a second line inside the result card, and then keeps going onto a third line that the two-line clamp has to hide from view, which is the tallest the description can be.</div>
  </div>
  <p class="strip-panel-path"><code>/services/commercial/finance/very-long-category-name/and-a-very-long-page-slug-that-ellipsises/</code></p>
  <p class="strip-facts" id="facts">
    <span>title <b class="bad">741 px</b> of 580</span> ·
    <span class="bad">falls off: <b>"and is cut there by Google"</b></span> ·
    <span>description <b class="bad">1204 px</b> of 920 · 214 characters · <b class="bad">cut</b></span>
  </p>
</div>
"""

#: The part column's width at the narrowest desktop layout the part page draws
#: before stacking - where the facts row is most likely to wrap.
COLUMN_PX = 620

_MEASURE = """() => {
  const panel = document.getElementById('panel');
  const box = panel.getBoundingClientRect();
  const cs = getComputedStyle(panel);
  const facts = document.getElementById('facts');
  const desc = document.getElementById('desc');
  // The content's own height: from the panel's top to the bottom of its last
  // child's box, plus the panel's bottom padding - what the panel would be if
  // its height were not fixed.
  panel.style.height = 'auto';
  const natural = panel.getBoundingClientRect().height;
  panel.style.height = '';
  // Line boxes, read from the rendered text: each distinct top among the facts
  // row's spans, and the description's clamped lines.
  const range = document.createRange();
  const lineTops = (el) => {
    range.selectNodeContents(el);
    return [...new Set([...range.getClientRects()].map((r) => Math.round(r.top)))].sort((a, b) => a - b);
  };
  const factsTops = lineTops(facts);
  const lastFacts = [...facts.querySelectorAll('span')].map((s) => s.getBoundingClientRect())
    .reduce((m, r) => Math.max(m, r.bottom), 0);
  const descRect = desc.getBoundingClientRect();
  return {
    height: box.height, natural,
    padBottom: parseFloat(cs.paddingBottom), borderBottom: parseFloat(cs.borderBottomWidth),
    factsLines: factsTops.length,
    factsBottom: Math.min(facts.getBoundingClientRect().bottom, lastFacts),
    factsRowBottom: facts.getBoundingClientRect().bottom,
    descLines: Math.round(descRect.height / parseFloat(getComputedStyle(desc).lineHeight)),
    descBottom: descRect.bottom,
    panelInnerBottom: box.bottom - parseFloat(cs.paddingBottom) - parseFloat(cs.borderBottomWidth),
  };
}"""


def _css() -> str:
    sheets = sorted(DIST.glob("*.css"))
    if not sheets:
        pytest.skip("dashboard not built (npm run build in dashboard/)")
    return "\n".join(s.read_text(encoding="utf-8") for s in sheets)


def _render():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            pg = browser.new_page(viewport={"width": 1568, "height": 900})
            pg.set_content(f"<!doctype html><html><head><style>{_css()}</style></head>"
                           f"<body><div style='width:{COLUMN_PX}px;padding:20px'>{TALLEST}"
                           "</div></body></html>")
            return pg.evaluate(_MEASURE)
        finally:
            browser.close()


def test_the_harness_draws_the_panel_the_screen_draws():
    src = (SRC / "title_snippet.tsx").read_text(encoding="utf-8")
    for cls in ("strip-panel", "strip-panel-head", "strip-panel-hint", "snip-card",
                "snip-site", "snip-title-wrap", "snip-title", "snip-desc",
                "strip-panel-path", "strip-facts"):
        assert re.search(rf'className=[{{`"][^>]*\b{cls}\b', src), cls


def test_the_tallest_panel_state_does_not_clip():
    got = _render()
    assert got["factsLines"] >= 2, (
        f"the fixture stopped being the tallest state: the facts row drew "
        f"{got['factsLines']} line(s) at {COLUMN_PX} px")
    assert got["descLines"] == 2, f"the description is not at its two-line clamp: {got}"
    assert got["descBottom"] <= got["panelInnerBottom"] + 0.5, (
        f"the description's second line is outside the panel: {got}")
    assert got["factsBottom"] <= got["panelInnerBottom"] + 0.5, (
        f"the facts row's second line is outside the panel: {got}")
    assert got["natural"] <= got["height"] + 0.5, (
        f"the panel's content is {got['natural']:.1f} px and the panel "
        f"{got['height']:.1f} px, so overflow: hidden is clipping it")
