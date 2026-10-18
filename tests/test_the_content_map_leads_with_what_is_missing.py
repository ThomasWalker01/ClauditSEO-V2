"""The content map leads with what is missing, and shows all on request
(item 269, row 12).

The topical map drew its first ten rows in the model's order and said "38
more not shown" with nothing to show them. Missing nodes come first, and a
control shows all, as Fixes opens its groups.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_missing_first_and_show_all():
    src = SRC.read_text(encoding="utf-8")
    block = src.split("function ContentMap", 1)[1].split("\n}\n", 1)[0]
    assert '=== "missing"' in block
    assert "`show all ${rows.length}`" in block
