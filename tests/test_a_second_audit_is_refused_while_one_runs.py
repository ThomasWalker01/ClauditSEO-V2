"""`POST /api/sites/{id}/audits` refuses a second audit while one is in flight.

The brief route has refused a duplicate since KI-19 — a test-and-set under a
lock, answering 409 with "wait for it to finish rather than paying for it
twice". The audit route, the dearer purchase, validated dimensions, tier,
scope, depth and start URL and then created the run unconditionally. The
second audit of 2026-09-02 (F-03) drove it: with a run in flight the chooser
rendered twelve enabled launch cells, and the route accepted each of them.

The guard here is the stored status rather than an in-memory claim, because a
crawl outlives a request: the row is what says it is running, and a restart
of the server must not forget an audit the worker is still executing.

**Through the route, not the persistence layer**, because the refusal is a
status code the screen acts on: `ScanMatrix` shows the route's `detail` in its
own error line, and a refusal that only the database knew about would leave
the cell reading "starting…" forever.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_coverage import DIMS


def _site(client: TestClient) -> str:
    c = client.post("/api/clients", json={"name": "Twice Co"}).json()
    return client.post(f"/api/clients/{c['id']}/sites",
                       json={"domain": "twice.fixture"}).json()["id"]


def test_a_second_audit_is_refused_with_409_and_names_the_run(tmp_path, monkeypatch):
    # No crawl may leave this test: the route starts one on a thread when it
    # accepts, and the fixture domain does not resolve. Refusal is asserted
    # before any acceptance would be, so the thread is never started.
    db = tmp_path / "twice.db"
    app = create_app(db_path=db)
    with TestClient(app) as client:
        site_id = _site(client)
        conn = connect(db)
        running = runs.create_run(conn, site_id, DIMS, "T2")   # status 'running'
        conn.close()

        r = client.post(f"/api/sites/{site_id}/audits",
                        json={"scope": "site", "depth": "quick"})
        assert r.status_code == 409, (r.status_code, r.text)
        assert "already running" in r.json()["detail"]
        assert running in r.json()["detail"], (
            "the refusal does not name the run the operator should wait for")

        conn = connect(db)
        n = conn.execute("SELECT COUNT(*) FROM audit_runs WHERE site_id=?",
                         (site_id,)).fetchone()[0]
        conn.close()
        assert n == 1, f"the refusal still created a run: {n} rows"


def test_a_finished_audit_does_not_block_the_next(tmp_path):
    """The other side of the guard: a completed run is not "in flight", so
    the route must not refuse on its account. Asserted by status code only —
    the accepted run starts a crawl thread against a domain that does not
    resolve, which fails on its own and is not what this test is about."""
    from tests.test_coverage import _Hub, _run

    db = tmp_path / "once.db"
    app = create_app(db_path=db)
    with TestClient(app) as client:
        site_id = _site(client)
        conn = connect(db)
        done = runs.create_run(conn, site_id, DIMS, "T2")
        runs.complete_run(conn, done, _run(_Hub()))
        conn.close()

        r = client.post(f"/api/sites/{site_id}/audits",
                        json={"scope": "site", "depth": "quick"})
        assert r.status_code != 409, r.text


def test_a_narrow_audit_in_flight_still_refuses_the_next(tmp_path):
    """WF-114: the guard asks a kind question, not a scope one.

    Brief v6 step V2 (`e7ff31c`) redefined `runs.kind_is_site_reading()` from
    "a site-reading kind" to "a site-reading kind whose scope is site-wide" —
    the right rule for the readers that ask which run may *stand for* the
    site, and the wrong one for this guard, which asks only whether a crawl
    is already in flight. A `nav`-scoped audit stopped matching, so the 409
    stopped firing and the dearer purchase went back to accepting a second
    concurrent crawl.

    The case above cannot see it: `create_run()` defaults `scan_scope` to
    `'full'` for `kind='audit'`, so its in-flight run is site-wide by
    accident and matches either predicate. The scope is stated here.

    Two concurrent crawls against one site race each other's writes and bill
    the analyst layer twice, which is what KI-19's "wait for it to finish
    rather than paying for it twice" exists to prevent.
    """
    db = tmp_path / "narrow.db"
    app = create_app(db_path=db)
    with TestClient(app) as client:
        site_id = _site(client)
        conn = connect(db)
        running = runs.create_run(conn, site_id, DIMS, "T2", scan_scope="nav")
        assert conn.execute("SELECT scan_scope FROM audit_runs WHERE id=?",
                            (running,)).fetchone()[0] == "nav", (
            "the fixture did not store the narrow scope this test is about")
        conn.close()

        r = client.post(f"/api/sites/{site_id}/audits",
                        json={"scope": "site", "depth": "quick"})
        assert r.status_code == 409, (
            "a nav-scoped audit in flight did not block a second audit: "
            f"{r.status_code} {r.text}")
        assert running in r.json()["detail"]

        conn = connect(db)
        n = conn.execute("SELECT COUNT(*) FROM audit_runs WHERE site_id=?",
                         (site_id,)).fetchone()[0]
        conn.close()
        assert n == 1, f"the refusal still created a run: {n} rows"
