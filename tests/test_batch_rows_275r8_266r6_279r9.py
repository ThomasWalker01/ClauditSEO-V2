"""Three small rows (items 275 r8, 266 r6, 279 r9).

- 275 (row 8): a Fixes group line said "2 pages" over two cards on `/`. Where
  cards exceed pages it says both.
- 266 (row 6): "copy change" was drawn over "keep ..." and "class:
  convention ..." notes. It is drawn only over a change; a note reads as
  text under Change.
- 279 (row 9): Accessibility drew the measurement-band legend for bars that
  are three kinds of work. It draws those three words instead.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_three_rows_are_in_the_source():
    src = SRC.read_text(encoding="utf-8")
    assert "if (pages && cards.length > paths.size) return" in src
    assert 'copyLabel: "copy change", copyWhen: isChange },' in src
    assert 'const BAND_PARTS = new Set(["title-desc", "speed"]);' in src
    assert 'a11y: ["fix-kind-chrome", "fix-kind-template", "fix-kind-page"],' in src
