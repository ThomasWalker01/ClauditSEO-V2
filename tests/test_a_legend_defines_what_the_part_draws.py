"""A part's legend defines what the part draws (item 268 row 8, item 270
row 16).

Every part's legend listed all five severities, "seen once" and "not
measured", whether or not a row on the part carried them. Structured data
defined Critical with no critical row on it. Those seven are now defined only
where the block draws them, read off the block as it renders; and each of the
three answers carries its registry sentence as a title.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_shared_list_holds_only_what_every_part_draws():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    shared = re.search(r"const PART_LEGEND = \[(.+?)\];", page, re.S).group(1)
    for gone in ("sev-critical", "state-candidate", "not-assessed"):
        assert f'"{gone}"' not in shared, gone
    # Item 273 (row 10): the bands join the drawn-only entries.
    assert "ifDrawn={[...PART_LEGEND_IF_DRAWN," in page


def test_the_legend_reads_the_block():
    src = (SRC / "glossary.tsx").read_text(encoding="utf-8")
    legend = src.split("export function Legend", 1)[1].split("\n}\n", 1)[0]
    assert "MutationObserver" in legend and "drawnIn(scope, legend, id)" in legend


def test_each_answer_says_what_it_does():
    src = (SRC / "to_confirm.tsx").read_text(encoding="utf-8")
    for word in ("confirm", "accept", "withdraw"):
        assert f'title={{entry("{word}").full}}' in src, word
