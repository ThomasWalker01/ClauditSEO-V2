"""The Links part's hub map says it is the analysis's, and of which crawl.

Screen audits round 3, Links AC-02 (High): the Hubs table is the model's
`brief_hubs` from an analysis of 23 Sept reading the 18 Sept crawl, drawn
directly under "What is drawn below was measured 3 Oct" with no source or date
of its own - a 16-day-old model reading presented as the current measurement.
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"


def test_the_hub_table_carries_its_own_source_line():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    start = page.index("function LinksSiteNow(")
    body = page[start:page.index("\n}\n", start)]
    assert "part.brief_runs" in body, "the hub map reads no analysis run to date it by"
    assert "From the analysis of {dayOf(by.at)}" in body
    assert "reading the crawl of ${dayOf(by.crawl_at)}" in body
    assert "not\n          the automatic checks" in body
    # Drawn before the table, where the reader meets the figures.
    assert body.index("links-hubs-source") < body.index("<table")
