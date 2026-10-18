"""The findings legend keys what is on the screen, not what is in the drawer.

Item 197, filed by the operator reading a part page with the catalogue shut:
"these status dots don't seem to have a purpose here any more."

They did not. The strip emitted all seven of its entries whenever the pane
was `findings`, and five of them keyed symbols drawn only by
`CatalogueList` - which, inside a part, lives in a drawer that is closed by
default. A reader saw a key to a legend with nothing to read.

**Why the shop clause is here.** The same `CatalogueList` is mounted twice:
in the drawer (`catalogue.tsx:124`) and as the shop (`anatomy.tsx:3928`),
which is what `?tab=findings` with no part open shows. The filing counted
the two SOURCE sites of the dot and read them as "both inside the drawer";
they are both inside the component, and the component stands on the page
whenever no part is open. Gating the keys on the drawer alone would have
taken them off the one pane that always draws the symbols. So the clause
that matters most here is not the one the operator reported - it is the
shop, asserting the fix did not overshoot the defect.

The claim is held from both ends, because it can come back from either:

  - **From the list.** If a dot, a rank or a re-check starts rendering
    somewhere `CatalogueList` is not, the keys should follow it. The source
    clause fails and names the file that changed.
  - **From the strip.** If the keys come back out unconditionally, the
    closed-drawer clause fails.

Neither half is sufficient alone: the source clause cannot see the default
state, and the rendered clauses cannot tell a symbol that moved from a
symbol that was deleted.

**The branch that outlived its pane**, folded in on the operator's
instruction while this file was open. Item 196 retired Triage as a step and
its legend branch stayed behind, drawing a key for a rank on a pane no
address can reach. Nothing failed, because a branch that cannot be entered
cannot be wrong - it was found by reading, which is not a method. The last
clause here is that method.
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

#: The three things the moved keys describe, and the token each is found by.
#: `LookDot` rather than `cat-dot` for the dot: `cat-dot` is also the class
#: the legend paints its own swatches with (`panels.tsx:77`), so matching the
#: class would count the key as a render site of the thing it keys. The
#: other two are matched bare - `anat-rank` is built in a template literal
#: (`catalogue.tsx:447`), so anchoring on a quote would match nothing and
#: pass for the wrong reason.
KEYED = {
    "the read/running/automatic dot": r"<LookDot\b",
    "the triage rank": r"anat-rank",
    "the re-check control": r"anat-rerun",
}

#: Where those may appear without being a render site. `panels.tsx` declares
#: `LookDot` and draws the legend's own swatches; `legend_strip.tsx` is the
#: key itself. Everything else that draws one must be the catalogue.
DECLARERS = {"panels.tsx", "legend_strip.tsx"}


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


def _part_page(pg, base, site):
    pg.goto(f"{base}/#/sites/{site}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=15_000)
    open_part(pg, "Title & description")
    pg.wait_for_selector(".anat-legend .anat-catalogue-open", timeout=15_000)


_KEYS = ".anat-legend .cat-dot, .anat-legend .anat-rank, .anat-legend .anat-rerun"


def test_the_keyed_symbols_are_drawn_by_the_catalogue_and_nothing_else():
    """The premise the move rests on, asserted so it cannot quietly expire.

    If one of these starts rendering somewhere `CatalogueList` is not, the
    key belongs wherever that is - and this fails naming the file that
    changed, rather than the strip going quietly wrong on a pane nobody
    re-read.
    """
    for what, token in KEYED.items():
        where = sorted(
            f.name for f in SRC.glob("*.tsx")
            if f.name not in DECLARERS
            and re.search(token, f.read_text(encoding="utf-8")))
        assert where == ["catalogue.tsx"], (
            f"{what} is drawn outside the catalogue now ({where}), so the "
            "legend's keys belong wherever it went - item 197 moved them "
            "behind the list on the premise that only the list draws them")


@live
def test_a_closed_catalogue_leaves_no_key_to_itself_on_the_strip(served, browser_page):
    """The operator's screen: a part page, drawer shut, and the strip saying
    what a dot means when there is no dot."""
    base, ids = served
    _part_page(browser_page, base, ids["site"])
    open_now = browser_page.eval_on_selector(
        ".anat-legend .anat-catalogue-open",
        "e => e.getAttribute('aria-expanded')")
    assert open_now == "false", (
        f"the catalogue is open before anything pressed it ({open_now}); this "
        "clause is about the closed state and is measuring the other one")
    found = browser_page.eval_on_selector_all(
        _KEYS, "els => els.map(e => e.className)")
    assert found == [], (
        "the closed strip still keys symbols that only the catalogue draws: "
        f"{found}")

    # This is NOT brief step 4's UX-03 returning, and the difference is one
    # number. UX-03 was the legend vanishing when a section opened *while the
    # other sections' dots were still on screen and still needed reading* -
    # the key leaving before the symbols did. Here the symbols leave with it:
    # a part page unmounts the shop, so nothing anywhere on the document
    # carries a dot, a rank or a re-check.
    #
    # Asserted page-wide rather than on the strip, because a strip clause
    # cannot tell the two faults apart - both look identical from inside
    # `.anat-legend`. If the shop is ever left mounted behind an open part,
    # this fails, and it should: the key would belong back.
    page = browser_page.evaluate(
        "() => document.querySelectorAll('.cat-dot, .anat-rank, .anat-rerun').length")
    assert page == 0, (
        f"{page} of the keyed symbols are still on the page with a part open, "
        "so removing the key is brief step 4's UX-03 all over again - the "
        "legend leaving while the dots it explains are still being read")


@live
def test_opening_the_catalogue_brings_its_key_with_it(served, browser_page):
    """The other half, and the one that stops this being a deletion: the keys
    are not gone, they arrive with the thing they describe."""
    base, ids = served
    _part_page(browser_page, base, ids["site"])
    browser_page.click(".anat-legend .anat-catalogue-open")
    # Wait on the DRAWER's dot, not the legend's. The legend swatch appears
    # the instant `listShowing` flips, while the drawer's rows render a beat
    # later - waiting on the swatch and then counting rows failed about one
    # run in three, and the failure read as "the drawer draws no dot", which
    # is a claim about the app rather than about this clause's timing.
    browser_page.wait_for_selector(".catalogue-drawer .cat-dot", timeout=15_000)
    got = browser_page.evaluate(
        """() => {
             const l = document.querySelector('.anat-legend');
             return { dot: !!l.querySelector('.cat-dot'),
                      rerun: !!l.querySelector('.anat-rerun'),
                      drawerDots: document.querySelectorAll(
                        '.catalogue-drawer .cat-dot').length };
           }""")
    assert got["dot"] and got["rerun"], (
        f"the open catalogue is missing its own key: {got}")
    assert got["drawerDots"] > 0, (
        "the drawer draws no dot, so the key that arrived with it keys "
        f"nothing after all: {got}")


@live
def test_the_shop_keeps_the_keys_because_the_shop_is_the_list(served, browser_page):
    """The overshoot this fix could have been, asserted rather than trusted.

    `?tab=findings` with no part open is `CatalogueList` standing on the page
    (`anatomy.tsx:3928`) rather than in a drawer. Every symbol the strip keys
    is drawn there, so the keys stay. A fix gated on the drawer alone passes
    the operator's report and fails here.
    """
    base, ids = served
    browser_page.goto(f"{base}/#/sites/{ids['site']}?tab=findings",
                      wait_until="load")
    # The ROWS, not the shop: `.catalogue-shop` mounts at once and its rows
    # arrive with the lanes a beat later, so waiting on the container and
    # counting the dots failed 2 runs in 4 under load - the race the drawer
    # clause above had and was fixed for, left standing in its sibling.
    browser_page.wait_for_selector(".catalogue-shop .cat-dot", timeout=15_000)
    got = browser_page.evaluate(
        """() => ({
             keys: [...document.querySelectorAll(
               '.anat-legend .cat-dot, .anat-legend .anat-rerun')].length,
             shopDots: document.querySelectorAll('.catalogue-shop .cat-dot').length,
             part: new URLSearchParams(
               location.hash.split('?')[1] || '').get('part') || '',
           })""")
    assert got["part"] == "", f"a part is open, so this is not the shop: {got}"
    assert got["shopDots"] > 0, (
        "the shop draws no dot, so this clause is asserting nothing about "
        f"whether the key is needed: {got}")
    assert got["keys"] > 0, (
        "the shop draws the symbols and the strip no longer keys them: item "
        f"197's fix has overshot the defect it was filed for ({got})")


# --- the branch that outlived its pane ---------------------------------------

#: Panes `LegendStrip` still branches on that no address can reach.
#:
#: `precheck` is dead by the same two mechanisms that killed `triage` -
#: `SIDEBAR_PANES` does not list it, and `paneFor` aliases the word to
#: `history` before any pane name is passed down - but it predates item 196
#: and was outside item 197. It is recorded here by name rather than
#: tolerated silently: while it sits in a set with a reason attached, the
#: NEXT dead branch cannot hide behind it. When it goes, this empties and
#: the clause below keeps working unchanged.
STILL_DEAD = {"precheck"}


def test_the_legend_branches_only_on_panes_an_address_can_reach():
    """The clause that would have caught the triage branch.

    Item 196 retired Triage as a step; its legend branch outlived it by a
    commit and nothing failed, because a branch that cannot be entered
    cannot be wrong. It was found by reading, which is not a method.

    Two independent things have to agree for a pane name to arrive here:
    `SIDEBAR_PANES` decides whether the strip is drawn at all, and `paneFor`
    decides what the `?tab=` word resolves to. A branch on a word neither
    produces is dead code wearing the shape of a feature.
    """
    lanes = (SRC / "legend_strip.tsx").read_text(encoding="utf-8")
    views = (SRC / "views.tsx").read_text(encoding="utf-8")

    branched = set(re.findall(r'pane === "(\w+)"', lanes))
    assert branched, "legend_strip.tsx branches on no pane at all any more"

    m = re.search(r"const SIDEBAR_PANES: readonly SidebarPane\[\] = \[([^\]]+)\]",
                  views)
    assert m, "views.tsx no longer declares which panes carry a legend strip"
    drawn = set(re.findall(r'"(\w+)"', m.group(1)))

    assert branched - drawn == STILL_DEAD, (
        "the legend strip branches on panes no address reaches: "
        f"{sorted((branched - drawn) - STILL_DEAD)}. `SIDEBAR_PANES` is "
        f"{sorted(drawn)} and `paneFor` resolves everything else away, so "
        "that branch cannot be entered - it is dead code in the shape of a "
        "feature, which is how the Triage key outlived Triage")

    assert "triage" not in branched, (
        "the triage branch is back; item 196 retired the pane and item 197 "
        "removed its key, and `TAB_ALIAS` still sends the word to `history`")
