"""Content's page view keeps its summary and caps its picture (item 269,
row 8).

On page mode the screenshot of a long page ran thousands of pixels between
the summary line and the region list and cards. It sits in a 900 px box
that scrolls (focusable, so a keyboard reaches it), and the summary counts
the thin regions.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_capped_and_counted():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert '<div className="tp-overlay-cap" tabIndex={0} role="region"' in page
    assert "thin region" in page
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    assert ".tp-overlay-cap { max-height: 900px; overflow-y: auto; }" in css
