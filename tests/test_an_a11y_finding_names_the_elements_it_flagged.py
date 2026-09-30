"""Every A11Y finding says which elements it flagged, and how many.

Relay item 136j Part A, answering `QUESTIONS.md` Q-52 with option (a).

Before this, the six static A11Y checks recorded hrefs, id maps and landmark
names — a sample of what was wrong, never *which* elements. `SAMPLE = 10`
capped even that, and the real number lived only inside an English sentence:
`link-name-missing` said *"4 link(s) on / have no accessible name."* and
stored `total_links`, which is every link on the page. So 136f could neither
group by element nor count instances, and `position_key`'s docstring had
recorded the reason since brief v15 — *"there is no selector here;
`html.parser` builds no tree"*.

That was true of the parser as it stood and not of what it can do. A
streaming parser sees every open and close, so the tree exists transiently
in a stack even though it is never built. The stack is now kept, and three
things are read off it at the moment an element is captured — which is why
no check re-parses HTML.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import Page
from clauditseo.modules import a11y
from clauditseo.modules.pagefacts import extract_facts


def _facts(body: str):
    html = f"<html lang=en><body>{body}</body></html>"
    return extract_facts(Page(url="https://x.test/", requested_url="https://x.test/",
                              status=200, content=html, headers={},
                              content_type="text/html"))


def _found(body: str) -> dict:
    return {f.check_id: f for f in a11y.AccessibilityModule()._page_checks(_facts(body))}


NAMELESS = "".join(f"<li><a href=/n{i}><img src=i.png></a></li>" for i in range(12))


# --- the elements themselves ---------------------------------------------

def test_every_flagged_element_has_a_selector():
    row = _found(f"<nav><ul>{NAMELESS}</ul></nav><main><h1>h</h1></main>")["link-name-missing"]
    e = row.evidence
    assert e["count"] == 12, e["count"]
    assert len(e["instances"]) == 12, len(e["instances"])
    assert all(i.get("selector") for i in e["instances"]), e["instances"]
    # And the selector is a path, not a placeholder.
    assert e["instances"][0]["selector"].endswith("a"), e["instances"][0]


def test_identity_is_not_truncated_even_though_the_summary_is():
    """`SAMPLE` caps what the human-readable keys list and nothing else. The
    two exist for different readers: `hrefs` is a sample for a person, and
    `instances` is the population for the block that groups them."""
    links = "".join(f"<a href=/n{i}></a>" for i in range(40))
    row = _found(f"<nav>{links}</nav><main><h1>h</h1></main>")["link-name-missing"]
    assert row.evidence["count"] == 40
    assert len(row.evidence["instances"]) == 40
    assert len(row.evidence["hrefs"]) == a11y.SAMPLE == 10


def test_the_count_is_a_field_and_not_only_a_sentence():
    """The defect this item exists to remove: the number was recoverable
    only by parsing English, so nothing downstream could add two of them."""
    row = _found(f"<nav><ul>{NAMELESS}</ul></nav><main><h1>h</h1></main>")["link-name-missing"]
    assert isinstance(row.evidence["count"], int)
    assert row.summary.startswith("12 link(s)"), row.summary


def test_the_selector_stops_at_an_id_and_counts_siblings_otherwise():
    """Two rules, both visible in one page. An id wins outright and the path
    stops there — it is the only part of this guaranteed unique. Without
    one, position among same-tag siblings is what separates them."""
    found = _found("<nav><a href=/a></a><a href=/b></a></nav>"
                   "<main id=m><a href=/c></a><h1>h</h1></main>")
    sels = {i["href"]: i["selector"] for i in found["link-name-missing"].evidence["instances"]}
    assert sels["/a"].endswith("nav > a"), sels
    assert sels["/b"].endswith("a:nth-of-type(2)"), sels
    assert sels["/c"] == "#m > a", sels


def test_an_unclosed_list_item_does_not_nest_the_next_one():
    """Real markup omits `</li>` constantly. A stack that believes the
    omission puts every later item one level deeper than it is, and every
    selector after the first would be wrong — silently, since nothing else
    reads them."""
    body = ("<nav><ul><li><a href=/a></a><li><a href=/b></a></ul></nav>"
            "<main><h1>h</h1></main>")
    sels = {i["href"]: i["selector"]
            for i in _found(body)["link-name-missing"].evidence["instances"]}
    assert sels["/a"] == "nav > ul > li > a", sels
    assert sels["/b"] == "nav > ul > li:nth-of-type(2) > a", sels


def test_a_void_element_does_not_swallow_its_siblings():
    """`html.parser` never calls `handle_endtag` for `<img>`, so a pushed
    one would parent everything after it for the rest of the document."""
    body = ("<main><img src=a.png><a href=/after></a><h1>h</h1></main>")
    inst = _found(body)["link-name-missing"].evidence["instances"][0]
    assert "img" not in inst["selector"], inst["selector"]


def test_the_landmark_is_the_nearest_ancestor_not_the_page():
    """136f classifies chrome by this, so `nav` and `main` have to be told
    apart on one page."""
    body = ("<header><nav><a href=/a></a></nav></header>"
            "<main><h1>h</h1><a href=/b></a></main><footer><a href=/c></a></footer>")
    marks = {i["href"]: i["landmark"]
             for i in _found(body)["link-name-missing"].evidence["instances"]}
    assert marks == {"/a": "nav", "/b": "main", "/c": "footer"}, marks


def test_a_generated_id_is_kept_raw_and_dropped_from_the_normalised_form():
    """A framework id is stable within one render and different on the next,
    so a selector built on one identifies an element on this page and
    nothing on the page beside it — the opposite of what 136f groups by. It
    stays in the raw form, which still resolves today."""
    body = "<main><div id=w-node-abc123><a href=/a></a></div><h1>h</h1></main>"
    inst = _found(body)["link-name-missing"].evidence["instances"][0]
    assert inst["selector"].startswith("#w-node-abc123"), inst["selector"]
    assert "w-node" not in inst["selector_norm"], inst["selector_norm"]


def test_the_element_is_carried_as_written():
    body = "<main><h1>h</h1><a href=/a class=btn><span></span></a></main>"
    inst = _found(body)["link-name-missing"].evidence["instances"][0]
    assert inst["html"].startswith("<a href=/a class=btn>"), inst["html"]
    assert inst["html"].endswith("</a>"), inst["html"]


# --- one shape for every check -------------------------------------------

@pytest.mark.parametrize("body,check", [
    ("<nav><a href=/a></a></nav><main><h1>h</h1></main>", "link-name-missing"),
    ("<nav><a href=/a>click here</a></nav><main><h1>h</h1></main>", "link-text-generic"),
    ("<main><h1>h</h1><form><input type=text></form></main>", "form-control-unlabelled"),
    ("<main><h1>h</h1><div id=d></div><div id=d></div></main>", "duplicate-id"),
])
def test_every_static_check_reports_the_same_two_fields(body, check):
    """136f reads one field for every check rather than branching on which
    one raised the row. A check that spelled these differently would be a
    group of its own for no reason."""
    e = _found(body)[check].evidence
    assert isinstance(e.get("count"), int), (check, e)
    assert isinstance(e.get("instances"), list), (check, e)
    assert e["count"] == len(e["instances"]), (check, e["count"], len(e["instances"]))
    assert all("selector" in i for i in e["instances"]), (check, e["instances"])


def test_axe_rows_carry_the_same_shape_from_their_own_nodes():
    """The rendered pass already had per-node targets in a different key.
    Normalised rather than left for the reader to join."""
    import inspect

    from clauditseo import axe
    src = inspect.getsource(axe)
    block = src[src.index('"nodes_total"'):src.index('"nodes_total"') + 1400]
    assert '"instances"' in block and '"count": len(nodes)' in block, block[:400]
    # And the rect travels with them (136j Part B), absent rather than null
    # where the node could not be resolved.
    assert '"rect": n["rect"]' in block, block[:600]


def test_the_count_agrees_with_the_summary_the_check_writes():
    """136j's agreement rule. `duplicate-id` is the case that made it bite:
    three divs sharing one id are three edits, so `count` is elements — and
    the summary used to say "1 id(s)", which would have made the two
    disagree by construction. The summary was changed, not the count."""
    row = _found("<main><h1>h</h1><div id=d></div><div id=d></div>"
                 "<div id=d></div></main>")["duplicate-id"]
    assert row.evidence["count"] == 3, row.evidence["count"]
    assert row.summary.startswith("3 element(s)"), row.summary
    assert "1 duplicated id(s)" in row.summary, row.summary


def test_landmark_main_missing_is_the_one_check_where_count_is_not_a_population():
    """Named rather than quietly exempted. 136j specifies this check as
    "instances = the landmarks found, count of `main` = 0 or >1", which
    contradicts its own general rule that count equals the length of
    instances. The specific instruction wins because the row is about an
    ABSENCE — there is no flagged element to count, and the landmarks that
    are present are context rather than instances."""
    e = _found("<header><nav><a href=/a>x</a></nav></header>"
               "<section><h1>h</h1></section>")["landmark-main-missing"].evidence
    assert e["count"] == 0, e["count"]
    assert e["instances"] and e["count"] != len(e["instances"]), e
    # `header` and `nav`, not `section`: a bare <section> is only a landmark
    # once it has an accessible name, and the parser's landmark set is right
    # to leave it out. Asserted rather than assumed - the first version of
    # this clause expected `section` and the code was correct.
    assert {i["landmark"] for i in e["instances"]} == {"header", "nav"}, e["instances"]
