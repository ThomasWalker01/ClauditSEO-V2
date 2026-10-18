"""A status card names the pages that link to the broken URL (item 275,
row 10).

`http-status-error` said "404 response at /x/" and "update internal links that
point at it", and named no page that does. The finding records the crawled
pages linking to it, and the card says them.
"""

from __future__ import annotations

from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Tier
from clauditseo.modules.tec import TechnicalModule
from clauditseo.persistence.runs import finding_targets


def _page(url, status=200, outlinks=()):
    p = Page(url=url, requested_url=url, status=status, content_type="text/html")
    p.outlinks = list(outlinks)
    return p


def test_linked_from():
    crawl = CrawlResult(start_url="https://t.co/", tier=list(Tier)[0], pages=[
        _page("https://t.co/", outlinks=["https://t.co/gone/"]),
        _page("https://t.co/about/", outlinks=["https://t.co/gone/"]),
        _page("https://t.co/gone/", status=404)])
    got = [f for f in TechnicalModule()._page_checks(crawl) if f.check_id == "http-status-error"]
    assert got and got[0].evidence["linked_from"] == ["/", "/about/"]
    assert finding_targets(got[0].evidence) == ["/", "/about/"]
