"""A title is graded as the check grades it (item 273, row 3).

The "now" card graded the title and description by a character range and
said "in range" over a 561 px title the length check had raised against the
410 px mobile cut. It reads the snippet's own verdict at the viewport the
check fires at, and the character minimum, and says the pixels.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_grade():
    src = SRC.read_text(encoding="utf-8")
    grade = src.split("export function lengthGrade", 1)[1].split("\n}\n", 1)[0]
    assert "const v = fired(f);" in grade
    assert "px · cut at ${v.limit_px} px on ${where}" in grade
    assert "chars · under ${f.min_chars}" in grade
    now = src.split("function TitleDescNow", 1)[1].split("\n}\n", 1)[0]
    assert now.count("lengthGrade(facts.snippet.") == 2
