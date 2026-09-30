"""`sitemap-invalid` and `sitemap-lastmod-stale` (brief v18 step AZ).

Both are site-level facts about the sitemap XML the crawl read, not about how
many pages it reached — so they carry no partial-crawl caveat, and they are
tested from a hand-built CrawlResult rather than a live crawl.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import clauditseo.modules  # noqa: F401  register dimensions
from clauditseo import anatomy
from clauditseo.crawler.types import CrawlResult, SitemapRecord
from clauditseo.engine.types import Tier
from clauditseo.modules.tec import TechnicalModule

HOME = "https://x.test/"


def _crawl(**kw) -> CrawlResult:
    return CrawlResult(start_url=HOME, tier=Tier.T2, **kw)


def _health(crawl) -> dict:
    return {f.check_id: f for f in TechnicalModule()._sitemap_health(crawl)}


# --- sitemap-invalid --------------------------------------------------------

def test_a_sitemap_that_will_not_parse_is_invalid():
    # A body that came back 200 but is not well-formed XML: the crawler stamps
    # `status=200` and a `malformed XML: …` error, and that pairing — not the
    # error string alone — is what marks it unparseable rather than unreachable.
    got = _health(_crawl(sitemaps=[
        SitemapRecord(url=HOME + "sitemap.xml", status=200, entry_count=10),
        SitemapRecord(url=HOME + "broken.xml", status=200,
                      error="malformed XML: not well-formed")]))
    assert "sitemap-invalid" in got
    assert got["sitemap-invalid"].severity.value == "high"
    assert "broken.xml" in got["sitemap-invalid"].summary


def test_a_sitemap_index_pointing_at_a_404_is_invalid():
    # The child is `declared` — an index that lists it is a declaration — so its
    # 404 is a broken promise, not the mere absence a probed /sitemap.xml would be.
    got = _health(_crawl(sitemaps=[
        SitemapRecord(url=HOME + "sitemap_index.xml", status=200, is_index=True),
        SitemapRecord(url=HOME + "posts.xml", status=404, declared=True)]))
    assert "sitemap-invalid" in got
    assert "HTTP 404" in got["sitemap-invalid"].summary


def test_a_probed_sitemap_that_404s_is_not_invalid():
    """The bare /sitemap.xml the crawler guesses when robots declares none:
    a 404 there is 'no sitemap', which `sitemap-missing` reports, not a broken
    one. `declared` defaults False, so this is the probe case."""
    got = _health(_crawl(sitemaps=[SitemapRecord(url=HOME + "sitemap.xml", status=404)]))
    assert "sitemap-invalid" not in got


def test_a_declared_sitemap_that_will_not_connect_is_not_invalid():
    """A declared sitemap that returns no HTTP status at all (a transport
    failure) is unreachable, not malformed — it belongs to `sitemap-missing`,
    not `sitemap-invalid`, which is about files that came back and are wrong."""
    got = _health(_crawl(sitemaps=[
        SitemapRecord(url=HOME + "sitemap.xml", status=None,
                      error="connection refused", declared=True)]))
    assert "sitemap-invalid" not in got


def test_a_sitemap_over_the_url_cap_is_invalid():
    got = _health(_crawl(sitemaps=[
        SitemapRecord(url=HOME + "big.xml", status=200, entry_count=60000)]))
    assert "sitemap-invalid" in got
    assert "over the 50,000 cap" in got["sitemap-invalid"].summary


def test_healthy_sitemaps_raise_nothing():
    got = _health(_crawl(sitemaps=[
        SitemapRecord(url=HOME + "sitemap.xml", status=200, entry_count=42)],
        sitemap_entries=[HOME + "a", HOME + "b"],
        sitemap_lastmod={HOME + "a": "2026-09-01", HOME + "b": "2026-08-15"}))
    assert "sitemap-invalid" not in got
    assert "sitemap-lastmod-stale" not in got


# --- sitemap-lastmod-stale --------------------------------------------------

def test_no_lastmod_anywhere_is_stale():
    got = _health(_crawl(sitemap_entries=[HOME + "a", HOME + "b", HOME + "c"]))
    assert "sitemap-lastmod-stale" in got
    assert "no <lastmod>" in got["sitemap-lastmod-stale"].summary


def test_one_lastmod_for_every_entry_is_stale():
    got = _health(_crawl(
        sitemap_entries=[HOME + "a", HOME + "b"],
        sitemap_lastmod={HOME + "a": "2026-09-01", HOME + "b": "2026-09-01"}))
    assert "sitemap-lastmod-stale" in got
    assert "same <lastmod>" in got["sitemap-lastmod-stale"].summary


def test_a_future_lastmod_is_stale():
    future = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    got = _health(_crawl(
        sitemap_entries=[HOME + "a", HOME + "b"],
        sitemap_lastmod={HOME + "a": "2026-01-01", HOME + "b": future}))
    assert "sitemap-lastmod-stale" in got
    assert "future" in got["sitemap-lastmod-stale"].summary


def test_a_single_entry_site_is_not_judged_stale():
    """One page cannot be 'all the same' or 'all missing' in a meaningful way,
    so the check declines rather than firing on a one-page site."""
    got = _health(_crawl(sitemap_entries=[HOME + "only"]))
    assert "sitemap-lastmod-stale" not in got


# --- both file under Crawl --------------------------------------------------

def test_both_checks_file_under_crawl():
    for check in ("sitemap-invalid", "sitemap-lastmod-stale"):
        assert anatomy.categorise(check, "TEC") == "crawl", check


# --- sitemap-404s and sitemap-noindex (declared vs reached) -----------------

from clauditseo.crawler.types import Page  # noqa: E402


def _page(path, status=200, content="", ctype="text/html"):
    u = HOME.rstrip("/") + path
    return Page(url=u, requested_url=u, status=status, content=content, content_type=ctype)


def test_a_declared_url_that_returns_an_error_is_reported():
    got = _health(_crawl(
        sitemap_entries=[HOME + "ok", HOME + "dead"],
        pages=[_page("/ok", 200, "<html></html>"), _page("/dead", 404)]))
    assert "sitemap-404s" in got
    assert got["sitemap-404s"].severity.value == "medium"
    assert any("dead" in u for u in got["sitemap-404s"].affected_urls)


def test_a_declared_url_carrying_noindex_is_reported():
    noindex = '<html><head><meta name="robots" content="noindex"></head><body>x</body></html>'
    got = _health(_crawl(
        sitemap_entries=[HOME + "hidden"],
        pages=[_page("/hidden", 200, noindex)]))
    assert "sitemap-noindex" in got
    assert any("hidden" in u for u in got["sitemap-noindex"].affected_urls)


def test_a_declared_url_the_crawl_never_reached_is_not_judged():
    """No page fetched for the entry, so neither 404s nor noindex speaks to it
    — that silence belongs to sitemap-coverage, not a false clean or a false
    error here."""
    got = _health(_crawl(sitemap_entries=[HOME + "ghost", HOME + "seen"],
                         pages=[_page("/seen", 200, "<html></html>")]))
    assert "sitemap-404s" not in got
    assert "sitemap-noindex" not in got


# --- sitemap-regression (prior-run comparison, injected context) ------------

from clauditseo.persistence.runs import sitemap_drop_fraction  # noqa: E402


def _crawl_with_entries(n, clean=True):
    return _crawl(
        sitemap_entries=[HOME + str(i) for i in range(n)],
        sitemaps=[SitemapRecord(url=HOME + "sitemap.xml", status=200 if clean else 500,
                                entry_count=n, error=None if clean else None)])


def _regression(crawl, prior):
    return {f.check_id: f for f in TechnicalModule()._sitemap_regression(crawl, prior)}


def test_a_20pct_fall_is_a_regression():
    got = _regression(_crawl_with_entries(50), {"total": 272, "unread": False})
    assert "sitemap-regression" in got
    assert got["sitemap-regression"].severity.value == "high"
    assert "272 to 50" in got["sitemap-regression"].summary


def test_no_prior_run_is_silent_not_green():
    assert _regression(_crawl_with_entries(50), None) == {}


def test_an_unread_prior_sitemap_is_not_comparable():
    assert _regression(_crawl_with_entries(50), {"total": 272, "unread": True}) == {}


def test_an_unread_sitemap_this_run_is_not_comparable():
    # A sitemap that did not come back 200 makes this run's total untrustworthy.
    crawl = _crawl(sitemap_entries=[HOME + "a"],
                   sitemaps=[SitemapRecord(url=HOME + "s.xml", status=500)])
    assert _regression(crawl, {"total": 272, "unread": False}) == {}


def test_a_small_drop_does_not_fire():
    assert _regression(_crawl_with_entries(90), {"total": 100, "unread": False}) == {}


def test_a_rise_is_not_a_regression():
    assert _regression(_crawl_with_entries(150), {"total": 100, "unread": False}) == {}


def test_the_drop_fraction_helper_encodes_every_guard():
    assert sitemap_drop_fraction(272, False, 50, False) > 0.8   # a real fall
    assert sitemap_drop_fraction(272, True, 50, False) is None  # prior unread
    assert sitemap_drop_fraction(272, False, 50, True) is None  # after unread
    assert sitemap_drop_fraction(0, False, 50, False) is None   # no baseline
    assert sitemap_drop_fraction(100, False, 90, False) is None  # under threshold
    assert sitemap_drop_fraction(100, False, 200, False) is None  # a rise


def test_sitemap_regression_files_under_crawl():
    assert anatomy.categorise("sitemap-regression", "TEC") == "crawl"


# --- sitemap-coverage, now reversed: reached pages absent from the sitemap ---

def test_a_reached_indexable_page_absent_from_the_sitemap_is_coverage():
    got = _health(_crawl(
        sitemap_entries=[HOME + "a"],
        pages=[_page("/a", 200, "<html></html>"),       # declared, fine
               _page("/b", 200, "<html></html>")]))     # reached, not declared
    assert "sitemap-coverage" in got
    assert got["sitemap-coverage"].severity.value == "medium"
    assert any("/b" in u for u in got["sitemap-coverage"].affected_urls)


def test_a_noindex_page_absent_from_the_sitemap_is_not_coverage():
    """A page the sitemap needn't list because it says don't index it."""
    noindex = '<html><head><meta name="robots" content="noindex"></head><body>x</body></html>'
    got = _health(_crawl(
        sitemap_entries=[HOME + "a"],
        pages=[_page("/a", 200, "<html></html>"), _page("/hidden", 200, noindex)]))
    assert "sitemap-coverage" not in got


def test_no_sitemap_means_no_coverage_finding():
    """With no sitemap at all, sitemap-missing owns it — not sitemap-coverage
    firing for every reached page."""
    got = _health(_crawl(pages=[_page("/a", 200, "<html></html>")]))
    assert "sitemap-coverage" not in got


# --- missing vs invalid vs coverage, told apart on `declared` ---------------

def _site(**kw) -> dict:
    return {f.check_id: f for f in TechnicalModule()._site_checks(_crawl(**kw))}


def test_a_declared_sitemap_that_could_not_be_read_is_missing_not_invalid():
    """The golden-fixture shape: robots declared a sitemap, the crawl could not
    fetch it. That is `sitemap-missing` (with the declaration named), never
    `sitemap-invalid` — nothing malformed was read."""
    got = _site(sitemap_urls=[HOME + "sitemap.xml"],
                sitemaps=[SitemapRecord(url=HOME + "sitemap.xml", status=None,
                                        error="connection refused", declared=True)],
                pages=[_page("/", 200, "<html></html>")])
    assert "sitemap-missing" in got
    assert "declared in robots.txt" in got["sitemap-missing"].summary
    assert "sitemap-invalid" not in got


def test_a_probed_404_reports_missing_the_plain_way():
    got = _site(sitemap_urls=[HOME + "sitemap.xml"],
                sitemaps=[SitemapRecord(url=HOME + "sitemap.xml", status=404)],
                pages=[_page("/", 200, "<html></html>")])
    assert "sitemap-missing" in got
    assert got["sitemap-missing"].summary.startswith("No XML sitemap was found")


# --- the whole chain on a live crawl (the probe the unit results can't fake) -

def test_a_live_site_with_no_sitemap_is_missing_not_invalid_or_coverage():
    """The regression that the hand-built results above cannot show: on a real
    crawl the guessed `/sitemap.xml` 404 is recorded as a sitemap, which once
    made every no-sitemap site read `sitemap-invalid` (HIGH) plus
    `sitemap-coverage` (every reached page 'absent'). A live crawl of a site
    that serves no sitemap must report exactly one thing: `sitemap-missing`."""
    import clauditseo.modules  # noqa: F401
    from clauditseo.crawler.crawl import crawl as run_crawl
    from clauditseo.crawler.types import TierBudget
    from tests.conftest import FixtureSite

    home = ('<html><head><title>Home Page For The Fixture</title>'
            '<meta name="description" content="A small site that serves no XML '
            'sitemap at all, only a home page and a permissive robots file.">'
            '</head><body><h1>Home</h1><p>Some words of body copy here so the '
            'page is a real indexable document worth listing.</p></body></html>')
    routes = {"/robots.txt": (200, {"Content-Type": "text/plain"},
                              "User-agent: *\nAllow: /\n"),
              "/": (200, {}, home)}
    site = FixtureSite(routes).start()
    try:
        cr = run_crawl(site.base_url + "/", Tier.T2, budget=TierBudget(30, 5, 30, 0))
    finally:
        site.stop()

    mod = TechnicalModule()
    ids = {f.check_id for f in mod._site_checks(cr)}
    assert "sitemap-missing" in ids
    assert "sitemap-invalid" not in ids
    assert "sitemap-coverage" not in ids
