"""Reflow at 320 CSS px — WCAG 2.2 AA 1.4.10, measured rather than asserted.

`auditor.md` records WCAG 2.2 AA as "enforced on the product's own dashboard
by that gate", meaning `test_a11y_rendered.py`. It is not, and could not be:
axe cannot see reflow. 1.4.10 is a failure of *layout at a width*, and axe
audits one rendered tree at whatever viewport the page happened to open at —
1280 px, where the defect does not exist.

So the claim was structural. `grep -rn scrollWidth tests/` returned nothing
for the whole life of this project, and the only number anyone ever had came
from an auditor driving a browser by hand: `document.documentElement.
scrollWidth` = 554 px at a 320 px viewport, on `#/` and on the site screen
(report 053, UI-07). DISCIPLINE rule 4: a coverage claim that cannot come
from what the harness reports is unverified, and unverified is unguarded.

This file is that harness. It parametrises over `ROUTES` — the same list the
axe sweep walks — rather than over the two screens the report happened to
name, so a route added to the app inherits reflow coverage without anybody
remembering a second list.

**The failure message names the box, not just the total.** A guard that says
"554 > 320" tells you the app is broken and nothing about where; the previous
plan named the topnav from reading the stylesheet, which is exactly the
inferring rule 2 exists to stop. The offender scan reports the *innermost*
elements that cross the viewport edge — a wide `<table>` inside a card makes
both overflow, and the table is the one you can do something about.
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

pytestmark = [
    pytest.mark.skipif(not axe.available(),
                       reason="needs clauditseo[render] and `playwright install chromium`"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

#: The width WCAG 2.2 AA 1.4.10 names. 320 CSS px is 1280 at 400% zoom, which
#: is what the criterion is actually about — not a phone.
NARROW = 320

#: Height is arbitrary and deliberately short: vertical scrolling is what
#: 1.4.10 permits, so nothing here should depend on it.
TALL = 640

#: Reported per route so a regression names its own box. Eight is enough to
#: read; a screen with more than eight distinct overflowing leaves has one
#: cause, not eight.
MAX_OFFENDERS = 8

_MEASURE = """() => {
  const vw = document.documentElement.clientWidth;
  const over = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;   // never drawn
    if (r.right <= vw + 0.5) continue;               // inside the edge
    over.push(el);
  }
  // Innermost only: a wide table drags its card and its section over the
  // edge too, and the table is the box worth naming.
  const leaves = over.filter(el => !over.some(o => o !== el && el.contains(o)));
  const name = (el) => {
    const c = el.getAttribute('class');
    return el.tagName.toLowerCase() + (c ? '.' + c.trim().split(/\\s+/).join('.') : '');
  };
  return {
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: vw,
    offenders: leaves.slice(0, %d).map(el => {
      const r = el.getBoundingClientRect();
      return { what: name(el).slice(0, 90),
               width: Math.round(r.width),
               right: Math.round(r.right) };
    }),
  };
}""" % MAX_OFFENDERS


#: The client screen's panes, each a bare route with `?tab=`. `ROUTES` holds
#: the client screen once, at its landing pane, and the axe sweep reaches the
#: others through `REVEAL`; this sweep shares `ROUTES` and not `REVEAL`, so
#: five of six panes were never measured at 320px (second audit of
#: 2026-09-02, F-26 - the Record pane scrolled sideways by 2px throughout).
#: Each names what it waits for, the way `READY` does.
PANES = [
    # Brief v24 step BN: Precheck folded into Audit, and the runs moved to
    # the Record; `?tab=precheck` is an alias of Audit now.
    ("client-audit", "#/sites/{site}?tab=history", ".scan-matrix"),
    ("client-record", "#/sites/{site}?tab=all", ".state-filters"),
    ("client-record-audits", "#/sites/{site}?tab=all&view=audits", ".runs-table"),
    ("client-pages", "#/sites/{site}?tab=pages", ".pane-body"),
    ("client-notes", "#/sites/{site}?tab=notes", ".pane-body"),
]

#: Everything this sweep measures, with what each waits for.
SWEPT = [(name, route, READY.get(name)) for name, route in ROUTES] + PANES


@pytest.fixture(scope="module")
def measured(served):
    """One narrow page load per route, in one browser.

    No axe, no reveal passes: reflow is a property of the screen as it first
    paints, and every disclosure this app has is inside a container that is
    already too wide. Loading once per route keeps this cheap enough to sit
    in the same CI job as the sweep.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    out: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for name, route, ready in SWEPT:
                pg = browser.new_page(viewport={"width": NARROW, "height": TALL})
                try:
                    pg.goto(base + "/" + route.format(**ids),
                            timeout=30_000, wait_until="load")
                    if ready:
                        # Allowed to raise, exactly as the sweep's waits are:
                        # a screen whose own content never arrives is a
                        # failure to report, not a narrower one to measure.
                        pg.wait_for_selector(ready, timeout=15_000)
                    else:
                        pg.wait_for_timeout(1_200)
                    out[name] = pg.evaluate(_MEASURE)
                finally:
                    pg.close()
        finally:
            browser.close()
    return out


@pytest.mark.parametrize("name", [r[0] for r in SWEPT])
def test_the_screen_reflows_at_320px(measured, name):
    """No horizontal scrolling at 320 CSS px — WCAG 2.2 AA 1.4.10.

    Measured 554 px on `home` and `client` before this existed, against
    bundle `Q4crahrs`.
    """
    m = measured[name]
    if m["scrollWidth"] > NARROW:
        boxes = "\n".join(
            f"      {o['width']:>5} px wide, right edge {o['right']:>5} px — {o['what']}"
            for o in m["offenders"]) or "      (no element crosses the edge — a margin or a fixed width on <body>?)"
        pytest.fail(
            f"{name} scrolls sideways at {NARROW} px: "
            f"document width {m['scrollWidth']} px "
            f"(viewport {m['clientWidth']} px).\n"
            f"    innermost boxes past the edge:\n{boxes}")


def test_every_route_was_actually_measured(measured):
    """The sweep's own lesson, applied here: listed is not painted.

    A route whose page never loaded would silently drop out of the
    parametrised set above by returning nothing, and sixteen green tests over
    fourteen measured screens reads identically to sixteen over sixteen.
    """
    missing = [name for name, _, _ in SWEPT if name not in measured]
    assert not missing, (
        "these routes were never measured, so nothing was tested about them: "
        + ", ".join(missing))
    unmeasured = [n for n, m in measured.items() if not m.get("clientWidth")]
    assert not unmeasured, (
        "these routes reported no viewport width, so the measurement is not "
        "a measurement: " + ", ".join(unmeasured))
