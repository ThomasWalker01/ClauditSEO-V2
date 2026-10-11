"""A part says its own count under its name (item 273, row 12).

The part page counted cards, rows and checks, and nothing under the part's
name said the part's total - the figure the parts strip carries. The header
says it: "103 open · 5 seen once · 9 held".
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "anatomy.tsx"


def test_the_count():
    src = SRC.read_text(encoding="utf-8")
    head = src.split('<h2 className="part-h2">{current.label}</h2>', 1)[1][:1800]
    assert '<p className="part-count muted">' in head
    # The strip's figure since screen audits round 3 (Security IP-01): "8
    # open" sat under a chip reading 12, the four regressions unnamed.
    assert "{current.total.value} open" in head
    assert "of them back after a fix" in head
    assert 'entry("state-candidate").word' in head
    # Holds in checks, the tables' unit, with their source.
    assert "the analysis held ${heldChecks} check" in head


def test_the_table_names_a_regressed_row():
    """Screen audits round 3 (Security IP-01): the checks table read "open"
    on all twelve rows, four of them back after a fix."""
    part = (SRC.parent / "part_page.tsx").read_text(encoding="utf-8")
    assert 'seen.regressed = seen.regressed || s.state === "regressed";' in part
    assert 'regressed: s.state === "regressed",' in part
    assert ': counted.some((f) => f.regressed) ? entry("state-regressed").word : "open")' in part
