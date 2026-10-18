"""The image chart stays in its frame and says one byte (item 272, row 12).

The budget label ran along the flat ceiling over the dots, the band ran
below the floor where nothing is scored, the largest dot sat on the frame's
edge, and the note read "1 bytes a pixel".
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "images_budget.tsx"


def test_the_chart():
    src = SRC.read_text(encoding="utf-8")
    assert "bytes_per_pixel} bytes" not in src
    assert '${n === 1 ? "byte" : "bytes"}' in src
    assert "${R},${ly(budget.floor_kb)}" in src and "${R},${B}" not in src
    assert "Math.min(lx(d.w * d.h), R - 6)" in src
    assert 'x={lx(flatAt) - 6} textAnchor="end"' in src
