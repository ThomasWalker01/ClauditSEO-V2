"""A row is pinned to the node it names (item 270, row 4).

On twenty22's `/` the inventory runs WebSite, SearchAction, WebPage,
ReadAction, Organization, Person, Organization. A row written
`Organization#2` - the second Organization, per the prompt's own
`Organization#1` - was read as index 2 of the whole inventory and pinned to
the SearchAction, while both Organization cards read clean. Automatic rows,
which name their node by an integer index, pinned to nothing.
"""

from __future__ import annotations

from clauditseo.persistence.runs import _graph_anchors

INVENTORY = [{"type": "WebSite", "id": "#website"}, {"type": "SearchAction", "id": "#search"},
             {"type": "WebPage", "id": "#webpage"}, {"type": "ReadAction", "id": "#read"},
             {"type": "Organization", "id": "#org-a"}, {"type": "Person", "id": "#person"},
             {"type": "Organization", "id": "#org-b"}]


def test_type_n_is_the_nth_node_of_that_type():
    assert _graph_anchors({"block": "Organization#2"}, INVENTORY) == ["#org-b"]
    assert _graph_anchors({"block": "Organization#1"}, INVENTORY) == ["#org-a"]


def test_the_flattened_index_is_used_only_where_the_type_agrees():
    # Person#6 is not the sixth Person; at flattened index 6 is a Person.
    assert _graph_anchors({"block": "Person#6"}, INVENTORY) == ["#person"]
    # WebSite#5 names a WebSite and index 5 is an Organization: nothing.
    assert _graph_anchors({"block": "WebSite#5"}, INVENTORY) == []


def test_an_automatic_rows_integer_block_is_its_index():
    assert _graph_anchors({"block": 4}, INVENTORY) == ["#org-a"]
    assert _graph_anchors({"block": 99}, INVENTORY) == []
    assert _graph_anchors({"block": True}, INVENTORY) == []
