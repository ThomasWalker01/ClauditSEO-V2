"""A site that links to itself with campaign parameters should be told.

Measured on stored run `fe97cc61` (www.acme.com.au, T3, 235 pages) before
this check existed: the sitemap declares 272 entries and not one contains a
`?`, yet eleven parameterised URLs were fetched and every one of them records
`discovered_via: "link"`. They are not a crawler artefact and not a sitemap
mistake — the site links to itself with campaign parameters, in its own
markup, and a search engine follows those links exactly as this crawler does.

Two costs, neither previously reported:

- **Attribution breaks mid-session.** A visitor who arrives from a paid
  campaign and then clicks an internal `?utm_source=` link is re-stamped with
  that link's parameters, so the campaign that won the visit loses the credit.
- **Crawlable duplicates are manufactured out of the site's own navigation**,
  spending crawl budget and splitting internal link equity across spellings
  of one page.

The population these guards search is derived from `extract_link_details`
parsing real markup, not from hand-built link dicts: the parser is half of
what is under test, and a fixture that states the answer cannot disagree with
it (DISCIPLINE rule 5).
"""

from __future__ import annotations

from clauditseo.crawler.crawl import extract_link_details, is_tracking_param
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Tier
from clauditseo.modules.tec import TechnicalModule

BASE = "https://example.test"


def _page(path: str, body: str) -> Page:
    page = Page(url=BASE + path, requested_url=BASE + path, status=200,
                content_type="text/html; charset=utf-8",
                content=f"<html><body>{body}</body></html>")
    page.link_details = extract_link_details(page)
    return page


def _crawl(*pages: Page) -> CrawlResult:
    result = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    result.pages.extend(pages)
    return result


def _findings(*pages: Page):
    return [f for f in TechnicalModule()._link_checks(_crawl(*pages))
            if f.check_id == "internal-link-tracking-params"]


# --- the population these guards search -------------------------------------

def test_the_parser_still_hands_the_check_a_tagged_url():
    """The check reads `href`, the link as the markup wrote it, and that
    spelling keeps its query.

    Stated as its own guard because the whole file is vacuous the moment it
    stops being true. It used to assert the query on `url`, and said so: relay
    item 101 would strip tracking parameters inside `normalise_url`, which
    `extract_link_details` calls, and every assertion below would then search
    a population of zero while still passing. 101 landed, this went red as
    designed, and the repair is the one it named — `extract_link_details`
    carries a raw `href` beside the normalised `url` and `_link_checks` reads
    it.

    So the guard now holds the two apart, which is the property that actually
    protects this file: `url` must not carry the tag, `href` must.
    """
    page = _page("/a", "<a href='/x?utm_source=a'>x</a>")
    assert page.link_details, "the parser found no link at all"
    assert "utm_source=a" in page.link_details[0]["href"], (
        "extract_link_details no longer carries the link as written, so TEC's "
        "internal-link-tracking-params check reads a URL that cannot carry a "
        "tracking parameter and every guard in this file is vacuous")
    assert "utm_source" not in page.link_details[0]["url"], (
        "normalise_url stopped stripping tracking parameters, so an ad-tagged "
        "link and the clean link beside it are two entries in the frontier "
        "again (relay 101, tests/test_url_tracking_params.py)")


# --- what raises ------------------------------------------------------------

def test_a_tagged_internal_link_raises_and_names_the_source_page():
    """The item's own acceptance case."""
    found = _findings(_page("/a", "<a href='/x?utm_source=a'>x</a>"))
    assert len(found) == 1, found
    assert found[0].affected_urls == [BASE + "/a"], (
        "the finding must name the page whose markup carries the link")
    assert found[0].subject == "/a"


def test_the_evidence_names_the_link_the_region_and_the_anchor():
    """Evidence, not an assertion. Whoever edits the site has to find the
    link, and "somewhere on this page" is not a location."""
    found = _findings(_page(
        "/a", "<nav><a href='/x?utm_source=a&utm_medium=email'>Apply now</a></nav>"))
    link = found[0].evidence["links"][0]
    assert link["target"] == BASE + "/x?utm_source=a&utm_medium=email"
    assert link["clean_target"] == BASE + "/x"
    assert link["region"] == "nav"
    assert link["anchor"] == "Apply now"
    assert link["params"] == ["utm_source", "utm_medium"], (
        "the parameters are reported in the order the markup wrote them")


def test_every_tracking_family_the_stored_crawls_actually_contain_is_caught():
    """Derived from every stored evidence snapshot rather than from the six
    keys the item happened to list — relay 101 measured that enumeration one
    family short, and re-measured the same three families still present when
    it landed."""
    for key in ("utm_source", "utm_medium", "utm_campaign", "utm_term",
                "gclid", "gad_source", "gad_campaignid", "gbraid"):
        found = _findings(_page("/a", f"<a href='/x?{key}=v'>x</a>"))
        assert found, f"{key} is not recognised as a tracking parameter"
        assert is_tracking_param(key)


