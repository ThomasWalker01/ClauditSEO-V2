"""Gate G1: politeness and budgets.

- a robots-disallowed path is NEVER fetched (asserted from the server's own
  request log, not the crawler's word for it);
- max-page and wall-clock budgets are enforced;
- redirects are followed and recorded;
- the user agent identifies ClauditSEO on every request.
"""

from __future__ import annotations

import time

from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget, USER_AGENT
from clauditseo.engine.types import Tier

FAST = TierBudget(max_pages=50, request_timeout_s=5, wall_clock_s=30, delay_s=0)


def _page(links: list[str] = (), extra: str = "") -> tuple[int, dict, str]:
    anchors = "".join(f'<a href="{l}">x</a>' for l in links)
    return (200, {}, f"<html><head><title>t</title></head><body>{anchors}{extra}</body></html>")


def test_robots_disallowed_path_is_never_fetched(make_site):
    site = make_site({
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nDisallow: /private/\n"),
        "/": _page(["/about", "/private/secret"]),
        "/about": _page(),
        "/private/secret": _page(extra="should never be seen"),
    })
    result = crawl(site.base_url + "/", Tier.T2, budget=FAST)

    assert "/private/secret" not in site.request_log, "crawler fetched a disallowed path"
    assert any(u.endswith("/private/secret") for u in result.robots_blocked)
    fetched = {p.url.rsplit("/", 1)[-1] or "/" for p in result.pages}
    assert "about" in fetched


def test_broad_allow_does_not_shadow_narrow_disallow(make_site):
    """G1 hardening: the commonest real-world robots shape — a broad Allow
    followed by a narrow Disallow — must still block the disallowed path."""
    site = make_site({
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nAllow: /\nDisallow: /private/\n"),
        "/": _page(["/about", "/private/secret"]),
        "/about": _page(),
        "/private/secret": _page(extra="should never be seen"),
    })
    result = crawl(site.base_url + "/", Tier.T2, budget=FAST)
    assert "/private/secret" not in site.request_log, \
        "broad Allow shadowed the narrow Disallow"
    assert any(u.endswith("/private/secret") for u in result.robots_blocked)


def test_robots_5xx_means_fetch_nothing(make_site):
    site = make_site({
        "/robots.txt": (503, {"Content-Type": "text/plain"}, "err"),
        "/": _page(),
    })
    result = crawl(site.base_url + "/", Tier.T2, budget=FAST)
    assert result.pages == []
    assert "/" not in site.request_log


def test_max_pages_budget_enforced(make_site):
    routes = {"/robots.txt": (404, {"Content-Type": "text/plain"}, "")}
    routes["/"] = _page([f"/p{i}" for i in range(20)])
    for i in range(20):
        routes[f"/p{i}"] = _page()
    site = make_site(routes)

    result = crawl(site.base_url + "/", Tier.T2,
                   budget=TierBudget(max_pages=5, request_timeout_s=5, wall_clock_s=30, delay_s=0))
    assert len(result.pages) == 5
    assert result.truncated_by == "max_pages"


def test_wall_clock_budget_enforced(make_site):
    routes = {"/robots.txt": (404, {"Content-Type": "text/plain"}, "")}
    routes["/"] = _page([f"/p{i}" for i in range(30)])
    for i in range(30):
        routes[f"/p{i}"] = _page()
    site = make_site(routes)

    started = time.monotonic()
    result = crawl(site.base_url + "/", Tier.T2,
                   budget=TierBudget(max_pages=1000, request_timeout_s=5,
                                     wall_clock_s=0.5, delay_s=0.15))
    elapsed = time.monotonic() - started
    assert result.truncated_by == "wall_clock"
    assert elapsed < 5, "crawl should stop soon after the wall clock expires"


def test_redirect_chain_recorded(make_site):
    site = make_site({
        "/robots.txt": (404, {"Content-Type": "text/plain"}, ""),
        "/": _page(["/old"]),
        "/old": (301, {"Location": "/new"}, ""),
        "/new": _page(),
    })
    result = crawl(site.base_url + "/", Tier.T2, budget=FAST)
    redirected = [p for p in result.pages if p.redirect_chain]
    assert redirected and redirected[0].url.endswith("/new")
    assert redirected[0].redirect_chain[0].endswith("/old")


def test_identifiable_user_agent():
    """The name every crawled site sees in its logs. Asserted against the
    shared constant rather than a literal, so a product rename cannot leave
    the crawler introducing itself as the old name to somebody else's
    server — which is exactly what a hard-coded string here would allow."""
    from clauditseo import BOT_NAME

    assert BOT_NAME in USER_AGENT
    assert "self-hosted SEO audit" in USER_AGENT, "it says what it is"
    assert "polite" in USER_AGENT


def test_sitemap_read_and_offsite_links_ignored(make_site):
    sitemap = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               "<url><loc>https://x.example/a</loc></url>"
               "<url><loc>https://x.example/b</loc></url></urlset>")
    site = make_site({
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, sitemap),
        "/": _page(["https://elsewhere.example/x", "/here"]),
        "/here": _page(),
    })
    result = crawl(site.base_url + "/", Tier.T1, budget=FAST)
    assert result.sitemap_entries == ["https://x.example/a", "https://x.example/b"]
    assert all("elsewhere.example" not in p.url for p in result.pages)


# --- date signals for freshness ----------------------------------------------
#
# Three signals, deliberately kept apart. Merging them into one "last updated"
# value would hide that a sitemap lastmod is often just the build time while a
# JSON-LD dateModified is a claim about the article itself.

def test_sitemap_lastmod_is_captured_without_changing_the_entry_list():
    from clauditseo.crawler.crawl import _parse_sitemap
    xml = ('<?xml version="1.0"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>https://x.example/a</loc><lastmod>2026-01-15</lastmod></url>'
           '<url><loc>https://x.example/b</loc></url>'
           '</urlset>')
    urls, is_index, lastmod = _parse_sitemap(xml, 100)
    assert urls == ["https://x.example/a", "https://x.example/b"]
    assert is_index is False
    assert lastmod == {"https://x.example/a": "2026-01-15"}   # absent stays absent


def test_a_sitemap_index_is_still_followed_not_counted():
    from clauditseo.crawler.crawl import _parse_sitemap
    xml = """<?xml version="1.0"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://x.example/post-sitemap.xml</loc>
               <lastmod>2026-02-01</lastmod></sitemap>
    </sitemapindex>"""
    urls, is_index, _ = _parse_sitemap(xml, 100)
    assert is_index is True and urls == ["https://x.example/post-sitemap.xml"]


def test_content_dates_are_read_from_json_ld_at_any_nesting():
    from clauditseo.crawler.evidence import content_dates
    blocks = ['{"@graph":[{"@type":"WebPage"},'
              '{"@type":"Article","datePublished":"2025-03-01",'
              '"dateModified":"2026-06-30T10:00:00+11:00"}]}']
    dates = content_dates(blocks)
    assert dates["datePublished"] == "2025-03-01"
    assert dates["dateModified"].startswith("2026-06-30")

    # Malformed JSON-LD is reported by the schema checks, not swallowed here
    # as a crash, and never guessed at.
    assert content_dates(["{not json"]) == {}
    assert content_dates([]) == {}
