"""A length strip draws its cut and counts what fits (item 273, row 9).

The strip named its cut above the bars and drew none; its foot read "first
crawled … last crawled", a constant with no dates; and its counts were over,
short and missing, which did not sum to the pages drawn. The cut is a dashed
line at its height with its figure, the constant is gone, and the counts
include the pages that fit.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "title_snippet.tsx"


def test_the_strip():
    src = SRC.read_text(encoding="utf-8")
    assert "first crawled" not in src
    assert '<span className="strip-fit">{fit} fit</span>' in src
    assert 'className="strip-cutline" aria-hidden="true"' in src
