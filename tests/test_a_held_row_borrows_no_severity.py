"""A held row borrows no severity (items 277 and 273, row 13).

A check whose only rows were holds drew an Info pill in the Severity column:
the hold's own "info", not the check's registered severity. The cell is a
dash, and the State column says the hold.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_dash():
    src = SRC.read_text(encoding="utf-8")
    assert 'held: state.startsWith("not assessable")' in src
    assert "<td>{r.held" in src
