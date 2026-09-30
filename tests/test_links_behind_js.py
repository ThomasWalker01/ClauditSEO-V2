"""`TEC/links-behind-js` — the link surface after the page renders.

Item 136q commit 2. Distinct from `TEC/js-rendering`, which asks whether the
page renders at all; this asks what the rendered DOM links at that the
initial HTML does not.

**The item said the rendered pass already stored an anchor set. It did not** —
`axe.py` stored axe violations, rects and screenshots and nothing else, so the
check was specified against an input that did not exist. The commit creates
it, in the `page.evaluate` that was already running.
"""

from __future__ import annotations

from clauditseo.crawler.types import CrawlResult, Page, Tier
from clauditseo.engine.types import Site
from clauditseo.modules.tec import TechnicalModule
from clauditseo.crawler.crawl import extract_link_details

BASE = "https://js.test"


def _page(path: str, body_html: str) -> Page:
    page = Page(url=BASE + path, requested_url=BASE + path, status=200,
                content_type="text/html; charset=utf-8",
                content=f"<html><body>{body_html}</body></html>")
    page.link_details = extract_link_details(page)
    page.outlinks = [l["url"] for l in page.link_details]
    return page


def _run(pages, rendered, seen, total):
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend(pages)
    ctx = {"crawl": crawl, "site": Site(domain="js.test"),
           "rendered_anchors": rendered,
           "rendered_coverage": {"rendered": seen, "pages": total}}
    return [f for f in TechnicalModule().run(list(crawl.pages), Tier.T2, ctx)
            if f.check_id == "links-behind-js"]


def test_render_only_link_counts():
    """A per-page fact, sound on any page the rendered pass visited."""
    pages = [_page("/", "<a href='/a'>A</a>"), _page("/a", "<p>a</p>")]
    got = _run(pages, {BASE + "/": [{"url": BASE + "/a", "anchor": "A"},
                                    {"url": BASE + "/hidden", "anchor": "More"}]},
               seen=2, total=2)
    assert len(got) == 1, got
    assert got[0].evidence["render_only"] == 1, got[0].evidence


def test_orphaned_destination_named():
    """Site-wide, and only where the whole crawl was rendered."""
    pages = [_page("/", "<a href='/a'>A</a>"), _page("/a", "<p>a</p>")]
    got = _run(pages, {BASE + "/": [{"url": BASE + "/hidden", "anchor": "More"}]},
               seen=2, total=2)
    ev = got[0].evidence
    assert ev["orphaned_without_js"] == 1, ev
    assert ev["destinations"] == [
        {"url": BASE + "/hidden", "first_reachable_via": "render only"}], ev
    assert got[0].severity.value == "high", got[0].severity


def test_a_destination_the_initial_html_reaches_elsewhere_is_not_orphaned():
    """Reachable by ANY initial-HTML path from ANY page. A link this page
    only renders is still reachable if another page links it in its HTML."""
    pages = [_page("/", "<a href='/a'>A</a>"),
             _page("/a", "<a href='/deep'>deep</a>"),
             _page("/deep", "<p>d</p>")]
    got = _run(pages, {BASE + "/": [{"url": BASE + "/deep", "anchor": "Deep"}]},
               seen=3, total=3)
    ev = got[0].evidence
    assert ev["orphaned_without_js"] == 0, ev
    assert ev["destinations"][0]["first_reachable_via"] == "initial html: /a", ev
    assert got[0].severity.value == "medium", got[0].severity


def test_a_partial_sample_will_not_make_a_site_wide_claim():
    """The operator's ruling of 2026-09-08, and the reason for it.

    With five of twelve pages rendered, a destination that looks render-only
    from the sample may be linked in the initial HTML of one of the seven
    that were not. `render_only` still emits - it is about this page - and
    the two site-wide fields say which question they cannot answer and why.
    No bounded restatement: a hedged site claim still reads as a site answer.
    """
    pages = [_page("/", "<a href='/a'>A</a>"), _page("/a", "<p>a</p>")]
    got = _run(pages, {BASE + "/": [{"url": BASE + "/hidden", "anchor": "More"}]},
               seen=1, total=2)
    ev = got[0].evidence
    assert ev["render_only"] == 1, ev
    assert "orphaned_without_js" not in ev, ev
    assert "destinations" not in ev, ev
    assert "1 of 2 pages" in ev["rendered_coverage"], ev
    assert "orphaned" in ev["not_assessable"]["orphaned_without_js"]
    # MEDIUM on `render_only` alone: HIGH depends on orphaned being
    # assessable, and here it is not.
    assert got[0].severity.value == "medium", got[0].severity


def test_unrendered_page_is_not_assessable():
    """A page the rendered pass never visited gets no row at all - not a
    clean one. The map holds only what was rendered."""
    pages = [_page("/", "<a href='/a'>A</a>"), _page("/a", "<p>a</p>")]
    got = _run(pages, {BASE + "/": [{"url": BASE + "/a", "anchor": "A"}]},
               seen=1, total=2)
    assert [f.affected_urls for f in got] == [], got


def test_no_rendered_pass_says_nothing():
    """A run without the rendered pass - every run taken before this item -
    emits nothing rather than reporting every page as clean."""
    pages = [_page("/", "<a href='/a'>A</a>")]
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend(pages)
    got = [f for f in TechnicalModule().run(list(crawl.pages), Tier.T2,
                                            {"crawl": crawl, "site": Site(domain="js.test")})
           if f.check_id == "links-behind-js"]
    assert got == [], got


def test_an_external_link_is_not_a_render_only_internal_link():
    pages = [_page("/", "<p>x</p>")]
    got = _run(pages, {BASE + "/": [{"url": "https://elsewhere.test/x",
                                     "anchor": "Out"}]}, seen=1, total=1)
    assert got == [], got


def test_the_producer_runs_before_its_consumer():
    """`dims` arrives from the request body, so without a fixed order the
    client's JSON would decide whether this check can answer - and "the
    rendered pass did not run" and "it ran after me" look identical from
    here."""
    from clauditseo.engine.core import RUN_FIRST, _in_run_order

    assert "A11Y" in RUN_FIRST
    assert _in_run_order(["TEC", "A11Y", "ONP"])[0] == "A11Y"
    # Order-preserving otherwise.
    assert _in_run_order(["ONP", "TEC"]) == ["ONP", "TEC"]
