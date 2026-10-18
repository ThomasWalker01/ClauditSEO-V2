"""Eligibility groups by rich result and verdict (item 270, row 9).

"Across the site" drew 24 eligibility lines for 45 pages: grouped on (rich
result, verdict, reason), and the model wrote a different reason per page.
It groups on (rich result, verdict), says the count in the line, and lists
each page's reason under the disclosure.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_reason_is_not_in_the_key():
    src = SRC.read_text(encoding="utf-8")
    block = src.split("function SchemaSiteNow", 1)[1].split("\n}\n", 1)[0]
    assert "const key = [rich, e.verdict.toLowerCase()].join(" in block
    assert "<summary>which, and why</summary>" in block