def test_one_finding_per_source_page_however_many_tagged_links_it_carries():
    """One per link is noise; one per page is the unit of the edit."""
    found = _findings(_page("/a", "<a href='/x?utm_source=a'>x</a>"
                                  "<a href='/y?gclid=b'>y</a>"))
    assert len(found) == 1, found
    assert len(found[0].evidence["links"]) == 2
    assert found[0].evidence["parameters"] == ["gclid", "utm_source"]


def test_two_source_pages_are_two_findings_each_naming_its_own_page():
    found = _findings(_page("/a", "<a href='/x?utm_source=a'>x</a>"),
                      _page("/b", "<a href='/x?utm_source=b'>x</a>"))
    assert sorted(f.subject for f in found) == ["/a", "/b"]
    assert all(len(f.affected_urls) == 1 for f in found), (
        "a finding naming a page it did not read can be cleared by a narrow "
        "run that never read that page")


def test_the_malformed_empty_valued_link_is_flagged_in_rendered_text():
    """`?utm_source=` with no value is the site's own templating failing to
    substitute. It is reported in the summary rather than only in evidence:
    a defect that reaches only a tooltip has not been said.
    """
    found = _findings(_page(
        "/a", "<a href='/x?utm_source=&utm_medium=PressRelease'>x</a>"))
    assert found[0].evidence["links"][0]["empty_valued"] == ["utm_source"]
    assert "utm_source" in found[0].summary
    assert "no value" in found[0].summary


# --- what does not raise ----------------------------------------------------

def test_a_clean_internal_link_raises_nothing():
    assert _findings(_page("/a", "<a href='/x'>x</a>")) == []


def test_a_functional_parameter_is_not_a_tracking_parameter():
    """`?product_type=loc` addresses different content — nine of the twenty
    parameterised links in run `fe97cc61` are this, and telling a client to
    strip them would break their application form."""
    assert _findings(_page("/a", "<a href='/x'>x</a>"
                                 "<a href='/x?product_type=loc'>x</a>")) == []


def test_the_functional_parameters_the_second_stored_site_uses_raise_nothing():
    """Run `9853d9c9` (meridian.io, 500 pages) carries 627 parameterised
    internal links and not one is a campaign tag: `_wpnonce`, `add-to-cart`,
    `redirect_to`, `slug` and `cs:nbp`. It is the negative control this check
    has to survive, and it is a real site rather than an invented one."""
    for key in ("_wpnonce", "add-to-cart", "redirect_to", "slug", "cs:nbp"):
        assert _findings(_page("/a", f"<a href='/x?{key}=v'>x</a>")) == [], key


def test_an_outbound_link_to_another_host_is_not_this_sites_defect():
    """The finding says the site links to *itself* with campaign parameters.
    A tagged link to a third party is normal practice and is not internal —
    `extract_link_details` already drops it, and this states that the check
    depends on that rather than on a filter of its own."""
    assert _findings(_page(
        "/a", "<a href='https://other.test/x?utm_source=a'>x</a>")) == []


def test_a_page_that_was_not_fetched_contributes_no_links():
    """A `Page` survives a failed fetch. Reading link details off a 404 would
    report markup nobody was served."""
    dead = Page(url=BASE + "/gone", requested_url=BASE + "/gone", status=404,
                content_type="text/html", content="")
    dead.link_details = [{"url": BASE + "/x?utm_source=a", "anchor": "x",
                          "rel": "", "region": "body"}]
    assert _findings(dead) == []


# --- how it is filed --------------------------------------------------------

def test_the_check_is_filed_under_urls_and_parameters():
    """Not `links`. The link is only where the parameter was found; the
    subject is the URL it builds and the duplicate that URL manufactures."""
    from clauditseo import anatomy
    assert anatomy.CHECK_CATEGORY["internal-link-tracking-params"] == "urls"
    assert anatomy.categorise("internal-link-tracking-params", "TEC") == "urls"


def test_urls_and_parameters_is_no_longer_a_section_nothing_sweeps():
    """It was `ANALYSIS_ONLY` — the launcher said running every dimension
    left it untouched. A sweep covers it now, so that sentence would be a
    lie, and `test_analysis_only_categories_really_have_no_sweep` is the
    guard that makes it one."""
    from clauditseo import anatomy
    assert "urls" not in anatomy.ANALYSIS_ONLY
    assert "urls" in anatomy.DIMENSION_CATEGORIES["TEC"]


def test_the_severity_is_the_band_the_duplicate_it_manufactures_already_has():
    """`canonical-missing-variant` — a crawled parameterised duplicate with no
    canonical — is MEDIUM. This check reports the markup that produces those
    URLs, plus an attribution loss the canonical does not fix, so it is not
    ranked below the symptom it causes."""
    from clauditseo.engine.types import Severity
    found = _findings(_page("/a", "<a href='/x?utm_source=a'>x</a>"))
    assert found[0].severity is Severity.MEDIUM


def test_the_recommendation_is_actionable_by_whoever_edits_the_site():
    found = _findings(_page("/a", "<a href='/x?utm_source=a'>x</a>"))
    text = found[0].recommendation.lower()
    assert "clean" in text and "campaign" in text
