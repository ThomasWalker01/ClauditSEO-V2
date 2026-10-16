"""The Headings guards hold what a page cannot support (item 268, row 7).

On twenty22 `h1-triple-restated` was `high` on `/`, a page typed `other` with
no triple; `h1-title-verbatim` fired on `/` where the H1 and the title
differ; and with no page typed `location`, `h2-location-service` and
`h3-geo-map` drew eight holds and two footers. The reader now holds the
first, drops the second, and says the location checks once, as not run.
"""

from __future__ import annotations

from clauditseo.analysts import contract
from clauditseo.analysts.contract import Rules


def _row(check, page="/"):
    return contract.Row(check=check, dimension="ONP", check_id=check.split("/")[1],
                        page=page, status="FAIL", severity="high",
                        evidence="e", replacement="New H1", note="")


def test_a_page_typed_other_holds_the_triple_check():
    rules = Rules(page_facts={"/": {"type": "other", "h1": "Hello", "title": "Hi there"}})
    kind, why = contract._headings_guard(_row("ONP/h1-triple-restated"), rules)
    assert kind == "hold" and "typed other" in why


def test_a_differing_h1_and_title_refute_verbatim():
    rules = Rules(page_facts={"/": {"type": "service", "h1": "Web design",
                                    "title": "Twenty22 Website and SEO"}})
    kind, why = contract._headings_guard(_row("ONP/h1-title-verbatim"), rules)
    assert kind == "drop" and "differ" in why
    same = Rules(page_facts={"/": {"type": "service", "h1": "Web Design!", "title": "web design"}})
    assert contract._headings_guard(_row("ONP/h1-title-verbatim"), same) is None


def test_the_location_checks_are_said_once_where_no_page_is_a_location():
    import inspect
    src = inspect.getsource(contract.enforce)
    assert "no page on the site record is typed location" in src


def _said(evidence, note="", status="FAIL"):
    r = _row("ONP/h1-triple-restated", page="/x/")
    r.evidence, r.note, r.status = evidence, note, status
    return contract._headings_guard(r, Rules())


def test_a_page_with_no_triple_is_held_whatever_its_status():
    # Screen audits round 3, Headings AC-01 and AC-02: twenty22's `/` came
    # back PASS-OVERRIDE "no page triple supplied", drawn as a verdict closing
    # nothing, and `/website-seo/` led the part as its one `high` on
    # "location_entity n/a per TRIPLES, primary_entity also n/a".
    kind, why = _said('h1 "SEO" - no page triple supplied (page_type other, primary_entity n/a)',
                      status="PASS-OVERRIDE")
    assert kind == "hold" and why == contract.TRIPLE_NONE
    kind, why = _said('h1 "Search Engine Optimisation" - location entity absent '
                      "(location_entity n/a per TRIPLES, primary_entity also n/a)")
    assert kind == "hold" and "the GBP primary category" in why


def test_a_missing_location_alone_is_a_record_blank_not_a_fault():
    kind, why = _said('h1 "WebSite Design" - names primary entity (Website Design) but '
                      "location entity absent (n/a per TRIPLES)", status="WARN")
    assert kind == "hold" and "location entity" in why and "location pages" in why


def test_an_h1_that_misses_its_primary_entity_still_stands():
    # The row has a fault of its own besides the blank: it stays a row.
    assert _said('h1 "Update Your Website" - names a generic action, not clearly the '
                 'primary_entity "Website Redesign" per TRIPLES, and location entity absent',
                 note="location entity still absent (n/a)", status="WARN") is None
    assert _said('h1 "Gate Six" - brand only, primary entity absent') is None
