"""The snippet's cut marks the description, and its rulers sit beside the card.

Items 198 and 199B, done together because they are one block and the filings
say so.

**198.** The operator, on a part page with the mobile snippet selected: "There
is a cut here line down the side of the page?" `.snip-desc-cut` is
`position: absolute; right: 0; top: 0; bottom: 0`, and the stylesheet says
"`.snip-desc` is the positioning context" - but the span was a SIBLING of
`.snip-desc`. `.snip-card` sets no `position`, nor does anything above it, so
the containing block resolved to the initial one: `right: 0` became the page's
right edge and `top: 0; bottom: 0` the page's whole height.

**199B.** The card was 652px in a column that stacked two full-width rulers
under it, so the rulers were the only thing spanning the block and the space
beside the card was empty.

**Why synthetic markup rather than a driven page.** The marker draws only when
a description is over the selected window, and the rulers only reposition on a
wide column - a combination no page in the fixture is guaranteed to present,
and a guard that silently finds no marker asserts nothing. So this renders the
block the component draws against the BUILT stylesheet and measures it, which
is how `test_the_strip_panel_holds_its_tallest_state.py` (item 161) holds the
panel it could not otherwise reach. `test_the_harness_draws_the_block_the
_screen_draws` is what stops this measuring markup the screen has stopped
drawing.

The structural half of 198 is also asserted on the source, because it is the
whole of the fix: the marker is a child of `.snip-desc` or it is not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("playwright")

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dashboard" / "dist" / "assets"
SRC = ROOT / "dashboard" / "src"

#: A description long enough to be over the window at either width, so the
#: marker draws, and a page far taller than the block, so "the height of the
#: description" and "the height of the page" cannot be confused.
BLOCK = """
<div class="part-page" style="width: WIDTHpx">
  <div class="snip">
    <div class="snip-head">
      <span class="snip-label">As a search result will cut it</span>
      <div class="snip-toggle" role="group" aria-label="preview width">
        <button type="button" class="snip-tab">desktop</button>
        <button type="button" class="snip-tab on">mobile</button>
      </div>
      <span class="snip-why muted">mobile: where the title cuts</span>
    </div>
    <div class="snip-body">
      <div class="snip-card" id="card" style="max-width: 652px">
        <div class="snip-site">www.example-client-site.com.au</div>
        <div class="snip-title-wrap"><span class="snip-title">A title long enough that it runs past the result box edge and is cut there</span></div>
        <div class="snip-desc" id="desc">A description written at length so that it is comfortably over the window
          at either width and the cut marker is drawn, which is the state this
          file exists to measure and the one the operator was looking at.
          <span class="snip-desc-cut" id="cut" aria-hidden="true">
            <span class="snip-desc-cut-label">cut here</span>
          </span>
        </div>
      </div>
      <div class="snip-measures">
        <div class="snip-ruler" id="ruler">title <b>561</b> / 600 px</div>
        <div class="snip-ruler">description <b>1180</b> / 920 px</div>
        <p class="snip-caption muted">title 561 px · description 1180 px</p>
      </div>
    </div>
  </div>
</div>
<div style="height: 3000px"></div>
"""

_MEASURE = """() => {
  const box = (id) => {
    const e = document.getElementById(id);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom,
             width: r.width, height: r.height };
  };
  return { card: box('card'), desc: box('desc'), cut: box('cut'),
           ruler: box('ruler'),
           page: document.documentElement.scrollHeight,
           viewport: window.innerWidth };
}"""


def _css() -> str:
    sheets = sorted(DIST.glob("*.css"))
    if not sheets:
        pytest.skip("dashboard not built (npm run build in dashboard/)")
    return "\n".join(s.read_text(encoding="utf-8") for s in sheets)


def _render(column: int, viewport: int = 1568):
    """The block in a part column `column` px wide."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            pg = browser.new_page(viewport={"width": viewport, "height": 900})
            pg.set_content(
                f"<!doctype html><html><head><style>{_css()}</style></head>"
                f"<body style='margin:0'>"
                f"{BLOCK.replace('WIDTH', str(column))}</body></html>")
            return pg.evaluate(_MEASURE)
        finally:
            browser.close()


