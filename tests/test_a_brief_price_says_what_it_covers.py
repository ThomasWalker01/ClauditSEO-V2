"""UX-74: a per-brief price says how many of its samples carried a price.

**The same breach as UX-04, in the paths UX-04's fix did not reach.** Round 079
closed the frame on the *monthly* figures — `_budget_status` and
`monthly_spend` now return `usd_entries` and `usd_unpriced` beside their
totals, and Home and Admin render them. The *per-brief* figures were left as
they were, and they are computed the same wrong way: a median or mean over the
priced subset of a sample, reported beside a count taken over the whole sample.

**Measured read-only against `data/clauditseo.db` on 22 August 2026**, which is
where the fixtures below come from rather than from an invented shape:
`expert_estimates` returns `indexability` as `{'samples': 3, ..., 'cost':
0.1195}` where one of those three stored briefs carries a cost, and
`site-architecture` as `samples 2` over one priced row. Across
`expert_reports`, 12 of 38 stored briefs carry a cost at all. `/api/playbook`
repeats it in a worse form: `AVG(actual_cost)` is returned beside
`runs_costed: COUNT(*)` — a key whose *name* says "runs that were costed" and
whose *value* is every run, costed or not.

**This guard is about the frame reaching the wire, not about any screen.**
The frame clause of the provenance invariant is that a number's scope travels
with the value; a figure that never leaves the database with its scope cannot
be rendered with it however careful the renderer is, which is the failure
`evidence.snapshot()` produced for the TLS floor (B-11) — measured in one
function and dropped one function later. So the three assertions here are at
the three boundaries the figure crosses: the estimator that computes it, the
playbook endpoint that re-derives it from a different table, and the schedule
endpoint that re-serialises the estimator and today keeps only the number.

**Pure Python, deliberately.** Nothing here loads `dashboard/dist`, so
`scripts/prove_fail.py` can answer for this file. That sentence used to end
"— CQ-164 records that it answers wrongly for twenty of the twenty-one test
files that do", which stopped being true at `2f8eb02`: `needs_build` now
derives the refusal set from each file's own AST, and report 083 records
CQ-164 under fixed. The count is removed rather than updated, for the same
reason its two siblings give.

**What this guard does not claim.** It does not assert any wording. What the
four render sites *say* about the frame is a separate step, and one that can
be argued about; that a renderer is given the frame at all cannot.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


def _seed(conn):
    """Three briefs for one tool, one of them priced.

    The operator's own `indexability` shape reduced to its smallest
    reproducing case. One row per (run, tool) is enforced by the table, so
    each sample needs its own run — the same constraint
    `test_expert_tools.py` records.
    """
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Partly Priced Co")
    site = repo.create_site(conn, client, "partly-priced.test")
    for tokens, cost in ((30_000, 0.1195), (30_000, None), (30_000, None)):
        run_id = runs.create_run(conn, site, ["TEC"], "T2")
        envelope = {"model": "m", "report": "r", "tokens": tokens}
        if cost is not None:
            envelope["cost"] = cost
        runs.store_expert_report(conn, run_id, "indexability", envelope)
        runs.log_cost(conn, run_id, "llm", "EXPERT:indexability", "tokens",
                      tokens, actual_cost=cost)
    return site


@pytest.fixture
def partly_priced_db(tmp_path):
    path = tmp_path / "brief-price.db"
    conn = connect(path)
    migrate(conn)
    _seed(conn)
    conn.close()
    return path


def test_the_estimator_says_how_many_of_its_samples_carried_a_price(tmp_path):
    """`samples: 3` beside `cost: 0.1195` is the whole finding.

    `samples` counts rows with tokens; `cost` is a median over rows with a
    non-NULL cost. Those are different populations and only the first is
    reported, so `0.1195` reads as the typical price of this brief when it is
    the only price this brief has ever recorded.
    """
    conn = connect(tmp_path / "estimator.db")
    migrate(conn)
    try:
        _seed(conn)
        est = runs.expert_estimates(conn)["indexability"]
    finally:
        conn.close()

    assert est["samples"] == 3
    assert est["cost"] == 0.1195
    assert est["cost_samples"] == 1, (
        "the estimate does not say how many of its samples carried a price, "
        "so a median over one row is indistinguishable from a median over "
        "three")


def test_the_playbook_names_the_count_its_average_cost_was_taken_over(
        partly_priced_db, monkeypatch):
    """`runs_costed` is `COUNT(*)`, and `AVG(actual_cost)` is not.

    SQLite's `AVG` skips NULLs, so the average and the count beside it are
    taken over different row sets while the key name asserts they are the
    same one. The name is the honest one; it is the value that has to move.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    api = TestClient(create_app(db_path=partly_priced_db))

    brief = api.get("/api/playbook").json()["experts"]["indexability"]

    assert brief["typical_cost"] == 0.1195
    assert brief["runs_costed"] == 1, (
        "`runs_costed` reports every run of this brief, priced or not, while "
        "the average beside it is taken over the priced ones alone")
    assert brief["runs_sampled"] == 3, (
        "the playbook does not say how many runs the priced subset was drawn "
        "from, so the reader cannot tell what share of them the price covers")


def test_the_schedule_payload_carries_the_frame_beside_each_price(
        partly_priced_db, monkeypatch):
    """The estimator's frame, one function later, at the wire.

    The schedule modal multiplies `typical_cost` into an annual forecast. A
    price drawn from one run of three, multiplied by fifty-two, is a forecast
    with a scope the screen has never been told about — and the endpoint
    re-serialises the estimator field by field, so a frame added upstream is
    dropped here unless it is carried deliberately.
    """
    monkeypatch.setenv("CLAUDITSEO_LLM_PROVIDER", "mock")
    conn = connect(partly_priced_db)
    site_id = repo.list_sites(conn, repo.list_clients(conn)[0]["id"])[0]["id"]
    conn.close()
    api = TestClient(create_app(db_path=partly_priced_db))

    payload = api.get(f"/api/sites/{site_id}/schedule").json()
    row = next(a for a in payload["available"]
               if a["tool_id"] == "indexability")

    assert row["typical_cost"] == 0.1195
    assert row["cost_samples"] == 1, (
        "the schedule payload carries the price and not the number of runs "
        "it was drawn from, so the annual forecast built from it cannot "
        "state its own scope")
    assert row["samples"] == 3, (
        "the schedule payload does not say how many runs of this brief exist, "
        "so `cost_samples` alone cannot be read as a share")
