"""LNK — the eight checks the sweep answers about internal linking
(brief v17 step AW).

The part existed as a name with nothing under it: `page-links` was in
`ANALYSIS_ONLY`, filled by the `site-architecture` brief or not at all,
and the one thing the product produced about internal links was a block of
suggestions on the Analyse pane that no check, no record row and no report
ever saw. Eight of these are arithmetic on a graph the crawler already
records — `link_details` carries the anchor, the `rel` and the region, and
`click_depth` walks the graph — so none of them needs a model and none of
them should ever have cost tokens.

**LNK carries half of ONP's weight** (operator, 2026-09-06; Q-50). Zero
was the safe default and was the wrong answer: a dimension at weight zero
is the product saying internal linking does not affect ranking. Every
existing composite moves, which is what the trend's break annotation is
for — it reads "dimensions added: LNK" and the line stops being a
comparison at that point, honestly.

The population these guards search is parsed from real markup by
`extract_link_details`, not hand-built link dicts: the parser is half of
what is under test (DISCIPLINE rule 5).
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.crawl import extract_link_details
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Site, Tier

BASE = "https://links.test"


def _page(path: str, body: str, status: int = 200) -> Page:
    page = Page(url=BASE + path, requested_url=BASE + path, status=status,
                content_type="text/html; charset=utf-8",
                content=f"<html><body>{body}</body></html>")
    page.link_details = extract_link_details(page)
    page.outlinks = [link["url"] for link in page.link_details]
    return page


def _crawl(*pages: Page) -> CrawlResult:
    result = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    result.pages.extend(pages)
    return result


def _run(*pages: Page):
    from clauditseo.modules.links import LinksModule

    crawl = _crawl(*pages)
    return LinksModule().run(list(crawl.pages), Tier.T2,
                             {"crawl": crawl, "site": Site(domain="links.test")})


def _by_check(findings):
    out: dict[str, list] = {}
    for f in findings:
        out.setdefault(f.check_id, []).append(f)
    return out


# --- the population -----------------------------------------------------

def test_the_parser_hands_the_module_an_anchor_a_rel_and_a_region():
    """Vacuous the moment this stops being true: every check below reads
    one of the three, and a parser that dropped them would leave each of
    them searching an empty set while still passing."""
    page = _page("/", '<nav><a href="/a" rel="nofollow">Learn more</a></nav>')
    assert page.link_details, page.content
    link = page.link_details[0]
    assert link["anchor"] == "Learn more", link
    assert "nofollow" in link["rel"], link
    assert link["region"] == "nav", link


# --- the eight ----------------------------------------------------------

def test_a_page_nothing_links_to_is_an_orphan():
    home = _page("/", '<a href="/reachable">Our travel team</a>')
    got = _by_check(_run(home, _page("/reachable", "<p>x</p>"),
                         _page("/nobody-links-here", "<p>x</p>")))
    assert "orphan" in got, sorted(got)
    urls = {u for f in got["orphan"] for u in f.affected_urls}
    assert urls == {BASE + "/nobody-links-here"}, urls


def test_a_page_with_too_few_body_inlinks_is_under_linked():
    """And nav and footer links do not satisfy it: they point at every
    page from every page, so counting them would mean no site ever has an
    under-linked page."""
    nav = '<nav><a href="/thin">Thin</a></nav><footer><a href="/thin">Thin</a></footer>'
    home = _page("/", nav + '<main><a href="/thick">Thick</a></main>')
    a = _page("/a", nav + '<main><a href="/thick">Thick</a></main>')
    b = _page("/b", nav + '<main><a href="/thick">Thick</a></main>')
    thin = _page("/thin", nav)
    thick = _page("/thick", nav)
    got = _by_check(_run(home, a, b, thin, thick))
    urls = {u for f in got.get("inlinks-low", []) for u in f.affected_urls}
    assert BASE + "/thin" in urls, urls
    assert BASE + "/thick" not in urls, urls


def test_a_generic_anchor_is_named_with_the_words_it_used():
    home = _page("/", '<main><a href="/a">Learn more</a>'
                      '<a href="/b">click here</a>'
                      '<a href="/c">https://links.test/c</a>'
                      '<a href="/d">Meet the travel team</a></main>')
    got = _by_check(_run(home, _page("/a", ""), _page("/b", ""),
                         _page("/c", ""), _page("/d", "")))
    assert "anchor-generic" in got, sorted(got)
    text = " ".join(f.summary for f in got["anchor-generic"])
    assert "Learn more" in text and "click here" in text, text
    assert "Meet the travel team" not in text, text


def test_one_anchor_pointing_at_two_targets_is_a_duplicate():
    home = _page("/", '<main><a href="/a">Our team</a></main>')
    other = _page("/other", '<main><a href="/b">Our team</a></main>')
    got = _by_check(_run(home, other, _page("/a", ""), _page("/b", "")))
    assert "anchor-duplicate-target" in got, sorted(got)
    assert "Our team" in got["anchor-duplicate-target"][0].summary


def test_a_link_to_a_page_that_errors_is_broken():
    home = _page("/", '<main><a href="/gone">Gone</a></main>')
    got = _by_check(_run(home, _page("/gone", "", status=404)))
    assert "broken-internal" in got, sorted(got)
    assert "404" in got["broken-internal"][0].summary


def test_a_link_through_two_hops_is_a_chain():
    home = _page("/", '<main><a href="/old">Old</a></main>')
    old = _page("/old", "")
    old.redirect_chain = [BASE + "/old", BASE + "/mid", BASE + "/new"]
    got = _by_check(_run(home, old))
    assert "redirect-chain" in got, sorted(got)


def test_an_internal_nofollow_is_reported():
    home = _page("/", '<main><a href="/a" rel="nofollow">A page</a></main>')
    got = _by_check(_run(home, _page("/a", "")))
    assert "nofollow-internal" in got, sorted(got)


def test_a_page_more_than_three_clicks_from_home_is_deep():
    pages = [_page("/", '<main><a href="/one">One</a></main>'),
             _page("/one", '<main><a href="/two">Two</a></main>'),
             _page("/two", '<main><a href="/three">Three</a></main>'),
             _page("/three", '<main><a href="/four">Four</a></main>'),
             _page("/four", "")]
    got = _by_check(_run(*pages))
    urls = {u for f in got.get("depth-deep", []) for u in f.affected_urls}
    assert urls == {BASE + "/four"}, urls


# --- the registry -------------------------------------------------------

FREE = ("inlinks-low", "orphan", "anchor-generic", "anchor-duplicate-target",
        "broken-internal", "redirect-chain", "nofollow-internal", "depth-deep")
MODEL = ("link-suggestion", "anchor-entity", "hub-spoke-gap", "anchor-flow")


def test_every_lnk_check_has_a_cost_and_it_is_the_right_one():
    from clauditseo.checks import check_costs

    costs = check_costs()
    for check in FREE:
        assert costs.get(f"LNK/{check}") == "free", (check, costs.get(f"LNK/{check}"))
    for check in MODEL:
        assert costs.get(f"LNK/{check}") == "model", (check, costs.get(f"LNK/{check}"))


def test_every_lnk_check_is_filed_under_the_links_part():
    from clauditseo import anatomy

    assert "links" in anatomy.BY_KEY, sorted(anatomy.BY_KEY)
    for check in FREE + MODEL:
        # Through the resolver, because `redirect-chain` is raised by two
        # dimensions and means two things: TEC's is about reaching a page,
        # LNK's about a link that points through a chain.
        assert anatomy.categorise(check, "LNK") == "links", check
    assert anatomy.categorise("redirect-chain", "TEC") == "crawl"
    # And the part is no longer analysis-only: eight checks now cover it.
    assert "links" not in anatomy.ANALYSIS_ONLY, anatomy.ANALYSIS_ONLY


def test_the_dimension_carries_half_of_on_pages_weight():
    """Stated as a relation, not as a number.

    The decision was "half of ONP", and pinning `0.11` would pass while
    ONP moved to 0.24 and LNK stayed where it was - which is the decision
    being quietly unmade by a change to a different line.
    """
    from clauditseo.engine import scoring

    weights = scoring.DEFAULT_WEIGHTS
    assert weights["LNK"] == round(weights["ONP"] / 2, 2), weights
    assert weights["LNK"] > 0, (
        "a dimension at weight zero is the product saying internal linking "
        "does not affect ranking")

# --- LNK/hub-unlinked (item 136q) ----------------------------------------
#
# The record is the authority. This check reads `sub_services`, `locations`
# and `authors` for a name and a URL, and the brand for `id_page_uri`; it
# never infers an entity from the site's own words. That is the line the
# AI-surface brief draws, and this is the structural half of it.


def _run_with(site, *pages):
    from clauditseo.modules.links import LinksModule

    crawl = _crawl(*pages)
    return _by_check(LinksModule().run(list(crawl.pages), Tier.T2,
                                       {"crawl": crawl, "site": site}))


def _site(**kw):
    return Site(domain="links.test", **kw)


HUB = {"name": "Bridging finance", "url": BASE + "/bridging"}


def test_a_page_owning_an_entity_with_no_hub_link_fires():
    got = _run_with(
        _site(sub_services=[HUB]),
        _page("/bridging", "<h1>Bridging finance</h1>"),
        _page("/guide", "<p>Our Bridging finance guide.</p>"
                        "<a href='/contact'>Contact</a>"),
        _page("/contact", "<p>Call us.</p>"))
    rows = got.get("hub-unlinked") or []
    assert len(rows) == 1, got.keys()
    ev = rows[0].evidence
    assert ev["entity"] == "Bridging finance"
    assert ev["disconnected"] == [BASE + "/guide"], ev


def test_a_link_in_either_direction_is_a_connection():
    """A spoke linking up and a hub linking down are both a cluster.
    Requiring the spoke to link up would report a well-built hub page as a
    fault on every page it serves."""
    up = _run_with(
        _site(sub_services=[HUB]),
        _page("/bridging", "<h1>Bridging finance</h1>"),
        _page("/guide", "<p>Bridging finance</p><a href='/bridging'>hub</a>"))
    assert "hub-unlinked" not in up, up

    down = _run_with(
        _site(sub_services=[HUB]),
        _page("/bridging", "<h1>Bridging finance</h1>"
                           "<a href='/guide'>the guide</a>"),
        _page("/guide", "<p>Bridging finance</p>"))
    assert "hub-unlinked" not in down, down


def test_a_render_only_link_does_not_fire_here():
    """Initial HTML only. `link_details` is the parsed anchor set, and a
    link that appears only after render is `TEC/links-behind-js` - one page
    on two rows for one cause is what saying it twice would produce.

    The page below carries the link in a script, which is where a
    render-only link lives before it is rendered: the check must not see it
    as an anchor, and must not see the name inside the script as the page
    mentioning the entity either.
    """
    got = _run_with(
        _site(sub_services=[HUB]),
        _page("/bridging", "<h1>Bridging finance</h1>"),
        _page("/quiet", "<script>var t='Bridging finance';"
                        "document.write('<a href=\"/bridging\">x</a>')</script>"))
    assert "hub-unlinked" not in got, (
        "the script's text was read as the page naming the entity")


def test_no_url_on_the_record_entry_is_not_assessable():
    """An entity the record gave no URL is a question nobody can answer.
    It is named on the row rather than dropped, because a reader counting
    rows would otherwise read its silence as a pass."""
    got = _run_with(
        _site(sub_services=[HUB, {"name": "Equipment finance"}]),
        _page("/bridging", "<h1>Bridging finance</h1>"),
        _page("/guide", "<p>Bridging finance and Equipment finance.</p>"))
    row = (got.get("hub-unlinked") or [])[0]
    assert row.evidence["not_assessable"] == ["Equipment finance"], row.evidence
    # And no row is raised FOR the entity with no hub.
    assert [r.evidence["entity"] for r in got["hub-unlinked"]] == ["Bridging finance"]


def test_an_anchor_naming_something_else_appears_in_the_optional_field():
    """A link that exists but whose anchor names another entity is a weaker
    observation than no link at all, and is reported beside the row rather
    than as the fault."""
    got = _run_with(
        _site(sub_services=[HUB]),
        _page("/bridging", "<h1>Bridging finance</h1>"),
        _page("/guide", "<p>Bridging finance</p>"
                        "<a href='/bridging'>read more</a>"),
        _page("/other", "<p>Bridging finance here.</p>"))
    row = (got.get("hub-unlinked") or [])[0]
    assert row.evidence["disconnected"] == [BASE + "/other"], row.evidence
    assert row.evidence["anchors_naming_something_else"] == [
        {"page": BASE + "/guide", "anchor": "read more"}], row.evidence


def test_a_record_naming_no_entity_raises_nothing():
    """Both live sites are in this state today: `sub_services`, `locations`,
    `authors` and `id_page_uri` are all NULL on Acme and on Birch. The
    check has nothing to read and says nothing - it does not invent an
    entity from the site's own words."""
    got = _run_with(_site(), _page("/", "<p>Bridging finance</p>"))
    assert "hub-unlinked" not in got, got


def test_the_entity_name_is_matched_on_a_word_boundary():
    got = _run_with(
        _site(sub_services=[{"name": "Birch", "url": BASE + "/birch"}]),
        _page("/birch", "<h1>Birch</h1>"),
        _page("/other", "<p>We visited Birchwood last year.</p>"))
    assert "hub-unlinked" not in got, (
        "`Birchwood` was read as a mention of `Birch`")