def test_the_harness_draws_the_block_the_screen_draws():
    """Every class measured below is one the component actually writes."""
    src = (SRC / "title_snippet.tsx").read_text(encoding="utf-8")
    for cls in ("snip", "snip-head", "snip-label", "snip-toggle", "snip-tab",
                "snip-why", "snip-body", "snip-card", "snip-site",
                "snip-title-wrap", "snip-title", "snip-desc", "snip-desc-cut",
                "snip-desc-cut-label", "snip-measures", "snip-caption"):
        assert re.search(rf'className=[{{`"][^>]*\b{cls}\b', src), (
            f"the harness draws .{cls} and the component no longer does")
    # `.snip-ruler` is written by `Ruler`, in the same file.
    assert "snip-ruler" in src, "the rulers' class has been renamed"


def test_the_cut_marker_is_a_child_of_the_description():
    """The whole of item 198's fix, asserted where it cannot be measured away.

    The marker's CSS resolves against its nearest positioned ancestor, and
    the only positioned thing in this block is `.snip-desc`. Put the marker
    beside it instead of inside it and the rule silently addresses the
    initial containing block - the page - which is what it did from item 136n
    until item 198. No rendered clause can tell that from a stylesheet
    change, so the structure is held here.
    """
    src = (SRC / "title_snippet.tsx").read_text(encoding="utf-8")
    desc = re.search(r'<div className="snip-desc">(.*?)\n      </div>', src, re.S)
    assert desc, "the description box is no longer written as expected here"
    assert "snip-desc-cut" in desc.group(1), (
        "the cut marker is not inside `.snip-desc`. Its CSS positions it "
        "against the nearest positioned ancestor, `.snip-desc` is the only "
        "one in the card, and outside it the rule resolves against the page "
        "- a dashed line down the whole window (item 198)")


def test_the_cut_rule_is_the_height_of_the_description_not_the_page():
    """Item 198, on the pixels. The page here is over 3000px tall, so a rule
    measured against the wrong box cannot be mistaken for one measured
    against the right one."""
    got = _render(1400)
    cut, desc, card = got["cut"], got["desc"], got["card"]
    assert cut, "the cut marker did not render, so this clause measures nothing"
    assert got["page"] > 2000, f"the page is not tall enough to tell: {got}"

    assert abs(cut["height"] - desc["height"]) <= 1.5, (
        f"the cut rule is {cut['height']:.0f}px and the description "
        f"{desc['height']:.0f}px; it is measured against the wrong box "
        f"(the page is {got['page']}px) - item 198")
    assert cut["right"] <= card["right"] + 0.5 and cut["left"] >= card["left"] - 0.5, (
        f"the cut rule is outside the result card: {got}")
    assert cut["top"] >= desc["top"] - 0.5 and cut["bottom"] <= desc["bottom"] + 0.5, (
        f"the cut rule is not within the description's box: {got}")


def test_the_card_and_its_rulers_sit_side_by_side_on_a_wide_column():
    """Item 199B. Beside, and top-aligned with, the card."""
    got = _render(1400)
    card, ruler = got["card"], got["ruler"]
    assert ruler["left"] >= card["right"] - 0.5, (
        f"the rulers still start inside the card's width, so they span the "
        f"block and the space beside the card is empty: {got}")
    assert ruler["top"] < card["bottom"], (
        f"the rulers are below the card rather than beside it: {got}")


def test_the_card_and_its_rulers_stack_on_a_narrow_column():
    """The other side of the one breakpoint. Below it the two-up would give
    the rulers less than their 16rem floor, so they go back under the card -
    in the single `@container part` rule, not one of this block's own."""
    got = _render(700)
    card, ruler = got["card"], got["ruler"]
    assert ruler["top"] >= card["bottom"] - 0.5, (
        f"a narrow column still draws the rulers beside the card: {got}")
