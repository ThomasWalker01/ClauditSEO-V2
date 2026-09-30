"""`normalise_url` strips tracking parameters, and nothing else.

Relay item 101. Re-measured at HEAD over all 15 stored crawl-evidence
snapshots in `data/clauditseo.db`, every query key the product has ever
fetched a page under is one of:

    redirect_to x27  utm_source x25  utm_medium x25  utm_campaign x25
    gclid x8  utm_term x6  product_type x5  gad_source x2
    gad_campaignid x2  gbraid x2  slug x1

Two populations, and the split is the whole rule. `utm_*`, `gclid`, `gbraid`
and the `gad_*` pair are appended by an ad platform to a link that already
resolved; the server never reads them, so by the same test `normalise_url`
already applies to scheme case, default ports and fragments — "cannot change
what is served" — they are spelling, not address. `redirect_to`,
`product_type` and `slug` are read by the application and can.

In run `fe97cc61ab52468ebb0c4bff36ac69f7` — 235 pages, the T3 crawl the item
was written from — ten fetched URLs carry nothing but tracking parameters, so
235 distinct URLs become 225 and about 4% of a paid crawl stops re-fetching
pages it already had. Every one of the ten collapses onto a URL that same
crawl already held; no clean path is lost.

Both directions are guarded here, because a stripper with no lower bound is a
stripper that will eventually eat `redirect_to` and lose a real page.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from clauditseo.crawler.crawl import (TRACKING_PARAMS, TRACKING_PREFIXES,
                                      extract_link_details, normalise_url,
                                      strip_tracking_params)
from clauditseo.crawler.types import Page

BASE = "https://x.example/a"


# --- what is stripped -------------------------------------------------------

@pytest.mark.parametrize("key", sorted(TRACKING_PARAMS))
def test_every_named_tracking_parameter_is_stripped(key):
    """Enumerated from the constant rather than from a literal list beside
    it: a key added to the set with no stripping behind it must fail here."""
    assert normalise_url(f"{BASE}?{key}=v") == BASE


@pytest.mark.parametrize("prefix", sorted(TRACKING_PREFIXES))
def test_every_named_tracking_prefix_is_stripped(prefix):
    assert normalise_url(f"{BASE}?{prefix}campaign=v") == BASE


def test_a_url_carrying_only_tracking_parameters_normalises_to_its_base():
    """The observed case, verbatim from run `fe97cc61`'s evidence — an
    ad-tagged landing URL and the same page linked cleanly are one page."""
    tagged = ("https://www.acme.com.au/line-of-credit"
              "?utm_source=acme&utm_medium=article&utm_campaign=eoy2025campaign")
    assert normalise_url(tagged) == normalise_url("https://www.acme.com.au/line-of-credit")


def test_the_auto_tagged_google_ads_url_folds_too():
    """The one URL in that run carrying `gad_source`, `gad_campaignid` and
    `gbraid`. Relay 101 enumerated its list from stored *findings*, a narrower
    population than stored evidence, and so named none of the three; without
    them nine of the ten observed duplicates fold instead of ten."""
    tagged = ("https://www.acme.com.au/partner-up?utm_source=google&utm_medium=paid"
              "&utm_campaign=22103893873&utm_term=acme%20partner&gad_source=1"
              "&gad_campaignid=22103893873&gbraid=0AAAAAC3tBmetW8smhYjkJEZki5DexiVsO"
              "&gclid=Cj0KCQjw5onGBhDeARIsAFK6QJY")
    assert normalise_url(tagged) == "https://www.acme.com.au/partner-up"


def test_an_empty_valued_tracking_parameter_is_stripped_too():
    """The site's own markup emits `utm_source=` with no value, on two of the
    ten. A blank value is still the key being present, and `parse_qsl` drops
    it by default — so a reader built with `keep_blank_values=False` would
    leave the URL unchanged and the duplicate uncollapsed."""
    tagged = ("https://www.acme.com.au/?utm_source=&utm_medium=PressRelease"
              "&utm_campaign=PRNewswire_GPTWcertification")
    assert normalise_url(tagged) == "https://www.acme.com.au/"


def test_stripping_is_idempotent_and_leaves_no_trailing_question_mark():
    once = normalise_url(f"{BASE}?utm_source=s")
    assert once == normalise_url(once) == BASE
    assert "?" not in once


# --- what is preserved ------------------------------------------------------

def test_a_non_tracking_parameter_is_preserved_exactly():
    """The other direction, and the one that costs a page if it goes wrong.
    All four are keys an application reads — the first three appear in this
    database's own stored crawls. Dropping `redirect_to` sends the crawler to
    a different destination than the link named."""
    for key, value in (("product_type", "loan"), ("redirect_to", "/dashboard"),
                       ("slug", "about-us"), ("_wpnonce", "abc123")):
        url = f"{BASE}?{key}={value}"
        assert normalise_url(url) == url, f"{key} is read by the server"


def test_a_mixed_url_keeps_the_content_parameters_and_drops_the_tracking_ones():
    """Order and encoding of what survives are preserved, because a
    re-encoding that reorders keys manufactures a second spelling of the URL
    it was meant to canonicalise."""
    got = normalise_url(f"{BASE}?product_type=loan&gclid=abc&redirect_to=%2Fx&utm_source=s")
    query = urlsplit(got).query
    assert parse_qs(query) == {"product_type": ["loan"], "redirect_to": ["/x"]}
    assert "redirect_to=%2Fx" in query, "a kept pair was re-encoded rather than copied"
    assert query.index("product_type") < query.index("redirect_to")


def test_the_tracking_set_and_the_preserved_keys_are_disjoint():
    """A guard against the set growing into the keys the server reads."""
    for key in ("redirect_to", "product_type", "slug", "_wpnonce", "q", "page", "id"):
        assert key not in TRACKING_PARAMS
        assert not any(key.startswith(p) for p in TRACKING_PREFIXES)


def test_normalise_url_and_strip_tracking_params_agree_on_the_query():
    """One rule, two entry points. `strip_tracking_params` computes the clean
    URL a finding quotes back to whoever edits the site; `normalise_url`
    computes the crawler's identity for it. They must not be able to disagree
    about what a tracking parameter is."""
    for url in (f"{BASE}?utm_source=s", f"{BASE}?product_type=loan&gclid=abc",
                f"{BASE}?redirect_to=%2Fx", BASE):
        assert urlsplit(normalise_url(url)).query == urlsplit(strip_tracking_params(url)).query


# --- the link detail keeps the spelling the markup wrote --------------------

def test_a_link_detail_carries_the_raw_href_beside_the_stripped_url():
    """Item 102's tripwire, discharged the way its message asks.

    TEC's `internal-link-tracking-params` reports internal links the site
    tags in its own markup, and it reads the link detail. The strip lands
    before the URL is enqueued, so `url` can no longer carry a tracking
    parameter — without a second field the check searches a population of
    zero while passing. `href` is that field: the link absolutised, spelled
    as the markup wrote it.
    """
    page = Page(url="https://x.example/p", requested_url="https://x.example/p",
                status=200, content_type="text/html; charset=utf-8",
                content="<html><body><a href='/q?utm_source=a&product_type=loan'>x</a>"
                        "</body></html>")
    link = extract_link_details(page)[0]
    assert link["href"] == "https://x.example/q?utm_source=a&product_type=loan"
    assert link["url"] == "https://x.example/q?product_type=loan"


def test_two_links_differing_only_in_their_tracking_tag_are_two_link_details():
    """They are two links in the markup and two attribution defects, so the
    check counts two. Deduplicating on the stripped URL would merge them and
    undercount the very thing the finding reports."""
    page = Page(url="https://x.example/p", requested_url="https://x.example/p",
                status=200, content_type="text/html; charset=utf-8",
                content="<html><body><a href='/q?utm_source=a'>go</a>"
                        "<a href='/q?utm_source=b'>go</a></body></html>")
    details = extract_link_details(page)
    assert [d["href"] for d in details] == ["https://x.example/q?utm_source=a",
                                            "https://x.example/q?utm_source=b"]
    assert {d["url"] for d in details} == {"https://x.example/q"}


# --- the frontier, the inventory and the link graph agree -------------------

def _html(links, extra: str = "") -> tuple[int, dict, str]:
    anchors = "".join(f'<a href="{href}">x</a>' for href in links)
    return (200, {}, f"<html><head><title>t</title></head>"
                     f"<body>{anchors}{extra}</body></html>")


def test_a_tracking_variant_is_fetched_once_and_counted_once(make_site):
    """Item 101's third clause, end to end.

    `/deals` is linked three ways from the homepage — clean, `?gclid=` and
    `?utm_source=` — plus once more from `/about`, and a fifth link carries
    the functional `?product_type=loan` that must survive. The assertion that
    matters is read from the fixture server's own request log rather than
    from the crawler's report of itself (DISCIPLINE rule 5): what the server
    was actually asked for is the one thing the crawler cannot be wrong about.

    Before the strip this crawl fetched `/deals` five times, filed four of
    them as separate pages, and gave the clean form one inlink where the site
    has four.
    """
    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.types import TierBudget
    from clauditseo.engine.types import Tier

    fast = TierBudget(max_pages=50, request_timeout_s=5, wall_clock_s=30, delay_s=0)
    site = make_site({
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/": _html(["/deals", "/deals?gclid=abc", "/deals?utm_source=s&utm_medium=m",
                    "/about", "/deals?product_type=loan"]),
        "/about": _html(["/deals?utm_campaign=spring"]),
        "/deals": _html([]),
        "/deals?product_type=loan": _html([]),
    })
    result = crawl(site.base_url + "/", Tier.T2, budget=fast)

    served = [u for u in site.request_log if u.split("?")[0] == "/deals"]
    assert len(served) == 2, f"/deals was served {len(served)} times: {served}"
    assert sorted(served) == ["/deals", "/deals?product_type=loan"], (
        "the surviving pair is the clean URL and the content variant")

    inventory = [p.url for p in result.pages]
    assert len(inventory) == len(set(inventory)), "a URL appears twice in the page inventory"
    deals = [u for u in inventory if u.split("?")[0].endswith("/deals")]
    assert len(deals) == 2, f"page inventory disagrees with the frontier: {deals}"

    clean = site.base_url + "/deals"
    graph = result.inlinks()
    assert sorted(graph[clean]) == sorted([site.base_url + "/", site.base_url + "/about"]), (
        "an inlink was double-counted or lost when the variants collapsed")
    assert result.stats["fetched"] == len(result.pages)
