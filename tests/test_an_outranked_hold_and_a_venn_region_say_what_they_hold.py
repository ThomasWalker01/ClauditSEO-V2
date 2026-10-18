"""An outranked hold, and a region of the crawl's venn, say what they hold
(screen audits round 4, Crawl IP-01, IP-04, Indexability AC-01).

"canonical-loop not assessable on /about/" stood three times under a clean
line naming canonical-loop; and "4 reached, not in a sitemap" named none of
the four.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_an_outranked_hold_is_said_as_held_and_measured_since():
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert '{l.outranked ? " held by the analysis" : " not assessable"}' in p
    assert "the automatic checks have since measured it clean" in p


def test_the_venn_names_its_pages():
    assert '"reached_not_in_sitemap_paths": sorted(reached - in_sitemap)[:20]' in inspect.getsource(runs)
    c = (SRC / "crawl_now.tsx").read_text(encoding="utf-8")
    assert "<VennPaths paths={v.reached_not_in_sitemap_paths}" in c


def test_a_broken_link_names_the_pages_that_carry_it():
    """Links UX-02: the card named the target and a count, not the page to
    edit."""
    from clauditseo.modules import links
    assert links._from_words({"/b/", "/a/"}) == "/a/, /b/"
    assert links._from_words({f"/p{i}/" for i in range(5)}) == "/p0/, /p1/, /p2/ and 2 more"
    assert '"linked_from": sorted(linked_from.get(u) or ())[:20]' in inspect.getsource(links)


def test_a_dot_counts_pages_at_its_drawn_size():
    """Images IP-04, AC-06: one dot is one file at one drawn size."""
    b = (SRC / "images_budget.tsx").read_text(encoding="utf-8")
    assert "pages at this size" in b


def test_a_fragmented_verdict_is_not_disputed_by_a_duplicate_id():
    """Structured data AC-02."""
    g = (SRC / "schema_graph.tsx").read_text(encoding="utf-8")
    assert '!/fragment/i.test(String(model.verdict.entity ?? ""))' in g


def test_a_card_from_another_analysis_says_whose_and_the_rerun_counts_its_own():
    """Links IP-04, Crawl IP-02."""
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "· from the {(fix.briefs ?? []).join(\" and \")} analysis" in p
    assert "|| (f.briefs ?? []).includes(mine.tool))).length," in p


def test_a_cdn_path_is_no_part_of_a_parts_dates():
    """Mobile IP-01, URLs AC-01: "Measured 2 Oct to 12 Oct" from the CDN's
    `/cdn-cgi/` page, last read before the crawler stopped counting it."""
    from clauditseo.persistence import latest_view
    assert "if is_edge_path(r[\"key\"]):" in inspect.getsource(latest_view.part_range)


def test_a_groups_template_share_is_in_cards():
    """Images IP-09: a page count and a card count in one label."""
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "{tpl.n} of {cards.length} card" in p
