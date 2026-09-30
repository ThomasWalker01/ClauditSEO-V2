"""No part-page block runs past the column it is drawn in (item 136m).

**The column is narrower than every v16 mockup assumed, and the mockups were
not measured.** On the running product, Client > a part page, browser default
zoom, 2026-09-07:

    viewport   column   card     part page with the Re-audit drawer
    1920       1084     1042     768
    1440       1076     1034     760
    1280        916      874     600

Two premises of the brief are wrong. The right panel is FIXED at 300px rather
than a proportion of the width, and it is absent on a three-block part page,
so those get the whole column. `.shell` caps at 1400px, so the column never
exceeds 1084 however wide the display - which is why `--part-narrow` is 1000
and not the ~1000-1240 the mockups were drawn at. A breakpoint at the assumed
column width would have put every part page permanently in its narrow layout.

The rule is a CONTAINER query, and that is the substance rather than the
technique: a block sizes to its column, and the column is not the viewport.
A drawer part is 768px wide on a 1920 display, and no media query can see
that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_a11y_rendered import DIST
from tests.test_the_part_page_is_three_blocks import _open, served, three_block_parts  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"

#: The three viewports, and the column each produces. Asserted, not assumed -
#: a change to `.shell` or to the rail would move these and the clause should
#: say so rather than quietly measure something else.
WIDTHS = (1920, 1440, 1280)

NARROW = 1000

@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


NEEDS_BROWSER = pytest.mark.skipif(
    not (DIST / "index.html").is_file(), reason="dashboard not built")


#: Every element inside the part page, and how far each runs past its own
#: edge. `> 1` rather than `> 0` because sub-pixel layout rounds.
_OVERFLOW_JS = """() => {
  const root = document.querySelector('.part-page');
  if (!root) return {column: null, over: []};
  const over = [...root.querySelectorAll('*')]
    // A visually hidden label clips its text by design (`.sr-only`).
    .filter(e => !e.classList.contains('sr-only') && e.scrollWidth - e.clientWidth > 1)
    .map(e => ({cls: (e.className || '').toString().split(' ')[0] || e.tagName,
                by: e.scrollWidth - e.clientWidth}));
  return {column: Math.round(root.getBoundingClientRect().width), over};
}"""


@NEEDS_BROWSER
@pytest.mark.parametrize("width", WIDTHS)
def test_no_part_page_block_overflows_its_column(browser, served, width):
    """The item's headline guard, and it found a real one immediately.

    `.img-markup` ran 1796px past a 1042px column: an `<img>` tag's
    attributes sat off-screen with nothing on the page saying so. Horizontal
    scroll inside a block is never the answer - the block has hidden
    something and does not admit it.

    **Site scope, with no page chosen.** That is where the defect this file
    was written after actually lived: the rendered sweep in
    `test_a11y_rendered.py` picks `/promo` before it walks the parts, so
    every part page it had ever audited was at page scope, and the headers
    grid rendering nowhere at site scope was invisible to it.

    **Stated limitation: this drives the fixture, and the fixture is thin.**
    Step 3 of item 136m ran the same measurement against the operator's own
    Acme data and found an overflow this clause did not - the headings
    skip-by-template table, whose bar was `flex: 0 0 auto` and ran 22px past
    its cell on the `/blog/*` row at 146 pages. The fixture has no template
    large enough to draw that bar, so the clause passed. A block only
    overflows when its content is big enough to make it, and a fixture is
    small by design; this guard catches structural overflow, and real data
    is still what catches the rest.
    """
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": width, "height": 1080})
    bad = {}
    try:
        _open(pg, base, site_id)
        for part in sorted(three_block_parts()):
            from tests.test_fetch_state import open_part_key
            open_part_key(pg, part)
            pg.wait_for_timeout(500)
            got = pg.evaluate(_OVERFLOW_JS)
            if got["over"]:
                bad[part] = (got["column"], got["over"][:4])
    finally:
        pg.close()
    assert not bad, (
        f"at a {width}px viewport these blocks run past their column: {bad}")


@NEEDS_BROWSER
def test_two_up_layouts_stack_below_the_breakpoint(browser, served):
    """One breakpoint, and it is the column's width and not the window's."""
    base, site_id, _ = served
    # 1040, not 1280: with the sidebar retired (brief v24 step BO) a 1280
    # viewport gives the column ~1190px, above the breakpoint.
    for width, expect_narrow in ((1920, False), (1040, True)):
        pg = browser.new_page(viewport={"width": width, "height": 1080})
        try:
            _open(pg, base, site_id)
            got = pg.evaluate("""() => {
              const r = document.querySelector('.part-page');
              return {w: r ? Math.round(r.getBoundingClientRect().width) : null,
                      type: r ? getComputedStyle(r).containerType : null};
            }""")
        finally:
            pg.close()
        assert got["type"] == "inline-size", (
            "the part page is not a query container, so every block below it "
            f"is sizing to the viewport instead: {got}")
        assert (got["w"] <= NARROW) is expect_narrow, (
            f"at a {width}px viewport the column measured {got['w']}px, which "
            f"is on the wrong side of --part-narrow ({NARROW})")


def test_the_breakpoint_is_one_constant():
    """No block carries its own pixel breakpoint.

    `crawl_depth.css` and `schema_graph.css` each held `max-width: 1024px` -
    a number nobody had measured, applied to the viewport rather than to the
    column the block is inside. Both are now rules under the single
    `@container part` in `styles.css`.

    `score_trend.css` keeps a media query on purpose and is named here: the
    trend is drawn on the Audit step, not on a part page, so it has no part
    column to size to.
    """
    import re

    allowed = {"styles.css", "score_trend.css"}
    offenders = {}
    for css in sorted(SRC.glob("*.css")):
        if css.name in allowed:
            continue
        # Comments stripped first: a file is allowed to SAY what breakpoint
        # it used to carry, and `schema_graph.css` does.
        text = re.sub(r"/\*.*?\*/", "", css.read_text(encoding="utf-8"), flags=re.S)
        hits = re.findall(r"@(?:media|container)[^{]*?(\d+)px", text)
        if hits:
            offenders[css.name] = hits
    assert not offenders, (
        "these block stylesheets carry their own breakpoint instead of using "
        f"the single `@container part` rule in styles.css: {offenders}")

    styles = (SRC / "styles.css").read_text(encoding="utf-8")
    assert styles.count(f"@container part (max-width: {NARROW}px)") == 1, (
        "the part breakpoint is written more than once, or not at all")
    assert f"--part-narrow: {NARROW}px" in styles, (
        "the measured value is not declared as a custom property, so nothing "
        "documents what the literal in the container query means")

    # And there is no SECOND container query beside it. The two assertions
    # above allow one: they count `@container part (max-width: 1000px)` and
    # they police only the OTHER stylesheets, so a `@container (max-width:
    # 1100px)` on a new container in this file would pass both while
    # contradicting the comment above `--part-narrow`, which says the literal
    # appears once in the single `@container` rule.
    #
    # Item 199 arrived proposing precisely that for the snippet block. Its
    # numbers turned out to fit inside 1000 and the rule joined the one
    # block; the next such proposal may not have the arithmetic to fall back
    # on, and by then the second query is in the file.
    #
    # Comments stripped for the reason the loop above strips them: this file
    # SAYS `@container` four times while using it once, so counting the word
    # would count its own documentation.
    bare = re.sub(r"/\*.*?\*/", "", styles, flags=re.S)
    assert bare.count("@container") == 1, (
        "styles.css carries more than one container query. Item 136m's rule "
        "is one `@container`, one literal, every part-page block - a block "
        "that needs a different breakpoint is a block whose numbers should "
        f"be argued at {NARROW}px first: {re.findall(r'@container[^{{]*', bare)}")


def test_no_block_declares_its_base_rule_after_the_container_that_narrows_it():
    """A narrow rule the base rule overrides is a narrow rule that does not run.

    The single `@container part` block sits in the middle of `styles.css`,
    not at the end as the comment above `--part-narrow` still says. Rules
    inside it have the same specificity as the base rules outside, so a base
    rule declared LATER wins and the block simply never narrows - with
    nothing on screen, in the build, or in the type-check to say so.

    Item 199B fell in exactly this hole: `.snip-body`'s base rule went in
    beside its `.snip-*` siblings, which are below the container block, and
    the rulers stayed beside the card at a 700px column. It was caught on
    rendered pixels, which is an expensive way to find a source-order
    mistake, and only because that item happened to have a clause measuring
    the narrow case.

    Every other selector in the block was already declared earlier, so there
    was no example to learn from - which is the argument for asserting it
    rather than writing it down.
    """
    import re

    css = (SRC / "styles.css").read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(css) if l.startswith("@container part"))
    end = next(i for i in range(start + 1, len(css)) if css[i] == "}")

    styled = set()
    for line in css[start + 1:end]:
        m = re.match(r"\s*(\.[\w.\- ,>]+)\s*\{", line)
        if m:
            styled.update(x.strip() for x in m.group(1).split(","))

    assert styled, "the container block styles nothing, so this checks nothing"
    late = {}
    for sel in sorted(styled):
        base = sel.split()[0].split(":")[0]
        after = [i + 1 for i in range(end + 1, len(css))
                 if css[i].startswith((base + " ", base + "{", base + ","))]
        if after:
            late[sel] = after[:3]
    assert not late, (
        "these selectors are narrowed inside `@container part` and then "
        "declared again below it, where the later rule wins at equal "
        f"specificity - so they never narrow: {late}. Move the base rule "
        f"above line {start + 1}.")
