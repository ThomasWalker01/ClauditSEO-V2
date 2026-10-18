"""One count of "the pages this run read", stated once per document.

CQ-04, first named in audit report 024 and carried by every report since, and
UX-84, which is CQ-04 arriving in a client's hands. Two counts of what a run
read are derivable from one stored row and every consumer picks one:

  `len(crawled_paths)`      the distinct **paths** the run touched, written by
                            `complete_run` from `AuditResult.crawled_paths` and
                            read by `_run_scope`. `compare_runs` puts its
                            length in `diff["scope"]["pages_crawled"]`.
  `scope["pages_fetched"]`  the **pages** a check could actually read, derived
                            by `_scope` from `crawl_evidence` and read by
                            `_breadth_phrase` for the coverage ratio.

They are different quantities and both are true: a site serving one page under
two URL forms is one path and two pages. Round 090's WF-02 fix put them four
lines apart in the same client deliverable, both introduced by the word
"fetched" and both tagged `confidence: high`. Measured on run `f80bc200` of
`www.acme.com.au`: 224 distinct paths, 235 readable pages, 272 declared by
the sitemap — so line 5 read "the current run fetched 224 pages" and line 10
read "measured across 235 of 272 discovered pages (86.4%)".

The rule this file guards: **a document states one count of what the current
run read, and names any second page-grain count as the different quantity it
is.** The coverage ratio's denominator is a count of sitemap URLs, so its
numerator is the URL-grain count and stays; the scope sentence is the line
that was stating the other grain under the same word.

The second half is `_scope`'s own fallback. `stats["eligible"]` — "what a
check could actually read" — has only been recorded since engine 0.9.0, and
for a run stored before it `_scope` fell through to `stats["fetched"]`, which
`clauditseo/crawler/types.py:page_is_eligible` documents as *URLs attempted*:
"a DNS failure leaves one with `status=0`". So a run that resolved nothing
reported every attempt as a page read, silently, under the same key the
coverage ratio is computed from. The stored evidence carries each page's
`status` and `content_type`, so the count can be derived rather than assumed —
and the value says which of the three ways it was arrived at.

DISCIPLINE rule 3 — the consumers were enumerated by grep before this was
written, not from the report's list: `_diff_scope_lines` and `_breadth_phrase`
in `clauditseo/reporting/render.py`, `CompareView` in `dashboard/src/views.tsx`,
`compare_runs` and `_scope` in `clauditseo/persistence/runs.py`, and
`share_basis`/`measured_share` in `clauditseo/engine/scoring.py`, which read
the value and never the word.
"""

import re
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.reporting.render import render_comparison_report


def _page(url: str, status: int = 200,
          content_type: str = "text/html; charset=utf-8") -> dict:
    """One stored page, in the shape `data/clauditseo.db` actually holds.

    CQ-203 is a guard whose fixture was a shape the product's own write path
    cannot produce, and this file must not be the next one — so the keys here
    were read off a stored blob rather than invented.
    """
    return {"url": url, "requested_url": url, "status": status,
            "content_type": content_type, "title": "t", "links": []}


def _evidence(pages: list[dict], discovered: int | None,
              eligible: int | None = None) -> dict:
    """A crawl record in the shape `store_evidence` receives.

    `eligible` is left out by default: it is a key engine 0.9.0 added, and
    every run stored before it — seven of the eleven in the operator's
    database — has `stats` without it.
    """
    stats = {"fetched": len(pages), "blocked_by_robots": 0, "errors": 0,
             "queue_remaining": 0, "duplicate_url_forms": 0, "sitemaps_read": 1}
    if eligible is not None:
        stats["eligible"] = eligible
    return {"stats": stats, "pages": pages, "robots_blocked": [],
            "sitemap_entry_total": discovered, "truncated_by": None}


# --- the two counts, at the source -----------------------------------------

def test_a_run_that_recorded_no_eligible_count_has_one_derived_not_assumed():
    """`fetched` counts attempts. A 404 and a PDF are attempts too.

    The evidence carries `status` and `content_type` for every page, which is
    exactly what `page_is_eligible` asks, so the answer is derivable and does
    not have to be stood in for by the count of URLs tried.
    """
    scope = runs._scope(_evidence(
        [_page("https://x.test/"), _page("https://x.test/gone", status=404),
         _page("https://x.test/a.pdf", content_type="application/pdf")],
        discovered=10))

    assert scope["pages_fetched"] == 1, (
        "a run whose crawl reached one readable page, one 404 and one PDF "
        f"reports {scope['pages_fetched']} pages read — the count of URLs "
        "attempted, which is what the coverage ratio is then computed from")


