"""An axe rule is counted over the pages the rendered pass visited (item 279).

The checks table counted every check over the crawl. Accessibility's axe
rules are read only on rendered pages, so `axe-color-contrast` - found on
every one of the 5 pages the rendered pass visited - read "5 of 45 pages
crawled", an 11% problem, beside the waterfall's "of 5 pages rendered".
Static checks (`link-name-missing`) keep the crawl.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_an_axe_row_is_counted_over_the_rendered_pages():
    src = SRC.read_text(encoding="utf-8")
    start = src.index("function ChecksTable(")
    body = src[start:src.index("\n}\n", start)]
    assert 'checkId.startsWith("axe-") && rendered > 0 ? { n: rendered, basis: "rendered" }' in body
    # Item 274: a trace-derived check over the traced pages, the same way.
    assert 'tracedChecks.has(checkId) && tracedN > 0 ? { n: tracedN, basis: "traced" }' in body
    # Everything else still reads the crawl.
    assert ": prevalence(named, pops, siteScope);" in body
