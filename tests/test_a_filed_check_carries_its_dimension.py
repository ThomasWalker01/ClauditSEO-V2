"""A filed check carries its dimension in the table (item 277, row 16).

The checks table drew the brief's checks as `TEC/noindex-linked` and a check
the engine filed that no brief names as bare `canonical-missing`, one table
with two spellings. The filed row takes its dimension from its findings.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_prefixed():
    src = SRC.read_text(encoding="utf-8")
    assert "part.findings.find((f) => f.check_id === id)?.dimension" in src
    assert "tableChecks.push(dim ? `${dim}/${filed}` : filed);" in src
