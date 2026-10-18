"""Two small rows (items 267 r15, 279 r10).

- 267 (row 15): the analysis provenance line aged the analysis, not the crawl
  it read. It now reads "read the crawl of 18 Sept, measured 13 days ago".
- 279 (row 10): a merged fix-order step with one selector on several pages
  was labelled with the selector count ("Rewrite the 1 generic link text"
  over a bar of 2), and "after step 1: 35 left" wore the fixed tone. The
  label counts instances, and the projection a neutral tone.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_provenance_ages_the_crawl():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "read the crawl of {dayOf(brief.crawl_at)}" in page
    assert "<MeasuredAge iso={brief.crawl_at}" in page


def test_the_step_label_counts_instances():
    src = inspect.getsource(runs)
    assert 'if n == 1 and st.get("instances", 1) > 1:' in src
    assert runs._fix_label("link-text-generic", 2, [], "page") == "Rewrite the 2 generic link texts"
    order = (SRC / "a11y_fixorder.tsx").read_text(encoding="utf-8")
    assert '<Pill tone="count-info" className="fixorder-after"' in order
