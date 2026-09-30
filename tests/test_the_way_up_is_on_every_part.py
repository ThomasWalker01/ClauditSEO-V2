"""The parts band leads the landing, wears severity, and carries the way up.

Items 194 and 195, done together because they are one band.

**194.** From inside a part there was no route to the screen the parts are a
breakdown of. Measured on the operator's own site: 59 links on an open part,
30 of them to this site, and not one the bare address the landing lives at.
Item 185 had fixed the sibling problem - the way back to the OTHER parts - and
the level above was never in its scope, so a fix that solved movement within a
level left movement between levels unreachable. The operator found it: "If I
click on title and description, I cannot get back to that screen."

**195A.** The band that is the only way to reach a part began at 873px on a
1067px landing - the bottom fifth, under three lanes. "This should be higher
on the home page like a secondary menu."

**195B.** Its counts carried no colour at all. `worst()` had sat unused since
brief v24 step BO retired the sidebar whose pills used it, with a docstring
saying what it was for. The operator: "Counts should get a severity colour as
every other measured item does."

**Why the contrast clause is here.** Giving the count a tone created a defect
in one move: `.parts-unread .parts-n` outranked `.tone-sev-*` (0,2,0 against
0,1,0), kept the background and replaced the ink - near-white on amber, about
2:1. A chip wearing someone else's ink is what
`test_dashboard_a11y.py::test_every_chip_declares_its_own_ink` exists to
catch, arriving through the cascade rather than a missing declaration. It is
asserted here on the rendered pixels because that is where it appeared.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)
from tests.parts import open_part

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"

#: Luminance and ratio, in the page, so the numbers are the rendered ones.
_RATIO_JS = """(sel) => {
  const lum = (c) => {
    const [r, g, b] = c.match(/\\d+/g).map(Number).map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  return [...document.querySelectorAll(sel)].map((n) => {
    const cs = getComputedStyle(n);
    const a = lum(cs.color), b = lum(cs.backgroundColor);
    return {
      cls: n.className,
      bg: cs.backgroundColor,
      ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
    };
  });
}"""


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


# --- the duplication this item declared -------------------------------------

def test_the_way_up_says_the_landings_registered_name():
    """`client_lanes.tsx` spells "Where it stands" and `views.tsx` registers
    it. That is a second spelling of a registered word, which item 166 exists
    to prevent - and it is spelled anyway, because `views.tsx` imports values
    from `client_lanes.tsx` and importing the label back would close a runtime
    cycle.

    So the duplication is declared and watched rather than hidden. If the pane
    is renamed and the control is not, this fails and names both files.
    """
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    views = (SRC / "views.tsx").read_text(encoding="utf-8")
    m = re.search(r'const LANDING_NAME = "([^"]+)"', lanes)
    assert m, "client_lanes.tsx no longer names the landing"
    registered = re.search(r'landing:\s*\{\s*label:\s*"([^"]+)"', views)
    assert registered, "views.tsx no longer registers the landing's label"
    assert m.group(1) == registered.group(1), (
        f"the way up says {m.group(1)!r} and the pane register says "
        f"{registered.group(1)!r} - one of them was renamed alone")


# --- the band, rendered -----------------------------------------------------

@live
def test_the_parts_band_leads_the_lanes(served, browser_page):
    """195A, on the operator's ruling: "I want it to sit between these two rows
    for this screen only. above the waiting on you section."

    It ended the page before - 873 px of a 1067 px landing, the bottom fifth -
    and it is the only control that reaches a part, so a reader who wanted one
    scrolled past everything the parts are a breakdown of.

    This is the one thing item 174's reference does not allow beside the
    legend, and it took the operator's word to put it there: I had built this,
    found it broke `test_the_landing_matches_the_reference` and
    `test_the_head_is_a_headline_then_actions`, and reverted rather than
    rewrite a relationship three rounds of work had converged on. Both guards
    now carry the amendment and the words it was made in.
    """
    base, ids = served
    browser_page.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
    browser_page.wait_for_selector(".cl-landing .cl-parts", timeout=15_000)
    tops = browser_page.evaluate(
        """() => {
             const at = (s) => {
               const e = document.querySelector(s);
               return e ? Math.round(e.getBoundingClientRect().top + window.scrollY) : null;
             };
             return { parts: at('.cl-parts'), lane: at('.cl-lane') };
           }""")
    assert tops["parts"] is not None and tops["lane"] is not None, tops
    assert tops["parts"] < tops["lane"], (
        "the parts band is below the lanes again; it is the only control that "
        f"reaches a part and it ended the page before item 195A: {tops}")


@live
def test_a_count_wears_the_worst_severity_in_it(served, browser_page):
    """195B, and the restoration `worst()` describes: "the count pill takes
    the colour of the worst thing inside it, so scanning the tree finds the
    severe categories before the merely large ones"."""
    base, ids = served
    browser_page.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
    browser_page.wait_for_selector(".cl-parts .parts-link", timeout=15_000)
    tones = browser_page.eval_on_selector_all(
        ".cl-parts .parts-link .parts-n",
        "els => els.map(e => e.className)")
    assert tones, "the band drew no counts"
    toned = [t for t in tones if "tone-sev-" in t]
    assert toned, (
        "no count carries a severity tone, so the band is back to a wall of "
        f"identical figures: {tones}")
    # More than one severity, or the colour is carrying nothing.
    kinds = {re.search(r"tone-sev-(\w+)", t).group(1) for t in toned}
    assert len(kinds) > 1, (
        "every count wears the same severity, so the tone distinguishes "
        f"nothing on this site: {sorted(kinds)}")


@live
def test_no_count_wears_a_background_without_its_own_ink(served, browser_page):
    """The defect giving the count a tone created, caught on the pixels.

    `.parts-unread .parts-n` outranked the tone and replaced only its colour,
    leaving the background: near-white on amber, about 2:1. The registered
    tones carry their measured ratios - 8.61 for medium, 5.65 for high - so
    anything far below that means an override has taken the ink off a
    background again.
    """
    base, ids = served
    browser_page.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
    browser_page.wait_for_selector(".cl-parts .parts-link", timeout=15_000)
    rows = browser_page.evaluate(_RATIO_JS, ".cl-parts .parts-link .parts-n")
    painted = [r for r in rows if "tone-sev-" in r["cls"]]
    assert painted, "no count is painted, so this clause is checking nothing"
    bad = [r for r in painted if r["ratio"] < 4.5]
    assert not bad, (
        "these counts render below 4.5:1, so a rule has replaced the tone's "
        f"ink and kept its background: {bad}")


# --- the way up -------------------------------------------------------------

@live
def test_an_open_part_offers_the_way_up_and_it_goes_there(served, browser_page):
    """194. The control exists, it clears the part, and it is not inert.

    "Not inert" is the half worth driving: `keepPageScope` copies `part`
    forward from the address being left, so a link to the landing built the
    ordinary way arrives back on the part - which is exactly what "Open the
    catalogue" does from inside a part, measured the same day.
    """
    base, ids = served
    browser_page.goto(f"{base}/#/sites/{ids['site']}?tab=findings",
                      wait_until="load")
    browser_page.wait_for_selector(".anat-layout", timeout=15_000)
    open_part(browser_page, "Title & description")
    up = browser_page.wait_for_selector(".part-switch .parts-up", timeout=15_000)
    assert up, "an open part offers no way up"

    before = browser_page.evaluate("() => location.hash")
    assert "part=" in before, before
    up.click()
    browser_page.wait_for_selector(".cl-landing", timeout=15_000)
    after = browser_page.evaluate("() => location.hash")
    assert after != before, (
        "the way up did not move: the scope carry has put the part back, "
        f"which is the defect it is built to avoid ({after})")
    assert "part=" not in after, after
    assert "tab=" not in after, after


@live
def test_the_way_up_keeps_the_audit_the_reader_pinned(served, browser_page):
    """The operator's own URL carried `?run=`, and the first click lost it.

    The general carry is a separate question - `keepPageScope` forwards `page`
    and `part` and no other key, so every link in the product drops `run=` -
    and this asserts only what this control promises: a reader who pinned an
    audit and went up still has it.
    """
    base, ids = served
    run = ids.get("run") or ids.get("run_id")
    if not run:
        pytest.skip("the fixture exposes no run id to pin")
    browser_page.goto(
        f"{base}/#/sites/{ids['site']}?tab=findings&part=title-desc&run={run}",
        wait_until="load")
    up = browser_page.wait_for_selector(".part-switch .parts-up", timeout=15_000)
    href = up.get_attribute("href")
    assert f"run={run}" in href, (
        f"the way up drops the pinned audit: {href}")
    up.click()
    browser_page.wait_for_selector(".cl-landing", timeout=15_000)
    after = browser_page.evaluate("() => location.hash")
    assert f"run={run}" in after, after


@live
def test_a_toned_count_says_its_severity_in_words(served, browser_page):
    """The other half of item 195B's rule, and item 166's whole point.

    I checked this tone's CONTRAST on rendered pixels when I added it -
    8.61 and 5.65 - and did not check whether anything said what the colour
    meant. The element's text is a number; the landing draws no legend strip
    at all (`views.tsx` gates it on `tab !== "landing"`); so the severity was
    carried by colour alone. WCAG 1.4.1, and item 166 puts it more strictly
    still: every tone carries its word on the element itself.

    The invariant is an IFF, which is why this compares the two sets rather
    than checking each separately: a count that wears a tone and says no
    severity is meaning by colour alone, and a count that says a severity
    while wearing no tone is a word with nothing behind it. The condition in
    the source is written once and read twice, so the two can drift.

    This closes the assistive-technology half only. The visible half is item
    166's disclosure, listed in that item's vocabulary sweep - inventing a
    second way to say what a colour means is the thing 166 exists to stop.
    """
    base, ids = served
    browser_page.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
    browser_page.wait_for_selector(".cl-parts .parts-link", timeout=15_000)
    rows = browser_page.eval_on_selector_all(
        ".cl-parts .parts-link",
        """els => els.map((a) => ({
             label: a.getAttribute('aria-label') || '',
             tone: (a.querySelector('.parts-n')?.className || '')
                     .match(/tone-sev-(\w+)/)?.[1] || null,
           }))""")
    assert rows, "the band drew no parts, so this clause checks nothing"
    toned = [r for r in rows if r["tone"]]
    assert toned, (
        "no count wears a tone here, so this cannot tell a fixed rule from "
        f"an absent one: {rows}")

    silent = [r for r in toned if f"worst {r['tone']}" not in r["label"]]
    assert not silent, (
        "these counts carry a severity tone and their accessible name does "
        f"not say which severity, so the colour is the only channel: {silent}")

    spurious = [r for r in rows if not r["tone"] and "worst " in r["label"]]
    assert not spurious, (
        "these counts name a severity they do not wear, so the word and the "
        f"tone have drifted apart: {spurious}")
