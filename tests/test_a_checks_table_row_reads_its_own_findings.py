"""Item 220 (Structured data, change 3's remainder): a checks-table row's
STATE is read from its findings, and a check a card resolves is not clean.

Items 206 and 208 took held rows out of the count columns. Two readings were
left, both seen on twenty22 T3:

  AC-06 `ONP/schema-sameas-missing` held one candidate (/about/) and one
        hold ("/"). STATE was `every row is a candidate`, a hold is not a
        candidate, so the row read "open" - the confirmed state - for a
        model-only finding nothing had confirmed.
  AC-07 `schema-catalog-mismatch` read "clean on every page this audit
        fetched" while the /website-seo/ card listed it in `also_resolves`:
        the same check on the same page was clean and fixed at once.
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://tablerows.fixture"
HOME, ABOUT = BASE + "/", BASE + "/about/"


def _row(check_id, page, also=()):
    return {"check": f"ONP/{check_id}", "dimension": "ONP", "check_id": check_id,
            "page": page, "status": "FAIL", "severity": "medium", "evidence": "x",
            "replacement": '{"@id": "x"}', "note": "", "also_resolves": list(also)}


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run_id, {"pages": [
        {"url": HOME, "status": 200, "title": "Home", "canonical": HOME},
        {"url": ABOUT, "status": 200, "title": "About", "canonical": ABOUT}]})
    runs.mark_complete(conn, run_id, now_iso())
    rows = [_row("schema-sameas-missing", ABOUT),
            _row("schema-required-missing", HOME, also=["ONP/schema-catalog-mismatch"])]
    held = [{"check": "ONP/schema-sameas-missing", "page": HOME,
             "needs": "the profiles the entity controls"}]
    runs.store_expert_report(conn, run_id, "structured-data", {
        "model": "m-1", "cost": 0.4, "report": "## Structured data", "findings": [],
        "contract": {"status": "read", "part": "schema", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": held, "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "structured-data", "m-1", rows)
    runs.recompute_contract_states(conn, site_id, "structured-data")
    conn.close()


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("tablerows")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Rows Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "tablerows.fixture"}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def table(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=schema",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-page .part-checks", timeout=15_000)
            return pg.evaluate("""() => ({
              rows: Object.fromEntries([...document.querySelectorAll('.checks-table tbody tr')]
                .map((tr) => [(tr.querySelector('code')?.textContent || '').trim(),
                              (tr.lastElementChild?.textContent || '').trim()])),
              clean: [...document.querySelectorAll('.part-checks .cause-clean-line')]
                .map((p) => p.textContent || '').join(' | '),
            })""")
        finally:
            b.close()


@needs_build
def test_a_candidate_beside_a_hold_reads_candidate(table):
    # "not yet confirmed" since item 237: `schema-sameas-missing` is a check
    # only a model raises, so its candidate waits for the operator. What this
    # holds is that the hold does not make it read "open".
    assert table["rows"].get("ONP/schema-sameas-missing") == "not yet confirmed", table["rows"]


@needs_build
def test_a_check_a_card_resolves_is_neither_clean_nor_unlisted(table):
    state = table["rows"].get("ONP/schema-catalog-mismatch", "")
    assert state.startswith("resolved by the ONP/schema-required-missing fix"), table["rows"]
    assert "clean on every page" in table["clean"], table["clean"]
    assert "schema-catalog-mismatch" not in table["clean"], table["clean"]
