"""An automatic structured-data row is pinned to the nodes it names (item
270, row 4, second half).

On twenty22's `/`, after `Type#n` was read per type, the analysis row landed
on the second Organization, but the automatic `schema-redundant-block` and
`schema-duplicate-id` rows landed on nothing: they name no block. One names
the type it found twice, the other the @id it found twice, and each is about
every node carrying it - so all three badges belong on the Organization
cards.
"""

from __future__ import annotations

import inspect

from clauditseo.persistence import runs
from clauditseo.persistence.runs import _graph_anchors

INVENTORY = [{"type": "WebSite", "id": "#website"}, {"type": "SearchAction", "id": "#search"},
             {"type": "Organization", "id": "https://t.co/#organization"},
             {"type": "Person", "id": "#person"},
             {"type": "Organization", "id": "https://t.co/#organization"}]


def test_a_duplicate_id_lands_on_the_nodes_that_carry_it():
    assert _graph_anchors({"node_ids": ["https://t.co/#organization"]}, INVENTORY) \
        == ["https://t.co/#organization"]


def test_a_redundant_block_lands_on_every_node_of_its_type():
    assert _graph_anchors({"node_type": "Organization", "block": None}, INVENTORY) \
        == ["https://t.co/#organization"]
    assert _graph_anchors({"node_type": "Product", "block": None}, INVENTORY) == []


def test_the_view_carries_what_the_rows_name():
    # From the stored text, not the view's cut-down parse, which skips
    # evidence naming none of its five fields - these rows' among them. The
    # first version read `ev` and carried None on twenty22.
    src = inspect.getsource(runs)
    assert '"node_ids": (_evidence_key(r["evidence"], "properties")' in src
    assert '"node_type": (_evidence_key(r["evidence"], "type")' in src
    assert runs._view_evidence('{"type": "Organization", "count": 2}') == {}
    assert runs._evidence_key('{"type": "Organization", "count": 2}', "type") == "Organization"
