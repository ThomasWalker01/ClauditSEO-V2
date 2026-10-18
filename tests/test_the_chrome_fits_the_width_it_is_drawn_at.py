"""The shell's own chrome never widens the page — measured across the band a
laptop is actually at, which nothing measured before this.

`test_reflow.py` measures 320 CSS px, because that is the width WCAG 2.2 AA
1.4.10 names, and it has been the whole of this project's horizontal-overflow
coverage. 320 is also the width at which the bar is *already* two rows, every
row inside it wraps, and half the desktop rules are switched off by
`@media (max-width: 560px)`. So the one band where the bar is drawn as one row
and told not to wrap — item 174's band — was never measured at all.

It was broken for a day. Item 178 put a 187px hold mark beside the nav's Reports
link, and `.topbar` was `flex-wrap: nowrap` with a context that could not shrink
(`flex: 1 0 auto`), so the row had no answer but to overflow: at 1280px it held
1339px of content in a 1232px row, Admin and Glossary sat off the right edge,
and every client screen scrolled sideways by 83px. Every width from 1120 to
1386 was affected, which is where laptops are. The suite was green throughout.

Two claims, and the second is why this file is not just a wider reflow sweep:

  1. No route widens the page at any of these widths.
  2. The bar is still ONE row where it fits. A wrapping bar cannot overflow, so
     claim 1 alone could be bought by a bar that is always two rows — which
     would throw away what item 174 measured. This pins both ends.
"""

from __future__ import annotations

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import (  # noqa: F401  (reused fixtures)
    DIST,
    READY,
    ROUTES,
    served,
)
from tests.test_reflow import _MEASURE

pytestmark = [
    pytest.mark.skipif(not axe.available(),
                       reason="needs clauditseo[render] and `playwright install chromium`"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: 1366 and 1280 are the two most common laptop widths and both were broken;
#: 1200 and 1120 are the rest of the band; 1440 is where the bar fits with room
#: and is the width every other rendered guard in this suite uses; 1000 is below
#: item 174's 1119, where the bar is two rows by design. The step is deliberately
#: coarse - this is a band, not a search - and 320 is left to `test_reflow.py`.
WIDTHS = (1440, 1366, 1280, 1200, 1120, 1000)

#: The height is irrelevant to the claim and short on purpose: vertical
#: scrolling is not a defect.
TALL = 900

#: The routes whose chrome is fullest, which is where this can fail. A client
#: screen's bar carries the site field, the audit picker, the mode, the page
#: filter, the two reference panes AND the nav; every other screen's carries the
#: site field and the nav. Home and Admin are in for the second group, since a
#: rule added to `.topbar` reaches every screen.
#:
#: Not all thirty of `ROUTES`: at six widths that is 180 page loads for a
#: property four of them can demonstrate. The band's own lesson is that an
#: unmeasured width is unguarded, so the widths are the axis that is complete
#: here and the routes are the sample.
SWEPT = ("client-landing", "client", "client-record", "home", "admin-keys", "reports")

#: The panes `ROUTES` does not hold, taken the way `test_reflow.py` takes them.
EXTRA = {"client-record": ("#/sites/{site}?tab=all", ".state-filters")}

_BAR_ROWS = """() => {
  const bar = document.querySelector('.topbar');
  if (!bar) return null;
  const brand = bar.querySelector('.brand');
  const nav = bar.querySelector('.topnav');
  if (!brand || !nav) return null;
  // One row iff the nav's top edge is the brand's. Not a height threshold and
  // not a count of distinct tops: `align-items: center` gives children of
  // different heights different tops on the SAME row, which is how the first
  // version of this measurement read every bar as two rows.
  const a = brand.getBoundingClientRect(), b = nav.getBoundingClientRect();
  return { oneRow: Math.abs(a.top - b.top) < 6,
           barHeight: Math.round(bar.getBoundingClientRect().height) };
}"""


@pytest.fixture(scope="module")
def swept(served):
    """Every route in `SWEPT` at every width in `WIDTHS`, one page each.

    The viewport is set before the load rather than after, so nothing is
    measured in a layout that was computed for a different width and has not
    settled - the failure mode that made the first pass of this measurement
    report a band 60px narrower than the real one.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    routes = dict(ROUTES)
    out: dict[tuple[str, int], dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for name in SWEPT:
                route, ready = EXTRA.get(name, (routes.get(name), READY.get(name)))
                assert route, f"{name} is not a route"
                for width in WIDTHS:
                    pg = browser.new_page(viewport={"width": width, "height": TALL})
                    try:
                        pg.goto(base + "/" + route.format(**ids),
                                timeout=30_000, wait_until="load")
                        if ready:
                            pg.wait_for_selector(ready, timeout=15_000)
                        else:
                            pg.wait_for_timeout(1_200)
                        out[(name, width)] = {**pg.evaluate(_MEASURE),
                                              "bar": pg.evaluate(_BAR_ROWS)}
                    finally:
                        pg.close()
        finally:
            browser.close()
    return out


@pytest.mark.parametrize("name", SWEPT)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_screen_does_not_widen_the_page(swept, name, width):
    m = swept[(name, width)]
    if m["scrollWidth"] > m["clientWidth"] + 0.5:
        boxes = "\n".join(
            f"      {o['width']:>5} px wide, right edge {o['right']:>5} px — {o['what']}"
            for o in m["offenders"]) or "      (nothing crosses the edge — a margin, or a width on <body>?)"
        pytest.fail(
            f"{name} scrolls sideways at {width} px: document width "
            f"{m['scrollWidth']} px (viewport {m['clientWidth']} px).\n"
            f"    innermost boxes past the edge:\n{boxes}")


@pytest.mark.parametrize("name", SWEPT)
def test_the_bar_is_one_row_where_it_fits(swept, name):
    """Item 174's band, held from the other side.

    `.topbar` wraps now, which is what makes the test above passable at all -
    and a wrapping row can also satisfy it by wrapping at every width, which
    would quietly retire "ONE row above 1119px". 1440 is the width that says
    it did not: the bar fits there with room, so it must be drawn as one row.
    """
    bar = swept[(name, 1440)]["bar"]
    assert bar is not None, f"{name} has no bar to measure"
    assert bar["oneRow"], (
        f"{name}: the bar is two rows at 1440 px (height {bar['barHeight']} px), "
        "where item 174 measured it as one")


def test_every_width_and_route_was_actually_measured(swept):
    """Listed is not painted - `test_reflow.py`'s lesson, and this file has two
    axes to lose a cell from."""
    missing = [(n, w) for n in SWEPT for w in WIDTHS if (n, w) not in swept]
    assert not missing, f"never measured: {missing}"
    assert len(swept) == len(SWEPT) * len(WIDTHS)
