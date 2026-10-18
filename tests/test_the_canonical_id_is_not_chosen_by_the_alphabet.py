"""The canonical @id is evidence, not alphabetical order (item 215).

With no `canonical_id` on the site record, the sweep took
`sorted(entity_ids)[0]`. On twenty22 that is `.../#local_business`, because
"l" sorts before "o", and it then raised `schema-orphan-instance` on every
page's Organization block for "declaring #organization rather than the
canonical #local_business" - 45 of 45 pages. The Structured data brief,
following its own principle, proposed `#organization`, and the part page
merged the two on (check, page) under "automatic checks and analysis agree":
43 cards whose Now and Replace-with named opposite nodes.

The rule now: one id is the only choice; an id ending `/#organization` is
the convention; else the id more nodes reference than any other; else the
orphan check is held and says what it needs.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.modules.onp import canonical_entity_id
from tests.test_the_structured_data_brief import BASE, _page, _site, _swept

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _node(kind: str, frag: str, extra: str = "") -> str:
    return (f'{{"@context":"https://schema.org","@type":"{kind}",'
            f'"@id":"{BASE}/#{frag}","name":"Entity Co"{extra}}}')


def _ref(frag: str) -> str:
    return (f'{{"@context":"https://schema.org","@type":"WebSite",'
            f'"@id":"{BASE}/#website","publisher":{{"@id":"{BASE}/#{frag}"}}}}')


def _orphans(found):
    return [f for f in found if f.check_id == "schema-orphan-instance"]


def test_the_organization_id_wins_over_one_that_sorts_first():
    """The twenty22 shape, reduced: both ids declared, neither on the record."""
    found = _swept([_page(BASE + "/", _node("LocalBusiness", "local_business")),
                    _page(BASE + "/about", _node("Organization", "organization"))])
    orphans = _orphans(found)
    assert orphans, "two entity ids for one business should raise an orphan"
    assert {f.evidence["canonical"] for f in orphans} == {f"{BASE}/#organization"}, (
        "the canonical was chosen by sorting, not by the brief's own convention: "
        f"{[f.evidence for f in orphans]}")
    assert {f.evidence["id"] for f in orphans} == {f"{BASE}/#local_business"}


def test_without_the_convention_the_most_referenced_id_is_the_canonical():
    ids = {f"{BASE}/#brand", f"{BASE}/#shop"}
    inventories = {f"{BASE}/p{n}": [{"id": f"{BASE}/#website", "type": "WebSite",
                                     "properties": {"publisher.@id": f"{BASE}/#shop"}}]
                   for n in range(3)}
    assert canonical_entity_id(ids, inventories) == f"{BASE}/#shop"


def test_one_id_is_the_only_choice_and_a_tie_is_no_choice():
    assert canonical_entity_id({f"{BASE}/#only"}, {}) == f"{BASE}/#only"
    assert canonical_entity_id({f"{BASE}/#a", f"{BASE}/#b"}, {}) is None


def test_when_the_markup_does_not_settle_it_the_orphan_check_is_held():
    found = _swept([_page(BASE + "/", _node("LocalBusiness", "shop")),
                    _page(BASE + "/about", _node("Organization", "brand"))])
    assert not _orphans(found), (
        f"orphans were raised against a canonical nothing chose: {_orphans(found)}")
    held = [f for f in found if f.check_id == "schema-orphan-not-assessed"]
    assert len(held) == 1, found
    assert held[0].evidence["status"] == "HELD"
    assert "site record" in held[0].evidence["needs"], held[0].evidence


def test_a_site_record_canonical_still_decides():
    site = _site(canonical_id=f"{BASE}/#local_business")
    found = _swept([_page(BASE + "/", _node("LocalBusiness", "local_business")),
                    _page(BASE + "/about", _node("Organization", "organization"))], site)
    assert {f.evidence["canonical"] for f in _orphans(found)} == {f"{BASE}/#local_business"}


def test_a_merged_card_says_agree_only_when_its_readings_do():
    """The part page's half, held on the source: the label is computed from
    the two readings, not from which sources raised the check."""
    src = (UI / "part_page.tsx").read_text(encoding="utf-8")
    assert "sourceWords(fix.sources, readingsDisagree(fix.current, fix.replacement))" in src
    assert "automatic checks and analysis disagree" in src
