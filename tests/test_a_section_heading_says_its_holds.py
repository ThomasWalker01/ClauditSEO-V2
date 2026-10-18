"""A section heading says its holds (item 275, row 15).

"Analysis · 0" stood over a table of two held rows, and read as nothing
there. Where a section holds checks, the heading reads "Analysis · 0 open ·
2 held".
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_heading_counts_holds():
    src = SRC.read_text(encoding="utf-8")
    assert 'return word + (heldN ? ` · ${heldN} held in this table` : "");' in src
    assert ': heldN ? " open" : "";' in src


def test_rows_waiting_on_the_operator_are_to_confirm_not_open():
    """Screen audits round 4 (Headings, r3 IP-06): "4 open" over four rows
    the STATE column called "to confirm"."""
    src = SRC.read_text(encoding="utf-8")
    assert 'r.state === candidateWord(true)' in src
    assert 'waiting && waiting === n ? " to confirm"' in src
