"""The Links brief is handed each page's triple (item 271, row 13).

The crawl stores no triple, so the Links page set read "-" on every page,
and the model held `anchor-entity` on every page to say so - a paid row
saying the record is empty. The engine fills each page's triple from the
site record, and leaves "-" only where the record holds neither a category
nor the page's location.
"""

from __future__ import annotations

from types import SimpleNamespace

from clauditseo.analysts.expert import _record_triples


def test_the_record_fills_the_triple():
    site = SimpleNamespace(brand="Birch", gbp_primary_category="Event planner",
                           location_pages=[{"url": "https://b.co/sydney/", "location_entity": "Sydney"}])
    of = _record_triples(site, "https://b.co/")
    assert of("https://b.co/sydney/") == "Birch · Event planner · Sydney"
    assert of("https://b.co/about/") == "Birch · Event planner · -"
    empty = _record_triples(SimpleNamespace(brand="Birch"), "https://b.co/")
    assert empty("https://b.co/") is None
