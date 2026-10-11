""""Counted the problems" only where there are problems (item 278, row 6).

A part no analysis has read said "The automatic checks counted the problems;
no specialist has read them" over a table of coverage notes - Backlinks, with
nothing to fix. The sentence now reads the causes: a count above Info, or
"found nothing to fix".
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "anatomy.tsx"


def test_the_sentence_reads_the_causes():
    src = SRC.read_text(encoding="utf-8")
    assert 'causesOf(current).some((c) => c.count > 0 && c.severity !== "info")' in src
    assert "found nothing to fix on this part; no specialist has read it." in src
