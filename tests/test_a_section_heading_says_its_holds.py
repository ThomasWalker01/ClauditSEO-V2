"""A section heading says its holds (item 275, row 15).

"Analysis · 0" stood over a table of two held rows, and read as nothing
there. Where a section holds checks, the heading reads "Analysis · 0 open ·
2 held".
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_heading_counts_holds():
    src = SRC.read_text(encoding="utf-8")
    assert 'return heldN ? ` open · ${heldN} held in this table` : "";' in src
