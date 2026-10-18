"""Item 178, commit 1: the client-report guard holds on the server before the
plan's model call, not after it.

UI audit 08-2. The landing held "Build the client report" while a Critical or
High finding was unassessed, and the document generator refused a client
report for the same reason - but the Reports screen writes the client plan
first, a model call, and only then asks for the document. On a held site the
plan was paid for and the document was then refused.

So the plan route takes `for_audience`. With `client`, it checks the same
threshold the generator does, with the same sentence from one owner
(`runs.client_report_hold`), before anything is claimed or spent. The
operator's own reading - no audience, or `internal` - is never held, because
the internal document is how the assessing gets done.

Driven against a real server with the model call replaced by a recorder, so
"no spend" is asserted as "the model was never reached", not inferred from a
status code.
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_coverage import DIMS, _Hub, _run
from tests.test_triage_ranks_the_section_rail import _serve

#: The threshold is off suite-wide and live only where it is the subject (conftest).
pytestmark = pytest.mark.integrity_threshold


def _plant_open_high(conn, run_id):
    site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?", (run_id,)).fetchone()[0]
    fp = "held-report-planted-high"
    conn.execute("INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                 " confidence, summary, affected_urls, evidence, recommendation, fingerprint,"
                 " created_at) VALUES (lower(hex(randomblob(16))), ?, 'TEC', 'robots-missing',"
                 " 'high', 'deterministic', 'high', 'planted High', '[]', '{}', '', ?,"
                 " '2026-09-18T00:00:00')", (run_id, fp))
    conn.execute("INSERT OR REPLACE INTO finding_states (site_id, fingerprint, state, updated_at)"
                 " VALUES (?, ?, 'open', '2026-09-18T00:00:00')", (site_id, fp))
    conn.commit()
    return site_id, fp


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("heldplan")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Held Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "heldplan.fixture"}, timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, _run(_Hub()))
        site_id, fp = _plant_open_high(conn, run_id)
        conn.close()
        yield base, db, run_id, site_id, fp
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def model_calls(monkeypatch):
    """Every model call the plan route would make, recorded and not made."""
    import clauditseo.analysts.expert as expert
    calls: list[str] = []

    def record(conn, run_id, tool_id, *args, **kwargs):
        calls.append(tool_id)
        raise RuntimeError("model call recorded, not made")

    monkeypatch.setattr(expert, "run_expert", record)
    return calls


def test_a_held_client_report_refuses_the_plan_before_it_spends(served, model_calls):
    base, db, run_id, site_id, fp = served
    conn = connect(db)
    # Held whatever ran before: tests are not guaranteed an order.
    runs.set_state(conn, site_id, fp, "open")
    hold = runs.client_report_hold(conn, site_id)
    conn.close()
    assert hold and "still open" in hold, "precondition: the fixture holds the report"

    refused = httpx.post(f"{base}/api/runs/{run_id}/expert/plan",
                         json={"for_audience": "client"}, timeout=30)
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == hold, "the plan route and the generator disagree on why"
    assert model_calls == [], f"the plan was paid for on a held report: {model_calls}"

    # The document is refused with the same sentence, so the two cannot drift.
    doc = httpx.post(f"{base}/api/reports", json={"template": "run", "audience": "client",
                                                  "run_ids": [run_id]}, timeout=30)
    assert doc.status_code == 422 and doc.json()["detail"] == hold, doc.text


def test_the_operators_own_plan_is_never_held(served, model_calls):
    """No audience and `internal` reach the model: the hold is on sending a
    client report, not on the operator reading one."""
    base, db, run_id, site_id, fp = served
    conn = connect(db)
    runs.set_state(conn, site_id, fp, "open")
    assert runs.client_report_hold(conn, site_id), "precondition: held, so not-held means not applied"
    conn.close()
    for body in ({}, {"for_audience": "internal"}):
        before = len(model_calls)
        r = httpx.post(f"{base}/api/runs/{run_id}/expert/plan", json=body, timeout=30)
        assert r.status_code != 422 or "still open" not in r.text, (body, r.text)
        assert len(model_calls) == before + 1, f"{body}: the operator's plan was held: {r.text}"


def test_once_assessed_the_client_plan_is_not_held(served, model_calls):
    base, db, run_id, site_id, fp = served
    conn = connect(db)
    # The site's open Critical and High, whichever run raised them: what the
    # hold counts since item 239 step 7.
    severe = conn.execute(
        "SELECT DISTINCT fs.fingerprint FROM finding_states fs"
        " JOIN findings f ON f.fingerprint = fs.fingerprint WHERE fs.site_id=?"
        " AND fs.state IN ('open','regressed') AND lower(f.severity) IN ('critical','high')",
        (site_id,)).fetchall()
    for row in severe:
        runs.set_state(conn, site_id, row["fingerprint"], "accepted-risk")
    assert runs.client_report_hold(conn, site_id) is None
    conn.close()
    r = httpx.post(f"{base}/api/runs/{run_id}/expert/plan",
                   json={"for_audience": "client"}, timeout=30)
    assert "still open" not in r.text, r.text
    assert model_calls == ["plan"], model_calls
