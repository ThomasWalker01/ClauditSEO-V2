"""A part no analysis writes to draws no analysis furniture (item 279, row 8).

Accessibility carried an ANALYSIS column of dashes and a disabled "$" button
for an analysis the catalogue does not offer. Where no analysis is catalogued
for the part and no row came from one, the column is not drawn and the
reason stands in place of the button.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_column_and_the_button_follow_the_catalogue():
    src = SRC.read_text(encoding="utf-8")
    assert "const analysisCol = part.catalogued !== false || rows.some((r) => r.brief > 0);" in src
    assert '{analysisCol && <th className="num">Analysis</th>}' in src
    assert "{part.catalogued === false && !brief ? (" in src
