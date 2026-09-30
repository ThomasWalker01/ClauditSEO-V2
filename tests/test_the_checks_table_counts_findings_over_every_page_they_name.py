"""The checks table counts findings, over every page they name (items 206, 208).

**206.** The operator, on Images: "only one result on the scan". The PAGES
cell counted each card's FIRST url, so a site-wide fault the engine files as
one finding over 31 pages (`img-logo`) read "1 of 45", while a check filing
one finding per page read 31. The card beneath already said 31.

**208.** Held rows (`needs`) were counted as findings - "ANALYSIS 2 · 2 of 45
pages crawled · not assessable" - and the two headings in one section used
one label for two numbers: "Free checks · 10" over the table counted every
check listed, "Free checks · 22" over Fixes counted cards.

The fixture holds the 206 shape on Crawl & sitemaps: `TEC/http-status-error`
is one finding naming 12 pages.
"""

from __future__ import annotations

import re

from tests.needs_build import needs_build
from tests.parts import open_part
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)
from tests.test_the_client_landing_is_three_lanes import _page

READ = """(check) => {
  const row = [...document.querySelectorAll('.checks-table tbody tr')]
    // A filed check's row prints its bare id, a brief's its full one.
    .find((r) => (r.querySelector('code')?.textContent.trim() || '').split('/').pop()
                 === check.split('/').pop());
  const heads = (sel) => [...document.querySelectorAll(sel)].map((h) => h.textContent.replace(/\s+/g, ' ').trim());
  return { pages: row ? row.querySelector('.check-prev').textContent.trim() : null,
           checks: heads('.checks-head'), fixes: heads('.fixes-head') };
}"""


def _part(served, label: str, check: str):
    base, ids = served

    def go(pg):
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
        pg.wait_for_selector(".anat-layout", timeout=15_000)
        open_part(pg, label)
        pg.wait_for_selector(".checks-table", timeout=15_000)
        states = pg.evaluate(f"async () => (await (await fetch('/api/sites/{ids['site']}')).json()).states")
        return states, pg.evaluate(READ, check)

    return _page(served, go)


def _named(states, check_id: str) -> int:
    paths = {re.sub(r"^https?://[^/]+", "", u).rstrip("/") or "/"
             for s in states if s["check_id"] == check_id and s["state"] in ("open", "regressed")
             for u in s["affected_urls"]}
    return len(paths)


@needs_build
def test_one_finding_over_many_pages_counts_every_page_it_names(served):
    for label, check, cid in (("Crawl & sitemaps", "TEC/http-status-error", "http-status-error"),):
        states, got = _part(served, label, check)
        want = _named(states, cid)
        assert want > 1, f"the fixture no longer has a multi-page {check}: {want}"
        assert got["pages"] and got["pages"].startswith(f"{want} "), (
            f"{check} names {want} pages and the PAGES cell reads {got['pages']!r}")


@needs_build
def test_the_two_headings_of_a_section_carry_one_number(served):
    """Checks with at least one finding, above the table and above Fixes."""
    _states, got = _part(served, "Crawl & sitemaps", "TEC/http-status-error")
    num = lambda h: int(re.search(r"· (\d+)", h).group(1))
    for word in ("Free checks", "Analysis"):
        table = [h for h in got["checks"] if h.startswith(word)]
        fixes = [h for h in got["fixes"] if h.startswith(word)]
        if table and fixes:
            assert num(table[0]) == num(fixes[0]), (
                f"'{word}' carries two numbers on one page: {table[0]!r} / {fixes[0]!r}")
            assert "card" in fixes[0], f"the card count is not said as cards: {fixes[0]!r}"
