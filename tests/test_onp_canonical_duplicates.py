"""A duplicate-title group must not count a page that canonicalises away.

A page declaring `rel=canonical` to another page in the same crawl is an alias
of its target, not a competitor for its target's query: the search engine
collapses the two. Raising `title-duplicate` over such a pair told a client to
"differentiate each title" about a filtered view of one page — advice that
cannot be followed. The crawler has stored the canonical on every page record
since the beginning; only this check was not reading it.

Every variant here is spelled with an addressing parameter — `product_type`,
not `utm_source`. That is deliberate and answered: `QUESTIONS.md` Q-29, *move
them* (operator, 2026-08-31). Relay 101 teaches `normalise_url` to strip
tracking parameters, so a `?utm_source=` variant folds onto its base before
this check ever sees two URLs, and a fixture spelled that way asserts over a
population of one while still passing. Do not spell a variant with a tracking
key here.
"""

from __future__ import annotations

import pytest

from clauditseo.modules.onp import OnPageModule
from clauditseo.modules.pagefacts import PageFacts

BASE = "https://example.test"
SHARED = "Apply for a business loan"


def _facts(path: str, title: str = SHARED, canonical: str | None = None,
           header_canonical: str | None = None) -> PageFacts:
    from urllib.parse import urlsplit
    url = BASE + path
    f = PageFacts(url=url, path=urlsplit(url).path or "/")
    f.title = title
    f.canonical = canonical
    f.link_header_canonical = header_canonical
    return f


def _ids(facts: list[PageFacts]) -> list[str]:
    return [f.check_id for f in OnPageModule()._duplication_checks(facts)]


def _findings(facts: list[PageFacts], check_id: str):
    return [f for f in OnPageModule()._duplication_checks(facts)
            if f.check_id == check_id]


def test_two_distinct_pages_sharing_a_title_still_raise():
    """The check the change must not weaken."""
    facts = [_facts("/dup-a", canonical=BASE + "/dup-a"),
             _facts("/dup-b", canonical=BASE + "/dup-b")]
    assert "title-duplicate" in _ids(facts)


def test_a_variant_canonicalising_to_a_crawled_base_does_not_raise():
    facts = [_facts("/apply", canonical=BASE + "/apply"),
             _facts("/apply?product_type=loc", canonical=BASE + "/apply")]
    assert "title-duplicate" not in _ids(facts)
    assert "canonical-missing-variant" not in _ids(facts)


def test_a_canonical_delivered_as_a_link_header_counts_the_same():
    facts = [_facts("/apply", canonical=BASE + "/apply"),
             _facts("/apply?product_type=loc", header_canonical=BASE + "/apply")]
    assert "title-duplicate" not in _ids(facts)


def test_a_relative_canonical_resolves_against_the_page_url():
    facts = [_facts("/apply", canonical="/apply"),
             _facts("/apply?product_type=loc", canonical="/apply")]
    assert "title-duplicate" not in _ids(facts)


def test_a_variant_with_no_canonical_raises_the_new_check_not_the_old_one():
    facts = [_facts("/apply", canonical=BASE + "/apply"),
             _facts("/apply?product_type=loc", canonical=None)]
    ids = _ids(facts)
    assert "title-duplicate" not in ids
    assert "canonical-missing-variant" in ids
    raised = _findings(facts, "canonical-missing-variant")[0]
    assert raised.affected_urls == [BASE + "/apply?product_type=loc"]
    assert "canonical" in raised.recommendation.lower()
    assert raised.evidence["base"] == BASE + "/apply"


def test_a_variant_whose_base_was_never_crawled_is_still_a_competitor():
    """The base is absent, so nothing here can be shown to be an alias."""
    facts = [_facts("/other", canonical=BASE + "/other"),
             _facts("/apply?product_type=loc", canonical=None)]
    ids = _ids(facts)
    assert "title-duplicate" in ids
    assert "canonical-missing-variant" not in ids


def test_a_canonical_target_outside_the_crawl_leaves_the_page_a_member():
    """The stated decision: an unverifiable claim does not suppress a finding."""
    facts = [_facts("/dup-a", canonical=BASE + "/dup-a"),
             _facts("/dup-b", canonical=BASE + "/never-crawled")]
    assert "title-duplicate" in _ids(facts)


def test_a_self_canonical_page_stays_a_member():
    facts = [_facts("/dup-a", canonical=BASE + "/dup-a"),
             _facts("/dup-b", canonical=BASE + "/dup-b/")]
    assert "title-duplicate" in _ids(facts)


def test_the_surviving_finding_names_only_the_competitors():
    facts = [_facts("/dup-a", canonical=BASE + "/dup-a"),
             _facts("/dup-b", canonical=BASE + "/dup-b"),
             _facts("/dup-b?product_type=loc", canonical=BASE + "/dup-b")]
    # One row per member page since brief v11 step AH, each carrying the
    # group and naming the competitors in its evidence.
    raised = _findings(facts, "title-duplicate")
    assert [r.affected_urls for r in raised] == [[BASE + "/dup-a"], [BASE + "/dup-b"]]
    assert all(r.evidence["paths"] == ["/dup-a", "/dup-b"] for r in raised)
    assert all(r.evidence["canonical_aliases"] == ["/dup-b?product_type=loc"] for r in raised)
    assert raised[0].summary.startswith("/dup-a shares its title")


def test_meta_description_groups_follow_the_same_rule():
    a = _facts("/apply", title="Apply", canonical=BASE + "/apply")
    b = _facts("/apply?product_type=loc", title="Apply — LOC",
               canonical=BASE + "/apply")
    a.meta_description = b.meta_description = "One description, two URLs."
    assert "meta-desc-duplicate" not in _ids([a, b])


def test_a_variant_is_reported_once_even_when_title_and_description_both_match():
    a = _facts("/apply", canonical=BASE + "/apply")
    b = _facts("/apply?product_type=loc", canonical=None)
    a.meta_description = b.meta_description = "One description, two URLs."
    assert _ids([a, b]).count("canonical-missing-variant") == 1


# --- through the module, not only the private helper -------------------------

def _page(path: str, title: str, canonical: str | None):
    from clauditseo.crawler.types import Page
    link = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    return Page(
        url=BASE + path, requested_url=BASE + path, status=200,
        headers={"content-type": "text/html"}, content_type="text/html",
        content=f"<html><head><title>{title}</title>{link}</head>"
                f"<body><h1>{title}</h1><p>Body copy.</p></body></html>",
    )


def _run(pages):
    from clauditseo.crawler.types import CrawlResult
    from clauditseo.engine.types import Tier
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2, pages=pages)
    return OnPageModule().run(pages, Tier.T2, {"crawl": crawl})


def test_the_variant_finding_replaces_the_generic_canonical_missing_one():
    """One URL, one canonical finding: the specific one, which names the page
    it duplicates and so can be acted on."""
    findings = _run([_page("/apply", SHARED, BASE + "/apply"),
                     _page("/apply?product_type=loc", SHARED, None)])
    variant = BASE + "/apply?product_type=loc"
    assert any(f.check_id == "canonical-missing-variant"
               and f.affected_urls == [variant] for f in findings)
    assert not any(f.check_id == "canonical-missing"
                   and variant in f.affected_urls for f in findings)


def test_a_page_missing_a_canonical_with_no_duplicate_still_reports_it():
    """The generic check gives way only where the specific one replaced it."""
    findings = _run([_page("/apply", SHARED, BASE + "/apply"),
                     _page("/lonely", "A title all of its own", None)])
    assert any(f.check_id == "canonical-missing"
               and f.affected_urls == [BASE + "/lonely"] for f in findings)
