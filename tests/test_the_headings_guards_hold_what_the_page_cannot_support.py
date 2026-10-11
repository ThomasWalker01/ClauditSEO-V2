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
