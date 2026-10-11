"""A measurement band is defined where it is drawn (item 273, row 10).

Title & description's legend listed all five bands, "for information"
among them, over strips that draw within range, near the limit, past it and
not measured. The bands join the entries the legend reads off the block.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_bands_if_drawn():
    src = SRC.read_text(encoding="utf-8")
    assert "ifDrawn={[...PART_LEGEND_IF_DRAWN, ...(BAND_PARTS.has(part.key) ? BAND_LEGEND : [])]}" in src
    assert "<Legend ids={[...PART_LEGEND, ...(BAND_PARTS" not in src
