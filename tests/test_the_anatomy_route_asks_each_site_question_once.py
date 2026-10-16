"""The anatomy route asks each site-level question once per request
(10 October, after round 3).

`_audits_since` was asked 32 times per load of twenty22's Client screen,
each re-reading every run's crawled-path list, and `page_facts` parsed the
1.8 MB reference evidence afresh twice per call, thirty times per load.
Measured on a copy of the live database: 2.1 s per load before, 0.8 s after.

The memo lives only inside `one_evidence_read`, the scope the route already
opens, so nothing outlives the request and a write is never hidden.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.persistence import runs


def _site(tmp_path):
    api = TestClient(create_app(db_path=tmp_path / "c.db"))
    client_id = api.post("/api/clients", json={"name": "T"}).json()["id"]
    site_id = api.post(f"/api/clients/{client_id}/sites",
                       json={"domain": "https://t.example/"}).json()["id"]
    conn = connect(tmp_path / "c.db")
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete', composite_score=70 WHERE id=?",
                 (run_id,))
    conn.commit()
    return conn, site_id, run_id


def _counting(conn):
    seen = []
    conn.set_trace_callback(lambda sql: seen.append(sql) if "FROM audit_runs" in sql else None)
    return seen


def test_inside_the_scope_the_question_is_asked_once(tmp_path):
    conn, site_id, run_id = _site(tmp_path)
    seen = _counting(conn)
    with runs.one_evidence_read(conn):
        for _ in range(5):
            assert runs._audits_since(conn, site_id, run_id) == 0
            runs.part_only_runs(conn, site_id)
    assert len(seen) == 2, seen
    conn.close()


def test_outside_it_every_call_reads_the_database(tmp_path):
    conn, site_id, run_id = _site(tmp_path)
    seen = _counting(conn)
    for _ in range(3):
        runs._audits_since(conn, site_id, run_id)
    # Two reads a call since screen audits round 4 (Shop AC-01): the
    # readings, and the part-only set they are counted without.
    assert len(seen) == 6, seen
    conn.close()


def test_a_caller_cannot_change_the_shared_answer(tmp_path):
    conn, site_id, _run_id = _site(tmp_path)
    with runs.one_evidence_read(conn):
        runs.part_only_runs(conn, site_id)["x"] = ["LNK"]
        assert "x" not in runs.part_only_runs(conn, site_id)
    conn.close()


def test_page_facts_hands_out_copies_of_the_shared_parse():
    import inspect
    src = inspect.getsource(runs.page_facts)
    assert "parsed_evidence(raw)" in src and "get_evidence(" not in src
    assert "_copy.deepcopy(tec.get(field))" in src
