"""Item 237: a brief-only finding is confirmed by the operator, not by a
second paid run (the operator's ruling on item 203, option 3).

For a check no sweep can raise, the corroboration branch of
`recompute_contract_states` can never fire, so "seen in two runs" was the
only way to open - a second purchase of the same answer from the same model
over the same evidence. The ruling: such a row stays `candidate` until the
operator confirms it (`open`), accepts it or withdraws it, through the
existing state route. It is shown by default, it is out of the report hold
and the client report until confirmed, and checks with a sweep leg keep the
rule they had.
"""

from __future__ import annotations

import json

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import now_iso
from tests.needs_build import needs_build
from tests.parts import ANATOMY_READY
from tests.test_triage_ranks_the_section_rail import _serve

BASE = "https://confirm.fixture"
HOME, ABOUT = BASE + "/", BASE + "/about/"
#: A model-only check (`title-entity-alignment`) and one with a sweep leg
#: (`meta-desc-length`), on the same part.
BRIEF_ONLY, SWEPT = "title-entity-alignment", "meta-desc-length"


def _row(check, page):
    return {"check": f"ONP/{check}", "dimension": "ONP", "check_id": check, "page": page,
            "status": "WARN", "severity": "high", "evidence": "x",
            "replacement": "A replacement of a sensible length for this page, naming it.",
            "note": ""}


def _audit_and_brief(conn, site_id, rows):
    run = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run, {"start_url": HOME, "pages": [
        {"url": HOME, "status": 200, "title": "Home"},
        {"url": ABOUT, "status": 200, "title": "About"}]})
    runs.mark_complete(conn, run, now_iso())
    conn.execute("UPDATE audit_runs SET crawled_paths=? WHERE id=?",
                 (json.dumps(["/", "/about/"]), run))
    conn.commit()
    runs.store_expert_report(conn, run, "title-desc", {
        "model": "m-1", "cost": 0.2, "report": "## Title & description", "findings": [],
        "contract": {"status": "read", "part": "title-desc", "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run, "title-desc", "m-1", rows)
    runs.recompute_contract_states(conn, site_id, "title-desc")
    return run


def _state(conn, site_id, check):
    return conn.execute(
        "SELECT s.state, s.changed_by_run FROM finding_states s JOIN findings f"
        " ON f.fingerprint = s.fingerprint WHERE s.site_id=? AND f.check_id=?"
        " AND f.source='model-judgement' LIMIT 1", (site_id, check)).fetchone()


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "confirm.fixture")
    yield conn, site
    conn.close()


def test_a_brief_only_row_seen_twice_stays_a_candidate(db):
    conn, site = db
    for _ in range(2):
        _audit_and_brief(conn, site, [_row(BRIEF_ONLY, HOME)])
    assert _state(conn, site, BRIEF_ONLY)["state"] == "candidate"


def test_a_row_with_a_sweep_leg_seen_twice_opens(db):
    """Uncorroborated (the sweep did not raise it here), so it waits one run
    - and then opens, as it always did: for these a second run is real."""
    conn, site = db
    for _ in range(2):
        _audit_and_brief(conn, site, [_row(SWEPT, ABOUT)])
    assert _state(conn, site, SWEPT)["state"] == "open"


def test_the_operators_confirmation_survives_a_third_run(db):
    conn, site = db
    _audit_and_brief(conn, site, [_row(BRIEF_ONLY, HOME)])
    fp = conn.execute("SELECT fingerprint FROM findings WHERE check_id=?",
                      (BRIEF_ONLY,)).fetchone()[0]
    assert runs.set_state(conn, site, fp, "open")
    for rows in ([_row(BRIEF_ONLY, HOME)], []):
        _audit_and_brief(conn, site, rows)
        got = _state(conn, site, BRIEF_ONLY)
        assert got["state"] == "open" and got["changed_by_run"] is None, dict(got)


def test_a_waiting_row_is_out_of_the_hold_and_the_client_report_until_confirmed(db):
    from clauditseo.reporting.generate import _contract_sections, tool_runs_for
    conn, site = db
    run = _audit_and_brief(conn, site, [_row(BRIEF_ONLY, HOME)])
    fp = conn.execute("SELECT fingerprint FROM findings WHERE check_id=?",
                      (BRIEF_ONLY,)).fetchone()[0]
    assert fp in runs.awaiting_confirmation(conn, site)
    assert not any(BRIEF_ONLY in line for line in _contract_sections(conn, tool_runs_for(conn, site)))
    runs.set_state(conn, site, fp, "open")
    assert fp not in runs.awaiting_confirmation(conn, site)
    assert any(BRIEF_ONLY in line for line in _contract_sections(conn, tool_runs_for(conn, site)))


# --- on the screen ------------------------------------------------------------

@pytest.fixture(scope="module")
def served():
    server, thread, dbpath, base = _serve("confirm")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Confirm Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "confirm.fixture"}, timeout=30).json()
        conn = connect(dbpath)
        _audit_and_brief(conn, site["id"], [_row(BRIEF_ONLY, HOME)])
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


