"""Each answer says what it is about and what it does (item 267, row 9).

A part with four cards to confirm read "Confirm, Accept, Withdraw" twelve
times to a screen reader, with nothing naming which card each answered, and
nothing on the card said what the three do.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_each_button_is_named_by_its_card_and_the_three_are_explained():
    tc = (SRC / "to_confirm.tsx").read_text(encoding="utf-8")
    assert "label={named(entry(\"confirm\").word)}" in tc
    assert "label={named(entry(\"withdraw\").word)}" in tc
    assert "Confirm opens it as a fault; Accept keeps it as a risk you live with; " in tc
    for name in ("part_page.tsx", "pane_record.tsx", "dossier.tsx"):
        src = (SRC / name).read_text(encoding="utf-8")
        calls = src.count("<ConfirmControls ")
        assert calls and src.count("subject={`") >= calls, (name, calls)
