"""The re-run says the brief has changed (item 274, row 6).

Each analysis stores its brief's version (item 249), and the Analysis
heading reads "analysed under an earlier brief · re-run to apply". The
control that applies it said nothing; its title and its confirmation now do.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_control_and_its_confirmation_say_it():
    src = SRC.read_text(encoding="utf-8")
    assert "The brief has changed since this analysis was written: a re-run applies it" in src
    assert "The brief has changed since that analysis was written, and this run applies it." in src
