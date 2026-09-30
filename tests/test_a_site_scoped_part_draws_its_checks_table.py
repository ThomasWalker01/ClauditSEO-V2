"""Item 230 (Security & transport, change 1): a site-scoped part draws its
checks table.

`security` and `content` render `siteScope`, and that branch drew the part's
picture INSTEAD of the checks table. So Security on twenty22 T3 had no table,
no "N checks pass" line naming what was measured clean, no Free/Analysis
split - and no row on which `csp-weak`'s gap could be seen at all. The
branch draws the picture, then the table, as the `siteNow` branch does.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://siteScoped.fixture".lower()


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["SEC"], "T2")
    runs.store_evidence(conn, run_id, {"start_url": BASE + "/",
                                       "pages": [{"url": BASE + "/", "status": 200}]})
    runs.mark_complete(conn, run_id, now_iso())
    conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?", (json.dumps(["/"]), run_id))
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
            " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'SEC', 'caa',"
            " 'low', 'deterministic', 'no CAA record', ?, 'sec-caa', ?)",
            (create_id(), run_id, json.dumps([BASE + "/"]), now_iso()))
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
            " updated_at) VALUES (?, 'sec-caa', 'open', ?, ?)", (site_id, run_id, now_iso()))
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("sitescoped")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Sec Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": BASE.split("//")[1]}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@needs_build
@pytest.mark.parametrize("part", ["security", "content"])
def test_the_part_draws_its_checks_table(served, part):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part={part}",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-page .now-card, .part-page .part-checks", timeout=15_000)
            got = pg.evaluate("""() => ({
              checks: !!document.querySelector('.part-page .part-checks'),
              rows: [...document.querySelectorAll('.part-page .checks-table tbody tr code')]
                .map((c) => c.textContent.trim()),
            })""")
        finally:
            b.close()
    assert got["checks"], f"{part}: no checks table at site scope"
    if part == "security":
        assert "SEC/caa" in got["rows"], got["rows"]
