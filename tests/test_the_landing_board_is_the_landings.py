"""The landing's board is the landing's; every tab keeps the way between panes (item 200).

The operator, on a part page: "Should this information only show on the client
home screen details rather than on every page." `StandingHeader` drew the
landing's primary and secondary actions and the full two-chapter board on every
tab, so a part page began below the shell bar, the next-step buttons, the board
with its chapter captions, the pane head and the legend strip.

The actions are the landing's now. The strip stays on every tab - it is the
only way between Audit, Analyses, Record and Client report - and off the
landing it is the way and not the board: the same four pills in the same
order, with no chapter heads.
"""

from __future__ import annotations

from tests.needs_build import needs_build
from tests.parts import open_part
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)
from tests.test_the_client_landing_is_three_lanes import _page

READ = """() => ({
  buttons: document.querySelectorAll('.bl-buttons').length,
  heads: document.querySelectorAll('.seq-chapter-head').length,
  names: [...document.querySelectorAll('nav.seq-chapters .seq-name')].map((a) => a.textContent.trim()),
  hrefs: [...document.querySelectorAll('nav.seq-chapters .seq-name')].filter((a) => a.getAttribute('href')).length,
  current: document.querySelectorAll('nav.seq-chapters .seq-name[aria-current]').length,
  captions: document.querySelectorAll('.seq-chapter-state').length,
})"""


@needs_build
def test_a_part_page_keeps_the_way_and_not_the_board(served):
    base, ids = served

    def go(pg):
        landing = pg.evaluate(READ)
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
        pg.wait_for_selector(".anat-layout", timeout=15_000)
        open_part(pg, "Indexability & canonicals")
        pg.wait_for_timeout(500)
        return landing, pg.evaluate(READ)

    landing, part = _page(served, go)
    assert landing["buttons"] == 1 and landing["heads"] == 2, (
        f"the landing lost its board: {landing}")
    assert part["buttons"] == 0, f"a part page still carries the landing's actions: {part}"
    assert part["heads"] == 0, f"a part page still draws the board's chapter heads: {part}"
    # The channel (20260924-0220-200): the captions carried the hold count,
    # which is the landing's, and must go with the heads.
    assert part["captions"] == 0 and landing["captions"] == 2, (landing, part)
    assert part["names"] == landing["names"] and len(part["names"]) == 4, (
        f"the way between panes changed between the two renderings: {landing} / {part}")
    assert part["hrefs"] == 4, f"a destination on the part page is not a link: {part}"
    assert part["current"] == 1, f"the part page does not mark where the reader is: {part}"
