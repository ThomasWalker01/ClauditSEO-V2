"""The accounting counts holds as the checks table does (item 274, row 10).

Mobile's accounting read "3 checks could not be assessed" over a checks
table with two held rows: the third, `tap-target`, the analysis held where
the automatic checks raised it, and the table shows it open. The accounting
says the two apart.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_a_hold_on_a_raised_check_is_said_apart():
    src = SRC.read_text(encoding="utf-8")
    assert "const held = heldChecks.size - heldOnRaised;" in src
    assert "more held where the automatic checks" in src