def test_the_page_count_says_which_of_the_three_ways_it_was_arrived_at():
    """The frame travels with the value, in one key beside it — the shape
    `run_measured_share` already uses for its own `basis`."""
    recorded = runs._scope(_evidence([_page("https://x.test/")], 10, eligible=1))
    derived = runs._scope(_evidence([_page("https://x.test/")], 10))
    nothing = runs._scope({"stats": {}, "pages": [], "sitemap_entry_total": 10})

    assert recorded["pages_fetched_basis"] == "recorded"
    assert derived["pages_fetched_basis"] == "derived"
    assert nothing["pages_fetched_basis"] == "attempted"


def test_a_recorded_eligible_count_is_never_second_guessed():
    """Rung one stays rung one: the crawler counted it at crawl time with the
    pages in hand, and the stored list can have been trimmed for size."""
    scope = runs._scope(_evidence(
        [_page("https://x.test/"), _page("https://x.test/b")], 10, eligible=7))

    assert scope["pages_fetched"] == 7


def test_a_trimmed_page_list_is_not_counted_as_if_it_were_whole():
    """`_scope`'s own docstring: `pages` can be trimmed, so counting it would
    understate a large crawl. Understating silently is the failure this rung
    order exists to avoid, so a trimmed list falls through to the attempt
    count and says that is what it is."""
    evidence = _evidence([_page("https://x.test/")], 10)
    evidence["stats"]["fetched"] = 400

    scope = runs._scope(evidence)

    assert scope["pages_fetched"] == 400
    assert scope["pages_fetched_basis"] == "attempted"


