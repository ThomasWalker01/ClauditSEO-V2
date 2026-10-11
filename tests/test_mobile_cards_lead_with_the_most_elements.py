"""Mobile cards lead with the most elements, under one roll-up (item 274,
row 9).

Twelve tap-target cards read in no particular order, and nothing said that
small targets on 12 of 12 traced pages across 11 of 12 templates is likely one
shared control. The cards sort by element count within a check, and the
group line says the shape.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_sorted_and_rolled_up():
    src = SRC.read_text(encoding="utf-8")
    assert "[...unsorted].sort((a, b) => elementCount(b) - elementCount(a))" in src
    assert ": likely one shared control" in src
    assert "export function elementCount(" in src
