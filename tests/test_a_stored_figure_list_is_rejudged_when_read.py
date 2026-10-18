r"""The operator's spot-check panel asks today's rule, not the rule that ran.

CQ-172. `expert_report` returns `figures_to_verify` straight out of the
`expert_reports.figures` column and `expert_report_figures` returns the same
column narrower; nothing recomputes either. So every improvement to what counts
as a figure — the token boundary at round 081, the shared masking at 082, the
two vocabulary shapes at 083 — lands on the deliverable, which re-judges at
render time through `figure_is_unverified`, and on neither of these two routes.

Measured read-only against `data/clauditseo.db` for report 084: of **189**
stored flagged values across 38 briefs, **28 are values today's code would not
produce** and **65 carry a context string that differs from what the code
returns today**. The shape from the operator's chair, read off the running
service: `GET /api/runs/1d85ff71.../expert/js-rendering` answers
`figures_to_verify` as exactly nine pairs — `14` `15` `16` `21` `24` `25` `26`
`27` `29`, every context the empty string — a panel asking for nine ordered-list
indices to be spot-checked before a client sees them.

What these guards pin is a **read-time re-judgement**, and its edges:

- a stored value today's `mask_vocabulary` hides is **dropped**;
- a value today's rule still produces is **kept, in stored order**;
- a kept value's **context is re-derived**, so the sentence the panel quotes is
  the one the current locator chooses rather than one a superseded one did;
- nothing is **added**. The judgement the brief made was `ungrounded_in_order`
  over the crawl evidence, and the evidence is not stored beside the payload,
  so this side can only narrow. Same floor argument `figure_is_unverified`
  already makes for the deliverable, for the same missing input;
- nothing is **written**. The stored row is the operator's history and a read
  does not get to edit it.

**And the client's document does not move.** `_declares_a_figure` intersects
the declared values with the *masked summary*, and the summaries are part of
the very scan this re-judge masks — so a value that survives masking in a
summary survives it in the scan, and narrowing the declared list cannot
withdraw a caveat. Asserted here rather than reasoned about, because it is what
decides whether this change is a renderer change.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.analysts.expert import figure_context, mask_vocabulary
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.reporting.generate import _expert_section, tool_runs_for
from clauditseo.reporting.render import ANALYST_FIGURE_NOTE

TOOL = "sitemap-coverage"

#: A derived total standing alone in prose, above the small-ordinal vocabulary
#: and clear of every masking pattern. The value that must survive.
DERIVED = "2300"

#: An ordered-list index. `_VOCABULARY` has masked a line-initial digit run
#: followed by a full stop and a space since round 083, so today's extractor
#: never sees it — but a brief run before that stored it, and nine of them are
#: on the operator's `js-rendering` panel now.
INDEX = "14"

#: The second half of a standards reference. Same round, same fix, and the row
#: it happened to in the operator's database is `local-signals/nap-inconsistent`.
STANDARD = "164"

REPORT = """## Sitemap coverage

14. Sitemap coverage was reviewed against the crawl.

Roughly 2300 indexable URLs are absent from the sitemap, which is the
gap this section is about.

