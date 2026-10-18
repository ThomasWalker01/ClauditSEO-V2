"""A page with no canonical is a line, and the key names what is drawn
(item 277, row 11).

At site scope every page with no canonical drew a chain card of one dot
reading "no canonical", four of them on twenty22 above the chains that go
somewhere, and the key named all four kinds over a grid that drew two.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "canonical_chains.tsx"


def test_the_block():
    src = SRC.read_text(encoding="utf-8")
    assert 'const missing = chains.chains.filter((c) => c.relation === "missing");' in src
    assert "<Legend kinds={drawn.map((c) => c.kind)} />" in src
    assert "LEGEND.filter(([kind]) => kinds.includes(kind))" in src
