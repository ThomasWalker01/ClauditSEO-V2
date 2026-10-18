"""The Fixes heading counts cards only (item 270, row 7).

The checks table read "Free checks · 13" and "Analysis · 5"; Fixes read
"Free checks · 8" and "Analysis · 9". Counted by the table's cost rule it
still read 10 under 11 on twenty22, because one replacement folds
`schema-redundant-block` into a card under another check's id. The row's
second option: the Fixes heading says its cards, and the table its checks.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_fixes_heading_says_cards_only():
    src = SRC.read_text(encoding="utf-8")
    head = src.split('className={`fixes-head fixes-head-${section}`}', 1)[1].split("</h4>", 1)[0]
    # Holds are said apart from cards (screen audits round 4, Headings r3
    # IP-02: "20 cards" over four cards and sixteen hold lines).
    assert "· {mine.length} card{" in head
    assert "{held.length} held" in head
    assert "mine.length + held.length" not in head
    assert "new Set(" not in head
