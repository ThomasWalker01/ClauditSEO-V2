"""Crawl ordering, and the navigation-only mode.

A budget of three pages spent on a cookie policy, a privacy notice and a
social profile is a wasted audit. The site's own navigation is the closest
thing to an editorial statement about which pages matter, and it is free —
the region of every link is already parsed.
"""

from __future__ import annotations

from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import Page, TierBudget
from clauditseo.engine.types import Tier

HOME = """<html><body>
  <p>Before anything else, the boilerplate:</p>
  <a href="/cookie-policy">Cookie policy</a>
  <a href="/privacy">Privacy</a>
  <a href="/terms">Terms</a>
  <nav>
    <a href="/business-loans">Business loans</a>
    <a href="/how-it-works">How it works</a>
    <a href="/contact">Contact</a>
  </nav>
  <main><a href="/blog/a-post">A blog post</a></main>
  <footer><a href="/sitemap-page">Sitemap</a></footer>
</body></html>"""

CHILD = """<html><body><nav><a href="/deeper">Deeper</a></nav>
  <main><a href="/also-deeper">Also deeper</a></main></body></html>"""


class FakeFetcher:
    """Serves the two documents above for any path, and records order."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def fetch(self, url: str) -> Page:
        self.asked.append(url)
        if url.endswith("/robots.txt"):
            return Page(url=url, requested_url=url, status=404, content="")
        # Only the real sitemap file, not any path that happens to contain
        # the word — /sitemap-page is a normal page and must be crawlable.
        if url.endswith("/llms.txt") or url.endswith("/sitemap.xml"):
            return Page(url=url, requested_url=url, status=404, content="")
        body = HOME if url.rstrip("/").endswith("x.test") else CHILD
        return Page(url=url, requested_url=url, status=200,
                    content_type="text/html", content=body)

    def close(self) -> None:
        pass


def budget(pages: int) -> TierBudget:
    return TierBudget(max_pages=pages, request_timeout_s=5,
                      wall_clock_s=30, delay_s=0)


def crawled(result) -> list[str]:
    return [p.url.replace("https://x.test", "") or "/" for p in result.pages]


# ---- ordering --------------------------------------------------------------

def test_a_small_budget_is_spent_on_the_navigation_not_the_boilerplate():
    """The three boilerplate links appear first in the HTML. A plain FIFO
    frontier would fetch exactly those and call it an audit."""
    r = crawl("https://x.test/", Tier.T1, budget=budget(4), fetcher=FakeFetcher())
    got = crawled(r)
    assert got[0] == "/"
    assert set(got[1:]) == {"/business-loans", "/how-it-works", "/contact"}
    assert "/cookie-policy" not in got
    assert "/privacy" not in got


def test_body_links_still_come_before_footer_ones():
    """Ranking is nav, then body, then footer — so a budget that stops early
    stops on the least valuable pages rather than the first-parsed ones."""
    r = crawl("https://x.test/", Tier.T2, budget=budget(30), fetcher=FakeFetcher())
    got = crawled(r)
    assert got.index("/blog/a-post") < got.index("/sitemap-page")


def test_a_page_linked_from_both_nav_and_body_is_treated_as_a_nav_page():
    html = """<html><body><a href="/x">in body first</a>
      <nav><a href="/x">and in the nav</a><a href="/y">y</a></nav></body></html>"""

    class F(FakeFetcher):
        def fetch(self, url):
            p = super().fetch(url)
            if url.rstrip("/").endswith("x.test"):
                p.content = html
            return p

    r = crawl("https://x.test/", Tier.T1, budget=budget(2), fetcher=F())
    assert "/x" in crawled(r), "the better region should win"


def test_everything_is_still_reached_when_the_budget_allows():
    r = crawl("https://x.test/", Tier.T2, budget=budget(50), fetcher=FakeFetcher())
    got = set(crawled(r))
    assert {"/cookie-policy", "/privacy", "/terms", "/sitemap-page",
            "/business-loans", "/blog/a-post"} <= got, "ordering must not drop pages"


# ---- navigation-only mode --------------------------------------------------

def test_nav_only_takes_the_entry_page_and_its_menu():
    r = crawl("https://x.test/", Tier.T2, budget=budget(50),
              fetcher=FakeFetcher(), nav_only=True)
    assert set(crawled(r)) == {"/", "/business-loans", "/how-it-works", "/contact"}


def test_nav_only_does_not_walk_the_site_through_repeated_menus():
    """Every page carries the same menu, so following nav links onward would
    crawl everything and make the mode pointless."""
    r = crawl("https://x.test/", Tier.T2, budget=budget(50),
              fetcher=FakeFetcher(), nav_only=True)
    assert "/deeper" not in crawled(r)
    assert "/also-deeper" not in crawled(r)


def test_nav_only_records_why_each_page_was_included():
    r = crawl("https://x.test/", Tier.T2, budget=budget(50),
              fetcher=FakeFetcher(), nav_only=True)
    via = {p.url.replace("https://x.test", ""): p.discovered_via for p in r.pages}
    assert via["/"] == "start"
    assert via["/contact"] == "nav", "the evidence should say it came from the menu"


def test_nav_only_on_a_site_with_no_nav_still_returns_the_entry_page():
    class NoNav(FakeFetcher):
        def fetch(self, url):
            p = super().fetch(url)
            if url.rstrip("/").endswith("x.test"):
                p.content = "<html><body><a href='/a'>a</a></body></html>"
            return p

    r = crawl("https://x.test/", Tier.T2, budget=budget(50),
              fetcher=NoNav(), nav_only=True)
    assert crawled(r) == ["/"], "no menu is a result, not an error"


# --- scope-dependent checks must not read as site defects ------------------

def _sitemap_crawl(scope: str, tier, crawled: int, entries: int = 271):
    from clauditseo.crawler.types import CrawlResult, Page
    urls = [f"https://x.test/p{i}" for i in range(entries)]
    pages = [Page(url=u, requested_url=u, status=200, content_type="text/html",
                  content="<html lang=en><head><title>t</title></head>"
                          "<body><main><h1>h</h1></main></body></html>")
             for u in urls[:crawled]]
    return CrawlResult(start_url="https://x.test/", tier=tier, scope=scope,
                       pages=pages, sitemap_entries=urls,
                       sitemap_urls=["https://x.test/sitemap.xml"],
                       robots_status=200, robots_txt="User-agent: *\nAllow: /\n")


def _coverage_findings(crawl):
    import clauditseo.modules  # noqa: F401
    from clauditseo.engine.types import Site
    from clauditseo.modules.tec import TechnicalModule
    return [f for f in TechnicalModule().run(
        crawl.pages, crawl.tier,
        {"crawl": crawl, "site": Site(domain="https://x.test/")})
        if "unreachable" in f.check_id]


def test_a_nav_scoped_crawl_does_not_report_the_rest_as_unreachable():
    """The defect this guards: a 20-page nav crawl against a 271-URL sitemap
    reported "252 sitemap URL(s) were not reachable from the site's internal
    links". They were never visited. An auditor putting that in a client
    report is wrong in front of a dev team that can check.

    `truncated_by` was the only guard, and a nav crawl is not truncated — it
    reached everything it set out to reach."""
    from clauditseo.engine.types import Tier
    found = _coverage_findings(_sitemap_crawl("nav", Tier.T2, crawled=20))
    assert [f.check_id for f in found] == ["unreachable-not-assessed"]
    assert found[0].severity.value == "info"          # deducts nothing
    assert "scoped to the navigation" in found[0].summary
    assert "20 of 271" in found[0].summary


def test_a_pulse_does_not_report_coverage_either():
    from clauditseo.engine.types import Tier
    found = _coverage_findings(_sitemap_crawl("site", Tier.T1, crawled=3))
    assert found[0].check_id == "unreachable-not-assessed"


def test_a_full_crawl_still_reports_genuine_orphans():
    """The check must not be defanged: a complete crawl that genuinely could
    not reach five sitemap URLs still says so, and still deducts."""
    from clauditseo.engine.types import Tier
    found = _coverage_findings(_sitemap_crawl("site", Tier.T2, crawled=266))
    assert found[0].check_id == "unreachable"
    assert found[0].severity.value == "medium"
    assert "5 of 271" in found[0].summary


def test_a_full_crawl_that_reached_everything_says_nothing():
    from clauditseo.engine.types import Tier
    assert _coverage_findings(_sitemap_crawl("site", Tier.T2, crawled=271)) == []


def test_the_crawler_records_its_own_scope():
    """The engine cannot tell a restricted frontier from a spent budget
    without being told."""
    from clauditseo.crawler.types import CrawlResult
    assert CrawlResult(start_url="x", tier=None).scope == "site"
