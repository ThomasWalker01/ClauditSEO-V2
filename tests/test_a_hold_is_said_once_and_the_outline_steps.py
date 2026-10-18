"""Title & description says a hold once and steps its headings (item 273,
row 13).

In page mode the alignment hold was a badge on the title and a full card 55
lines below; and the outline went from the part's h2 straight to h4. The
badge gives way where the card stands, and the two blocks are h3.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_once_and_h3():
    src = SRC.read_text(encoding="utf-8")
    now = src.split("function TitleDescNow", 1)[1].split("\n}\n", 1)[0]
    assert 'fixes.some((f) => f.checkId === "title-entity-alignment" && f.needs)' in now
    assert "<h3>What the page has now</h3>" in now
    assert "<h3>Every page&rsquo;s length</h3>" in src
