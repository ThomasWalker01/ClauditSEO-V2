"""Cards stand in the analysis's rollout order (item 276, row 8).

Security's analysis numbers its changes in the order they should be made.
The cards sorted by severity, so the Order lines read 2, 11, 12, 4, 1, 6 ...
down the page. Where every card a section counts carries an order, the
section is read in it; anywhere one does not, severity stays the order.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_a_section_with_a_rollout_order_is_read_in_it():
    src = SRC.read_text(encoding="utf-8")
    # Any placed card switches it on; an unplaced card follows the placed
    # ones (it read none on twenty22, where one Info card had no place).
    assert 'const byRollout = placed.some((f) => typeof f.rollout?.order === "number");' in src
    assert "Number.MAX_SAFE_INTEGER" in src
    assert ".sort(([, a], [, b]) => firstOrder(a) - firstOrder(b))" in src