def test_the_comparison_carries_the_same_count_the_run_report_states(tmp_path):
    """Driven through the product's own writers, not a hand-built dict.

    `compare_runs` wrote only `pages_crawled`, so the document's frame and its
    coverage ratio came from two different derivations of one row. This asserts
    the diff now carries the figure `get_run` computes, so the two surfaces
    read one number.
    """
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Site, Tier

    conn = connect(tmp_path / "one-count.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site = repo.create_site(conn, client, "https://x.test/")

    def store(paths: list[str], pages: list[dict], discovered: int) -> str:
        run_id = runs.create_run(conn, site, ["ONP"], "T2")
        runs.store_evidence(conn, run_id, _evidence(pages, discovered))
        runs.complete_run(conn, run_id, AuditResult(
            site=Site(domain="https://x.test/"), tier=Tier.T2,
            dimensions=["ONP"], findings=[], crawled_paths=set(paths)))
        return run_id

    baseline = store(["/"], [_page("https://x.test/")], 10)
    # One page served under two URL forms: three distinct paths, four pages a
    # check could read. This is the `f80bc200` shape at a size a test can hold.
    current = store(
        ["/", "/a", "/b"],
        [_page("https://x.test/"), _page("https://x.test/a"),
         _page("https://x.test/a?ref=nav"), _page("https://x.test/b")],
        10)

    diff = runs.compare_runs(conn, baseline, current)
    stored = runs.get_run(conn, current)["scope"]
    conn.close()

    assert diff["scope"]["pages_crawled"] == 3, (
        "the distinct-path count is the one thing `compare_runs` did carry "
        "and it must keep carrying it")
    assert diff["scope"]["pages_fetched"] == stored["pages_fetched"] == 4, (
        "the comparison does not carry the page count the run report states, "
        "so the document's frame and its coverage ratio are two derivations "
        f"of one row: diff says {diff['scope'].get('pages_fetched')}, the run "
        f"says {stored['pages_fetched']}")


# --- the two counts, in the document ---------------------------------------

#: `run_b`'s scope as `get_run` assembles it: four readable pages of ten
#: declared, so `_breadth_phrase` states a ratio.
RUN_SCOPE = {"pages_fetched": 4, "pages_fetched_basis": "derived",
             "discovered": 10, "robots_blocked": 0, "truncated_by": None}

#: `diff["scope"]` as `compare_runs` assembles it for the same run.
DIFF_SCOPE = {"pages_crawled": 3, "pages_fetched": 4,
              "pages_fetched_basis": "derived", "dimensions": ["ONP", "TEC"]}


def _render(diff_scope: dict | None = None, audience: str = "client") -> str:
    a = {"id": "run-a", "finished_at": "2026-08-01T00:00:00+10:00",
         "composite_score": 70.0, "scope": None}
    b = {"id": "run-b", "finished_at": "2026-08-20T00:00:00+10:00",
         "composite_score": 74.0, "scope": RUN_SCOPE}
    diff = {"new": [], "resolved": [], "persisting": [], "not_rechecked": [],
            "scope": DIFF_SCOPE if diff_scope is None else diff_scope}
    markdown, _ = render_comparison_report({"domain": "x.test"}, a, b, diff,
                                           audience)
    return markdown


def _scope_sentence(markdown: str) -> str:
    line = [ln for ln in markdown.splitlines()
            if ln.startswith("Comparison scope:")]
    assert line, "the document states no comparison scope at all"
    return line[0]


def _current_composite_line(markdown: str) -> str:
    line = [ln for ln in markdown.splitlines()
            if ln.startswith("- Current composite:")]
    assert line, "the document states no current composite"
    return line[0]


@pytest.mark.parametrize("audience", ["client", "internal"])
def test_the_scope_sentence_and_the_coverage_ratio_agree_on_pages_read(audience):
    """The finding, stated as an assertion.

    Both numbers are introduced by a verb of reading and both describe the
    current run, so a reader takes them as one quantity. Matched on the figure
    rather than on the whole sentence: the wording is free to change and the
    agreement is not.
    """
    markdown = _render(audience=audience)
    scope = _scope_sentence(markdown)
    composite = _current_composite_line(markdown)

    stated = re.search(r"fetched (\d+) pages?", scope)
    # CQ-70 moved the noun off the ratio's denominator and gave the numerator
    # its own, so "measured across 4 of 10" became "measured across 4 pages a
    # check could read, of 10". This docstring's own rule applies — the figure
    # is what is matched and the wording was free to change — and the pattern
    # is re-anchored rather than loosened: it still binds to the numerator.
    measured = re.search(r"measured across (\d+) pages a check could read",
                         composite)
    assert stated and measured, (
        f"one of the two counts is no longer stated: {scope!r} / {composite!r}")

    assert stated.group(1) == measured.group(1), (
        "the document states two counts of what the current run read: "
        f"{stated.group(1)} in {scope!r} and {measured.group(1)} in "
        f"{composite!r}")


def test_the_distinct_path_count_is_named_as_the_other_quantity_it_is():
    """Not dropped — it is the count the screen has always shown, and it is
    the honest answer to "how much of the site" where the page count is the
    honest answer to "how much did we read". Both stay; only one may wear the
    word "fetched"."""
    scope = _scope_sentence(_render())

    assert "3 distinct paths" in scope, (
        f"the scope sentence does not name the distinct-path count: {scope!r}")
    assert not re.search(r"fetched 3 pages?", scope), (
        f"the distinct-path count is still introduced as pages: {scope!r}")


def test_two_counts_that_agree_are_stated_once():
    """A site with no duplicate URL forms has one answer, and saying it twice
    would be the same defect wearing the opposite coat."""
    scope = _scope_sentence(_render({**DIFF_SCOPE, "pages_crawled": 4}))

    assert "fetched 4 pages" in scope
    assert "distinct path" not in scope, (
        f"the two counts agree and the sentence states both: {scope!r}")


def test_a_diff_from_before_this_change_states_the_grain_it_actually_has():
    """`pages_crawled` alone is what every diff built before this round
    carries. It is a path count, so it is stated as one rather than being
    given the word that belongs to the other quantity."""
    scope = _scope_sentence(_render({"pages_crawled": 3, "dimensions": ["ONP"]}))

    assert "3 distinct paths" in scope, (
        f"a diff carrying only the path count mislabels it: {scope!r}")


def test_the_screen_reads_the_same_count_the_document_states():
    """Tripwire on the fourth consumer — DISCIPLINE rule 4, so this is
    evidence the key is read and not evidence of what is painted. The split it
    watches for is the one this round closed: two surfaces reading two
    different counts of one run out of one payload."""
    view = Path("dashboard/src/views.tsx").read_text(encoding="utf-8")
    # Scoped to `CompareResult`'s own scope declaration, not to the file.
    # `pages_fetched` already appears elsewhere in this module — on the
    # measured-share note, a different payload — so a document-wide `in view`
    # is satisfied by a string that has nothing to do with the comparison.
    # That is CQ-85's class, and it is the reason this assertion is a slice.
    declared = re.search(r"scope\?: \{(.*?)\}", view, re.S)
    assert declared, "CompareResult no longer declares a scope at all"

    for key in ("pages_crawled", "pages_fetched"):
        assert key in declared.group(1), (
            f"the compare screen's payload type does not carry {key}: it is "
            f"back to picking one count of the run, which is the finding — "
            f"{declared.group(1)!r}")
