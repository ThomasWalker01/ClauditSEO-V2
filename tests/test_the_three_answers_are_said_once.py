"""The three answers are said once per page (item 266, row 5).

Item 267 (row 9) put "Confirm opens it as a fault; Accept keeps it as a risk
you live with; Withdraw takes it back." under every card's three buttons; on
a part with ten cards waiting, it read ten times. The part page says it once
above the cards, and the legend carries the three ids.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_said_once_on_the_part_page():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert page.count("explain={false}") == 2
    assert '<p className="muted fix-meta">{CONFIRM_SAYS}</p>' in page
    confirm = (SRC / "to_confirm.tsx").read_text(encoding="utf-8")
    assert 'export const TO_CONFIRM_LEGEND = ["to-confirm", "confirm", "accept", "withdraw"];' in confirm
