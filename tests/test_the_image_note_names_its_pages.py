"""The image chart note names its page population (item 272, row 8).

"Weighed on 40 of 48 pages" sat on a screen whose header read 45 crawled
pages. The 48 is the pages with a stored snapshot; the note says so.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "images_budget.tsx"


def test_the_note_names_its_population():
    assert "pages with a stored snapshot." in SRC.read_text(encoding="utf-8")
