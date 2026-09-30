"""The layout of last resort, for rendered tests (brief v25 step BP).

Crawl & sitemaps, Indexability & canonicals, URLs & parameters and Speed moved
to the three-block part page. The across-the-site layout they left still
serves Accessibility, AI surface, Backlinks and Local & citations, and its
machinery - the cause table and its templates, the tick and the mark bar, the
re-audit drawer, section refresh, the count lists - is still product code. But
the sweep's fixture holds no page-level finding in any of those four parts, so
the tests that guard that machinery had nothing to drive.

`on_the_layout_of_last_resort(page)` names the fixture parts that DO carry
findings, and the anatomy screen draws them on the old layout for that page
only (`window.__CLAUDITSEO_LAST_RESORT__`, read in `anatomy.tsx`). Nothing in
the product sets it. Their three-block pages are swept by their own routes in
`test_a11y_rendered.py`.
"""

from __future__ import annotations

#: AI surface joined at item 145 step BH, when it took its three-block page:
#: its `llms-txt-missing` is the fixture's page-less row the cause-table and
#: population clauses drive.
PARTS = ("crawl", "indexability", "urls", "speed", "ai-surface")

SCRIPT = "window.__CLAUDITSEO_LAST_RESORT__ = %s;" % list(PARTS)


def on_the_layout_of_last_resort(page) -> None:
    """Before the page's first navigation: an init script runs on every load."""
    page.add_init_script(SCRIPT)
