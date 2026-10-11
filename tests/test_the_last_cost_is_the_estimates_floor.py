"""The last recorded cost is the estimate's floor (item 276 row 11; 268
row 10; 270 row 17; 275 row 15).

The paid button quoted the median over every site's runs; the last run of the
same analysis on this site cost more, so the quote was a figure the operator
had already paid past. The price shown is the larger, and the line says which
it is.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_floor():
    src = SRC.read_text(encoding="utf-8")
    assert "const floored = lastCost != null && (median == null || lastCost > median);" in src
    assert "const estCost = floored ? lastCost : median;" in src
    assert '" what the last run here cost"' in src
