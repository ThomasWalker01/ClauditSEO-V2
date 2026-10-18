"""The Mobile table says a shared viewport once (item 274, row 14).

Twelve templates repeated one viewport tag twelve times in a column, and
Overflow printed a bare "0". A viewport every template shares is said once
above the table, and Overflow reads in pixels throughout.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_once_above_and_pixels():
    src = SRC.read_text(encoding="utf-8")
    block = src.split("function MobileNow", 1)[1].split("\n}\n", 1)[0]
    assert "Viewport on every template:" in block
    assert "{`${t.overflow_px ?? 0} px`}" in block