Every listing gives the `tel` value as an E.164 string.
"""

MISSING = "pages-absent-from-sitemap"
INCONSISTENT = "tel-values-inconsistent"

FINDINGS = [
    {"code": MISSING, "severity": "high",
     "summary": f"Roughly {DERIVED} indexable pages are absent from the sitemap."},
    {"code": INCONSISTENT, "severity": "medium",
     "summary": "The `tel` values are not written consistently."},
]

#: The row as a brief stored it before the two vocabulary shapes existed:
#: three values, in the order the extractor found them, and a context for the
#: survivor that a superseded locator chose. The two stale ones carry the empty
#: string, which is what the operator's panel really holds — `figure_context`
#: could not locate them once the masking moved.
STORED_FIGURES = [
    {"value": INDEX, "context": ""},
    {"value": DERIVED, "context": "2300 URLs"},
    {"value": STANDARD, "context": ""},
]


@pytest.fixture
def stored(tmp_path):
    """One run, one brief, one stored figure list, and the connection back."""
    conn = connect(tmp_path / "rejudge-figures.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Rejudge Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, TOOL, {
        "model": "stub-model",
        "report": REPORT,
        "findings": FINDINGS,
        "figures_to_verify": STORED_FIGURES,
    })
    runs.record_expert_findings(conn, run_id, TOOL, "stub-model", FINDINGS,
                                figures=STORED_FIGURES)
    try:
        yield conn, run_id, site_id
    finally:
        conn.close()


def _values(figures):
    return [f["value"] for f in figures]


def test_the_panel_drops_a_value_todays_rule_would_not_produce(stored):
    """The two stale values go and the derived one stays, from `expert_report`.

    Both of the dropped ones appear in the brief's prose only inside a span
    `mask_vocabulary` covers, so today's extractor produces neither. Asserted
    as the whole list rather than two absences: a re-judge that dropped
    everything would satisfy two `not in`s and be wrong.
    """
    conn, run_id, _ = stored
    report = runs.expert_report(conn, run_id, TOOL)
    assert _values(report["figures_to_verify"]) == [DERIVED]


def test_the_narrow_read_drops_them_too(stored):
    """`expert_report_figures` is the same question asked by the renderer.

    Two routes onto one column, and a rule applied to one of them is the
    defect this file is about wearing a different hat.
    """
    conn, run_id, _ = stored
    assert _values(runs.expert_report_figures(conn, run_id, TOOL)) == [DERIVED]


def test_a_kept_values_context_is_the_sentence_todays_locator_chooses(stored):
    """`2300 URLs` is not a sentence in the brief; the stored row says it is.

    Sixty-five of the operator's 189 stored contexts disagree with what
    `figure_context` returns today. The value survives the re-judge and its
    sentence is re-derived with it, because a panel quoting prose the brief
    does not contain is the defect `figure_context` was written against.
    """
    conn, run_id, _ = stored
    scan = "\n".join([f["summary"] for f in FINDINGS] + [REPORT])
    want = figure_context(scan, DERIVED, locate_in=mask_vocabulary(scan))
    assert want and want != "2300 URLs"
    kept = runs.expert_report(conn, run_id, TOOL)["figures_to_verify"]
    assert [f["context"] for f in kept] == [want]


def test_a_list_todays_rule_still_produces_comes_back_whole_and_in_order(stored):
    """Must-not-change. Narrowing is the point; narrowing everything is not."""
    conn, run_id, _ = stored
    whole = [{"value": DERIVED, "context": "x"},
             {"value": "4718", "context": "y"}]
    runs.store_expert_report(conn, run_id, "hreflang", {
        "model": "stub-model",
        "report": f"The audit counted {DERIVED} pages and 4718 links.",
        "findings": [],
        "figures_to_verify": whole,
    })
    got = runs.expert_report(conn, run_id, "hreflang")["figures_to_verify"]
    assert _values(got) == [DERIVED, "4718"]


def test_the_read_writes_nothing_back(stored):
    """Must-not-change. The stored row is the operator's history.

    Read through both routes and through the deliverable, then compare the
    column byte for byte — re-stamping would destroy the only evidence of
    which rows predate the rule that re-judges them.
    """
    conn, run_id, site_id = stored
    before = conn.execute(
        "SELECT figures FROM expert_reports WHERE run_id=? AND tool_id=?",
        (run_id, TOOL)).fetchone()["figures"]
    runs.expert_report(conn, run_id, TOOL)
    runs.expert_report_figures(conn, run_id, TOOL)
    _expert_section(conn, tool_runs_for(conn, site_id), site_id, "client")
    after = conn.execute(
        "SELECT figures FROM expert_reports WHERE run_id=? AND tool_id=?",
        (run_id, TOOL)).fetchone()["figures"]
    assert after == before
    assert json.loads(after) == STORED_FIGURES


def test_the_clients_document_is_not_moved_by_the_narrower_list(stored):
    """Must-not-change, and the one that decides this is not a renderer change.

    The finding quoting the surviving figure keeps its caveat, and the one
    quoting no figure at all still has none. If narrowing the declared list
    could withdraw a caveat, this change would alter what a stored deliverable
    says and would owe a `RENDERER_VERSION` bump; it cannot, because the
    summaries are inside the scan the re-judge masks.
    """
    conn, run_id, site_id = stored
    section, _ = _expert_section(conn, tool_runs_for(conn, site_id), site_id, "client")
    caveated = [ln for ln in section.splitlines() if ANALYST_FIGURE_NOTE in ln]
    assert len(caveated) == 1
    assert f"`{MISSING}`" in caveated[0] and DERIVED in caveated[0]