_CARD = """() => {
  const card = [...document.querySelectorAll('.part-fixes .fix-card')]
    .find((c) => c.querySelector('[data-fix-check="title-entity-alignment"]'));
  const row = [...document.querySelectorAll('.checks-table tbody tr')]
    .find((tr) => (tr.querySelector('code')?.textContent || '').includes('title-entity-alignment'));
  return {
    card: !!card,
    pill: card ? [...card.querySelectorAll('.pill, .tone')].map((p) => p.textContent.trim()) : [],
    controls: card ? [...card.querySelectorAll('.fix-confirm button')].map((b) => b.textContent.trim()) : [],
    state: row ? (row.lastElementChild?.textContent || '').trim() : null,
  };
}"""


@needs_build
def test_the_card_asks_the_operator_and_confirm_opens_it(served):
    from playwright.sync_api import sync_playwright
    base, site_id = served
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            pg = b.new_page(viewport={"width": 1568, "height": 1080})
            pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=title-desc",
                    wait_until="load", timeout=30_000)
            pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
            pg.wait_for_selector(".part-fixes .fix-card", timeout=15_000)
            before = pg.evaluate(_CARD)
            pg.click(".fix-confirm .fix-confirm-open")
            pg.wait_for_function(
                """() => ![...document.querySelectorAll('.part-fixes .fix-card')]
                  .some((c) => c.querySelector('[data-fix-check="title-entity-alignment"]')
                               && c.querySelector('.fix-confirm'))""", timeout=15_000)
            after = pg.evaluate(_CARD)
        finally:
            b.close()
    assert before["card"], before
    assert "analysis, not yet confirmed" in before["pill"], before
    assert before["controls"] == ["Confirm", "Accept", "Withdraw"], before
    assert before["state"] == "not yet confirmed", before
    assert after["state"] == "open", after
    states = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["states"]
    row = next(s for s in states if s["check_id"] == BRIEF_ONLY)
    assert row["state"] == "open", row


@needs_build
def test_the_record_shows_a_waiting_finding_without_a_press(tmp_path):
    from playwright.sync_api import sync_playwright
    server, thread, dbpath, base = _serve("confirmrecord")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Wait Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "confirm.fixture"}, timeout=30).json()
        conn = connect(dbpath)
        _audit_and_brief(conn, site["id"], [_row(BRIEF_ONLY, HOME)])
        conn.close()
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                pg = b.new_page(viewport={"width": 1568, "height": 1080})
                pg.goto(f"{base}/#/sites/{site['id']}?tab=all", wait_until="load", timeout=30_000)
                pg.wait_for_selector("[aria-label='state filter'] [data-state]", timeout=30_000)
                # What a check costs arrives with the analyses payload, a
                # moment after the record's own rows.
                try:
                    pg.wait_for_function(
                        """() => (document.querySelector("[aria-label='state filter'] [data-state='to-confirm']")
                                  ?.textContent || '').trim().endsWith('1')""", timeout=15_000)
                except Exception:
                    pass
                got = pg.evaluate("""() => ({
                  pressed: document.querySelector("[aria-label='state filter'] [aria-pressed='true']")
                    ?.getAttribute('data-state'),
                  chips: Object.fromEntries([...document.querySelectorAll("[aria-label='state filter'] [data-state]")]
                    .map((c) => [c.getAttribute('data-state'), c.textContent.replace(/\\s+/g, ' ').trim()])),
                  text: document.querySelector('.site-main')?.textContent || '',
                })""")
            finally:
                b.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert got["pressed"] == "attention", got
    assert got["chips"]["attention"].startswith("Open + regressed + to confirm"), got["chips"]
    assert got["chips"]["attention"].endswith("1") and got["chips"]["to-confirm"].endswith("1"), got["chips"]
    assert got["chips"]["outstanding"].endswith("0"), got["chips"]
