"""The terminal-axis canonical checks (item 137, brief v18 step BA).

canonical-to-404, canonical-loop and canonical-sitemap-conflict are crawl-state
facts about where a page's canonical chain ends, born TEC while the relation
checks stay ONP (channel 20260910-0830/0850). Held here, through the real ONP
and TEC modules sharing one node index:

  - a canonical to a 4xx target -> canonical-to-404 (TEC), and the ONP relation
    check for that page is suppressed (one finding per page);
  - a canonical loop -> canonical-loop (TEC);
  - a page in the sitemap whose canonical points at a page that is not ->
    canonical-sitemap-conflict (TEC), including where the relation is a mute
    variant;
  - a plain elsewhere canonical to a live page, not in the sitemap, keeps
    canonical-mismatch (ONP) — no terminal check.
"""

from __future__ import annotations

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Tier
from clauditseo.modules.onp import OnPageModule
from clauditseo.modules.tec import TechnicalModule

_H = ('<html><head><title>A page with a real title here</title>'
      '{canon}</head><body>a body with enough words to read as real content</body></html>')


def _page(path, status=200, canonical=None, content_type="text/html"):
    url = f"https://x.test{path}"
    canon = f'<link rel="canonical" href="https://x.test{canonical}">' if canonical else ""
    body = _H.format(canon=canon) if content_type == "text/html" else ""
    return Page(url=url, requested_url=url, status=status, content=body,
                content_type=content_type)


def _run(pages, sitemap=()):
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=list(pages),
                        sitemap_entries=[f"https://x.test{p}" for p in sitemap])
    ctx = {"crawl": crawl, "site": None}
    onp = {(f.check_id, f.subject) for f in OnPageModule().run(crawl.pages, Tier.T2, ctx)}
    tec = {(f.check_id, f.subject) for f in TechnicalModule().run(crawl.pages, Tier.T2, ctx)}
    return onp, tec


def test_a_canonical_to_a_404_is_canonical_to_404_and_suppresses_the_relation():
    onp, tec = _run([
        _page("/a", canonical="/dead"),        # canonical to a 4xx target
        _page("/dead", status=404, content_type="text/plain"),
        _page("/self"),                        # a clean self-canonical control
    ])
    assert ("canonical-to-404", "/a") in tec
    # The ONP relation check for /a is suppressed — one finding per page.
    assert ("canonical-mismatch", "/a") not in onp
    assert not any(c.startswith("canonical-") and s == "/a" for c, s in onp)


def test_a_loop_is_canonical_loop():
    onp, tec = _run([
        _page("/loop-a", canonical="/loop-b"),
        _page("/loop-b", canonical="/loop-a"),
    ])
    assert ("canonical-loop", "/loop-a") in tec
    assert ("canonical-loop", "/loop-b") in tec
    assert not any(c == "canonical-mismatch" for c, _ in onp)


def test_in_sitemap_canonicalising_to_a_page_not_in_it_is_sitemap_conflict():
    onp, tec = _run(
        [_page("/p", canonical="/q"), _page("/q")],   # /q is live and 200
        sitemap=["/p"])                               # only /p is declared
    assert ("canonical-sitemap-conflict", "/p") in tec
    assert ("canonical-mismatch", "/p") not in onp    # suppressed


def test_a_plain_elsewhere_not_in_sitemap_stays_canonical_mismatch():
    onp, tec = _run([_page("/p", canonical="/q"), _page("/q")])  # no sitemap
    assert ("canonical-mismatch", "/p") in onp
    assert not any(c in ("canonical-to-404", "canonical-loop",
                         "canonical-sitemap-conflict") for c, _ in tec)


def test_both_ends_in_the_sitemap_is_out_of_scope():
    # The sitemap lists both forms — a sitemap defect BA names no id for, left
    # out of scope deliberately (channel 20260910-0850). Not a sitemap-conflict.
    onp, tec = _run(
        [_page("/p", canonical="/q"), _page("/q")],
        sitemap=["/p", "/q"])
    assert not any(c == "canonical-sitemap-conflict" for c, _ in tec)
    # It is still an elsewhere canonical, so ONP keeps its relation finding.
    assert ("canonical-mismatch", "/p") in onp
