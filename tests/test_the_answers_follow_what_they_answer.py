"""The answers follow what they answer (item 270, row 10).

A card's Confirm / Accept / Withdraw stood above its Now and Replace with,
so a reader answered before reading what the finding said. They follow the
body.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_controls_after_the_body():
    src = SRC.read_text(encoding="utf-8")
    card = src.split("function FixCard", 1)[1].split("\n}\n", 1)[0]
    assert card.index("<render.body fix={fix} facts={facts} />") < card.index("<ConfirmControls")
