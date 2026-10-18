"""The graph the engine builds reaches the part page's payload.

Brief v16a step AT-b, the data path. `build_model` existed after AT-a and
nothing carried its answer anywhere: the sweep called it for one finding and
the record kept `len(jsonld_blocks)`, so the picture could not have been
drawn from a stored crawl at all.

**Why the raw blocks and not the inventory.** `schema_inventory` flattens to
two levels and keeps a list's first member, which is the right shape for a
row about a property and the wrong one for a graph. Summit's fifteen
`provider` references live inside an `itemListElement`; none of them is in
the inventory, and a node wired only through one would be drawn adrift. The
assertion below is that count, measured against the inventory rather than
asserted about it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clauditseo.modules import pagefacts
from clauditseo.persistence import runs

EXAMPLES = Path(__file__).resolve().parent / "fixtures" / "schema_examples"


def _text(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def summit_text():
    return _text("2_rich_but_fragmented.json")


# --- the record keeps the blocks as served -------------------------------

def test_the_record_keeps_each_block_whole_and_names_its_source(summit_text):
    """A block is kept entire or not at all, with the source the markup
    names. Truncating one would produce markup that does not parse, and
    `schema-invalid-json` would then fire on a page whose markup is valid -
    a storage limit inventing a finding about the site."""
    kept = pagefacts.jsonld_raw([summit_text], ["yoast-schema-graph"])
    assert len(kept) == 1
    assert kept[0]["source"] == "plugin:yoast"
    # Whole: it still parses, and it parses to what was stored.
    assert json.loads(kept[0]["text"]) == json.loads(summit_text)


def test_a_block_past_the_byte_ceiling_is_dropped_rather_than_cut(monkeypatch,
                                                                  summit_text):
    monkeypatch.setattr(pagefacts, "JSONLD_RAW_BYTES", 10)
    kept = pagefacts.jsonld_raw([summit_text], [""])
    assert kept == []


def test_the_inventory_cannot_see_the_references_the_graph_is_built_from(
        summit_text):
    """The measurement behind storing the raw blocks (DISCIPLINE rule 2).

    Summit's `provider` references sit inside `hasOfferCatalog`'s
    `itemListElement`. The graph resolves fifteen of them; the flattened
    inventory carries none, because it stops at two levels and keeps the
    first member of a list.
    """
    inventory = pagefacts.schema_inventory([summit_text], [""])
    flat = json.dumps([row.get("properties") for row in inventory])
    assert flat.count('"provider"') == 0

    from clauditseo import schema_graph as sg
    model = sg.build_model(
        [{"source": "inline", "json": json.loads(summit_text)}], None,
        {"host": "summit-roofing-fixture.com.au", "page": "/", "page_type": "home"}, [])
    catalog = next(c for c in model.collections.values()
                   if c.prop == "hasOfferCatalog")
    assert catalog.count == 15


# --- the payload carries the model ---------------------------------------

def _facts(text: str) -> dict:
    return {"url": "https://www.summit-roofing-fixture.com.au/",
            "jsonld_raw": [{"source": "inline", "text": text}],
            "schema_inventory": pagefacts.schema_inventory([text], [""]),
            "profile_links": []}


def test_the_payload_carries_the_graph_the_engine_built(summit_text):
    payload = runs.schema_graph_payload(_facts(summit_text), [], [], "home")
    assert payload is not None
    # The numbers brief v16a states for this fixture, through the payload
    # rather than through `build_model` - the point of this guard is that
    # the two are the same answer.
    assert payload["verdict"]["entity"] == "FRAGMENTED"
    assert len([n for n in payload["nodes"] if n["island"]]) == 2
    assert len([g for g in payload["ghosts"]
                if g["kind"] == "ghost-dangling"]) == 2


def test_a_run_crawled_before_the_raw_blocks_existed_gets_no_graph():
    """`None`, and not an empty model. A crawl that predates `jsonld_raw`
    has nothing to draw, and an empty canvas would say the page has no
    markup - which is a different claim from "this run did not store it"."""
    assert runs.schema_graph_payload(
        {"url": "https://example.test/", "schema_inventory": []},
        [], [], "home") is None
    assert runs.schema_graph_payload(None, [], [], "home") is None


def test_a_block_that_does_not_parse_draws_nothing_and_is_not_an_error():
    facts = {"url": "https://example.test/", "schema_inventory": [],
             "jsonld_raw": [{"source": "inline", "text": "{not json"}]}
    assert runs.schema_graph_payload(facts, [], [], "home") is None


# --- anchors come off the rows, and are never invented --------------------

def test_a_rows_block_reference_pins_it_to_that_node(summit_text):
    facts = _facts(summit_text)
    inventory = facts["schema_inventory"]
    # The first inventory row that carries an `@id` is the node a row
    # naming `Type#n` should land on.
    n, entry = next((i + 1, row) for i, row in enumerate(inventory)
                    if row.get("id"))
    rows = [{"check_id": "ONP/schema-entity-thin", "severity": "medium",
             "summary": "Entity could say more", "source": "sweep",
             "block": "{}#{}".format(entry.get("type"), n)}]
    payload = runs.schema_graph_payload(facts, rows, [], "home")
    pinned = payload["findings"][0]
    assert pinned["anchor_keys"] == [entry["id"]]
    node = next(x for x in payload["nodes"] if x["key"] == entry["id"])
    assert node["findings"] == [1]


def test_a_row_naming_no_block_is_left_unpinned_rather_than_guessed(
        summit_text):
    """RENDER_RULES 7's rule one level up: an anchor that resolves to
    nothing is dropped, and a row that named nothing gets none. Pinning by
    `@type` alone would put a finding about one of three Organization nodes
    on all three."""
    rows = [{"check_id": "ONP/schema-sameas-missing", "severity": "low",
             "summary": "Profiles not linked", "source": "sweep"}]
    payload = runs.schema_graph_payload(_facts(summit_text), rows, [], "home")
    assert payload["findings"][0]["anchor_keys"] == []
    assert all(not n["findings"] for n in payload["nodes"])


def test_a_block_reference_past_the_inventory_resolves_to_nothing(
        summit_text):
    rows = [{"check_id": "ONP/schema-entity-thin", "severity": "medium",
             "summary": "x", "source": "sweep", "block": "Organization#999"}]
    payload = runs.schema_graph_payload(_facts(summit_text), rows, [], "home")
    assert payload["findings"][0]["anchor_keys"] == []


def test_a_held_row_is_held_in_the_picture_not_ranked_by_its_severity(
        summit_text):
    rows = [{"check_id": "ONP/schema-hidden-markup", "severity": "high",
             "summary": "x", "source": "sweep", "needs": "a rendered page"}]
    payload = runs.schema_graph_payload(_facts(summit_text), rows, [], "home")
    assert payload["findings"][0]["sev"] == "Held"


def test_a_brief_row_is_marked_analysis_and_a_sweep_row_free(summit_text):
    rows = [{"check_id": "ONP/a", "severity": "low", "summary": "x",
             "source": "model-judgement"},
            {"check_id": "ONP/b", "severity": "low", "summary": "y",
             "source": "sweep"}]
    payload = runs.schema_graph_payload(_facts(summit_text), rows, [], "home")
    assert [f["src"] for f in payload["findings"]] == ["analysis", "free"]
