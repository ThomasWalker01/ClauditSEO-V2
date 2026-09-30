"""A record chip counts the rows its press will show (item 201).

The operator, on twenty22's Record: "analysis shows 15 as a number but
nothing is present when filtered." Each chip counted over every state row,
while the table applied every filter at once; all fifteen analysis rows were
`candidate` and "Open + regressed" was pressed, so the chip promised rows its
press could not show. The comment above the count said this was deliberate -
"a chip says what the set holds, not what the other filters left of it" - and
the operator's report is the case where that reads as a broken filter.

Now each row of chips counts within the OTHER rows' selection. The invariant,
walked over every chip the fixture's record draws with another row's filter
set: the number on a chip at the moment it is pressed is the number of rows
the table then shows.
"""

from __future__ import annotations

import re

from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)
from tests.test_the_client_landing_is_three_lanes import _page

SHOWN = """() => { const t = document.querySelector('.record-shape > span.muted').textContent;
                   const m = t.match(/(\d+) findings?/) || t.match(/^(\d+) of/);
                   return m ? Number(m[1]) : -1; }"""
CHIPS = """(row) => [...document.querySelectorAll(`.${row} .chip`)].map((c) => ({
  key: c.dataset.state || c.dataset.severity || c.dataset.cost,
  n: Number((c.querySelector('.tone')?.textContent || c.textContent.match(/(\d+)\s*$/)?.[1] || '-1').trim()),
  pressed: c.getAttribute('aria-pressed') === 'true' }))"""
ATTR = {"state-filters": "state", "severity-filters": "severity", "cost-filters": "cost"}


@needs_build
def test_every_chip_shows_what_its_press_will_show(served):
    base, ids = served

    def go(pg):
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&state=outstanding", wait_until="load")
        pg.wait_for_selector(".state-filters .chip", timeout=15_000)
        pg.wait_for_timeout(500)
        wrong, walked = [], 0
        for row in ("state-filters", "severity-filters", "cost-filters"):
            for chip in pg.evaluate(CHIPS, row):
                if chip["pressed"] or chip["n"] < 0:
                    continue
                sel = f'.{row} .chip[data-{ATTR[row]}="{chip["key"]}"]'
                pg.click(sel)
                pg.wait_for_timeout(250)
                shown = pg.evaluate(SHOWN)
                walked += 1
                if shown != chip["n"]:
                    wrong.append((row, chip["key"], chip["n"], shown))
        return wrong, walked

    wrong, walked = _page(served, go)
    assert walked >= 6, f"only {walked} chips were pressed; the fixture draws too few to prove this"
    assert not wrong, (
        "a chip promised rows its press did not show (row, chip, said, shown): "
        f"{wrong}")
