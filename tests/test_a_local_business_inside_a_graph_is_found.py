"""Item 233 (Local & citations, change 2): a LocalBusiness inside a
`@graph` is found.

`loc.py` read only top-level JSON-LD items. Yoast and most CMS plugins emit
every node inside one `@graph`, so the top level carries no `@type` - and on
twenty22 the part's one finding said "No LocalBusiness structured data found
on any crawled page" over the `#local_business` node on /contact-us/ that
the Structured data part itself reads. It now descends the graph the way
`pagefacts.schema_inventory` does. (Change 1 was item 218.)
"""

from __future__ import annotations

import json

from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Tier
from clauditseo.modules.loc import LocalModule

BASE = "https://graph.fixture"


def _ids(jsonld: dict) -> set[str]:
    html = ("<html lang='en-AU'><head><title>Contact</title>"
            f"<script type='application/ld+json'>{json.dumps(jsonld)}</script></head>"
            "<body><main><h1>Contact</h1><p>Call 02 9000 0000, 1 Street, Sydney NSW 2000.</p>"
            "</main></body></html>")
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2, pages=[
        Page(url=BASE + "/contact-us/", requested_url=BASE + "/contact-us/", status=200,
             content_type="text/html", content=html)])
    return {f.check_id for f in LocalModule().run(list(crawl.pages), Tier.T2, {"crawl": crawl})}


GRAPH = {"@context": "https://schema.org", "@graph": [
    {"@type": "WebPage", "@id": BASE + "/contact-us/#webpage"},
    {"@type": "LocalBusiness", "@id": BASE + "/#local_business", "name": "Graph Co",
     "openingHours": "Mo-Fr 09:00-17:00"}]}


def test_a_graph_node_is_read():
    got = _ids(GRAPH)
    assert "localbusiness-schema-missing" not in got, got
    assert "opening-hours-missing" not in got, got


def test_a_graph_without_one_still_raises():
    got = _ids({"@context": "https://schema.org",
                "@graph": [{"@type": "WebPage", "@id": BASE + "/#webpage"}]})
    assert "localbusiness-schema-missing" in got, got


def test_a_top_level_node_is_still_read():
    got = _ids({"@context": "https://schema.org", "@type": "Dentist", "name": "Top"})
    assert "localbusiness-schema-missing" not in got, got
