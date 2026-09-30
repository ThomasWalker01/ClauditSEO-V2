"""The shared state model for "an analysis you can run".

These guard the thing the model exists to prevent: screens disagreeing about
what the same tool is doing, and — the expensive case — a control that reads
as "open the stored report" in fact buying a new one.
"""

from __future__ import annotations

from clauditseo import analyses as an

BRIEFS = {
    "crawl": {"scope": "site", "inputs": []},
    "page-advisor": {"scope": "page", "inputs": []},
    "content-coverage": {"scope": "site",
                    "inputs": [{"key": "competitors", "required": True}]},
    # `triage` stood here until item 196 retired it; the clauses that used it
    # wanted any site-scoped brief.
    "hreflang": {"scope": "site", "inputs": []},
    "reporting": {"scope": "site", "inputs": []},
    "regression-monitoring": {"scope": "site", "inputs": []},
}


def _lanes(stored=None, in_flight=(), estimates=None):
    return an.lanes(stored or {}, estimates or {}, set(in_flight), BRIEFS)


# --- states ---------------------------------------------------------------

def test_a_stored_report_is_free_and_says_read():
    """The whole point. This row must never carry a price or a spending verb:
    the report is already bought, and the control that looked identical to a
    buying one is what charged for a second run of something already paid
    for."""
    out = _lanes(stored={"crawl": {"created_at": "2026-08-08T10:00:00",
                                          "findings": 12, "tokens": 11913}})
    row = next(r for r in out["ready"] if r["tool"] == "crawl")
    assert row["state"] == an.READY
    assert row["verb"] == "read"
    assert not any(r["tool"] == "crawl" for r in out["available"])


def test_nothing_stored_says_run_and_lands_in_the_spending_lane():
    out = _lanes()
    row = next(r for r in out["available"] if r["tool"] == "crawl")
    assert (row["state"], row["verb"]) == (an.NOT_RUN, "run")
    assert not out["ready"]


def test_a_required_input_blocks_before_it_spends():
    """A brief that cannot run without context should ask for the context,
    not offer a run button that fails."""
    row = next(r for r in _lanes()["available"] if r["tool"] == "content-coverage")
    assert (row["state"], row["verb"]) == (an.NEEDS_INPUT, "supply")


def test_running_offers_a_stop_not_another_run():
    row = next(r for r in _lanes(in_flight=["crawl"])["available"]
               if r["tool"] == "crawl")
    assert (row["state"], row["verb"]) == (an.RUNNING, "stop")


def test_every_state_has_exactly_one_verb():
    """Eight verbs across five screens is what this replaces."""
    assert set(an.VERB) == {an.READY, an.RUNNING, an.NEEDS_INPUT, an.NOT_RUN}
    assert len(set(an.VERB.values())) == 4


# --- types ----------------------------------------------------------------

def test_types_are_declared_not_guessed_from_the_id():
    """Renaming a tool must not silently reclassify it."""
    assert an.type_of("triage", "site") == "triage"
    assert an.type_of("reporting", "report") == "report"
    assert an.type_of("regression-monitoring", "site") == "monitor"
    assert an.type_of("crawl", "sweep") == "site"
    assert an.type_of("page-advisor", "page") == "page"


def test_a_page_analysis_is_marked_as_one():
    """It cannot run until a page is chosen, which is why a bare run control
    on one of these did nothing useful."""
    row = next(r for r in _lanes()["available"] if r["tool"] == "page-advisor")
    assert row["type"] == "page"


# --- money ----------------------------------------------------------------

def test_the_two_unknowns_are_kept_apart():
    """Conflating them produced a footer that contradicted itself: "~1004k
    tokens for all 16 · 16 never run here, so not in that figure". Tokens
    were known for all sixteen; only the dollar rate was missing."""
    out = _lanes(estimates={
        "crawl": {"tokens": 12000, "cost": None},   # measured, no rate
        # Any fully priced tool; this was `triage` until item 196 retired it,
        # and the clause is about the two kinds of unknown rather than about
        # which tool carries the price.
        "hreflang": {"tokens": 21000, "cost": 0.42},       # fully priced
    })
    assert out["no_dollar_rate"] == 1        # crawl
    # page-advisor, reporting, regression-monitoring, content-coverage
    assert out["unestimated"] == 4
    assert out["outstanding_cost"] == 0.42
    assert out["outstanding_tokens"] == 33000


def test_cost_is_absent_rather_than_zero_when_nothing_is_priced():
    assert _lanes()["outstanding_cost"] is None



# --- what a section still offers once its read and run pills have theirs ---

def test_the_leftover_tools_say_the_true_thing_about_themselves():
    """A section's tool list holds more than its briefs, and the difference
    matters.

    The Current tab used to end with an "Investigate" row of every tool in
    the category, rendered as links. Folding that row into the read/run line
    meant classifying what was left — and the first cut called all of it a
    sweep, which put "link-gap runs in every audit" on screen. link-gap is
    not built. The playbook already records the difference; nothing should be
    inferring it.
    """
    status = an.tool_status()
    # Unbuilt: there is nothing to run and nothing that ran.
    for unbuilt in ("link-gap", "disavow-review", "citation-readiness",
                    "measurement-validation"):
        assert status[unbuilt] == "planned", unbuilt
    # Dark without a key, which is not the same as absent.
    for gated in ("core-web-vitals", "backlink-profile"):
        assert status[gated] == "needs_key", gated
    # Genuinely measured by the audit itself.
    # `perf-signals` was here until migration 0054 retired it; `speed`, the
    # brief that superseded its checks, is a SITE tool rather than a sweep, so
    # the example is not simply swapped -- the sweep list is one shorter.
    for sweep in ("schema-validation", "a11y-sweep",
                  "content-signals", "extractability"):
        assert status[sweep] == "ready", sweep


def test_every_tool_in_a_category_has_a_status():
    """The section row classifies by looking each tool up. A tool that is in
    the category map but not the playbook would fall through to whatever the
    default happens to be, which is how a false label gets shipped."""
    from clauditseo import anatomy

    status = an.tool_status()
    missing = sorted(t for t in anatomy.TOOL_CATEGORIES if t not in status)
    assert not missing, f"in TOOL_CATEGORIES but not the playbook: {missing}"


def test_the_page_panels_are_real_and_are_not_briefs():
    """They get an "open" pill that reveals their own panel. A brief would
    already be a read or a run pill, and offering it twice is the duplication
    the row was collapsed to remove."""
    from clauditseo import anatomy
    from clauditseo.analysts.expert import EXPERT_TOOLS

    status = an.tool_status()
    assert anatomy.PAGE_PANELS, "no page panels declared"
    for tool in anatomy.PAGE_PANELS:
        assert status.get(tool) == "ready", tool
        assert tool not in EXPERT_TOOLS, f"{tool} is a brief; it belongs above"
        assert tool in anatomy.TOOL_CATEGORIES, f"{tool} belongs to no section"
