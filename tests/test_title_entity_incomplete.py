"""`ONP/title-entity-incomplete` — does the title name what the page owns?

Item 136q commit 5. Three observable properties, each `True`, `False` or
`"n/a"`.

**`"n/a"` is not a soft failure**, and that is the whole design. Where the site
record supplies nothing to test against — no entity owning this page, no brand,
no location scope — the question cannot be asked, and answering `False` would
report the operator's empty record as the site's fault. On both live sites
today only `brand` is set, so this check asks one of its three questions and the
row says which.
"""

from __future__ import annotations

from clauditseo.crawler.types import CrawlResult, Page, Tier
from clauditseo.engine.types import Site
from clauditseo.modules.onp import OnPageModule, TITLE_MAX

BASE = "https://titles.test"


def _page(path: str, title: str) -> Page:
    return Page(url=BASE + path, requested_url=BASE + path, status=200,
                content_type="text/html; charset=utf-8",
                content=f"<html><head><title>{title}</title></head>"
                        f"<body><h1>x</h1><p>words</p></body></html>")


def _rows(site, *pages):
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend(pages)
    return [f for f in OnPageModule().run(list(crawl.pages), Tier.T2,
                                          {"crawl": crawl, "site": site})
            if f.check_id == "title-entity-incomplete"]


HUB = {"name": "Bridging finance", "url": BASE + "/bridging"}


def test_owned_entity_in_title_passes_names_entity():
    site = Site(domain="titles.test", brand="Acme", sub_services=[HUB])
    got = _rows(site, _page("/bridging", "Bridging finance | Acme"))
    assert got == [], got


def test_brand_absent_fails_names_brand():
    site = Site(domain="titles.test", brand="Acme", sub_services=[HUB])
    got = _rows(site, _page("/bridging", "Bridging finance"))
    assert len(got) == 1, got
    crit = got[0].evidence["criteria"]
    assert crit["names_entity"] is True and crit["names_brand"] is False, crit
    assert "the brand" in got[0].summary, got[0].summary


def test_no_location_scope_is_n_a():
    """A service page that names no suburb is not incomplete — it is not
    about a suburb. `n/a`, never `False`."""
    site = Site(domain="titles.test", brand="Acme", sub_services=[HUB],
                locations="Richmond")
    got = _rows(site, _page("/bridging", "Bridging finance"))
    crit = got[0].evidence["criteria"]
    assert crit["names_place"] == "n/a", crit


def test_a_location_scoped_page_does_ask_for_the_place():
    site = Site(domain="titles.test", brand="Acme", locations="Richmond",
                page_types={"/branch": "location"})
    got = _rows(site, _page("/branch", "Our branch | Acme"))
    crit = got[0].evidence["criteria"]
    assert crit["names_place"] is False, crit
    assert crit["names_brand"] is True, crit


def test_an_empty_record_asks_nothing_and_raises_nothing():
    """Both live sites are close to this: `sub_services`, `locations` and
    `id_page_uri` are NULL on Acme and Birch, and only `brand` is set. A
    record that supplies nothing at all must not produce a finding."""
    got = _rows(Site(domain="titles.test"), _page("/x", "Some title"))
    assert got == [], got


def test_the_replacement_uses_the_record_and_fits_the_bound():
    site = Site(domain="titles.test", brand="Acme", sub_services=[HUB])
    got = _rows(site, _page("/bridging", "Bridging finance"))
    rep = got[0].evidence["replacement"]
    assert "Acme" in rep and "Bridging finance" in rep, rep
    assert len(rep) <= TITLE_MAX, (len(rep), TITLE_MAX)


def test_a_recorded_variant_counts_as_naming_the_entity():
    site = Site(domain="titles.test", brand="Acme", sub_services=[HUB],
                entity_variants={"Bridging finance": ["bridging loans"]})
    got = _rows(site, _page("/bridging", "Bridging loans | Acme"))
    assert got == [], got


def test_the_check_is_free_and_lives_in_title_and_description():
    """The item calls it "analysis where a title template is supplied". The
    contract already settles what that means: a check the sweep emits is free
    whether or not a brief also reads it, because the brief adds reading to a
    finding that exists rather than creating one."""
    from clauditseo.anatomy import CHECK_CATEGORY
    from clauditseo.checks import check_cost

    assert check_cost("ONP/title-entity-incomplete") == "free"
    assert CHECK_CATEGORY["title-entity-incomplete"] == "title-desc"
