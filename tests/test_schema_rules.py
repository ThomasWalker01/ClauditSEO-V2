"""Structured-data validation: real checks, not "does it parse".

The prompting case for this module: an advisor recommended FAQPage "to
capture rich-result eligibility" — markup that earned no rich result. FAQ was
narrowed to authoritative government and health sites in 2023 and stopped
appearing for anyone on 7 May 2026. Deprecation facts therefore live in
deterministic, tested code rather than in a model's recollection.

The tests at the foot of this file guard the other half of that idea: a fact
table only beats recollection while someone is checking it against the source,
so the entries carry their source and the day it was read, and one test fails
when they age past the review window.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import clauditseo.modules  # noqa: F401
from clauditseo import schema_rules
from clauditseo.analysts.schema_advisor import validate_audit
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.schema_rules import audit_entities, parse_blocks, types_of
from tests.conftest import FixtureSite

FAST = TierBudget(max_pages=10, request_timeout_s=5, wall_clock_s=30, delay_s=0)


def _kinds(entities):
    return {(i["kind"], i.get("type")) for i in audit_entities(entities)}


def test_graph_and_array_blocks_are_flattened():
    entities, errors = parse_blocks([
        '{"@context":"https://schema.org","@graph":['
        '{"@type":"Organization","name":"A"},{"@type":"WebSite","name":"B"}]}',
        '[{"@type":"BreadcrumbList","itemListElement":[]}]',
    ])
    assert errors == []
    assert {t for e in entities for t in types_of(e)} == {
        "Organization", "WebSite", "BreadcrumbList"}


def test_deprecated_rich_results_are_flagged():
    entities, _ = parse_blocks(['{"@type":"FAQPage","mainEntity":[]}'])
    issues = audit_entities(entities)
    faq = next(i for i in issues if i["kind"] == "deprecated-rich-result")
    assert faq["type"] == "FAQPage"
    # Read from the table, not pinned to a string. This assertion used to
    # spell out "August 2023", which meant correcting a wrong date broke the
    # test that was supposed to protect it — a test can quietly become the
    # reason a stale fact stays put.
    assert faq["changed"] == schema_rules.DEPRECATED_RICH_RESULTS["FAQPage"]["changed"]
    assert faq["severity_hint"] == "info"      # harmless to keep, not an error
    assert "no rich result" in faq["summary"]

    howto, _ = parse_blocks(['{"@type":"HowTo","name":"x","step":[]}'])
    assert ("deprecated-rich-result", "HowTo") in _kinds(howto)


def test_deprecated_sitelinks_search_box_is_flagged():
    entities, _ = parse_blocks([
        '{"@type":"WebSite","name":"x","url":"https://x.example",'
        '"potentialAction":{"@type":"SearchAction","target":"https://x.example?q="}}'
    ])
    assert ("deprecated-rich-result", "SearchAction") in _kinds(entities)


def test_required_and_one_of_properties():
    entities, _ = parse_blocks(['{"@type":"Product","description":"a widget"}'])
    kinds = _kinds(entities)
    assert ("missing-required", "Product") in kinds      # name
    assert ("missing-one-of", "Product") in kinds        # offers/review/rating

    complete, _ = parse_blocks([
        '{"@type":"Product","name":"Widget","image":"https://x/i.jpg",'
        '"description":"d","brand":"B","offers":{"@type":"Offer","price":"10"}}'])
    assert not [i for i in audit_entities(complete)
                if i["kind"] in ("missing-required", "missing-one-of")]


def test_localbusiness_subtypes_inherit_requirements():
    entities, _ = parse_blocks(['{"@type":"RoofingContractor","name":"Acme"}'])
    missing = next(i for i in audit_entities(entities)
                   if i["kind"] == "missing-required")
    assert "address" in missing["properties"]


def test_untyped_and_duplicate_ids():
    entities, _ = parse_blocks(['{"name":"no type here"}'])
    assert ("untyped-entity", None) in _kinds(entities)

    dupes, _ = parse_blocks([
        '[{"@type":"Organization","@id":"https://x/#org","name":"A"},'
        ' {"@type":"Organization","@id":"https://x/#org","name":"B"}]'])
    assert ("duplicate-id", None) in _kinds(dupes)


def test_schema_findings_reach_the_engine():
    """End to end: a page with FAQPage plus an incomplete Product produces
    ONP schema findings, not just a parse check."""
    markup = ('<script type="application/ld+json">'
              '{"@context":"https://schema.org","@graph":['
              '{"@type":"FAQPage","mainEntity":[]},'
              '{"@type":"Product","description":"no name or offer"}]}</script>')
    page = ('<html><head><title>Schema Fixture Page Title</title>'
            '<meta name="description" content="Fixture with structured data.">'
            '<meta name="viewport" content="width=device-width">'
            '<link rel="canonical" href="/"></head>'
            f'<body><h1>Schema</h1><p>Body copy for the fixture.</p>{markup}'
            '</body></html>')
    site = FixtureSite({
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/": (200, {}, page),
    }).start()
    try:
        crawl_result = crawl(site.base_url + "/", Tier.T1, budget=FAST)
    finally:
        site.stop()
    result = run_audit(Site(domain="schema.fixture"), crawl_result, ["ONP"], Tier.T1)
    checks = {f.check_id for f in result.findings}
    assert "schema-deprecated-rich-result" in checks
    assert "schema-missing-required" in checks
    assert "schema-missing-one-of" in checks
    faq = next(f for f in result.findings
               if f.check_id == "schema-deprecated-rich-result")
    assert schema_rules.DEPRECATED_RICH_RESULTS["FAQPage"]["changed"] in faq.summary


# --- advisor ingest ---------------------------------------------------------

def _bundle(page_text="Roofing repairs in Melbourne.", existing="{}") -> dict:
    return {"page": {"untrusted_page_text": page_text, "title_tag": "t"},
            "existing_structured_data": {"entities": [existing]}}


def test_audit_flags_invented_figures_but_allows_placeholders():
    bad = {"verdict": [], "corrected_jsonld":
           '{"@type":"Product","aggregateRating":{"ratingValue":"4.8",'
           '"reviewCount":"312"}}'}
    problems = validate_audit(bad, _bundle())
    assert any("4.8" in p or "312" in p for p in problems)

    ok = {"verdict": [], "corrected_jsonld":
          '{"@type":"Product","aggregateRating":'
          '{"ratingValue":"[TO CONFIRM: aggregateRating.ratingValue]"}}'}
    assert validate_audit(ok, _bundle()) == []


def test_opening_hours_times_are_structural_not_invented_figures():
    """"opens": "07:00" is the ISO rendering of a visible "7am"; no literal
    match against page text could confirm it, so times must not be flagged."""
    hours = {"verdict": [], "corrected_jsonld":
             '{"@type":"LocalBusiness","openingHoursSpecification":'
             '[{"@type":"OpeningHoursSpecification","opens":"07:00",'
             '"closes":"17:30"}]}'}
    assert validate_audit(hours, _bundle()) == []


def test_audit_rejects_claiming_eligibility_for_a_deprecated_type():
    claim = {"verdict": [{"rich_result": "FAQ rich result", "status": "ELIGIBLE",
                          "reason": "FAQPage markup present"}],
             "corrected_jsonld": "{}"}
    problems = validate_audit(claim, _bundle())
    changed = schema_rules.DEPRECATED_RICH_RESULTS["FAQPage"]["changed"]
    assert any("FAQPage" in p and changed in p for p in problems)

    honest = {"verdict": [{"rich_result": "FAQ rich result",
                           "status": "NOT AVAILABLE",
                           "reason": "no longer shown for any site"}],
              "corrected_jsonld": "{}"}
    assert validate_audit(honest, _bundle()) == []


def test_audit_rejects_unparseable_jsonld():
    broken = {"verdict": [], "corrected_jsonld": '{"@type":"Product",'}
    assert any("does not parse" in p for p in validate_audit(broken, _bundle()))


# --- currency of the fact table -------------------------------------------
# The point of schema_rules is to stop an analyst reciting stale deprecation
# facts. It had the same disease: three dates recalled from training data
# rather than read from Google, sitting unchallenged for as long as nobody
# happened to look. These are the guards that make that loud.

def test_every_fact_names_its_source_and_when_it_was_read():
    """An entry recording *when* something changed but not *where* that was
    published cannot be checked, which is how three wrong dates survived."""
    for label, info in schema_rules.dated_entries().items():
        assert info.get("source", "").startswith("https://developers.google.com/"), (
            f"{label} has no Google source URL to check it against")
        datetime.strptime(info["verified"], "%Y-%m-%d")  # raises if malformed


def test_no_entry_has_aged_past_its_review_window():
    """Fails on the passage of time, deliberately.

    It cannot tell whether Google changed anything — nothing offline can. It
    refuses to let a table whose entire job is currency go unexamined, the
    same reason CI fails when the accessibility sweep skips rather than runs.

    To clear it: open each URL below, confirm or correct the entry, and set
    `verified` to today. Do not just bump the date.
    """
    stale = schema_rules.stale_entries()
    assert not stale, (
        f"{len(stale)} schema fact(s) unchecked for more than "
        f"{schema_rules.REVIEW_AFTER_DAYS} days:\n"
        + "\n".join(f"  {label} — {days} days old, check {url}"
                    for label, days, url in stale))


def test_the_staleness_gate_actually_fires():
    """A gate nobody has watched fail is a gate nobody knows works."""
    future = date.today() + timedelta(days=schema_rules.REVIEW_AFTER_DAYS + 1)
    assert schema_rules.stale_entries(today=future), "the review window never trips"


def test_the_advisor_is_told_how_old_the_table_is():
    """The framing tells the model to prefer this table over its own
    recollection. That is right while it is fresh and exactly wrong once it is
    not, so the bundle has to carry its own age."""
    assert "2026-" in schema_rules.verification_note()
    stale_note = schema_rules.verification_note()
    assert "checked" in stale_note.lower()


def test_a_withdrawn_feature_whose_type_is_still_useful_is_not_matched():
    """Course, VideoObject, Occupation and Vehicle all lost a rich result but
    remain legitimate markup. A review once proposed listing them as
    deprecated types; that would have told every site with a Course or a
    VideoObject that its markup was dead."""
    for still_fine in ("Course", "VideoObject", "Occupation", "Vehicle", "Car"):
        assert still_fine not in schema_rules.DEPRECATED_RICH_RESULTS
    entities, _ = parse_blocks(
        ['{"@type":"Course","name":"Intro","description":"d"}'])
    assert not [i for i in audit_entities(entities)
                if i["kind"] == "deprecated-rich-result"]
    # But the advisor must still know the feature is gone.
    assert "Course Info" in schema_rules.DEPRECATED_FEATURES


def test_book_actions_is_absent_on_purpose():
    """Listed as withdrawn in a review of this file. It was not — the
    deprecation banner came off because a Search feature still reads it."""
    assert "Book" not in schema_rules.DEPRECATED_RICH_RESULTS
    assert not [k for k in schema_rules.DEPRECATED_FEATURES if "Book" in k]


def test_faq_is_recorded_as_gone_for_everyone():
    """It sat at its 2023 state — "restricted to government and health sites" —
    for months after May 2026, when it stopped appearing for anybody. A report
    generated from that told clients FAQ markup still earned rich results for
    someone."""
    faq = schema_rules.DEPRECATED_RICH_RESULTS["FAQPage"]
    assert faq["status"] == "removed"
    assert "2026" in faq["changed"]
    assert "government" not in faq["instead"]


def test_jobposting_requires_everything_google_requires():
    """Listed three of five. A posting could pass here and still be ineligible."""
    required = set(schema_rules.REQUIRED_PROPERTIES["JobPosting"])
    assert {"title", "datePosted", "description", "hiringOrganization",
            "jobLocation"} == required
