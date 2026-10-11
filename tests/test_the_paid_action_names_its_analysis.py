"""The paid action names its analysis and its scope (item 269, row 5).

Content has four analyses writing to it, and "Re-run analysis · this page"
named neither which one runs nor the scope it runs over: the request is
posted against the part's reference crawl with no page in it. The button now
names the analysis it runs, priced from that one, says "this audit, all
pages" in page mode, and names the others writing to the part.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_button_names_its_tool_and_true_scope():
    src = SRC.read_text(encoding="utf-8")
    assert 'const briefScope = page ? "this audit, all pages" : "this audit";' in src
    assert '${tool ? `${tool} analysis` : "analysis"} · ${briefScope}' in src
    assert "Also writing here: {others.join(\", \")}" in src
