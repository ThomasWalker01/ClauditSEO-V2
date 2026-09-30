"""Item 219 (Content, IP-01): a paid content card is not a free check.

Content's model rows are stored under `EXP:<brief>` (Q-56,
`runs.contract_storage_dimension`), and the registry prices the same checks
as `CNT/<id>`. The screen's lookup tried the stored id and `ONP/<id>`, missed
both, and read "free" - the default for a check it has never heard of. On
twenty22 T3 that put every content-substance and content-coverage card under
"Free checks · 163", left "Analysis · 7" holding only holds, and let "free
only" show paid work as free.

Planted: one free sweep row (`CNT/thin`) and one paid analysis row
(`content-substance`'s `eeat`, which the recorder files as
`EXP:content-substance`). Asserted: the paid card is under Analysis, and
"free only" hides it while keeping the free one.
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

BASE = "https://paidcontent.fixture"
HOME, ABOUT = BASE + "/", BASE + "/about/"


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["CNT"], "T2")
    runs.store_evidence(conn, run_id, {"pages": [
        {"url": HOME, "status": 200, "title": "Home", "canonical": HOME},
        {"url": ABOUT, "status": 200, "title": "About", "canonical": ABOUT}]})
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
            " summary, affected_urls, fingerprint, created_at) VALUES (?, ?, 'CNT', 'thin',"
            " 'medium', 'deterministic', 'thin on about', ?, 'sweep-thin', ?)",
            (create_id(), run_id, json.dumps([ABOUT]), now_iso()))
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
            " updated_at) VALUES (?, 'sweep-thin', 'open', ?, ?)", (site_id, run_id, now_iso()))
    rows = [
        {"check": "CNT/eeat", "check_id": "eeat", "dimension": "CNT", "page": HOME,
         "severity": "high", "status": "FAIL", "evidence": "no named author or proof",
         "replacement": "name the author"}]
    # As `expert.py` does: the report, its rows, then the states the screen reads.
    runs.store_expert_report(conn, run_id, "content-substance", {
        "model": "m-1", "cost": 0.09, "report": "## Content substance", "findings": [],
        "contract": {"status": "read", "part": "content", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run_id, "content-substance", "m-1", rows)
    runs.recompute_contract_states(conn, site_id, "content-substance")
    stored = conn.execute("SELECT dimension FROM findings WHERE check_id='eeat'").fetchone()
    conn.close()
    assert stored[0] == "EXP:content-substance", stored[0]
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("paidcontent")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Paid Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "paidcontent.fixture"}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_CARDS = """() => [...document.querySelectorAll('.part-fixes .fix-card')].map((c) => {
  let head = '';
  for (let n = c; n && !head; n = n.previousElementSibling) {
    if (n.classList && n.classList.contains('fixes-head')) head = n.textContent.trim();
  }
  if (!head) {
    const h = [...document.querySelectorAll('.part-fixes .fixes-head')]
      .filter((x) => x.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING).pop();
    head = h ? h.textContent.trim() : '';
  }
  return { head: head.split('·')[0].trim(), check: (c.querySelector('.fix-check')?.textContent || '').trim() };
})"""


def _cards(browser, url):
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(url, wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        pg.wait_for_selector(".part-page .part-fixes", timeout=15_000)
        return pg.evaluate(_CARDS)
    finally:
        pg.close()


@needs_build
def test_a_paid_content_card_sits_under_analysis(browser, served):
    base, site_id = served
    cards = _cards(browser, f"{base}/#/sites/{site_id}?tab=findings&part=content")
    under = {c["check"]: c["head"] for c in cards}
    paid = [k for k in under if k.startswith("EXP:content-substance")]
    assert paid, cards
    assert all(under[k] == "Analysis" for k in paid), under
    assert under.get("CNT/thin") == "Free checks", under


@needs_build
def test_free_only_hides_every_paid_content_card(browser, served):
    base, site_id = served
    cards = _cards(browser, f"{base}/#/sites/{site_id}?tab=findings&part=content&cost=free")
    checks = [c["check"] for c in cards]
    assert "CNT/thin" in checks, checks
    assert not [c for c in checks if c.startswith("EXP:")], checks
