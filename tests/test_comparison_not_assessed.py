"""A not-assessed finding says the same thing in every template it reaches.

UX-10, carried since report 019 and dispositioned to the engineering cohort
at seventeen rounds. `render_run_report` has routed a `-not-assessed` check
through `_not_assessed_line` since round 003, which rebuilds a client
sentence from structured evidence and never prints the stored
`recommendation`. `render_comparison_report` rendered the same findings
through `_finding_line`, which prints it verbatim — so the comparison
deliverable told a fee-paying client to set environment variables under the
prefix this product was renamed away from on 14 August 2026. Four findings in
the operator's live database carry exactly that recommendation.

The prefix is never spelled in this file. `tests/test_naming.py` owns it,
refuses it in everything that ships, and bounds the files allowed to name it
in order to refuse it — so importing `RETIRED` is what keeps this guard from
becoming the next entry on that allowance list.

This is the case `.claude/DISCIPLINE.md` rule 3 names in its own evidence —
"the vendor leak in the run template but not comparison" — so the guard is
written over *every* bucket the comparison template renders, not the one a
report happened to cite.
"""

from clauditseo.reporting.render import (
    NOT_ASSESSED_CHECKS, render_comparison_report,
)
from tests.test_naming import RETIRED

#: The recommendation as it is stored, rebuilt around the one owner of the
#: retired prefix rather than transcribed. Four `cwv-not-assessed` rows in
#: `data/clauditseo.db` carry this exact text.
STORED_RECOMMENDATION = (
    f"Add {RETIRED}PAGESPEED_KEY or {RETIRED}CRUX_KEY for real CWV data.")

#: Every bucket `render_comparison_report` renders findings into. A
#: hard-coded list of three is how a partial fix passes, so this drives the
#: fixture rather than describing it: adding a bucket to the renderer without
#: adding it here leaves the new one unguarded, and the count assertion below
#: is what makes that visible.
BUCKETS = ("new", "resolved", "persisting", "not_rechecked")


def _not_assessed_finding() -> dict:
    return {
        "dimension": "PRF",
        "check_id": "cwv-not-assessed",
        "fingerprint": "f" * 8,
        "severity": "info",
        "source": "deterministic",
        "model_id": None,
        "confidence": "high",
        "summary": "Core Web Vitals not assessed",
        "recommendation": STORED_RECOMMENDATION,
        "evidence": {
            "unmeasured": ["Core Web Vitals"],
            "providers_failing": ["pagespeed"],
            "providers_answering": [],
            "reason": "no provider available",
            "tier_calls_external": True,
            "pages_fetched": True,
        },
    }


def _runs() -> tuple[dict, dict]:
    a = {"id": "run-a", "finished_at": "2026-08-01T00:00:00+10:00",
         "composite_score": 70.0, "scope": None}
    b = {"id": "run-b", "finished_at": "2026-08-20T00:00:00+10:00",
         "composite_score": 74.0, "scope": None}
    return a, b


def _diff_with_one_in_every_bucket() -> dict:
    return {bucket: [_not_assessed_finding()] for bucket in BUCKETS}


def test_the_fixture_check_is_one_the_product_calls_not_assessed():
    """Precondition. Without it the test below passes for the wrong reason."""
    assert "cwv-not-assessed" in NOT_ASSESSED_CHECKS


def test_no_comparison_bucket_hands_a_client_the_stored_recommendation():
    markdown, _ = render_comparison_report(
        {"domain": "example.test"}, *_runs(),
        _diff_with_one_in_every_bucket(), "client")

    assert RETIRED not in markdown, (
        "the comparison deliverable instructs a client to set an environment "
        "variable naming a retired product")
    assert "pagespeed" not in markdown.lower(), (
        "the comparison deliverable names the operator's supplier to a client")
    assert "What to do: " not in markdown, (
        "a dimension that was not measured is not something the client has "
        "an action for; the run template does not offer one either")


def test_every_bucket_still_tells_the_client_the_dimension_went_unmeasured():
    """Silence is the other failure. The gap belongs in the client's copy.

    Suppressing the line rather than rebuilding it would let a client read
    an absent dimension as a clean bill — which is what `_not_assessed_line`
    exists to prevent, and it must hold once per bucket rather than once per
    document.
    """
    markdown, _ = render_comparison_report(
        {"domain": "example.test"}, *_runs(),
        _diff_with_one_in_every_bucket(), "client")

    stated = [line for line in markdown.splitlines()
              if "Not assessed: Core Web Vitals" in line]
    assert len(stated) == len(BUCKETS), (
        f"{len(stated)} of {len(BUCKETS)} buckets state the gap: "
        f"{stated}")


def test_the_internal_copy_keeps_the_operator_facing_reason():
    """The distinction is the audience, not the removal of information."""
    markdown, _ = render_comparison_report(
        {"domain": "example.test"}, *_runs(),
        _diff_with_one_in_every_bucket(), "internal")

    assert "Reason: no provider available" in markdown, (
        "the operator's copy no longer says why the dimension was not "
        "measured, which is the half only the operator can act on")


def test_an_ordinary_finding_is_untouched_by_the_routing():
    """The change is a route, not a filter. A real defect still reports."""
    ordinary = {
        "dimension": "ONP", "check_id": "img-alt-missing",
        "fingerprint": "a" * 8, "severity": "medium",
        "source": "deterministic", "model_id": None, "confidence": "high",
        "summary": "Images lack alt text on 3 pages",
        "recommendation": "Write alt text describing each image.",
        "evidence": {},
    }
    diff = {bucket: [] for bucket in BUCKETS}
    diff["persisting"] = [ordinary]

    markdown, _ = render_comparison_report(
        {"domain": "example.test"}, *_runs(), diff, "client")

    assert "Images lack alt text on 3 pages" in markdown
    assert "What to do: Write alt text describing each image." in markdown
