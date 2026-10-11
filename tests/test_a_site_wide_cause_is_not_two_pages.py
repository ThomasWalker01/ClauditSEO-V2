"""A site-wide cause is not a fault on an analysis's pages (item 278, row 9).

Local's one cause showed the automatic checks' sentence, "LocalBusiness
schema present but without opening hours.", filed site-wide with no page,
while its PAGES cell read "2 of 45 pages crawled": the analysis candidate's
two URLs, from an older crawl, unioned under the sweep's sentence. The cell
now reads "site · analysis names 2 pages".
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "anatomy.tsx"


def test_the_cell_follows_the_sentence_shown():
    src = SRC.read_text(encoding="utf-8")
    assert "&& sweepRows.every((st) => !st.affected_urls.length);" in src
    assert "const urls = g.siteWide ? []" in src
    assert "` · analysis names ${cause.analysisPages} page" in src
