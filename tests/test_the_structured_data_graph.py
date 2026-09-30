"""`build_model` draws the same picture the render rules describe.

Brief v16a step AT-a. The three JSON examples in `fixtures/schema_examples/`
are the designer's pack, byte for byte, and the numbers asserted here are the
ones the item states — one block against three, five wired nodes against
three islands, a graph that resolves against one that dangles.

**Why these three and not a synthetic page.** A fixture written to exercise
the rules would be written by the same reading of the rules that implemented
them, and would agree with a wrong implementation (DISCIPLINE rule 5). These
are real markup off three real sites, and the expected model was computed by
the reference implementation before this code existed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clauditseo import schema_graph as sg

EXAMPLES = Path(__file__).resolve().parent / "fixtures" / "schema_examples"


def _load(name: str):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def voltaic():
    ctx = _load("1_thin_but_wired_CONTEXT.json")
    return sg.build_model(
        [{"source": "plugin:yoast",
          "json": _load("1_thin_but_wired.json")}],
        None,
        {"host": "13acme.com.au", "page": "/", "page_type": "home",
         "footer_profile_links": ctx["footer_profile_links"]},
        [])


@pytest.fixture(scope="module")
def summit():
    return sg.build_model(
        [{"source": "inline · xr-schema",
          "json": _load("2_rich_but_fragmented.json")}],
        None, {"host": "summit-roofing-fixture.com.au", "page": "/",
               "page_type": "home"}, [])


@pytest.fixture(scope="module")
def acme():
    """Three objects in one file, each with its own `@context`: three blocks.

    An array at the top of a page's markup is not a `@graph`, and reading it
    as one would draw Acme's disjointed page as a single wired block —
    which is the whole finding, drawn away.
    """
    blocks = _load("3_disjointed_three_blocks.json")
    return sg.build_model(
        [{"source": "inline", "json": b} for b in blocks],
        None, {"host": "acme.com.au", "page": "/", "page_type": "home"}, [])


# --- Voltaic: thin but wired -------------------------------------------------

def test_voltaic_is_one_block_of_five_wired_nodes(voltaic):
    assert voltaic.verdict["blocks"] == 1, voltaic.verdict
    assert voltaic.verdict["nodes"] == 5, [n.type for n in voltaic.nodes]
    assert voltaic.verdict["islands"] == 0, [n.type for n in voltaic.nodes if n.island]
    assert voltaic.verdict["dangling"] == 0, [
        r for r in voltaic.refs if not r["resolved"]]


def test_kugas_entity_is_consolidated_and_the_reason_names_what_decided_it(voltaic):
    assert voltaic.verdict["entity"] == "CONSOLIDATED", voltaic.verdict
    assert "about" in voltaic.verdict["why"] and "publisher" in voltaic.verdict["why"], (
        voltaic.verdict["why"])


def test_the_footers_maps_places_become_one_ghost_and_not_four_cards(voltaic):
    """Four Google Maps links in the footer and no `address` anywhere is one
    absence, and one card. Four ghosts would read as four missing nodes when
    what is missing is the decision to declare any."""
    ghosts = [g for g in voltaic.ghosts if g.kind == "ghost-expected"]
    assert len(ghosts) == 1, [g.key for g in voltaic.ghosts]
    g = ghosts[0]
    assert g.types == ["LocalBusiness"] and g.count == 4, (g.types, g.count)
    assert len(g.props) == 4 and all(p["mark"] == "miss" for p in g.props), g.props
    assert any(e["from"] == g.key and e["kind"] == "expected"
               and e["label"] == "parentOrganization ×4" for e in voltaic.edges), (
        voltaic.edges)


def test_a_nested_definition_is_a_definition_so_the_logo_reference_resolves(voltaic):
    """Voltaic's logo `ImageObject` is defined inside the Organization. §2 says
    an `@id` + `@type` object anywhere defines that identifier, so
    `image.@id` → the logo is a self-reference and not a dangling one."""
    org = voltaic.node("https://www.13acme.com.au/#organization")
    row = next(p for p in org.props if p["k"] == "image.@id")
    assert row["mark"] == "ok", row
    assert row["note"] == "nested definition in this node", row


def test_the_property_marks_read_the_values_they_are_about(voltaic):
    """§7a. `en-US` on an `.au` site is red; the entity's absent address and
    telephone are added amber rows; `image` pointing at the logo is amber."""
    org = voltaic.node("https://www.13acme.com.au/#organization")
    marks = {p["k"]: (p.get("mark"), p.get("note")) for p in org.props}
    assert marks["address"] == ("miss", "missing"), marks.get("address")
    assert marks["telephone"] == ("miss", "missing"), marks.get("telephone")

    page = voltaic.node("https://www.13acme.com.au/")
    assert page.props[[p["k"] for p in page.props].index("inLanguage")]["mark"] == "bad"
    lang = next(p for p in page.props if p["k"] == "inLanguage")
    assert "en-AU" in lang["note"], lang

    website = voltaic.node("https://www.13acme.com.au/#website")
    empty = next(p for p in website.props if p["k"] == "description")
    assert (empty["mark"], empty["note"]) == ("miss", "empty"), empty


def test_the_site_tier_ghost_is_absent_when_the_map_is_satisfied(voltaic):
    """WebSite, WebPage and the entity are all declared, so no "expected ·
    absent" card is drawn for them. A picture that showed one anyway would be
    saying the page is missing something it has."""
    assert not [g for g in voltaic.ghosts if g.role == "site"], voltaic.ghosts


# --- Summit: rich but fragmented ---------------------------------------

def test_summit_is_one_block_of_four_nodes_two_of_them_islands(summit):
    assert summit.verdict["blocks"] == 1, summit.verdict
    assert summit.verdict["nodes"] == 4, [n.type for n in summit.nodes]
    islands = sorted(n.types[0] for n in summit.nodes if n.island)
    assert islands == ["FAQPage", "ItemList"], islands


def test_the_entity_is_not_an_island_because_its_own_lists_point_at_it(summit):
    """The rejected definition — "nothing points at it" — would call the
    healthiest node on the page an island, because its fifteen services and
    three reviews reference it from inside itself. Connection is to a
    *different* top-level node, in either direction."""
    entity = summit.node("https://summit-roofing-fixture.com.au/#localbusiness")
    assert entity.island is False, entity.flags


def test_two_references_resolve_to_nothing_and_get_a_ghost_each(summit):
    ghosts = sorted(g.key for g in summit.ghosts if g.kind == "ghost-dangling")
    assert ghosts == [
        "dangling:https://summit-roofing-fixture.com.au/#organization",
        "dangling:https://summit-roofing-fixture.com.au/#person-sam-fixture",
    ], ghosts
    assert summit.verdict["dangling"] == 2, summit.verdict
    assert summit.verdict["entity"] == "FRAGMENTED", summit.verdict
    # The guessed type is labelled as guessed, from the property name.
    org = summit.node("dangling:https://summit-roofing-fixture.com.au/#organization")
    person = summit.node(
        "dangling:https://summit-roofing-fixture.com.au/#person-sam-fixture")
    assert org.types == ["Organization"] and org.role == "entity", org
    assert person.types == ["Person"], person


def test_the_lists_are_counted_chips_and_not_sixty_cards(summit):
    """§8's point, tested as a count: level 0 grows with top-level nodes,
    never with items."""
    entity = summit.node("https://summit-roofing-fixture.com.au/#localbusiness")
    counts = {c.prop: c.count for c in entity.collections}
    assert counts["hasOfferCatalog"] == 15, counts
    assert counts["areaServed"] == 29, counts
    assert counts["sameAs"] == 5, counts
    assert counts["review"] == 3, counts


def test_an_item_mark_says_what_is_wrong_with_that_item(summit):
    """§7b. Every service in the catalogue is missing a `url`, so the chip's
    caption is "all no url" rather than a count an operator has to divide."""
    entity = summit.node("https://summit-roofing-fixture.com.au/#localbusiness")
    catalog = next(c for c in entity.collections if c.prop == "hasOfferCatalog")
    assert catalog.problems == 15, [i["marks"] for i in catalog.items]
    assert catalog.caption() == "all no url", catalog.caption()
    cities = next(c for c in entity.collections if c.prop == "areaServed")
    assert all(i["marks"][0]["note"] == "no location page" for i in cities.items)
    assert all(i["marks"][0]["mark"] == "held" for i in cities.items), (
        "a check output about the site's page list is held, not failing")


def test_an_encoding_defect_is_read_where_it_sits(summit):
    """`COLORBONDÂ®` in the description is the mojibake an operator can see
    on the page; the mark is on the row that carries it."""
    entity = summit.node("https://summit-roofing-fixture.com.au/#localbusiness")
    desc = next(p for p in entity.props if p["k"] == "description")
    assert (desc["mark"], desc["note"]) == ("miss", "encoding defect"), desc


# --- Acme: three disjointed blocks -------------------------------------

def test_acme_is_three_blocks_of_three_nodes_all_islands(acme):
    assert acme.verdict["blocks"] == 3, acme.verdict
    assert acme.verdict["nodes"] == 3, [n.type for n in acme.nodes]
    assert acme.verdict["islands"] == 3, [
        n.type for n in acme.nodes if n.kind == "node" and not n.island]


def test_the_provider_is_a_second_copy_of_the_entity_not_a_reference(acme):
    """§4's inline copy, and the reason the page is UNIDENTIFIED. Drawn as
    its own node so the dotted "should be an @id" edge has somewhere to go."""
    copies = [n for n in acme.nodes if n.kind == "inline-copy"]
    assert len(copies) == 1, [n.key for n in acme.nodes]
    copy = copies[0]
    assert copy.via_prop == "provider" and copy.name == "Acme", copy
    assert copy.state == "high", (
        "an inline copy is red with nothing pinned to it: the copy is the "
        "defect whether or not a check has been written that says so")
    assert any(e["to"] == acme.entity_key and e["kind"] == "expected"
               and "@id" in e["label"] for e in acme.edges), acme.edges
    parent = acme.node(copy.parent)
    row = next(p for p in parent.props if p["k"] == "provider")
    assert row["mark"] == "bad", row


def test_the_verdict_is_unidentified_and_says_which_condition_decided_it(acme):
    assert acme.verdict["entity"] == "UNIDENTIFIED", acme.verdict
    assert "no @id" in acme.verdict["why"], acme.verdict["why"]


def test_a_bracketed_value_is_a_placeholder_and_is_marked_red(acme):
    """`[505 Toorak Rd]` is a template that was never filled in. It parses,
    it validates, and it is wrong — which is exactly the class of defect a
    picture of the markup exists to surface."""
    entity = acme.node(acme.entity_key)
    street = next(p for p in entity.props if p["k"] == "address.streetAddress")
    assert street["v"] == "[505 Toorak Rd]", street
    assert (street["mark"], street["note"]) == ("bad", "template placeholder"), street


def test_a_node_with_no_id_says_so_at_the_top_of_its_properties(acme):
    entity = acme.node(acme.entity_key)
    assert entity.props[0]["k"] == "@id", entity.props[0]
    assert entity.props[0]["mark"] == "bad", entity.props[0]


# --- anchors, §7 ----------------------------------------------------------

def test_an_anchor_that_resolves_to_nothing_is_dropped_and_never_invented():
    """§7's last line. A finding pinned to a node that is not on the page
    would otherwise draw a card for a node the page does not have."""
    model = sg.build_model(
        [{"source": "inline",
          "json": _load("3_disjointed_three_blocks.json")[0]}],
        None, {"host": "acme.com.au", "page": "/", "page_type": "home"},
        [{"n": 1, "sev": "High", "name": "x", "checks": ["ONP/schema-graph-wiring"],
          "src": "free", "anchors": ["b1n0", "https://nowhere.test/#nope",
                                     "expected:Nothing", "block:9"]}])
    assert model.findings[0]["anchor_keys"] == ["b1n0"], model.findings[0]


def test_a_finding_pinned_to_a_nested_object_gets_a_chip_it_can_land_on():
    """§7's promotion: `address` is an object rather than a list, so an
    anchor naming it makes a collection of one. Without it the finding has
    nowhere on the picture to be and disappears silently."""
    model = sg.build_model(
        [{"source": "inline",
          "json": _load("3_disjointed_three_blocks.json")[0]}],
        None, {"host": "acme.com.au", "page": "/", "page_type": "home"},
        [{"n": 1, "sev": "High", "name": "x", "checks": ["ONP/schema-nap-mismatch"],
          "src": "free", "anchors": ["b1n0#address"]}])
    assert model.findings[0]["anchor_keys"] == ["b1n0#address"], model.findings[0]
    col = model.collections["b1n0#address"]
    assert col.count == 1 and col.items[0]["marks"], col.items
    assert col.state == "high", "the ring is the worst finding pinned to it"


def test_the_worst_finding_pinned_to_a_thing_is_the_things_colour():
    model = sg.build_model(
        [{"source": "inline",
          "json": _load("3_disjointed_three_blocks.json")[0]}],
        None, {"host": "acme.com.au", "page": "/", "page_type": "home"},
        [{"n": 2, "sev": "Low", "name": "b", "checks": ["x"], "src": "free",
          "anchors": ["b1n0"]},
         {"n": 1, "sev": "High", "name": "a", "checks": ["y"], "src": "free",
          "anchors": ["b1n0"]}])
    node = model.node("b1n0")
    assert [f["n"] for f in node.findings] == [1, 2], node.findings
    assert node.state == "high", node.state


def test_the_model_survives_a_round_trip_through_json():
    """The dashboard receives this as JSON and draws it. A model that cannot
    be serialised is a model the picture never sees."""
    blocks = _load("3_disjointed_three_blocks.json")
    model = sg.build_model([{"source": "inline", "json": b} for b in blocks],
                           None, {"host": "acme.com.au", "page": "/",
                                  "page_type": "home"}, [])
    out = json.loads(json.dumps(model.as_dict()))
    assert out["verdict"]["entity"] == "UNIDENTIFIED", out["verdict"]
    assert len(out["nodes"]) == 4, [n["key"] for n in out["nodes"]]


def test_eligibility_is_passed_through_and_can_say_none_targeted():
    """It is a check output, not a reading of the JSON, so the model carries
    it and decides nothing about it. The fourth verdict exists because a home
    page targets no rich result and the other three would have to lie."""
    elig = [{"target": "Rich result on this page", "verdict": "none targeted",
             "reason": "a home page targets no rich result"}]
    model = sg.build_model([], None, {"host": "x.test", "page_type": "home"},
                           [], elig)
    assert model.eligibility == elig, model.eligibility
    assert "none targeted" in sg.ELIGIBILITY_VERDICTS
