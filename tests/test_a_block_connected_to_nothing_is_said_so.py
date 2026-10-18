"""`schema-island` — the sweep says when a block reaches nothing else.

Brief v16a step AT-a. Before this, a page whose three `<script>` blocks
never mention each other looked, in the record, exactly like a page whose
blocks are wired: `schema-orphan-instance` asks a different question (does
an instance describing the entity reference the canonical `@id`), and no
check asked this one at all.

INFO rather than a defect severity, because it is a reading of the graph's
shape. A `SpeakableSpecification` sitting on its own is a fact; whether a
node adrift ought to be wired to something is the brief's judgement, and
the row exists so the brief and the operator both know it is there.

The island rule itself is `schema_graph`'s, called rather than repeated —
two implementations of one rule is how a card and a row end up saying
different things about the same node.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clauditseo.engine.types import Severity
from clauditseo.modules import onp

EXAMPLES = Path(__file__).resolve().parent / "fixtures" / "schema_examples"


class _Facts:
    """Only what `_islands` reads. A whole `PageFacts` would carry forty
    fields none of this rule touches, and building one would say this check
    depends on them."""

    def __init__(self, blocks: list[str], url: str, path: str = "/") -> None:
        self.jsonld_blocks = blocks
        self.url = url
        self.path = path


def _raw(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def test_the_check_is_registered_as_information_and_not_as_a_defect():
    assert onp.DEFAULT_SEVERITY["schema-island"] is Severity.INFO
    assert "schema-island" not in onp.BRIEF_ONLY_CHECKS, (
        "an island is derivable from the JSON, so the sweep answers it free; "
        "listing it brief-only would make an operator pay for arithmetic")


def test_a_wired_page_has_no_islands_at_all():
    """Voltaic's five nodes all reference one another. A check that fired here
    would be reporting the healthiest graph in the pack as broken."""
    facts = _Facts([_raw("1_thin_but_wired.json")],
                   "https://www.13acme.com.au/")
    assert onp._islands(facts, None) == []


def test_three_blocks_that_never_mention_each_other_are_three_islands():
    """Acme's home page: an Organization, a FinancialProduct and an
    FAQPage in three separate scripts, none carrying an `@id` and none
    referencing anything. The `provider` on the FinancialProduct looks like
    a connection and is not — it is a second copy of the entity written
    inline, which is why an edge to an inline copy does not count."""
    blocks = json.loads(_raw("3_disjointed_three_blocks.json"))
    facts = _Facts([json.dumps(b) for b in blocks], "https://www.acme.com.au/")
    islands = onp._islands(facts, None)
    assert sorted(n.types[0] for n in islands) == [
        "FAQPage", "FinancialProduct", "Organization"]


def test_a_node_referenced_only_from_inside_itself_is_still_an_island():
    """Summit's FAQPage and ItemList. Its entity is not an island even
    though nothing outside the block points at it, because its own lists
    reference it — the rejected definition would have called the page's one
    healthy node adrift."""
    facts = _Facts([_raw("2_rich_but_fragmented.json")],
                   "https://summit-roofing-fixture.com.au/")
    islands = onp._islands(facts, None)
    assert sorted(n.types[0] for n in islands) == ["FAQPage", "ItemList"]


def test_markup_that_does_not_parse_produces_no_island_rows():
    """That is `schema-invalid-json`'s finding. Counting it twice would put
    two rows in front of an operator for one broken block."""
    facts = _Facts(["{not json", ""], "https://x.test/")
    assert onp._islands(facts, None) == []


def test_a_page_with_no_markup_says_nothing_rather_than_nothing_wrong():
    facts = _Facts([], "https://x.test/")
    assert onp._islands(facts, None) == []


@pytest.mark.parametrize("consumer", ["anatomy", "plain-name", "brief"])
def test_the_new_check_reaches_every_place_a_check_has_to_reach(consumer):
    """Enumerated rather than assumed (DISCIPLINE rule 3). A check id that
    the registry knows and the category map does not is a finding with no
    part; one the dashboard does not name is a card headed by a slug."""
    if consumer == "anatomy":
        from clauditseo import anatomy
        assert anatomy.categorise("schema-island", "ONP") == "schema"
    elif consumer == "plain-name":
        src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
               / "part_page.tsx").read_text(encoding="utf-8")
        assert '"schema-island": "' in src
    else:
        from clauditseo import briefs
        from clauditseo.analysts.expert import SCHEMA_CHECKS
        assert "schema-island" in SCHEMA_CHECKS
        assert "ONP/schema-island" in briefs.by_id()["structured-data"].checks
