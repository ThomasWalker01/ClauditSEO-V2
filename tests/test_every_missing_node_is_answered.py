"""Every Missing node on the map is answered (item 269, row 12).

The topical map drew 13 Missing nodes and the analysis wrote rows for some
of them; the rest were holes on the map that nothing on the page answered.
The Coverage prompt now requires a row or a named skip for each.
"""

from __future__ import annotations

from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1] / "clauditseo" / "prompts" / "content-coverage.md"


def test_the_rule():
    text = PROMPT.read_text(encoding="utf-8")
    assert "Every Missing node in `map` gets a row, or a named skip" in text
    assert "`skip: service › node: <why it is not worth a page>`" in text
