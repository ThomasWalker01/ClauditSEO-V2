"""A page reaches its fixes from the top (item 269, row 8).

In page mode Content's tab - the screenshot and its regions - ran some
thousand pixels above the cards, with nothing saying they were there. A
"Fixes (N)" control beside the tabs scrolls to them.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_jump():
    src = SRC.read_text(encoding="utf-8")
    tabs = src.split("function ContentTabs", 1)[1].split("\n}\n", 1)[0]
    assert "Fixes ({fixes.length})" in tabs
    assert 'getElementById("part-fixes")' in tabs
    assert '<section className="part-fixes" id="part-fixes" ref={wrap}>' in src
