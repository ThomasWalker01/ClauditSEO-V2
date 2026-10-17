"""Content's page actions (screen audits round 4, Content UX-02, UX-03):
"Write a brief for this page · no estimate yet" stood beside a priced
Re-run, and "Fixes (11)" scrolled and left focus on the button.
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_write_a_brief_is_priced_as_the_rerun_is():
    p = SRC.read_text(encoding="utf-8")
    assert "return b?.est_cost_default ?? b?.est_cost ?? null;" in p


def test_the_fixes_jump_moves_focus():
    p = SRC.read_text(encoding="utf-8")
    assert 'el.focus({ preventScroll: true });' in p
