"""One definition of a run that reads the site: a site-reading kind whose
scope is site-wide - the stored scope, else the crawl's page count for a
row that stored none, never the tier. The server says so on every run row
and the client reads it.

Brief v6 step V2 (`_plans/site-screen-brief-v6-2026-09-03.md`). On Birch
the 08:48 run - T3, twelve crawled paths, no stored scope - was admitted
as a reading of the site by its kind alone, so the anatomy computed its
"read" pills against it while the picker, correctly, would not default to
it. An audit created without a stated scope now reads the site (`full`);
only a row from before the column is NULL, and the page count judges it.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_coverage import DIMS, _Hub, _run
from tests.test_triage_ranks_the_section_rail import _serve


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("onepredicate")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Predicate Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "predicate.fixture"}, timeout=30).json()
        conn = connect(db)
        result = _run(_Hub())
        # A legacy T3 row: twelve paths, no stored scope.
        legacy = runs.create_run(conn, site["id"], DIMS, "T3")
        runs.complete_run(conn, legacy, result)
        conn.execute("UPDATE audit_runs SET scan_scope=NULL, crawled_paths=? WHERE id=?",
                     (json.dumps([f"/p{n}" for n in range(12)]), legacy))
        # An audit created without a stated scope.
        plain = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, plain, result)
        # A verification: never a reading, whatever it fetched.
        verify = runs.create_run(conn, site["id"], DIMS, "T2", kind="verify")
        runs.complete_run(conn, verify, result)
        conn.execute("UPDATE audit_runs SET scan_scope='full' WHERE id=?", (verify,))
        conn.commit()
        conn.close()
        yield base, db, site["id"], legacy, plain, verify
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_predicate_is_kind_and_scope_never_tier(served):
    base, db, site_id, legacy, plain, verify = served
    conn = connect(db)
    by = {r["id"]: r for r in runs.list_runs(conn, site_id)}
    assert by[plain]["scan_scope"] == "full", "an audit with no stated scope did not default to full"
    assert runs.reads_site(by[plain]) and by[plain]["site_reading"] and by[plain]["effective_scope"] == "full"
    assert not runs.reads_site(by[legacy]) and by[legacy]["effective_scope"] == "nav", by[legacy]["effective_scope"]
    assert not runs.reads_site(by[verify]), "a verification reads the site"
    # The SQL owner agrees with the Python one, alias or no alias.
    ids = {r["id"] for r in conn.execute(
        f"SELECT r.id FROM audit_runs r WHERE r.site_id=? AND {runs.kind_is_site_reading('r.kind')}",
        (site_id,))}
    assert ids == {plain}, ids
    assert [r["id"] for r in runs.site_readings(conn, site_id)] == [plain]
    conn.close()


def test_the_wire_and_the_runs_table_agree(served):
    base, db, site_id, legacy, plain, verify = served
    rows = {r["id"]: r for r in httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["runs"]}
    assert rows[legacy]["site_reading"] is False and rows[legacy]["effective_scope"] == "nav"
    assert rows[plain]["site_reading"] is True and rows[plain]["effective_scope"] == "full"
    assert rows[verify]["site_reading"] is False
