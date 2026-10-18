"""CQ-169: "what does this brief typically cost" has one computation.

**Three answers to one question, reaching four screens by three routes.**
`/api/playbook` took `AVG(actual_cost)` over `cost_entries`; `expert_estimates`
takes a median over `expert_reports.cost`; and the estimator answers again
differently depending on whether the caller passes `pages`. The Brief panel
(`expert.tsx:95-96`) reads the first, the Schedule modal (`schedule.tsx:144`)
reads the second, and no screen names which one it is showing.

**Measured read-only against `data/clauditseo.db` on 22 August 2026**, which is
where both fixtures below come from rather than from an invented shape::

    hreflang         playbook 0.0648   estimator 0.0633
    onpage-hygiene   playbook 0.0356   estimator 0.0352
    mobile-viewport  playbook 0.0687   estimator has no price at all

**The estimator is the right owner, and that was checked rather than assumed.**
Both divergences are the *playbook* being wrong, not a coin toss between two
defensible readings:

1. `hreflang` and `onpage-hygiene` each carry **two** `cost_entries` rows for
   one run against a **single** `expert_reports` row — `KNOWN_ISSUES.md`
   KI-19, "one brief can be run twice at once; both calls bill, and only the
   second report survives". `AVG` counts the abandoned retry as a second run,
   so `runs_costed: 2` describes one run and the price is the mean of a charge
   and its own replacement. `expert_reports` is one row per (run, tool) by
   table constraint, so the estimator cannot make this error. Note this fix
   does not *close* KI-19 — the double billing is still real. It stops the
   display inheriting it.
2. `mobile-viewport`'s playbook price is drawn from a run whose stored brief
   records **0 tokens**, which the estimator excludes by its `tokens > 0`
   filter. A price for a brief that recorded no work is not the more complete
   answer; it is the less trustworthy one.

**What this guard deliberately does not assert.** Nothing about *site* scope.
UX-77 — the Schedule modal pricing a brief from every site in the install under
a sentence saying it was measured on this one — is report 080's open question 1
and is the operator's to answer: show the install-wide price labelled as such,
or show nothing. The `site_id` argument report 080 proposes has no caller until
that is decided, so it is not added here. This file is about there being *one*
computation, not about which population it runs over.

**Pure Python, deliberately.** Nothing here loads `dashboard/dist`, so
`scripts/prove_fail.py` can answer for this file. That sentence used to end
"— CQ-164 records that it answers wrongly for twenty-one of the twenty-two
test files that do", which stopped being true at `2f8eb02`: `needs_build`
now derives the refusal set from each file's own AST, and report 083 records
CQ-164 under fixed. The count is removed rather than updated - it measured a
defect that no longer exists, and a number kept alive past its subject is the
wrong-address cost CQ-151 tracks.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


def _seed(conn):
    """The operator's `hreflang` and `mobile-viewport` rows, reduced.

    One row per (run, tool) is enforced by the table, so the double-billed
    retry has to be expressed where it really lives — two `cost_entries` rows
    against one `expert_reports` row for the *same* run.
    """
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Billed Twice Co")
    site = repo.create_site(conn, client, "billed-twice.test")

    # KI-19's shape: one run, one surviving report, two charges.
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, "hreflang",
                             {"model": "m", "report": "r",
                              "tokens": 9407, "cost": 0.063329})
    runs.log_cost(conn, run_id, "llm", "EXPERT:hreflang", "tokens",
                  8987, actual_cost=0.066342)
    runs.log_cost(conn, run_id, "llm", "EXPERT:hreflang", "tokens",
                  9407, actual_cost=0.063329)

    # `mobile-viewport`'s shape: charged, but the brief recorded no tokens, so
    # the estimator has no sample for it.
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.store_expert_report(conn, run_id, "mobile-viewport",
                             {"model": "m", "report": "r", "tokens": 0})
    runs.log_cost(conn, run_id, "llm", "EXPERT:mobile-viewport", "tokens",
                  0, actual_cost=0.06871)
    return site


@pytest.fixture
def billed_twice_db(tmp_path):
    path = tmp_path / "one-typical-cost.db"
    conn = connect(path)
    migrate(conn)
    _seed(conn)
    conn.close()
    return path


@pytest.fixture
def api(billed_twice_db, monkeypatch):
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    return TestClient(create_app(db_path=billed_twice_db))


def _site_id(db_path):
    conn = connect(db_path)
    try:
        return repo.list_sites(conn, repo.list_clients(conn)[0]["id"])[0]["id"]
    finally:
        conn.close()


def test_the_two_endpoints_report_one_price_for_one_brief(
        api, billed_twice_db):
    """The Brief panel and the Schedule modal cannot disagree about a price.

    They read different endpoints, and until this landed those endpoints ran
    different SQL over different tables. On the operator's own data that is
    `hreflang` at 0.0648 on one screen and 0.0633 on the other, with nothing
    on either screen saying which to believe.
    """
    site_id = _site_id(billed_twice_db)

    brief = api.get("/api/playbook").json()["experts"]["hreflang"]
    row = next(a for a in api.get(f"/api/sites/{site_id}/schedule").json()
               ["available"] if a["tool_id"] == "hreflang")

    assert brief["typical_cost"] == row["typical_cost"], (
        "the Brief panel and the Schedule modal price the same brief "
        "differently, and neither screen says which computation it is showing")
    assert brief["typical_cost"] == 0.0633, (
        "the price is the mean of a charge and the retry that replaced it "
        "(KI-19), not the cost the surviving brief recorded")


def test_a_brief_the_estimator_cannot_price_is_not_priced_by_the_playbook(api):
    """A charge without a brief behind it is not a typical cost.

    `mobile-viewport` carries an `actual_cost` against a stored brief of zero
    tokens. Averaging the charge produces a confident price for work nothing
    recorded, on the one screen where the operator decides what to buy.
    """
    brief = api.get("/api/playbook").json()["experts"]["mobile-viewport"]

    assert brief["typical_cost"] is None, (
        "the playbook prices a brief whose stored report recorded no tokens, "
        "so the Brief panel shows a price the estimator has no sample for")
    assert brief["runs_costed"] == 0, (
        "`runs_costed` counts charges rather than priced briefs, so it "
        "reports a sample the price was not taken over")


def test_the_playbook_counts_runs_rather_than_charges(api):
    """`runs_costed: 2` for one run is the double-billing leaking into a count.

    The name has always been the honest one. Taken over `cost_entries` its
    value counts charges; taken over `expert_reports` it counts the briefs
    that actually carried a price, which is what the name says.
    """
    brief = api.get("/api/playbook").json()["experts"]["hreflang"]

    assert brief["runs_costed"] == 1, (
        "one run billed twice is reported as two costed runs")
    assert brief["runs_sampled"] == 1, (
        "`runs_sampled` counts charge rows rather than stored briefs, so the "
        "share `runs_costed` is a share *of* is itself wrong")


def test_the_schedule_payload_says_whether_its_token_figure_was_scaled(
        api, billed_twice_db):
    """`scaled_to_pages` is computed and then dropped at the wire.

    The estimator returns it; the schedule endpoint re-serialises field by
    field and keeps only four keys, so the modal's annual forecast cannot say
    whether the tokens behind it were scaled to a crawl or are a flat median.
    This is the shape that lost the TLS floor between the probe that measured
    it and the panel that needed it (B-11).
    """
    site_id = _site_id(billed_twice_db)
    row = next(a for a in api.get(f"/api/sites/{site_id}/schedule").json()
               ["available"] if a["tool_id"] == "hreflang")

    assert "scaled_to_pages" in row, (
        "the endpoint drops the one key that says what the token figure was "
        "computed against")
    assert row["scaled_to_pages"] is None, (
        "this endpoint passes no `pages`, so the honest answer is that the "
        "figure is unscaled — which is a statement the payload must make "
        "rather than leave the reader to assume either way")
