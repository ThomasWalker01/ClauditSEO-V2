"""The landing's "Outstanding in the record" figure and the sentence under it
count one population.

Screen audits round 3, landing IP-02 (High): `Outstanding in the record 496`
over `591 open and 13 regressed across every audit`. The figure is the parts'
sum - one per card (item 276) and without rows a newer reading overtook (item
270) - and the sentence was `standing_by_state`'s rows. 591 + 13 is 604, not
496. AC-04, page mode: `43 open` under `Regressed on this page 11`, because
the regressed clause was dropped on one page and every row printed as open.

The split now comes from the parts, the figure's own population, and where
the record's door lists a different number of rows the sentence says so and
why (AC-03) instead of leaving the reader to find it behind the door.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"
LANES = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")


def _outstanding_block() -> str:
    start = LANES.index("if (outstanding > 0) {")
    return LANES[start:LANES.index('key: "outstanding"', start)]


def test_the_split_is_the_parts_not_the_records_rows():
    block = _outstanding_block()
    assert "const open = outstanding - regressed;" in block, (
        "the open count is not the figure less the parts' regressed")
    assert not re.search(r"const open = .*current\?\.open", block), (
        "the sentence still reads standing_by_state's open rows under the parts' sum")
    assert 'const back = regressed > 0' in block, (
        "the regressed clause still depends on page mode or the record's rows")


def test_a_differing_row_count_is_said_with_its_reason():
    block = _outstanding_block()
    assert "current.open + current.regressed" in block
    assert "The record lists ${rows} rows" in block
    assert "one card here" in block and "overtook" in block
    # And the note rides on the sentence the figure carries.
    assert "+ rowsNote" in LANES
