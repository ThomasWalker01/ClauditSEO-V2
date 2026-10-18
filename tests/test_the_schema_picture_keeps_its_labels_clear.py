"""The structured-data picture keeps its labels clear and keys what it
draws (item 270, row 14).

Edge labels sat on the cards they ran between, over the card's type, and the
key named four marks over a picture that drew two. A label that lands on a
card or an earlier label steps up a line, and the key names the marks the
model has.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "schema_graph.tsx"


def test_labels_and_key():
    src = SRC.read_text(encoding="utf-8")
    assert "for (let step = 0; step < 4 && hits(box); step++)" in src
    assert 'model.edges.some((e) => e.kind === "dangling")' in src
    assert "model.nodes.some((n) => n.island)" in src
