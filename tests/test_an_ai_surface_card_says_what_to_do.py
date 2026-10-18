"""An AI surface card says what to do (item 267, row 7).

The part's four HIGH cards, firewall blocks, carried the summary and nothing
else: the module's one actionable sentence reached no screen. The card now
draws the automatic check's advice, and a firewall block - a policy the
client may have chosen - links the field that records the choice, which the
next audit reads (a declared agent's row is Low, "the policy working").
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.modules import ais

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "ai_surface.tsx"


def test_the_card_draws_the_advice_and_links_the_choice():
    src = SRC.read_text(encoding="utf-8")
    assert '{fix.recommendation && !fix.replacement && (' in src
    assert "Admin › Sites › Blocked at the firewall on purpose" in src


def test_the_field_the_card_names_is_the_one_the_module_reads():
    import inspect
    assert "ai_edge_blocked_agents" in inspect.getsource(ais)
    admin = (SRC.parent / "admin.tsx").read_text(encoding="utf-8")
    assert "Blocked at the firewall on purpose" in admin
